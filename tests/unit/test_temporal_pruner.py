"""
tests/unit/test_temporal_pruner.py - Unit tests for PathFeasibilityPruner.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.pruner import PathFeasibilityPruner


@pytest.fixture
def pruning_fixtures() -> tuple[dict[str, TemporalHint], datetime]:
    utc = timezone.utc
    ref = datetime(2026, 10, 24, 12, 0, 0, tzinfo=utc)

    def _dt(seconds: int) -> datetime:
        return datetime(2026, 10, 24, 10, 0, 0, tzinfo=utc) + timedelta(seconds=seconds)

    hints = {
        # Valid starting hop
        "e_start": TemporalHint(edge_id="e_start", earliest_observed=_dt(0), latest_observed=_dt(0), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
        # Valid continuation hop (observed at +30s)
        "e_valid_next": TemporalHint(edge_id="e_valid_next", earliest_observed=_dt(30), latest_observed=_dt(30), credential_issued=_dt(30), credential_expiry=_dt(3630), last_used=_dt(30)),
        # Infeasible continuation hop (observed BEFORE start: -50s, causal violation)
        "e_invalid_causal": TemporalHint(edge_id="e_invalid_causal", earliest_observed=_dt(-50), latest_observed=_dt(-50), credential_issued=_dt(0), credential_expiry=_dt(3600), last_used=_dt(0)),
        # Infeasible continuation hop (attempted at +4000s, after e_start expired)
        "e_invalid_expired": TemporalHint(edge_id="e_invalid_expired", earliest_observed=_dt(4000), latest_observed=_dt(4000), credential_issued=_dt(4000), credential_expiry=_dt(7600), last_used=_dt(4000)),
    }
    return hints, ref


class TestPathFeasibilityPruner:
    def test_can_extend_valid(
        self, pruning_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = pruning_fixtures
        pruner = PathFeasibilityPruner(reference_time=ref)

        assert pruner.can_extend(["e_start"], "e_valid_next", hints) is True
        assert pruner.metrics.evaluated_extensions == 1
        assert pruner.metrics.pruned_extensions == 0

    def test_can_extend_causal_inversion_pruned(
        self, pruning_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = pruning_fixtures
        pruner = PathFeasibilityPruner(reference_time=ref)

        assert pruner.can_extend(["e_start"], "e_invalid_causal", hints) is False
        assert pruner.metrics.pruned_extensions == 1
        assert pruner.metrics.prune_rate == 1.0

    def test_can_extend_expired_pruned(
        self, pruning_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = pruning_fixtures
        pruner = PathFeasibilityPruner(reference_time=ref)

        assert pruner.can_extend(["e_start"], "e_invalid_expired", hints) is False

    def test_prune_candidate_extensions_filters_unviable(
        self, pruning_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = pruning_fixtures
        pruner = PathFeasibilityPruner(reference_time=ref)

        candidates = ["e_valid_next", "e_invalid_causal", "e_invalid_expired"]
        viable = pruner.prune_candidate_extensions(["e_start"], candidates, hints)

        assert viable == ["e_valid_next"]
        assert pruner.metrics.evaluated_extensions == 3
        assert pruner.metrics.pruned_extensions == 2
        assert pruner.metrics.prune_rate == pytest.approx(2.0 / 3.0)
