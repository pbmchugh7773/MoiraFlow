"""Map a job's `retry` policy to a Temporal RetryPolicy (ADR: direct mapping).

Pure and deterministic — safe to call from workflow code. `fixed` uses a backoff
coefficient of 1.0 (constant interval); `exponential` uses 2.0.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio.common import RetryPolicy

from .durations import parse_duration

_BACKOFF = {"fixed": 1.0, "exponential": 2.0, "custom": 2.0}
# A job that declares no `retry` still gets a bounded policy. Temporal's own default
# is unlimited attempts, so a permanently-failing job (bad URL, unreachable host)
# would retry forever and wedge the whole execution. Bound it so it fails fast.
_DEFAULT_MAX_ATTEMPTS = 3


def build_retry_policy(retry: dict[str, Any] | None) -> RetryPolicy:
    if retry is None:
        return RetryPolicy(
            maximum_attempts=_DEFAULT_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=1),
        )
    strategy = retry.get("strategy", "fixed")
    interval = parse_duration(retry.get("initial_interval") or retry.get("interval"))
    return RetryPolicy(
        maximum_attempts=int(retry.get("max_attempts", 1)),
        backoff_coefficient=_BACKOFF.get(strategy, 2.0),
        initial_interval=interval or timedelta(seconds=1),
    )
