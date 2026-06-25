from datetime import timedelta

import pytest

from moiraflow_worker.durations import parse_duration


def test_parses_seconds():
    assert parse_duration("30s") == timedelta(seconds=30)


def test_parses_minutes():
    assert parse_duration("2m") == timedelta(minutes=2)


def test_parses_hours_and_days():
    assert parse_duration("1h") == timedelta(hours=1)
    assert parse_duration("1d") == timedelta(days=1)


def test_parses_fractional():
    assert parse_duration("1.5m") == timedelta(minutes=1, seconds=30)


def test_none_returns_none():
    assert parse_duration(None) is None


def test_invalid_raises():
    with pytest.raises(ValueError):
        parse_duration("soon")
    with pytest.raises(ValueError):
        parse_duration("10")  # missing unit
