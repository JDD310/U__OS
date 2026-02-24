import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import db
import pubsub
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("api")


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Track active WebSocket connections and their conflict subscriptions."""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[ws] = set()

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.pop(ws, None)

    def subscribe(self, ws: WebSocket, conflict_codes: list[str]) -> None:
        if ws in self._connections:
            self._connections[ws] = set(conflict_codes)

    async def broadcast(self, event: dict) -> None:
        """Send event to all connections subscribed to its conflict."""
        conflict = event.get("conflict")
        dead = []
        for ws, subs in self._connections.items():
            # Send if client subscribes to this conflict or to everything (empty set)
            if not subs or conflict in subs:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Redis → WebSocket bridge (background task)
# ---------------------------------------------------------------------------

async def _redis_bridge():
    """Subscribe to processed_events and forward to WebSocket clients."""
    while True:
        try:
            ps = await pubsub.subscribe_processed_events()
            log.info("Redis bridge: subscribed to processed_events")
            async for raw in ps.listen():
                if raw["type"] != "message":
                    continue
                try:
                    event = json.loads(raw["data"])
                    await manager.broadcast(event)
                except (json.JSONDecodeError, TypeError):
                    continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Redis bridge error: %s — reconnecting in 5s", e)
            await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge_task = asyncio.create_task(_redis_bridge())
    log.info("OSINT Monitor API starting on %s:%s", settings.host, settings.port)
    yield
    bridge_task.cancel()
    try:
        await bridge_task
    except asyncio.CancelledError:
        pass
    await pubsub.close_redis()
    await db.close_pool()
    log.info("API shutdown complete")


app = FastAPI(title="OSINT Monitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    stats = await db.get_stats()
    return {
        "status": "ok",
        "ws_clients": manager.active_count,
        **stats,
    }


@app.get("/conflicts")
async def list_conflicts(active_only: bool = True):
    """Return all conflicts for the conflict selector UI."""
    return await db.list_conflicts(active_only=active_only)


@app.get("/conflicts/{conflict_id}")
async def get_conflict(conflict_id: int):
    """Return a single conflict with its map config."""
    conflict = await db.get_conflict(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return conflict


@app.get("/conflicts/{conflict_id}/events")
async def get_events(
    conflict_id: int,
    since: datetime | None = None,
    event_type: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Return geolocated events for a specific conflict."""
    conflict = await db.get_conflict(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    events = await db.get_events(
        conflict_id=conflict_id,
        since=since,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    total = await db.count_events(
        conflict_id=conflict_id,
        since=since,
        event_type=event_type,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/messages")
async def list_messages(
    conflict_id: int | None = None,
    source_id: int | None = None,
    platform: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return messages with optional filtering."""
    return await db.get_messages(
        conflict_id=conflict_id,
        source_id=source_id,
        platform=platform,
        since=since,
        limit=limit,
        offset=offset,
    )


@app.get("/messages/{message_id}")
async def get_message(message_id: int):
    """Return a single message with full detail (including raw_json)."""
    msg = await db.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.get("/messages/unclassified")
async def list_unclassified_messages(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return messages that were processed but produced no event."""
    messages = await db.get_unclassified_messages(limit=limit, offset=offset)
    total = await db.count_unclassified_messages()
    return {"messages": messages, "total": total, "limit": limit, "offset": offset}


@app.post("/messages/{message_id}/classify")
async def classify_message(message_id: int, body: dict):
    """Manually classify a message into a conflict."""
    conflict_id = body.get("conflict_id")
    event_type = body.get("event_type", "statement")
    if conflict_id is None:
        raise HTTPException(status_code=400, detail="conflict_id is required")
    event_id = await db.manual_classify_message(message_id, conflict_id, event_type)
    if event_id is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"event_id": event_id, "message_id": message_id}


@app.get("/sources")
async def list_sources(
    platform: str | None = None,
    active_only: bool = True,
):
    """Return registered sources."""
    return await db.list_sources(platform=platform, active_only=active_only)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def live_feed(ws: WebSocket):
    """Real-time event stream.

    After connecting, the client sends a JSON message to subscribe:
        {"subscribe": ["israel-iran", "russia-ukraine"]}

    Or subscribe to all conflicts:
        {"subscribe": []}

    The server pushes processed events matching the subscription.
    """
    await manager.connect(ws)
    log.info("WebSocket client connected (%d active)", manager.active_count)
    try:
        while True:
            data = await ws.receive_json()
            if "subscribe" in data:
                codes = data["subscribe"]
                manager.subscribe(ws, codes if isinstance(codes, list) else [])
                await ws.send_json({"status": "subscribed", "conflicts": codes})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("WebSocket error: %s", e)
    finally:
        manager.disconnect(ws)
        log.info("WebSocket client disconnected (%d active)", manager.active_count)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port)
