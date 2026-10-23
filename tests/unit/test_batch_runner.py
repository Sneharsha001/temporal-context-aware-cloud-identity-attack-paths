"""
tests/unit/test_batch_runner.py - Unit tests for PathFeasibilityBatchRunner.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.batch_runner import PathFeasibilityBatchRunner
from arf_rt.temporal.hints import TemporalHint


@pytest.fixture
def batch_test_data() -> dict[str, tuple[list[list[str]], dict[str, TemporalHint]]]:
    utc = timezone.utc
    ref = datetime(2026, 10, 23, 12, 0, 0, tzinfo=utc)

    def _dt(seconds: int) -> datetime:
        return datetime(2026, 10, 23, 10, 0, 0, tzinfo=utc) + timedelta(seconds=seconds)

    # Scenario 1: fully feasible path
    s1_hints = {
        "e1": TemporalHint(edge_id="e1", earliest_observed=_dt(0), latest_observed=_dt(0), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
        "e2": TemporalHint(edge_id="e2", earliest_observed=_dt(10), latest_observed=_dt(10), credential_issued=_dt(10), credential_expiry=_dt(3610), last_used=_dt(10)),
    }
    s1_paths = [["e1", "e2"]]

    # Scenario 2: infeasible path (causal violation)
    s2_hints = {
        "e3": TemporalHint(edge_id="e3", earliest_observed=_dt(100), latest_observed=_dt(100), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
        "e4": TemporalHint(edge_id="e4", earliest_observed=_dt(10), latest_observed=_dt(10), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
    }
    s2_paths = [["e3", "e4"]]

    return {
        "scenario_alpha": (s1_paths, s1_hints),
        "scenario_beta": (s2_paths, s2_hints),
    }


class TestPathFeasibilityBatchRunner:
    def test_run_scenario_feasible(
        self, batch_test_data: dict[str, tuple[list[list[str]], dict[str, TemporalHint]]]
    ) -> None:
        runner = PathFeasibilityBatchRunner(reference_time=datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc))
        paths, hints = batch_test_data["scenario_alpha"]
        res = runner.run_scenario("scenario_alpha", paths, hints)

        assert res.scenario_id == "scenario_alpha"
        assert res.total_paths == 1
        assert res.feasible_paths == 1
        assert res.elimination_rate == 0.0

    def test_run_scenario_infeasible(
        self, batch_test_data: dict[str, tuple[list[list[str]], dict[str, TemporalHint]]]
    ) -> None:
        runner = PathFeasibilityBatchRunner(reference_time=datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc))
        paths, hints = batch_test_data["scenario_beta"]
        res = runner.run_scenario("scenario_beta", paths, hints)

        assert res.scenario_id == "scenario_beta"
        assert res.infeasible_paths == 1
        assert res.elimination_rate == 1.0

    def test_run_all_and_comparison_table(
        self, batch_test_data: dict[str, tuple[list[list[str]], dict[str, TemporalHint]]]
    ) -> None:
        runner = PathFeasibilityBatchRunner(reference_time=datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc))
        results = runner.run_all(batch_test_data)

        assert len(results) == 2
        assert runner.global_metrics.total_paths == 2
        assert runner.global_metrics.feasible_count == 1
        assert runner.global_metrics.infeasible_count == 1

        table = runner.generate_comparison_table()
        assert "| Scenario ID | Total Paths | Feasible | Infeasible | Unknown | Elimination Rate |" in table
        assert "`scenario_beta`" in table
        assert "`scenario_alpha`" in table
