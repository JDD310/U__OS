# U__OS

Self-hosted, real-time OSINT situation monitor. Ingests messages from Telegram channels and X (Twitter) accounts, classifies events by conflict, extracts and geocodes locations, and renders them on an interactive map.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│            React 19 + MapLibre GL JS + Nginx                 │
│     Conflict selector · Map view · Live event feed           │
├──────────────────────────────────────────────────────────────┤
│                        API LAYER                             │
│               FastAPI — REST + WebSocket                     │
│    /conflicts  /events  /messages  /sources  /ws/live        │
├──────────────────────────────────────────────────────────────┤
│                     PROCESSING LAYER                         │
│       Keyword classifier · spaCy NER · Nominatim geocoder   │
│            Dual-loop: real-time + backlog sweep              │
├──────────────────────────────────────────────────────────────┤
│                     INGESTION LAYER                          │
│         Telegram (Telethon)  ·  X (Twscrape)                │
│            Source registry · Raw message queue               │
├──────────────────────────────────────────────────────────────┤
│                       DATA LAYER                             │
│    PostgreSQL 16 (persistent store)  ·  Redis 7 (pub/sub)   │
└──────────────────────────────────────────────────────────────┘
```

### Data flow

```
Telegram channels ──→ telegram-ingester ──┐
                                          ├──→ Redis [raw_messages]
X accounts ─────────→ x-ingester ─────────┘           │
                                                       ▼
                                                   processor
                                              (classify → tag →
                                               NER → geocode)
                                                       │
                                                       ▼
                                              Redis [processed_events]
                                                       │
                                          ┌────────────┤
                                          ▼            ▼
                                      PostgreSQL    API (WebSocket)
                                          │            │
                                          ▼            ▼
                                      API (REST)    Frontend
                                          │            │
                                          └──────┬─────┘
                                                 ▼
                                            Browser UI
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Telegram ingestion | Telethon (MTProto) |
| X ingestion | Twscrape |
| Database | PostgreSQL 16 |
| Message queue | Redis 7 (pub/sub) |
| NLP / NER | spaCy (`en_core_web_sm`) |
| Geocoding | Nominatim |
| API | FastAPI + uvicorn |
| Frontend | React 19 + MapLibre GL JS |
| Build tooling | Vite |
| Reverse proxy | Nginx |
| Containerization | Docker Compose |

## Project structure

```
├── docker-compose.yml            # Service orchestration
├── sources.yml                   # Conflict + source registry
├── .env.example                  # Environment variable template
├── scripts/
│   └── seed_db.py                # Seed conflicts and sources from sources.yml
└── services/
    ├── db/
    │   └── migrations/           # PostgreSQL schema (auto-applied on first boot)
    ├── telegram-ingester/        # Telethon-based Telegram channel monitor
    ├── x-ingester/               # Twscrape-based X account poller
    ├── processor/                # Classification, NER, geocoding pipeline
    ├── api/                      # FastAPI REST + WebSocket server
    └── frontend/                 # React SPA with MapLibre map
```

## Prerequisites

- Docker and Docker Compose
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- (Optional) At least one X account for Twscrape — the X ingester runs in standby without it

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set the required values:

| Variable | Description |
|----------|-------------|
| `DB_PASSWORD` | PostgreSQL password |
| `TELEGRAM_API_ID` | From my.telegram.org → API development tools |
| `TELEGRAM_API_HASH` | From my.telegram.org → API development tools |

### 2. Configure sources

Edit `sources.yml` to define which conflicts to track and which Telegram channels / X accounts to monitor. Each source is assigned a default conflict, reliability tier, and optional content filter rules.

### 3. Start infrastructure

```bash
docker compose up postgres redis -d
```

Database migrations in `services/db/migrations/` run automatically on first start.

### 4. Seed the database

```bash
docker compose run --rm telegram-ingester python /scripts/seed_db.py
```

This loads conflicts and sources from `sources.yml` into PostgreSQL.

### 5. Authenticate Telegram (one-time)

```bash
docker compose run --rm -it telegram-ingester python setup_session.py
```

Enter your phone number and verification code when prompted. The session file persists in a Docker volume — this only needs to be done once.

### 6. Authenticate X (one-time, optional)

```bash
docker compose run --rm -it x-ingester python -m twscrape add_accounts
docker compose run --rm -it x-ingester python -m twscrape login_accounts
```

### 7. Start all services

```bash
docker compose up -d
```

The frontend is available at `http://localhost:3000`. The API is available at `http://localhost:8080`.

### Verify

```bash
# Check service logs
docker compose logs -f telegram-ingester
docker compose logs -f x-ingester
docker compose logs -f processor

# Query the database
docker compose exec postgres psql -U osint -d osint_monitor \
  -c "SELECT count(*) FROM messages;"

# Hit the health endpoint
curl http://localhost:8080/health
```

## Frontend

The frontend is a React SPA served by Nginx, which also reverse-proxies `/api/` and `/ws/` to the FastAPI backend.

**Map** — MapLibre GL JS renders events as colored circles on a CartoDB Dark Matter basemap. Circle color maps to event type, opacity scales with geocoding confidence. Clicking a dot fetches the source message and displays it in a popup. Country boundaries are shaded by conflict color scheme (allies / adversaries / involved).

**Conflict selector** — Sidebar lists all conflicts. Selecting one flies the map to that conflict's region, loads its events, and filters the live feed.

**Live feed** — Real-time event stream via WebSocket. Clicking a feed item pans the map to its location; clicking a map dot scrolls the feed to the corresponding item.

## API reference

### REST endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with message/event counts |
| `GET` | `/conflicts` | List conflicts (query: `active_only`) |
| `GET` | `/conflicts/{id}` | Single conflict with map configuration |
| `GET` | `/conflicts/{id}/events` | Events for a conflict (query: `since`, `event_type`, `limit`, `offset`) |
| `GET` | `/messages` | List messages (query: `conflict_id`, `source_id`, `platform`, `since`, `limit`, `offset`) |
| `GET` | `/messages/{id}` | Single message with full detail |
| `GET` | `/sources` | Registered sources (query: `platform`, `active_only`) |

### WebSocket

Connect to `ws://localhost:8080/ws/live` and send a subscription message:

```json
{ "subscribe": ["israel-iran", "russia-ukraine"] }
```

Use an empty array to subscribe to all conflicts. The server confirms with `{"status": "subscribed", "conflicts": [...]}` and then pushes events as they arrive:

```json
{
  "event_id": 42,
  "message_id": 187,
  "conflict": "israel-iran",
  "event_type": "airstrike",
  "lat": 33.85,
  "lon": 35.86,
  "location": "Sidon, Lebanon",
  "text": "IAF drone-struck a target in Sidon...",
  "timestamp": "2026-02-20T14:32:00Z"
}
```

## Processing pipeline

Each ingested message passes through three stages:

1. **Classification** — Keyword-based scoring against category dictionaries (geopolitical, domestic politics, satire). Messages above the confidence threshold are tagged with an event type. Telegram sources bypass the relevance filter when classifier confidence is low.

2. **Conflict tagging** — Assigns the source's `default_conflict` from the registry as the primary conflict. Keyword matching against conflict-specific term lists supplements this to catch messages that span multiple conflicts (e.g. an X analyst commenting on both Israel-Iran and Russia-Ukraine).

3. **NER + Geocoding** — spaCy extracts location entities (GPE, LOC, FAC). Each entity is geocoded via Nominatim with region bias from the matched conflict. Results are cached in three layers: in-memory, PostgreSQL `geocode_cache` table, and the Nominatim API (rate-limited to 1 req/sec).

The processor runs two concurrent loops:
- **Real-time**: subscribes to Redis `raw_messages` and processes immediately
- **Backlog sweep**: polls PostgreSQL every 30 seconds for any unprocessed messages missed by the real-time path

### Event types

The classifier infers an event type from matched keywords:

| Type | Triggers |
|------|----------|
| `airstrike` | airstrike, drone strike, bombing, JDAM |
| `missile_strike` | missile strike, cruise missile, ballistic missile, rocket attack |
| `shelling` | shelling, artillery, mortar |
| `interception` | intercepted, air defense, SAM, S-300, S-400 |
| `casualty_report` | casualties, KIA, WIA, killed, wounded |
| `movement` | deployment, convoy, troops, armor, advancing |
| `diplomatic` | ceasefire, truce, peace talks, negotiation |
| `arms_transfer` | arms shipment, weapons transfer, military aid |
| `statement` | statement, announcement, declaration |

## Configuration reference

### Environment variables

Set in `.env` and passed through `docker-compose.yml`:

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `DB_PASSWORD` | all | — | PostgreSQL password (required) |
| `TELEGRAM_API_ID` | telegram-ingester | — | Telegram API ID (required) |
| `TELEGRAM_API_HASH` | telegram-ingester | — | Telegram API hash (required) |
| `TELEGRAM_SESSION_PATH` | telegram-ingester | `/app/sessions/osint_monitor` | Path to Telethon session file |
| `X_POLL_INTERVAL` | x-ingester | `300` | Polling interval in seconds |
| `X_ACCOUNTS_DB_PATH` | x-ingester | `/app/accounts/accounts.db` | Twscrape accounts database path |
| `NOMINATIM_URL` | processor | `https://nominatim.openstreetmap.org` | Nominatim geocoding endpoint |
| `CLASSIFICATION_THRESHOLD` | processor | `0.8` | Minimum confidence to accept classification |
| `BATCH_SIZE` | processor | `50` | Backlog sweep batch size |
| `BACKLOG_POLL_INTERVAL` | processor | `30` | Seconds between backlog sweeps |

### Source registry

`sources.yml` defines conflicts and sources. To add a new source:

1. Add an entry under `sources.telegram` or `sources.x` in `sources.yml`
2. Re-run the seed script: `docker compose run --rm telegram-ingester python /scripts/seed_db.py`
3. Restart the relevant ingester: `docker compose restart telegram-ingester`

Sources can also be inserted directly into the `sources` table in PostgreSQL.

## Database schema

Managed via migration files in `services/db/migrations/`:

| Table | Purpose |
|-------|---------|
| `conflicts` | Conflict definitions with map center, zoom, and color scheme |
| `sources` | Monitored channels/accounts with platform, reliability tier, and filter rules |
| `messages` | Raw ingested content with text, metadata, and processing status |
| `events` | Geocoded events linked to messages and conflicts |
| `geocode_cache` | Nominatim lookup cache to avoid redundant API calls |

## License

[AGPL-3.0](LICENSE)
