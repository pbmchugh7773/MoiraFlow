"""Live execution feed: Redis subscriber -> persist + fan-out to WebSockets.

The worker publishes lifecycle events to Redis (EVENTS_CHANNEL). This subscriber
persists each event (`handle_event`, advancing execution status) and broadcasts it
to any WebSocket clients watching that execution. Temporal does not push to external
subscribers — Redis is the bridge (docs 05 §5).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from .services.events import handle_event

# Must match moiraflow_worker.events.EVENTS_CHANNEL (shared pub/sub protocol).
EVENTS_CHANNEL = "moiraflow:events"


class WebSocketLike(Protocol):
    async def accept(self) -> None: ...
    async def send_json(self, data: Any) -> None: ...


class ConnectionManager:
    """In-memory registry of WebSocket clients keyed by execution id (string)."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocketLike]] = {}

    async def connect(self, execution_id: str, websocket: WebSocketLike) -> None:
        await websocket.accept()
        self._connections.setdefault(execution_id, set()).add(websocket)

    def disconnect(self, execution_id: str, websocket: WebSocketLike) -> None:
        conns = self._connections.get(execution_id)
        if conns:
            conns.discard(websocket)
            if not conns:
                del self._connections[execution_id]

    async def broadcast(self, execution_id: str, message: dict[str, Any]) -> None:
        for websocket in list(self._connections.get(execution_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:  # pragma: no cover - drop broken connections
                self.disconnect(execution_id, websocket)


manager = ConnectionManager()


async def _handle_message(factory: sessionmaker[Session], event: dict[str, Any]) -> None:
    with factory() as session:
        row = handle_event(session, event)
        session.commit()
        execution_id = str(row.execution_id) if row is not None else None
    if execution_id is not None:
        await manager.broadcast(execution_id, event)


async def run_event_subscriber(factory: sessionmaker[Session], redis_url: str) -> None:
    """Subscribe to Redis and process events until cancelled (with reconnect)."""
    import redis.asyncio as aioredis

    while True:
        try:
            client = aioredis.from_url(redis_url)
            pubsub = client.pubsub()
            await pubsub.subscribe(EVENTS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                except (ValueError, TypeError):
                    continue
                await _handle_message(factory, event)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - reconnect on Redis hiccups
            await asyncio.sleep(2.0)
