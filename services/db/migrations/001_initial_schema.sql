-- OSINT Monitor — Initial Schema
-- Phase 1: Source registry, messages, conflicts, events

-- Conflicts: the "buckets" that organize events and sources
CREATE TABLE IF NOT EXISTS conflicts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    short_code VARCHAR(50) UNIQUE NOT NULL,
    involved_countries TEXT[] DEFAULT '{}',
    map_center_lat FLOAT,
    map_center_lon FLOAT,
    map_zoom_level INTEGER DEFAULT 5,
    color_scheme JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sources: registry of all monitored channels and accounts
CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20) NOT NULL,           -- 'telegram', 'x', 'rss', etc.
    identifier VARCHAR(255) NOT NULL,         -- channel username or account handle
    display_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    default_conflict_id INTEGER REFERENCES conflicts(id),
    reliability_tier VARCHAR(10) CHECK (reliability_tier IN ('high', 'medium', 'low')),
    content_filter_rules JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, identifier)
);

-- Messages: raw ingested content from all sources
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    platform VARCHAR(20) NOT NULL,
    external_id VARCHAR(255),                -- tweet ID or Telegram message ID (platform-scoped)
    text TEXT NOT NULL,
    raw_json JSONB DEFAULT '{}',             -- full raw payload from source
    has_media BOOLEAN DEFAULT false,
    timestamp TIMESTAMP NOT NULL,            -- original message timestamp
    ingested_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT false,         -- picked up by Phase 2 processor
    UNIQUE(platform, external_id)
);

-- Events: geolocated events extracted from messages (populated by Phase 2)
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id),
    conflict_id INTEGER REFERENCES conflicts(id),
    event_type VARCHAR(50),                  -- 'airstrike', 'movement', 'statement', etc.
    latitude FLOAT,
    longitude FLOAT,
    location_name VARCHAR(255),
    confidence FLOAT,                        -- geocoding confidence [0, 1]
    timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_messages_platform ON messages(platform);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_unprocessed ON messages(processed) WHERE processed = false;
CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source_id);
CREATE INDEX IF NOT EXISTS idx_events_conflict ON events(conflict_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sources_platform_active ON sources(platform, is_active);
