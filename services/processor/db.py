import asyncio
import json
import logging
from datetime import datetime

import asyncpg

from config import settings
from geocoder import GeoResult

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


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

async def get_unprocessed_messages(limit: int = 50) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT m.id, m.source_id, m.platform, m.text, m.raw_json, m.timestamp,
               s.default_conflict_id, s.content_filter_rules, s.reliability_tier,
               s.identifier AS source_identifier
        FROM messages m
        JOIN sources s ON s.id = m.source_id
        WHERE m.processed = false
        ORDER BY m.timestamp ASC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_conflict_map() -> dict[str, int]:
    """Return {short_code: id} for all active conflicts."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, short_code FROM conflicts WHERE is_active = true"
    )
    return {r["short_code"]: r["id"] for r in rows}


async def get_source_by_id(source_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, identifier, default_conflict_id, content_filter_rules "
        "FROM sources WHERE id = $1",
        source_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

async def insert_event(
    message_id: int,
    conflict_id: int,
    event_type: str | None,
    latitude: float,
    longitude: float,
    location_name: str,
    confidence: float,
    timestamp: datetime,
) -> int | None:
    pool = await get_pool()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO events
                (message_id, conflict_id, event_type,
                 latitude, longitude, location_name,
                 confidence, timestamp)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            message_id,
            conflict_id,
            event_type,
            latitude,
            longitude,
            location_name,
            confidence,
            timestamp,
        )
        return row["id"] if row else None
    except Exception as e:
        log.error("Event insert error: %s", e)
        return None


async def mark_processed(message_id: int) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE messages SET processed = true WHERE id = $1",
        message_id,
    )


# ---------------------------------------------------------------------------
# Geocode cache (backed by geocode_cache table)
# ---------------------------------------------------------------------------

async def geocode_cache_get(cache_key: str) -> GeoResult | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT place_name, lat, lon, display_name, confidence "
        "FROM geocode_cache WHERE cache_key = $1",
        cache_key,
    )
    if row is None:
        return None
    return GeoResult(
        name=row["place_name"],
        lat=row["lat"],
        lon=row["lon"],
        display_name=row["display_name"],
        confidence=row["confidence"],
    )


async def geocode_cache_put(cache_key: str, result: GeoResult) -> None:
    pool = await get_pool()
    try:
        await pool.execute(
            """
            INSERT INTO geocode_cache (cache_key, place_name, lat, lon, display_name, confidence)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (cache_key) DO NOTHING
            """,
            cache_key,
            result.name,
            result.lat,
            result.lon,
            result.display_name,
            result.confidence,
        )
    except Exception as e:
        log.warning("Geocode cache write failed: %s", e)
