#!/usr/bin/env python3
"""
Seed the database with conflicts and sources from sources.yml.
Idempotent — safe to run multiple times.

Usage:
    docker compose run --rm telegram-ingester python /scripts/seed_db.py
"""

import asyncio
import json
import os
import sys

import asyncpg
import yaml


async def init_connection(conn):
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def seed(sources_path: str = "/app/sources.yml"):
    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("ERROR: DB_URL environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(sources_path):
        print(f"ERROR: sources file not found: {sources_path}", file=sys.stderr)
        sys.exit(1)

    with open(sources_path) as f:
        config = yaml.safe_load(f)

    pool = await asyncpg.create_pool(db_url, init=init_connection)

    # ── Conflicts ──────────────────────────────────────────────────────────────
    conflicts_config = config.get("conflicts") or []
    conflict_id_map = {}  # short_code → id

    for conflict in conflicts_config:
        row = await pool.fetchrow(
            """
            INSERT INTO conflicts (name, short_code, involved_countries,
                map_center_lat, map_center_lon, map_zoom_level, color_scheme)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (short_code) DO UPDATE
                SET name = EXCLUDED.name,
                    involved_countries = EXCLUDED.involved_countries,
                    map_center_lat = EXCLUDED.map_center_lat,
                    map_center_lon = EXCLUDED.map_center_lon,
                    map_zoom_level = EXCLUDED.map_zoom_level,
                    color_scheme = EXCLUDED.color_scheme
            RETURNING id, short_code
            """,
            conflict["name"],
            conflict["short_code"],
            conflict.get("involved_countries", []),
            conflict.get("map_center_lat"),
            conflict.get("map_center_lon"),
            conflict.get("map_zoom_level", 5),
            conflict.get("color_scheme", {}),
        )
        conflict_id_map[row["short_code"]] = row["id"]
        print(f"  conflict: {row['short_code']} (id={row['id']})")

    print(f"Upserted {len(conflicts_config)} conflicts.")

    # ── Sources ────────────────────────────────────────────────────────────────
    sources_config = config.get("sources") or {}
    total = 0

    for platform, entries in sources_config.items():
        if not entries:
            continue
        for source in entries:
            default_conflict_short = source.get("default_conflict")
            default_conflict_id = (
                conflict_id_map.get(default_conflict_short)
                if default_conflict_short
                else None
            )

            row = await pool.fetchrow(
                """
                INSERT INTO sources (platform, identifier, display_name,
                    default_conflict_id, reliability_tier)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (platform, identifier) DO UPDATE
                    SET display_name = EXCLUDED.display_name,
                        default_conflict_id = EXCLUDED.default_conflict_id,
                        reliability_tier = EXCLUDED.reliability_tier
                RETURNING id, identifier
                """,
                platform,
                source["identifier"],
                source.get("display_name"),
                default_conflict_id,
                source.get("reliability_tier"),
            )
            print(f"  source [{platform}]: {row['identifier']} (id={row['id']})")
            total += 1

    print(f"Upserted {total} sources.")
    await pool.close()


if __name__ == "__main__":
    sources_path = sys.argv[1] if len(sys.argv) > 1 else "/app/sources.yml"
    asyncio.run(seed(sources_path))
