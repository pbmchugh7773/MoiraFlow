"""Publish interpreter lifecycle events to Redis (UI feed).

Events are non-critical for correctness (the durable truth is Temporal + Postgres),
so publishing is best-effort. They go to a Redis **Stream** (not fire-and-forget
pub/sub): the API reads them via a consumer group, so events published while the
API is briefly down (e.g. a restart) are retained and delivered on reconnect. The
stream is length-capped — the authoritative record is `execution_events` in Postgres.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

EVENTS_STREAM = "moiraflow:events:stream"
# Bound the stream so it can't grow unbounded; the durable record is in Postgres.
_STREAM_MAXLEN = 10000


class RedisLike(Protocol):
    def xadd(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        maxlen: int | None = ...,
        approximate: bool = ...,
    ) -> Any: ...


def publish_to_redis(client: RedisLike, event: dict[str, Any]) -> None:
    client.xadd(EVENTS_STREAM, {"data": json.dumps(event)}, maxlen=_STREAM_MAXLEN, approximate=True)


_client: Any | None = None


def get_redis() -> Any:
    global _client
    if _client is None:
        import redis  # imported lazily so non-publishing code paths don't need it

        _client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _client
