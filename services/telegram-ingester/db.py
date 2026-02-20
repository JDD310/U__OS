import asyncio
import json
import logging
from datetime import datetime

import asyncpg

from config import settings

log = logging.getLogger(__name__)

_pool = None


async def _init_connection(conn):
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        for attempt in range(1, 11):
            try:
                _pool = await asyncpg.create_pool(
                    settings.db_url, init=_init_connection
                )
                break
            except (OSError, asyncpg.PostgresError) as e:
                if attempt == 10:
                    raise
                wait = min(attempt * 2, 30)
                log.warning(
                    "DB connection attempt %d failed: %s. Retrying in %ds.",
                    attempt, e, wait,
                )
                await asyncio.sleep(wait)
    return _pool


async def get_active_telegram_sources() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, identifier, display_name, telegram_chat_id FROM sources "
        "WHERE platform = 'telegram' AND is_active = true"
    )
    return [dict(r) for r in rows]


async def update_telegram_chat_id(source_id: int, chat_id: int) -> None:
    """Persist chat ID for a source so messages can be matched when username is unavailable."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE sources SET telegram_chat_id = $1 WHERE id = $2 AND telegram_chat_id IS NULL",
        chat_id,
        source_id,
    )


async def insert_message(
    source_id: int,
    external_id: str,
    text: str,
    raw_json: dict,
    has_media: bool,
    timestamp: datetime,
) -> int | None:
    pool = await get_pool()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO messages
                (source_id, platform, external_id, text, raw_json, has_media, timestamp)
            VALUES ($1, 'telegram', $2, $3, $4, $5, $6)
            ON CONFLICT (platform, external_id) DO NOTHING
            RETURNING id
            """,
            source_id,
            external_id,
            text,
            raw_json,
            has_media,
            timestamp,
        )
        return row["id"] if row else None
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("DB insert error: %s", e)
        return None
