"""
tests/unit/test_temporal_stats.py - Unit tests for arf_rt.util.temporal_stats.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.util.temporal_stats import (
    compute_duration_statistics,
    compute_inter_arrival_times,
    detect_timing_outliers,
)


class TestTemporalStats:
    def test_inter_arrival_times_empty_and_single(self) -> None:
        utc = timezone.utc
        assert compute_inter_arrival_times([]) == []
        assert compute_inter_arrival_times([datetime(2026, 10, 23, 10, 0, tzinfo=utc)]) == []

    def test_inter_arrival_times_sorted(self) -> None:
        utc = timezone.utc
        t0 = datetime(2026, 10, 23, 10, 0, 0, tzinfo=utc)
        t1 = t0 + timedelta(seconds=15)
        t2 = t0 + timedelta(seconds=45)

        intervals = compute_inter_arrival_times([t2, t0, t1])  # unsorted input
        assert intervals == [15.0, 30.0]

    def test_duration_statistics(self) -> None:
        durations = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_duration_statistics(durations)

        assert stats["count"] == 5.0
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["mean"] == 30.0
        assert stats["median"] == 30.0
        assert stats["stddev"] > 0

    def test_duration_statistics_empty(self) -> None:
        stats = compute_duration_statistics([])
        assert stats["count"] == 0.0
        assert stats["mean"] == 0.0

    def test_detect_timing_outliers(self) -> None:
        durations = [10.0, 11.0, 10.5, 9.8, 10.2, 1000.0]  # 1000.0 is an outlier
        outliers = detect_timing_outliers(durations, threshold_z_score=2.0)
        assert 5 in outliers
