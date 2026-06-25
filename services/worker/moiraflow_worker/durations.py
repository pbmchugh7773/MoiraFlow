"""Parse the workflow's human duration strings (e.g. "2m", "30s") to timedelta."""

from __future__ import annotations

import re
from datetime import timedelta

_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)(s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str | None) -> timedelta | None:
    if value is None:
        return None
    match = _PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"invalid duration: {value!r} (expected e.g. '30s', '2m', '1h')")
    amount, unit = float(match.group(1)), match.group(2)
    return timedelta(seconds=amount * _UNIT_SECONDS[unit])
