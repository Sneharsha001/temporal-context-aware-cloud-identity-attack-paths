"""
tests/unit/test_path_filter.py - Unit tests for arf_rt.temporal.path_filter.

Covers TemporalPathFilter.filter(), passing(), and reject_on_window_anomaly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.path_filter import FilterResult, TemporalPathFilter
from arf_rt.temporal.verdict import VerdictKind


UTC = timezone.utc
BASE = datetime(2025, 6, 15, 8, 0, 0, tzinfo=UTC)


def _h(eid: str, obs_s: float | None = None, issued_s: float | None = None,
        expiry_s: float | None = None, last_used_s: float | None = None) -> TemporalHint:
    from datetime import timedelta
    def _dt(s):
        return BASE + timedelta(seconds=s) if s is not None else None
    return TemporalHint(
        edge_id=eid,
        earliest_observed=_dt(obs_s),
        latest_observed=_dt(obs_s),
        credential_issued=_dt(issued_s),
        credential_expiry=_dt(expiry_s),
        last_used=_dt(last_used_s),
    )


REF = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


class TestTemporalPathFilterFilter:
    def _pf(self, **kwargs) -> TemporalPathFilter:
        from datetime import timedelta
        cfg = TemporalConfig(**kwargs) if kwargs else TemporalConfig()
        return TemporalPathFilter(config=cfg, run_window_checks=False)

    def test_feasible_path_passes(self) -> None:
        hints = {
            "e1": _h("e1", obs_s=0, issued_s=0, expiry_s=3600, last_used_s=0),
            "e2": _h("e2", obs_s=10, issued_s=10, expiry_s=3610, last_used_s=10),
        }
        pf = TemporalPathFilter(config=TemporalConfig(), run_window_checks=False)
        results = pf.filter([["e1", "e2"]], hints)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].verdict_kind == "FEASIBLE"

    def test_infeasible_path_is_rejected(self) -> None:
        hints = {
            "e1": _h("e1", obs_s=100),
            "e2": _h("e2", obs_s=50),   # TC-1 violation: observed before e1
        }
        pf = TemporalPathFilter(
            config=TemporalConfig(enabled_constraints=frozenset({"TC-1"})),
            run_window_checks=False,
        )
        results = pf.filter([["e1", "e2"]], hints)
        assert results[0].passed is False
        assert results[0].rejected_by != ""

    def test_empty_paths_returns_empty(self) -> None:
        pf = TemporalPathFilter()
        assert pf.filter([], {}) == []

    def test_multiple_paths_all_evaluated(self) -> None:
        hints = {}
        paths = [["e1"], ["e2"], ["e3"]]
        pf = TemporalPathFilter(config=TemporalConfig(unknown_passthrough=True))
        results = pf.filter(paths, hints)
        assert len(results) == 3

    def test_passing_returns_only_feasible(self) -> None:
        hints = {
            "good": _h("good", obs_s=0, last_used_s=0),
            "bad1": _h("bad1", obs_s=100),
            "bad2": _h("bad2", obs_s=50),
        }
        pf = TemporalPathFilter(
            config=TemporalConfig(enabled_constraints=frozenset({"TC-1"})),
            run_window_checks=False,
        )
        passed = pf.passing([["good"], ["bad1", "bad2"]], hints)
        # Single-hop path has no TC-1 to check → FEASIBLE; two-hop has violation
        assert ["good"] in passed

    def test_filter_result_contains_edge_ids(self) -> None:
        pf = TemporalPathFilter(config=TemporalConfig(unknown_passthrough=True))
        results = pf.filter([["e1", "e2"]], {})
        assert results[0].edge_ids == ["e1", "e2"]


class TestWindowAnomalyAnnotation:
    def test_window_anomalies_attached_when_enabled(self) -> None:
        from datetime import timedelta
        # Two hops with 0s gap → impossible concurrency anomaly
        t = BASE
        hints = {
            "e1": TemporalHint(edge_id="e1", earliest_observed=t, latest_observed=t),
            "e2": TemporalHint(edge_id="e2", earliest_observed=t),
        }
        pf = TemporalPathFilter(
            config=TemporalConfig(enabled_constraints=frozenset()),
            run_window_checks=True,
            reject_on_window_anomaly=False,
        )
        results = pf.filter([["e1", "e2"]], hints)
        assert len(results[0].window_anomalies) > 0

    def test_reject_on_window_anomaly_works(self) -> None:
        t = BASE
        hints = {
            "e1": TemporalHint(edge_id="e1", earliest_observed=t, latest_observed=t),
            "e2": TemporalHint(edge_id="e2", earliest_observed=t),
        }
        pf = TemporalPathFilter(
            config=TemporalConfig(
                enabled_constraints=frozenset(),
                unknown_passthrough=True,
            ),
            run_window_checks=True,
            reject_on_window_anomaly=True,
        )
        results = pf.filter([["e1", "e2"]], hints)
        assert results[0].passed is False
