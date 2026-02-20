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
        _pool = await asyncpg.create_pool(settings.db_url, init=_init_connection)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------

async def list_conflicts(active_only: bool = True) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT id, name, short_code, involved_countries,
               map_center_lat, map_center_lon, map_zoom_level,
               color_scheme, is_active, created_at
        FROM conflicts
    """
    if active_only:
        query += " WHERE is_active = true"
    query += " ORDER BY name"
    rows = await pool.fetch(query)
    return [dict(r) for r in rows]


async def get_conflict(conflict_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, name, short_code, involved_countries,
               map_center_lat, map_center_lon, map_zoom_level,
               color_scheme, is_active, created_at
        FROM conflicts
        WHERE id = $1
        """,
        conflict_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

async def get_events(
    conflict_id: int,
    since: datetime | None = None,
    event_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT e.id, e.message_id, e.conflict_id, e.event_type,
               e.latitude, e.longitude, e.location_name,
               e.confidence, e.timestamp, e.created_at
        FROM events e
        WHERE e.conflict_id = $1
    """
    params: list = [conflict_id]
    idx = 2

    if since is not None:
        query += f" AND e.timestamp >= ${idx}"
        params.append(since)
        idx += 1

    if event_type is not None:
        query += f" AND e.event_type = ${idx}"
        params.append(event_type)
        idx += 1

    query += f" ORDER BY e.timestamp DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def count_events(
    conflict_id: int,
    since: datetime | None = None,
    event_type: str | None = None,
) -> int:
    pool = await get_pool()
    query = "SELECT count(*) FROM events WHERE conflict_id = $1"
    params: list = [conflict_id]
    idx = 2

    if since is not None:
        query += f" AND timestamp >= ${idx}"
        params.append(since)
        idx += 1

    if event_type is not None:
        query += f" AND event_type = ${idx}"
        params.append(event_type)
        idx += 1

    return await pool.fetchval(query, *params)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def get_messages(
    conflict_id: int | None = None,
    source_id: int | None = None,
    platform: str | None = None,
    since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT m.id, m.source_id, m.platform, m.external_id,
               m.text, m.has_media, m.timestamp, m.ingested_at, m.processed,
               s.identifier AS source_identifier,
               s.display_name AS source_display_name,
               s.reliability_tier
        FROM messages m
        JOIN sources s ON s.id = m.source_id
    """
    conditions = []
    params: list = []
    idx = 1

    if conflict_id is not None:
        conditions.append(
            f"m.id IN (SELECT message_id FROM events WHERE conflict_id = ${idx})"
        )
        params.append(conflict_id)
        idx += 1

    if source_id is not None:
        conditions.append(f"m.source_id = ${idx}")
        params.append(source_id)
        idx += 1

    if platform is not None:
        conditions.append(f"m.platform = ${idx}")
        params.append(platform)
        idx += 1

    if since is not None:
        conditions.append(f"m.timestamp >= ${idx}")
        params.append(since)
        idx += 1

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY m.timestamp DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


async def get_message(message_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT m.id, m.source_id, m.platform, m.external_id,
               m.text, m.raw_json, m.has_media, m.timestamp,
               m.ingested_at, m.processed,
               s.identifier AS source_identifier,
               s.display_name AS source_display_name,
               s.reliability_tier
        FROM messages m
        JOIN sources s ON s.id = m.source_id
        WHERE m.id = $1
        """,
        message_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

async def list_sources(
    platform: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT id, platform, identifier, display_name, is_active,
               default_conflict_id, reliability_tier, created_at
        FROM sources
    """
    conditions = []
    params: list = []
    idx = 1

    if active_only:
        conditions.append("is_active = true")

    if platform is not None:
        conditions.append(f"platform = ${idx}")
        params.append(platform)
        idx += 1

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY platform, identifier"
    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats (for dashboard / health)
# ---------------------------------------------------------------------------

async def get_stats() -> dict:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
            (SELECT count(*) FROM messages) AS total_messages,
            (SELECT count(*) FROM events) AS total_events,
            (SELECT count(*) FROM sources WHERE is_active = true) AS active_sources,
            (SELECT count(*) FROM conflicts WHERE is_active = true) AS active_conflicts,
            (SELECT max(ingested_at) FROM messages) AS last_ingested_at
        """
    )
    return dict(rows[0])
