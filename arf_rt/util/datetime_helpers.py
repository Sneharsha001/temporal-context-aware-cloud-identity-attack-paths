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


def time_range_overlaps(
    start1: datetime,
    end1: datetime,
    start2: datetime,
    end2: datetime,
) -> bool:
    """Check if two time ranges overlap.

    Args:
        start1: Start of first range.
        end1: End of first range.
        start2: Start of second range.
        end2: End of second range.

    Returns:
        True if ranges overlap, False otherwise.
    """
    s1 = start1.astimezone(timezone.utc)
    e1 = end1.astimezone(timezone.utc)
    s2 = start2.astimezone(timezone.utc)
    e2 = end2.astimezone(timezone.utc)
    return s1 <= e2 and s2 <= e1


def time_range_contains(
    outer_start: datetime,
    outer_end: datetime,
    inner_start: datetime,
    inner_end: datetime,
) -> bool:
    """Check if one time range fully contains another.

    Args:
        outer_start: Start of outer range.
        outer_end: End of outer range.
        inner_start: Start of inner range.
        inner_end: End of inner range.

    Returns:
        True if outer range contains inner range, False otherwise.
    """
    os = outer_start.astimezone(timezone.utc)
    oe = outer_end.astimezone(timezone.utc)
    is_ = inner_start.astimezone(timezone.utc)
    ie = inner_end.astimezone(timezone.utc)
    return os <= is_ and ie <= oe


def intersect_time_ranges(
    start1: datetime,
    end1: datetime,
    start2: datetime,
    end2: datetime,
) -> tuple[datetime, datetime] | None:
    """Compute the intersection of two time ranges.

    Args:
        start1: Start of first range.
        end1: End of first range.
        start2: Start of second range.
        end2: End of second range.

    Returns:
        Tuple of (start, end) of intersection, or None if no overlap.
    """
    s1 = start1.astimezone(timezone.utc)
    e1 = end1.astimezone(timezone.utc)
    s2 = start2.astimezone(timezone.utc)
    e2 = end2.astimezone(timezone.utc)

    intersect_start = max(s1, s2)
    intersect_end = min(e1, e2)

    if intersect_start > intersect_end:
        return None
    return (intersect_start, intersect_end)


def format_duration_seconds(seconds: int) -> str:
    """Format seconds into human-readable duration string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string (e.g., '1h 30m 45s').
    """
    if seconds < 0:
        return "0s"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)
