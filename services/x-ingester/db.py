import json
from datetime import datetime

import asyncpg

from config import settings

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
        _pool = await asyncpg.create_pool(settings.db_url, init=_init_connection)
    return _pool


async def get_active_x_sources() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, identifier, display_name FROM sources "
        "WHERE platform = 'x' AND is_active = true"
    )
    return [dict(r) for r in rows]


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
            VALUES ($1, 'x', $2, $3, $4, $5, $6)
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
