-- Geocode cache — avoids repeated Nominatim lookups for the same place names.
-- "Sidon, Lebanon" will appear hundreds of times; look it up once, store forever.

CREATE TABLE IF NOT EXISTS geocode_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(512) UNIQUE NOT NULL,   -- "place|region_bias" lowercased
    place_name VARCHAR(255) NOT NULL,
    lat FLOAT NOT NULL,
    lon FLOAT NOT NULL,
    display_name TEXT,
    confidence FLOAT DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geocode_cache_key ON geocode_cache(cache_key);
