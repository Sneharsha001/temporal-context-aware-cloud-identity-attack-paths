"""
arf_rt/util/datetime_helpers.py - ISO-8601 timestamp parsing and temporal window helpers.

Used by the CCPF temporal evaluator to check credential validity, role assumption
expiry, and time-bound policy constraints.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


def parse_iso8601(timestamp_str: str) -> datetime:
    """Parse an ISO-8601 formatted timestamp string into a timezone-aware UTC datetime.

    Args:
        timestamp_str: ISO string (e.g. '2026-10-16T12:00:00Z' or '+00:00').

    Returns:
        Timezone-aware datetime in UTC.
    """
    ts = timestamp_str.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso8601(dt: Optional[datetime] = None) -> str:
    """Format a datetime into a standard ISO-8601 UTC string ending in 'Z'.

    Args:
        dt: Optional datetime. Defaults to current UTC time.

    Returns:
        ISO-8601 string representation.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_within_temporal_window(
    target_time: datetime,
    valid_from: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
) -> bool:
    """Verify whether target_time falls within [valid_from, valid_until].

    Args:
        target_time: Datetime to test.
        valid_from: Optional start bound (inclusive).
        valid_until: Optional end bound (inclusive).

    Returns:
        True if target_time is within the bounds, False otherwise.
    """
    t = target_time.astimezone(timezone.utc)
    if valid_from is not None and t < valid_from.astimezone(timezone.utc):
        return False
    if valid_until is not None and t > valid_until.astimezone(timezone.utc):
        return False
    return True


def parse_duration_seconds(duration_str: str) -> int:
    """Parse common duration expressions (e.g. '1h', '30m', '12h', '3600s') into seconds.

    Args:
        duration_str: Formatted duration string.

    Returns:
        Integer duration in seconds.
    """
    s = duration_str.strip().lower()
    if s.endswith("s"):
        return int(s[:-1])
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("d"):
        return int(s[:-1]) * 86400
    return int(s)
