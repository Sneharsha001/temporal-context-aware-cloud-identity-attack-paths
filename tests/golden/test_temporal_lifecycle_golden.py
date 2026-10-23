"""
tests/golden/test_temporal_lifecycle_golden.py - Golden regression tests for lifecycle scenarios.

Locks deterministic outcomes for reference multi-hop attack path scenarios.
Any unexpected drift in evaluation logic will immediately trigger test failures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind

UTC = timezone.utc
REF_TIME = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)


def _dt(seconds: int) -> datetime:
    return datetime(2026, 10, 23, 8, 0, 0, tzinfo=UTC) + timedelta(seconds=seconds)


class TestTemporalLifecycleGolden:
    """Golden reference scenarios for multi-hop attack path lifecycles."""

    def test_golden_scenario_1_expiry_at_penultimate_hop(self) -> None:
        """4-hop chain where hop 3 is attempted after hop 2's session expired (TC-2)."""
        hints = {
            "h1": TemporalHint(edge_id="h1", earliest_observed=_dt(0), latest_observed=_dt(0), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
            "h2": TemporalHint(edge_id="h2", earliest_observed=_dt(100), latest_observed=_dt(100), credential_issued=_dt(100), credential_expiry=_dt(1000), last_used=_dt(100)),
            "h3": TemporalHint(edge_id="h3", earliest_observed=_dt(2000), latest_observed=_dt(2000), credential_issued=_dt(2000), credential_expiry=_dt(5000), last_used=_dt(2000)),
            "h4": TemporalHint(edge_id="h4", earliest_observed=_dt(2100), latest_observed=_dt(2100), credential_issued=_dt(2100), credential_expiry=_dt(6000), last_used=_dt(2100)),
        }
        ev = TemporalEvaluator(reference_time=REF_TIME)
        verdict = ev.evaluate(["h1", "h2", "h3", "h4"], hints)

        assert verdict.kind == VerdictKind.INFEASIBLE
        assert verdict.violated_constraint == "TC-2"

    def test_golden_scenario_2_perfect_multihop_traversal(self) -> None:
        """3-hop path where all causal and validity conditions are strictly met."""
        hints = {
            "h1": TemporalHint(edge_id="h1", earliest_observed=_dt(0), latest_observed=_dt(0), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
            "h2": TemporalHint(edge_id="h2", earliest_observed=_dt(60), latest_observed=_dt(60), credential_issued=_dt(60), credential_expiry=_dt(3660), last_used=_dt(60)),
            "h3": TemporalHint(edge_id="h3", earliest_observed=_dt(120), latest_observed=_dt(120), credential_issued=_dt(120), credential_expiry=_dt(3720), last_used=_dt(120)),
        }
        ev = TemporalEvaluator(reference_time=REF_TIME)
        verdict = ev.evaluate(["h1", "h2", "h3"], hints)

        assert verdict.kind == VerdictKind.FEASIBLE
        assert verdict.violated_constraint is None

    def test_golden_scenario_3_dormant_credential_resuscitation(self) -> None:
        """Single hop path where credential was last used 120 days before ref time (TC-4)."""
        stale_time = REF_TIME - timedelta(days=120)
        hints = {
            "h1": TemporalHint(edge_id="h1", earliest_observed=stale_time, latest_observed=stale_time, credential_issued=stale_time, credential_expiry=stale_time + timedelta(hours=1), last_used=stale_time),
        }
        ev = TemporalEvaluator(reference_time=REF_TIME)
        verdict = ev.evaluate(["h1"], hints)

        assert verdict.kind == VerdictKind.INFEASIBLE
        assert verdict.violated_constraint == "TC-4"

    def test_golden_scenario_4_sparse_unknown_pass_through(self) -> None:
        """Path with unpopulated hints yields UNKNOWN in default mode."""
        hints = {
            "h1": TemporalHint(edge_id="h1"),
            "h2": TemporalHint(edge_id="h2"),
        }
        ev = TemporalEvaluator(reference_time=REF_TIME)
        verdict = ev.evaluate(["h1", "h2"], hints)

        assert verdict.kind == VerdictKind.UNKNOWN

    def test_golden_scenario_5_causal_inversion(self) -> None:
        """Hop 2 observed before hop 1 was observed (TC-1)."""
        hints = {
            "h1": TemporalHint(edge_id="h1", earliest_observed=_dt(500), latest_observed=_dt(500), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
            "h2": TemporalHint(edge_id="h2", earliest_observed=_dt(200), latest_observed=_dt(200), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
        }
        ev = TemporalEvaluator(reference_time=REF_TIME)
        verdict = ev.evaluate(["h1", "h2"], hints)

        assert verdict.kind == VerdictKind.INFEASIBLE
        assert verdict.violated_constraint == "TC-1"
