"""Tests for temporal metrics module."""

from __future__ import annotations

import pytest

from arf_rt.temporal.metrics import (
    TemporalMetrics,
    TemporalMetricsExtended,
    percentile,
)


class TestPercentile:
    """Tests for percentile function."""

    def test_percentile_50(self):
        """Test 50th percentile (median)."""
        data = {1: 10, 2: 10, 3: 10}
        assert percentile(data, 50) == 2.0

    def test_percentile_0(self):
        """Test 0th percentile (minimum)."""
        data = {1: 10, 2: 10, 3: 10}
        assert percentile(data, 0) == 1.0

    def test_percentile_100(self):
        """Test 100th percentile (maximum)."""
        data = {1: 10, 2: 10, 3: 10}
        assert percentile(data, 100) == 3.0

    def test_percentile_skewed(self):
        """Test percentile with skewed data."""
        data = {1: 100, 10: 1}
        # 50th percentile should be 1 (first bucket has 100/101 of data)
        assert percentile(data, 50) == 1.0

    def test_percentile_empty(self):
        """Test percentile with empty data."""
        assert percentile({}, 50) == 0.0


class TestTemporalMetrics:
    """Tests for TemporalMetrics class."""

    def test_initial_state(self):
        """Test initial state of metrics."""
        metrics = TemporalMetrics()
        assert metrics.total_paths == 0
        assert metrics.feasible_count == 0
        assert metrics.infeasible_count == 0
        assert metrics.unknown_count == 0
        assert metrics.elimination_rate == 0.0
        assert metrics.unknown_rate == 0.0

    def test_record_feasible(self):
        """Test recording feasible paths."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        assert metrics.feasible_count == 1
        assert metrics.total_paths == 1
        assert metrics.path_length_histogram[3] == 1

    def test_record_infeasible(self):
        """Test recording infeasible paths."""
        metrics = TemporalMetrics()
        metrics.record_infeasible("constraint_a", 4)
        assert metrics.infeasible_count == 1
        assert metrics.total_paths == 1
        assert metrics.constraint_violations["constraint_a"] == 1
        assert metrics.path_length_histogram[4] == 1

    def test_record_unknown(self):
        """Test recording unknown paths."""
        metrics = TemporalMetrics()
        metrics.record_unknown(2)
        assert metrics.unknown_count == 1
        assert metrics.total_paths == 1
        assert metrics.path_length_histogram[2] == 1

    def test_elimination_rate(self):
        """Test elimination rate calculation."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        metrics.record_feasible(3)
        metrics.record_infeasible("c1", 4)
        metrics.record_infeasible("c2", 5)
        assert metrics.elimination_rate == 0.5

    def test_unknown_rate(self):
        """Test unknown rate calculation."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        metrics.record_unknown(4)
        metrics.record_unknown(5)
        assert metrics.unknown_rate == 2/3

    def test_top_violated_constraint(self):
        """Test top violated constraint."""
        metrics = TemporalMetrics()
        metrics.record_infeasible("c1", 3)
        metrics.record_infeasible("c1", 4)
        metrics.record_infeasible("c2", 5)
        assert metrics.top_violated_constraint == "c1"

    def test_top_violated_constraint_none(self):
        """Test top violated constraint with no violations."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        assert metrics.top_violated_constraint is None

    def test_mean_path_length(self):
        """Test mean path length."""
        metrics = TemporalMetrics()
        metrics.record_feasible(2)
        metrics.record_feasible(4)
        metrics.record_infeasible("c1", 6)
        # Mean = (2 + 4 + 6) / 3 = 4
        assert metrics.mean_path_length() == 4.0

    def test_to_dict(self):
        """Test serialization to dict."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        metrics.record_infeasible("c1", 4)
        d = metrics.to_dict()
        assert d["total_paths"] == 2
        assert d["feasible_count"] == 1
        assert d["infeasible_count"] == 1
        assert d["elimination_rate"] == 0.5

    def test_reset(self):
        """Test resetting metrics."""
        metrics = TemporalMetrics()
        metrics.record_feasible(3)
        metrics.record_infeasible("c1", 4)
        metrics.reset()
        assert metrics.total_paths == 0
        assert metrics.feasible_count == 0
        assert metrics.infeasible_count == 0
        assert metrics.unknown_count == 0
        assert metrics.constraint_violations == {}
        assert metrics.path_length_histogram == {}


class TestTemporalMetricsExtended:
    """Tests for TemporalMetricsExtended class."""

    def test_initial_state(self):
        """Test initial state of extended metrics."""
        metrics = TemporalMetricsExtended()
        assert metrics.total_paths == 0
        assert len(metrics.evaluation_latencies) == 0

    def test_record_latency(self):
        """Test recording evaluation latency."""
        metrics = TemporalMetricsExtended()
        metrics.record_latency(10.5)
        metrics.record_latency(20.0)
        assert len(metrics.evaluation_latencies) == 2
        assert metrics.evaluation_latencies == [10.5, 20.0]

    def test_median_path_length(self):
        """Test median path length."""
        metrics = TemporalMetricsExtended()
        metrics.record_feasible(1)
        metrics.record_feasible(2)
        metrics.record_feasible(3)
        assert metrics.median_path_length == 2.0

    def test_p95_path_length(self):
        """Test 95th percentile path length."""
        metrics = TemporalMetricsExtended()
        for i in range(1, 101):
            metrics.record_feasible(i)
        assert metrics.p95_path_length == 95.0

    def test_p99_path_length(self):
        """Test 99th percentile path length."""
        metrics = TemporalMetricsExtended()
        for i in range(1, 101):
            metrics.record_feasible(i)
        assert metrics.p99_path_length == 99.0

    def test_std_path_length(self):
        """Test standard deviation of path lengths."""
        metrics = TemporalMetricsExtended()
        metrics.record_feasible(1)
        metrics.record_feasible(3)
        # Mean = 2, variance = ((1-2)^2 + (3-2)^2) / 2 = 1, std = 1
        assert metrics.std_path_length == 1.0

    def test_std_path_length_single(self):
        """Test standard deviation with single path."""
        metrics = TemporalMetricsExtended()
        metrics.record_feasible(5)
        assert metrics.std_path_length == 0.0

    def test_mean_latency_ms(self):
        """Test mean latency."""
        metrics = TemporalMetricsExtended()
        metrics.record_latency(10.0)
        metrics.record_latency(20.0)
        metrics.record_latency(30.0)
        assert metrics.mean_latency_ms == 20.0

    def test_median_latency_ms(self):
        """Test median latency."""
        metrics = TemporalMetricsExtended()
        metrics.record_latency(10.0)
        metrics.record_latency(20.0)
        metrics.record_latency(30.0)
        assert metrics.median_latency_ms == 20.0

    def test_median_latency_ms_even(self):
        """Test median latency with even count."""
        metrics = TemporalMetricsExtended()
        metrics.record_latency(10.0)
        metrics.record_latency(30.0)
        assert metrics.median_latency_ms == 20.0

    def test_p95_latency_ms(self):
        """Test 95th percentile latency."""
        metrics = TemporalMetricsExtended()
        for i in range(1, 101):
            metrics.record_latency(float(i))
        assert metrics.p95_latency_ms == 95.0

    def test_to_dict_extended(self):
        """Test extended serialization to dict."""
        metrics = TemporalMetricsExtended()
        metrics.record_feasible(3)
        metrics.record_latency(15.0)
        d = metrics.to_dict()
        assert "median_path_length" in d
        assert "p95_path_length" in d
        assert "p99_path_length" in d
        assert "std_path_length" in d
        assert "mean_latency_ms" in d
        assert "median_latency_ms" in d
        assert "p95_latency_ms" in d
        assert "evaluation_count" in d

    def test_reset_extended(self):
        """Test resetting extended metrics."""
        metrics = TemporalMetricsExtended()
        metrics.record_feasible(3)
        metrics.record_latency(15.0)
        metrics.reset()
        assert metrics.total_paths == 0
        assert len(metrics.evaluation_latencies) == 0