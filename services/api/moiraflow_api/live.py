"""Live execution feed: Redis Stream consumer -> persist + fan-out to WebSockets.

The worker appends lifecycle events to a Redis Stream. This subscriber consumes them
through a consumer group, persists each (`handle_event`, advancing execution status),
and broadcasts it to any WebSocket clients watching that execution. Using a stream +
consumer group (instead of fire-and-forget pub/sub) makes the feed durable: events
published while this subscriber is briefly down (e.g. a restart) are retained and
delivered on reconnect. Temporal does not push to external subscribers — Redis is the
bridge (docs 05 §5).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from .services.events import handle_event

# Must match moiraflow_worker.events.EVENTS_STREAM (shared protocol).
EVENTS_STREAM = "moiraflow:events:stream"
_GROUP = "moiraflow-api"
_CONSUMER = "api"


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


def _persist_event(factory: sessionmaker[Session], event: dict[str, Any]) -> str | None:
    """Synchronous DB work for one event. Returns the execution id to fan out to."""
    with factory() as session:
        row = handle_event(session, event)
        session.commit()
        return str(row.execution_id) if row is not None else None


async def _handle_message(factory: sessionmaker[Session], event: dict[str, Any]) -> None:
    # Run the blocking DB work in a thread so it can never stall the event loop. Doing
    # the synchronous session checkout/commit directly on the loop could deadlock the
    # whole API if the connection pool is momentarily exhausted by in-flight requests.
    loop = asyncio.get_running_loop()
    execution_id = await loop.run_in_executor(None, _persist_event, factory, event)
    if execution_id is not None:
        await manager.broadcast(execution_id, event)


async def run_event_subscriber(factory: sessionmaker[Session], redis_url: str) -> None:
    """Consume the events stream via a consumer group until cancelled (with reconnect).

    The group's read position is retained by Redis, so on reconnect we first drain any
    delivered-but-unacked messages (crash recovery) and then receive every event that
    arrived while we were down — nothing is lost to a restart.
    """
    import redis.asyncio as aioredis
    from redis.exceptions import ResponseError

    while True:
        try:
            client = aioredis.from_url(redis_url, decode_responses=True)
            try:
                # New group starts at the tail; on restart the group already exists
                # (BUSYGROUP) and keeps its retained position.
                await client.xgroup_create(EVENTS_STREAM, _GROUP, id="$", mkstream=True)
            except ResponseError:
                pass  # group already exists
            cursor = "0"  # first pass: redeliver our pending (un-acked) messages
            while True:
                # redis-py types this as a deep union; treat as plain data.
                resp: Any = await client.xreadgroup(
                    _GROUP, _CONSUMER, {EVENTS_STREAM: cursor}, count=200, block=5000
                )
                messages: Any = resp[0][1] if resp else []
                if not messages:
                    cursor = ">"  # pending drained -> only brand-new messages from here
                    continue
                for msg_id, fields in messages:
                    try:
                        await _handle_message(factory, json.loads(fields["data"]))
                    except Exception:  # never let one bad event wedge the stream
                        pass
                    await client.xack(EVENTS_STREAM, _GROUP, msg_id)
                if cursor != ">":
                    cursor = messages[-1][0]  # advance the pending-recovery cursor
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - reconnect on Redis hiccups
            await asyncio.sleep(2.0)
