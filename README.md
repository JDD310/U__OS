# U__OS — Real-Time OSINT Situation Monitor

Self-hosted platform that ingests Telegram channels and X accounts, classifies events, geocodes locations, and renders them on an interactive conflict map.

## Architecture

```
Telegram (Telethon) ──┐
                      ├─→ PostgreSQL ──→ FastAPI ──→ React + MapLibre
X (Twscrape/API) ─────┘       ↑
                          Processing:
                          spaCy NER → Nominatim geocoding
                          Keyword classifier (+ optional Ollama)
```

**Stack:** Telethon · Twscrape · PostgreSQL 16 · Redis · spaCy · Nominatim · FastAPI · MapLibre GL JS · React · Docker

## Status

- [x] Phase 1: Data ingestion (Telegram + X ingesters, source registry, DB schema)
- [ ] Phase 2: Processing pipeline (classify + NER + geocode)
- [ ] Phase 3: FastAPI REST + WebSocket layer
- [ ] Phase 4: React + MapLibre frontend
- [ ] Phase 5: Full integration

---

## Phase 1 Setup

### Prerequisites

- Docker + Docker Compose
- Telegram API credentials (get from [my.telegram.org](https://my.telegram.org))
- At least one X account for Twscrape (optional — X ingester runs in standby without it)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set DB_PASSWORD, TELEGRAM_API_ID, TELEGRAM_API_HASH
```

### 2. Configure sources

Edit `sources.yml` — add Telegram channel usernames and X handles to monitor.

### 3. Start the database

```bash
docker compose up postgres redis -d
```

The migration in `services/db/migrations/001_initial_schema.sql` runs automatically on first start.

### 4. Seed conflicts and sources

```bash
docker compose run --rm telegram-ingester python /scripts/seed_db.py
```

### 5. Telegram session setup (one-time, interactive)

```bash
docker compose run --rm -it telegram-ingester python setup_session.py
```

You'll be prompted for your phone number and Telegram verification code. The session file is saved to a persistent Docker volume — you only need to do this once.

### 6. X account setup (one-time, interactive)

```bash
docker compose run --rm -it x-ingester python -m twscrape add_accounts
docker compose run --rm -it x-ingester python -m twscrape login_accounts
```

### 7. Start ingesters

```bash
docker compose up -d
```

Verify messages are flowing:

```bash
docker compose logs -f telegram-ingester
docker compose logs -f x-ingester

# Check DB directly
docker compose exec postgres psql -U osint -d osint_monitor -c "SELECT count(*) FROM messages;"
```

---

## Source Registry

Sources and conflicts are managed via `sources.yml` + the seed script. To add a new channel:

1. Add it to `sources.yml` under `sources.telegram` or `sources.x`
2. Run `docker compose run --rm telegram-ingester python /scripts/seed_db.py`
3. Restart the relevant ingester

You can also insert directly into the `sources` table in PostgreSQL.

---

## Homelab Placement

| Service | Host |
|---------|------|
| PostgreSQL + Redis | REDACTED-NAS |
| Ingesters + Processor | REDACTED-HOST-1 |
| API + Frontend | REDACTED-HOST-0 |

Accessible via network from any device on the mesh.
