"""
Telegram ingester — monitors configured channels via Telethon MTProto.

First-time setup:
    docker compose run --rm -it telegram-ingester python setup_session.py

Then run normally:
    docker compose up telegram-ingester
"""

import asyncio
import logging
from datetime import timezone

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from config import settings
from db import get_active_telegram_sources, insert_message
from pubsub import publish_raw_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [telegram] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

RECONNECT_BASE_DELAY = 5
RECONNECT_MAX_DELAY = 300
STANDBY_POLL_INTERVAL = 60


async def run_ingester() -> None:
    sources = await get_active_telegram_sources()

    if not sources:
        log.warning("No active Telegram sources in database. Add entries to sources table.")
        log.info("Entering standby — rechecking every %ds.", STANDBY_POLL_INTERVAL)
        while True:
            await asyncio.sleep(STANDBY_POLL_INTERVAL)
            sources = await get_active_telegram_sources()
            if sources:
                log.info("Sources found, starting ingester.")
                break

    source_map: dict[str, int] = {s["identifier"]: s["id"] for s in sources}
    channels = list(source_map.keys())
    log.info("Monitoring %d channel(s): %s", len(channels), channels)

    client = TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    async def handler(event) -> None:
        try:
            chat = await event.get_chat()
            channel_username = getattr(chat, "username", None) or str(chat.id)
        except Exception:
            channel_username = str(event.chat_id)

        source_id = source_map.get(channel_username)
        if source_id is None:
            return

        text = event.raw_text or ""
        raw_json = {
            "source": "telegram",
            "channel": channel_username,
            "text": text,
            "timestamp": event.date.isoformat(),
            "media": bool(event.media),
            "message_id": event.id,
            "views": getattr(event.message, "views", None),
            "forwards": getattr(event.message, "forwards", None),
        }

        msg_id = await insert_message(
            source_id=source_id,
            external_id=f"{channel_username}_{event.id}",
            text=text,
            raw_json=raw_json,
            has_media=bool(event.media),
            timestamp=event.date.replace(tzinfo=timezone.utc),
        )

        if msg_id:
            raw_json["db_id"] = msg_id
            await publish_raw_message(raw_json)
            log.info("Ingested msg %d from @%s", msg_id, channel_username)

    client.add_event_handler(handler, events.NewMessage(chats=channels))

    await client.start()
    log.info("Telegram client connected.")
    await client.run_until_disconnected()


async def main() -> None:
    delay = RECONNECT_BASE_DELAY
    while True:
        try:
            await run_ingester()
        except FloodWaitError as e:
            wait = e.seconds + 5
            log.warning("FloodWaitError — sleeping %ds.", wait)
            await asyncio.sleep(wait)
            delay = RECONNECT_BASE_DELAY
        except Exception as e:
            log.error("Disconnected: %s. Reconnecting in %ds.", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)


if __name__ == "__main__":
    asyncio.run(main())
