"""
Geolocation extraction — spaCy NER + Nominatim geocoding with caching.

Extracts place names from message text, then resolves them to lat/lon
coordinates.  Results are cached in-memory and in PostgreSQL to minimise
Nominatim requests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
import spacy

from config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# spaCy NER
# ---------------------------------------------------------------------------

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        log.info("Loading spaCy model '%s' ...", settings.spacy_model)
        _nlp = spacy.load(settings.spacy_model)
        log.info("spaCy model loaded.")
    return _nlp


def extract_locations(text: str) -> list[str]:
    """Return deduplicated location entity strings from *text*."""
    doc = _get_nlp()(text)
    seen: set[str] = set()
    locations: list[str] = []
    for ent in doc.ents:
        if ent.label_ in ("GPE", "LOC", "FAC") and ent.text not in seen:
            seen.add(ent.text)
            locations.append(ent.text)
    return locations


# ---------------------------------------------------------------------------
# Geocoding result
# ---------------------------------------------------------------------------

@dataclass
class GeoResult:
    name: str
    lat: float
    lon: float
    display_name: str
    confidence: float  # 0.0 – 1.0 based on Nominatim importance


# ---------------------------------------------------------------------------
# In-memory cache (lives for the process lifetime)
# ---------------------------------------------------------------------------

_mem_cache: dict[str, GeoResult | None] = {}

# ---------------------------------------------------------------------------
# Rate limiter — Nominatim allows 1 req/sec on public instance
# ---------------------------------------------------------------------------

_last_request_time: float = 0.0
_rate_lock = asyncio.Lock()


async def _rate_limit():
    global _last_request_time
    async with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        wait = (1.0 / settings.nominatim_rate_limit) - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Nominatim lookup
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.nominatim_url,
            headers={"User-Agent": "osint-monitor/1.0"},
            timeout=10.0,
        )
    return _http_client


async def _nominatim_lookup(place: str, region_bias: str | None = None) -> GeoResult | None:
    query = f"{place}, {region_bias}" if region_bias else place
    await _rate_limit()
    try:
        resp = await _get_http_client().get(
            "/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        top = results[0]
        importance = float(top.get("importance", 0.5))
        return GeoResult(
            name=place,
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            display_name=top.get("display_name", query),
            confidence=min(importance, 1.0),
        )
    except Exception as e:
        log.warning("Nominatim lookup failed for '%s': %s", query, e)
        return None


# ---------------------------------------------------------------------------
# Public API — geocode with multi-layer cache
# ---------------------------------------------------------------------------

async def geocode(
    place: str,
    region_bias: str | None = None,
    *,
    db_cache_get=None,
    db_cache_put=None,
) -> GeoResult | None:
    """Resolve *place* to coordinates.

    Cache layers:
      1. In-memory dict (instant)
      2. PostgreSQL geocode_cache table (via *db_cache_get*)
      3. Nominatim API (rate-limited)

    *db_cache_get(cache_key)* and *db_cache_put(cache_key, result)* are
    async callables injected from db.py so this module stays DB-agnostic.
    """
    cache_key = f"{place}|{region_bias or ''}".lower().strip()

    # Layer 1: in-memory
    if cache_key in _mem_cache:
        return _mem_cache[cache_key]

    # Layer 2: DB cache
    if db_cache_get:
        cached = await db_cache_get(cache_key)
        if cached is not None:
            _mem_cache[cache_key] = cached
            return cached

    # Layer 3: Nominatim
    result = await _nominatim_lookup(place, region_bias)
    _mem_cache[cache_key] = result

    if db_cache_put and result is not None:
        await db_cache_put(cache_key, result)

    return result


async def geocode_locations(
    locations: list[str],
    region_bias: str | None = None,
    *,
    db_cache_get=None,
    db_cache_put=None,
) -> list[GeoResult]:
    """Geocode a list of place names, returning only successful results."""
    results: list[GeoResult] = []
    for place in locations:
        geo = await geocode(
            place,
            region_bias,
            db_cache_get=db_cache_get,
            db_cache_put=db_cache_put,
        )
        if geo is not None:
            results.append(geo)
    return results
