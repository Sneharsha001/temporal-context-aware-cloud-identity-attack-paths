"""Tests for datetime_helpers module."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from arf_rt.util.datetime_helpers import (
    parse_iso8601,
    format_iso8601,
    is_within_temporal_window,
    parse_duration_seconds,
    time_range_overlaps,
    time_range_contains,
    intersect_time_ranges,
    format_duration_seconds,
)


class TestParseISO8601:
    """Tests for parse_iso8601 function."""

    def test_parse_zulu_timestamp(self):
        """Test parsing Zulu (Z) timestamp."""
        dt = parse_iso8601("2026-10-16T12:00:00Z")
        assert dt == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)

    def test_parse_offset_timestamp(self):
        """Test parsing timestamp with explicit offset."""
        dt = parse_iso8601("2026-10-16T12:00:00+00:00")
        assert dt == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)

    def test_parse_negative_offset(self):
        """Test parsing timestamp with negative offset."""
        dt = parse_iso8601("2026-10-16T07:00:00-05:00")
        assert dt == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


class TestFormatISO8601:
    """Tests for format_iso8601 function."""

    def test_format_current_time(self):
        """Test formatting current time."""
        result = format_iso8601()
        assert result.endswith("Z")
        assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ

    def test_format_specific_time(self):
        """Test formatting a specific datetime."""
        dt = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        result = format_iso8601(dt)
        assert result == "2026-10-16T12:00:00Z"

    def test_format_with_timezone_conversion(self):
        """Test formatting with timezone conversion."""
        dt = datetime(2026, 10, 16, 7, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
        result = format_iso8601(dt)
        assert result == "2026-10-16T12:00:00Z"


class TestIsWithinTemporalWindow:
    """Tests for is_within_temporal_window function."""

    def test_within_bounds(self):
        """Test time within bounds."""
        target = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        valid_from = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        valid_until = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        assert is_within_temporal_window(target, valid_from, valid_until) is True

    def test_before_bounds(self):
        """Test time before bounds."""
        target = datetime(2026, 10, 16, 9, 0, 0, tzinfo=timezone.utc)
        valid_from = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        valid_until = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        assert is_within_temporal_window(target, valid_from, valid_until) is False

    def test_after_bounds(self):
        """Test time after bounds."""
        target = datetime(2026, 10, 16, 15, 0, 0, tzinfo=timezone.utc)
        valid_from = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        valid_until = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        assert is_within_temporal_window(target, valid_from, valid_until) is False

    def test_none_bounds(self):
        """Test with None bounds (unbounded)."""
        target = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        assert is_within_temporal_window(target, None, None) is True
        assert is_within_temporal_window(target, datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc), None) is True
        assert is_within_temporal_window(target, None, datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)) is True


class TestParseDurationSeconds:
    """Tests for parse_duration_seconds function."""

    def test_parse_seconds(self):
        assert parse_duration_seconds("30s") == 30
        assert parse_duration_seconds("3600s") == 3600

    def test_parse_minutes(self):
        assert parse_duration_seconds("1m") == 60
        assert parse_duration_seconds("30m") == 1800

    def test_parse_hours(self):
        assert parse_duration_seconds("1h") == 3600
        assert parse_duration_seconds("2h") == 7200

    def test_parse_days(self):
        assert parse_duration_seconds("1d") == 86400
        assert parse_duration_seconds("2d") == 172800

    def test_parse_plain_number(self):
        assert parse_duration_seconds("3600") == 3600


class TestTimeRangeOverlaps:
    """Tests for time_range_overlaps function."""

    def test_overlapping_ranges(self):
        """Test overlapping ranges."""
        start1 = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        assert time_range_overlaps(start1, end1, start2, end2) is True

    def test_non_overlapping_ranges(self):
        """Test non-overlapping ranges."""
        start1 = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        assert time_range_overlaps(start1, end1, start2, end2) is False

    def test_adjacent_ranges(self):
        """Test adjacent ranges (touching at boundary)."""
        start1 = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        assert time_range_overlaps(start1, end1, start2, end2) is True  # Inclusive


class TestTimeRangeContains:
    """Tests for time_range_contains function."""

    def test_contains_inner_range(self):
        """Test outer range contains inner range."""
        outer_start = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        outer_end = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        inner_start = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        inner_end = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        assert time_range_contains(outer_start, outer_end, inner_start, inner_end) is True

    def test_not_contains(self):
        """Test outer range does not contain inner range."""
        outer_start = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        outer_end = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        inner_start = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        inner_end = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        assert time_range_contains(outer_start, outer_end, inner_start, inner_end) is False


class TestIntersectTimeRanges:
    """Tests for intersect_time_ranges function."""

    def test_intersecting_ranges(self):
        """Test intersecting ranges."""
        start1 = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        result = intersect_time_ranges(start1, end1, start2, end2)
        assert result is not None
        assert result[0] == datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        assert result[1] == datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)

    def test_non_intersecting_ranges(self):
        """Test non-intersecting ranges."""
        start1 = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 10, 16, 16, 0, 0, tzinfo=timezone.utc)
        assert intersect_time_ranges(start1, end1, start2, end2) is None


class TestFormatDurationSeconds:
    """Tests for format_duration_seconds function."""

    def test_format_seconds(self):
        assert format_duration_seconds(30) == "30s"
        assert format_duration_seconds(59) == "59s"

    def test_format_minutes(self):
        assert format_duration_seconds(60) == "1m"
        assert format_duration_seconds(120) == "2m"
        assert format_duration_seconds(90) == "1m 30s"

    def test_format_hours(self):
        assert format_duration_seconds(3600) == "1h"
        assert format_duration_seconds(7200) == "2h"
        assert format_duration_seconds(5400) == "1h 30m"

    def test_format_days(self):
        assert format_duration_seconds(86400) == "1d"
        assert format_duration_seconds(172800) == "2d"
        assert format_duration_seconds(90000) == "1d 1h"

    def test_format_complex(self):
        assert format_duration_seconds(90061) == "1d 1h 1m 1s"

    def test_zero(self):
        assert format_duration_seconds(0) == "0s"

    def test_negative(self):
        assert format_duration_seconds(-1) == "0s"