"""
Telegram ingester — monitors configured channels via Telethon MTProto.

First-time setup:
    docker compose run --rm -it telegram-ingester python setup_session.py

Then run normally:
    docker compose up telegram-ingester
"""

import asyncio
import logging
import os
import sqlite3
from datetime import timezone

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from config import settings
from db import get_active_telegram_sources, insert_message, update_telegram_chat_id
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
    # Verify session file exists before starting
    session_file = settings.telegram_session_path + ".session"
    if not os.path.exists(session_file):
        log.error(
            "Session file %s not found. Run setup first: "
            "docker compose run --rm -it telegram-ingester python setup_session.py",
            session_file,
        )
        raise FileNotFoundError(f"Session file missing: {session_file}")

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

    source_map: dict[str, int] = {}
    channels: list[str | int] = []
    for s in sources:
        source_map[s["identifier"]] = s["id"]
        channels.append(s["identifier"])
        if s.get("telegram_chat_id") is not None:
            cid = s["telegram_chat_id"]
            source_map[str(cid)] = s["id"]
            if str(cid) != s["identifier"]:
                channels.append(cid)
    log.info("Monitoring %d channel(s): %s", len(sources), [s["identifier"] for s in sources])

    client = TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    await client.start()
    log.info("Telegram client connected.")

    # Resolve channel entities at startup to validate access
    resolved_channels: list[str | int] = []
    for ch in channels:
        try:
            entity = await client.get_entity(ch)
            resolved_channels.append(ch)
            log.info("Resolved channel: %s (id=%d)", getattr(entity, "title", ch), entity.id)
        except Exception as e:
            log.error("Failed to resolve channel %r — skipping: %s", ch, e)

    if not resolved_channels:
        log.error(
            "Could not resolve any channels. Ensure the session account "
            "has joined the target channels."
        )
        await client.disconnect()
        raise RuntimeError("No channels resolved")

    if len(resolved_channels) < len(channels):
        log.warning(
            "Only resolved %d/%d channels. Unresolved channels will not be monitored.",
            len(resolved_channels), len(channels),
        )

    async def handler(event) -> None:
        try:
            try:
                chat = await event.get_chat()
                channel_username = getattr(chat, "username", None) or str(chat.id)
            except Exception:
                channel_username = str(event.chat_id)

            source_id = source_map.get(channel_username)
            if source_id is None:
                log.warning(
                    "Skipping message from chat %s (no matching source). "
                    "Add a source with identifier=%r for private channels.",
                    channel_username,
                    channel_username,
                )
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
                timestamp=event.date.replace(tzinfo=None) if event.date.tzinfo else event.date,
            )

            if msg_id:
                raw_json["db_id"] = msg_id
                await publish_raw_message(raw_json)
                log.info("Ingested msg %d from @%s", msg_id, channel_username)
                await update_telegram_chat_id(source_id, event.chat_id)
        except Exception:
            log.exception("Error in message handler for chat %s", event.chat_id)

    client.add_event_handler(handler, events.NewMessage(chats=resolved_channels))

    log.info("Event handler registered for %d channel(s). Listening for messages...", len(resolved_channels))
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
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                log.warning("Session DB locked — retrying in %ds.", RECONNECT_BASE_DELAY)
                await asyncio.sleep(RECONNECT_BASE_DELAY)
                delay = RECONNECT_BASE_DELAY
            else:
                log.error("SQLite error: %s. Reconnecting in %ds.", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except FileNotFoundError:
            log.info("Waiting for session file... retrying in 60s.")
            await asyncio.sleep(60)
        except Exception as e:
            log.error("Disconnected: %s. Reconnecting in %ds.", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)


if __name__ == "__main__":
    asyncio.run(main())
