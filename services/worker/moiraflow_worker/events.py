"""Publish interpreter lifecycle events to Redis (UI pub/sub).

Events are non-critical for correctness (the durable truth is Temporal + Postgres),
so publishing is best-effort. The API subscribes to EVENTS_CHANNEL, persists events
to `execution_events`, updates execution status, and fans them out over WebSocket.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

EVENTS_CHANNEL = "moiraflow:events"


class RedisLike(Protocol):
    def publish(self, channel: str, message: str) -> Any: ...


def publish_to_redis(client: RedisLike, event: dict[str, Any]) -> None:
    client.publish(EVENTS_CHANNEL, json.dumps(event))


_client: Any | None = None


def get_redis() -> Any:
    global _client
    if _client is None:
        import redis  # imported lazily so non-publishing code paths don't need it

        _client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _client
