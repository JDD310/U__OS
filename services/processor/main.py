"""
Processing pipeline — classifies, geocodes, and conflict-tags raw messages.

Runs two concurrent loops:
  1. Real-time: subscribes to Redis ``raw_messages`` channel for instant
     processing of newly ingested messages.
  2. Backlog sweep: periodically polls the DB for any messages whose
     ``processed`` flag is still false (covers startup catch-up and any
     messages missed by the real-time path).
"""

import asyncio
import json
import logging

from config import settings
from classifier import classify, ClassificationResult
from geocoder import extract_locations, geocode_locations
from tagger import tag_conflicts, get_region_bias
from db import (
    get_unprocessed_messages,
    get_conflict_map,
    insert_event,
    mark_processed,
    geocode_cache_get,
    geocode_cache_put,
)
from pubsub import subscribe_raw_messages, publish_processed_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [processor] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core processing logic (shared by both loops)
# ---------------------------------------------------------------------------

async def process_message(msg: dict, conflict_map: dict[str, int]) -> None:
    """Run the full pipeline on a single message row."""
    msg_id = msg["id"]
    text = msg.get("text", "")
    source_filter_rules = msg.get("content_filter_rules") or {}
    default_conflict_id = msg.get("default_conflict_id")
    platform = msg.get("platform", "")
    timestamp = msg.get("timestamp")

    # ---- Step 1: Classify ------------------------------------------------
    result: ClassificationResult = classify(text, source_filter_rules)

    # Telegram OSINT channels are high-signal by default — only filter
    # if the classifier is very confident it's irrelevant.
    if platform == "telegram" and not result.is_relevant and result.confidence < settings.classification_threshold:
        result.is_relevant = True
        result.category = "geopolitical"

    if not result.is_relevant and result.confidence >= settings.classification_threshold:
        log.debug(
            "Filtered msg %d (%s, conf=%.2f)", msg_id, result.category, result.confidence
        )
        await mark_processed(msg_id)
        return

    # ---- Step 2: Conflict tagging ----------------------------------------
    conflicts = tag_conflicts(text, default_conflict_id, conflict_map)

    if not conflicts:
        # Can't place this message in any conflict bucket — mark processed,
        # skip event creation (no orphan events).
        log.debug("No conflict match for msg %d — skipping.", msg_id)
        await mark_processed(msg_id)
        return

    # ---- Step 3: NER + Geocoding -----------------------------------------
    locations = extract_locations(text)

    # Use the top conflict's region to bias geocoding
    region_bias = get_region_bias(conflicts[0].short_code)

    geo_results = await geocode_locations(
        locations,
        region_bias,
        db_cache_get=geocode_cache_get,
        db_cache_put=geocode_cache_put,
    )

    # ---- Step 4: Create events -------------------------------------------
    event_type = result.event_type

    if geo_results:
        for geo in geo_results:
            for conflict in conflicts:
                event_id = await insert_event(
                    message_id=msg_id,
                    conflict_id=conflict.conflict_id,
                    event_type=event_type,
                    latitude=geo.lat,
                    longitude=geo.lon,
                    location_name=geo.name,
                    confidence=geo.confidence,
                    timestamp=timestamp,
                )
                if event_id:
                    payload = {
                        "event_id": event_id,
                        "message_id": msg_id,
                        "conflict": conflict.short_code,
                        "event_type": event_type,
                        "lat": geo.lat,
                        "lon": geo.lon,
                        "location": geo.name,
                        "text": text[:500],
                        "timestamp": timestamp,
                    }
                    await publish_processed_event(payload)
                    log.info(
                        "Event %d: msg %d → %s @ %s (%.4f, %.4f)",
                        event_id, msg_id, conflict.short_code,
                        geo.name, geo.lat, geo.lon,
                    )
    else:
        # No geocodable locations — still create a locationless event
        # so the message appears in the conflict feed.
        for conflict in conflicts:
            event_id = await insert_event(
                message_id=msg_id,
                conflict_id=conflict.conflict_id,
                event_type=event_type,
                latitude=0.0,
                longitude=0.0,
                location_name="",
                confidence=0.0,
                timestamp=timestamp,
            )
            if event_id:
                payload = {
                    "event_id": event_id,
                    "message_id": msg_id,
                    "conflict": conflict.short_code,
                    "event_type": event_type,
                    "lat": None,
                    "lon": None,
                    "location": None,
                    "text": text[:500],
                    "timestamp": timestamp,
                }
                await publish_processed_event(payload)
                log.info(
                    "Event %d: msg %d → %s (no location)",
                    event_id, msg_id, conflict.short_code,
                )

    await mark_processed(msg_id)


# ---------------------------------------------------------------------------
# Loop 1: Real-time subscriber
# ---------------------------------------------------------------------------

async def realtime_loop(conflict_map: dict[str, int]) -> None:
    """Subscribe to Redis raw_messages and process each one immediately."""
    pubsub = await subscribe_raw_messages()
    log.info("Subscribed to raw_messages channel.")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            db_id = data.get("db_id")
            if db_id is None:
                continue

            # Build a minimal msg dict matching get_unprocessed_messages format
            from db import get_pool
            pool = await get_pool()
            row = await pool.fetchrow(
                """
                SELECT m.id, m.source_id, m.platform, m.text, m.raw_json, m.timestamp,
                       s.default_conflict_id, s.content_filter_rules, s.reliability_tier,
                       s.identifier AS source_identifier
                FROM messages m
                JOIN sources s ON s.id = m.source_id
                WHERE m.id = $1 AND m.processed = false
                """,
                db_id,
            )
            if row is None:
                continue

            await process_message(dict(row), conflict_map)
        except Exception:
            log.exception("Error processing real-time message")


# ---------------------------------------------------------------------------
# Loop 2: Backlog sweep
# ---------------------------------------------------------------------------

async def backlog_loop(conflict_map: dict[str, int]) -> None:
    """Periodically poll DB for unprocessed messages and process them."""
    while True:
        try:
            messages = await get_unprocessed_messages(limit=settings.batch_size)
            if messages:
                log.info("Backlog sweep: processing %d message(s).", len(messages))
                for msg in messages:
                    try:
                        await process_message(msg, conflict_map)
                    except Exception:
                        log.exception("Error processing backlog msg %d", msg["id"])
        except Exception:
            log.exception("Backlog sweep error")

        await asyncio.sleep(settings.backlog_poll_interval)


# ---------------------------------------------------------------------------
# Conflict map refresh
# ---------------------------------------------------------------------------

async def refresh_conflict_map(conflict_map: dict[str, int]) -> None:
    """Periodically refresh the conflict map from DB."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        try:
            updated = await get_conflict_map()
            conflict_map.clear()
            conflict_map.update(updated)
            log.info("Conflict map refreshed: %s", list(conflict_map.keys()))
        except Exception:
            log.exception("Failed to refresh conflict map")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    log.info("Processor starting up...")

    # Pre-load spaCy model at startup
    from geocoder import extract_locations
    extract_locations("warm up the model")

    conflict_map = await get_conflict_map()
    if not conflict_map:
        log.warning("No conflicts in database. Waiting for seed data...")
        while not conflict_map:
            await asyncio.sleep(10)
            conflict_map = await get_conflict_map()

    log.info("Loaded %d conflict(s): %s", len(conflict_map), list(conflict_map.keys()))

    await asyncio.gather(
        realtime_loop(conflict_map),
        backlog_loop(conflict_map),
        refresh_conflict_map(conflict_map),
    )


if __name__ == "__main__":
    asyncio.run(main())
