"""
tests/unit/test_metrics.py - Unit tests for arf_rt.temporal.metrics.

Covers TemporalMetrics recording, derived statistics, serialization, and reset.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.metrics import TemporalMetrics


class TestTemporalMetricsBasic:
    def test_initial_state_all_zero(self) -> None:
        m = TemporalMetrics()
        assert m.total_paths == 0
        assert m.feasible_count == 0
        assert m.infeasible_count == 0
        assert m.unknown_count == 0

    def test_record_feasible_increments_counts(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(path_length=3)
        assert m.total_paths == 1
        assert m.feasible_count == 1

    def test_record_infeasible_increments_counts(self) -> None:
        m = TemporalMetrics()
        m.record_infeasible(constraint_id="TC-1", path_length=2)
        assert m.total_paths == 1
        assert m.infeasible_count == 1
        assert m.constraint_violations["TC-1"] == 1

    def test_record_unknown_increments_counts(self) -> None:
        m = TemporalMetrics()
        m.record_unknown(path_length=4)
        assert m.total_paths == 1
        assert m.unknown_count == 1

    def test_multiple_violations_same_constraint(self) -> None:
        m = TemporalMetrics()
        m.record_infeasible("TC-3", 2)
        m.record_infeasible("TC-3", 3)
        assert m.constraint_violations["TC-3"] == 2


class TestDerivedStatistics:
    def test_elimination_rate_zero_when_no_paths(self) -> None:
        assert TemporalMetrics().elimination_rate == 0.0

    def test_elimination_rate_half(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(2)
        m.record_infeasible("TC-1", 2)
        assert m.elimination_rate == pytest.approx(0.5)

    def test_unknown_rate(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(1)
        m.record_unknown(1)
        assert m.unknown_rate == pytest.approx(0.5)

    def test_top_violated_constraint_none_when_empty(self) -> None:
        assert TemporalMetrics().top_violated_constraint is None

    def test_top_violated_constraint_most_common(self) -> None:
        m = TemporalMetrics()
        m.record_infeasible("TC-1", 2)
        m.record_infeasible("TC-3", 2)
        m.record_infeasible("TC-3", 2)
        assert m.top_violated_constraint == "TC-3"

    def test_mean_path_length_zero_when_empty(self) -> None:
        assert TemporalMetrics().mean_path_length() == 0.0

    def test_mean_path_length_correct(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(2)
        m.record_feasible(4)
        assert m.mean_path_length() == pytest.approx(3.0)


class TestSerialization:
    def test_to_dict_has_all_keys(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(2)
        d = m.to_dict()
        required = {
            "total_paths", "feasible_count", "infeasible_count",
            "unknown_count", "elimination_rate", "unknown_rate",
            "top_violated_constraint", "mean_path_length",
            "constraint_violations", "path_length_histogram",
        }
        assert required.issubset(d.keys())

    def test_to_dict_values_are_json_safe(self) -> None:
        import json
        m = TemporalMetrics()
        m.record_infeasible("TC-2", 3)
        json.dumps(m.to_dict())  # must not raise


class TestReset:
    def test_reset_clears_all(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(2)
        m.record_infeasible("TC-1", 2)
        m.record_unknown(3)
        m.reset()
        assert m.total_paths == 0
        assert m.feasible_count == 0
        assert m.infeasible_count == 0
        assert m.unknown_count == 0
        assert len(m.constraint_violations) == 0
