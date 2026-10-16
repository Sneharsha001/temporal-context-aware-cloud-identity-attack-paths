"""
tests/unit/test_datetime_helpers.py - Unit tests for datetime and temporal helpers.
"""

from datetime import datetime, timezone, timedelta
from arf_rt.util.datetime_helpers import (
    parse_iso8601,
    format_iso8601,
    is_within_temporal_window,
    parse_duration_seconds,
)


def test_parse_iso8601():
    dt = parse_iso8601("2026-10-16T12:00:00Z")
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 16
    assert dt.tzinfo == timezone.utc


def test_format_iso8601():
    dt = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    s = format_iso8601(dt)
    assert s == "2026-10-16T12:00:00Z"


def test_is_within_temporal_window():
    now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    assert is_within_temporal_window(now, past, future) is True
    assert is_within_temporal_window(past - timedelta(minutes=1), past, future) is False
    assert is_within_temporal_window(future + timedelta(minutes=1), past, future) is False


def test_parse_duration_seconds():
    assert parse_duration_seconds("60s") == 60
    assert parse_duration_seconds("5m") == 300
    assert parse_duration_seconds("2h") == 7200
    assert parse_duration_seconds("1d") == 86400
