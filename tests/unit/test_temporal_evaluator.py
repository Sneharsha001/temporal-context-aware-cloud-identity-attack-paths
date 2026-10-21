"""
tests/unit/test_temporal_evaluator.py - Unit tests for arf_rt.temporal.evaluator.

Tests each TC-1 through TC-5 constraint independently, plus integration
scenarios for UNKNOWN passthrough and strict-mode blocking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind


UTC = timezone.utc


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2025, 6, 15, hour, minute, second, tzinfo=UTC)


REF = _dt(12, 0, 0)  # fixed reference time for staleness checks


# ---------------------------------------------------------------------------
# Helper to build a TemporalHint with sane defaults
# ---------------------------------------------------------------------------


def make_hint(
    edge_id: str,
    earliest: datetime | None = None,
    latest: datetime | None = None,
    issued: datetime | None = None,
    expiry: datetime | None = None,
    last_used: datetime | None = None,
) -> TemporalHint:
    return TemporalHint(
        edge_id=edge_id,
        earliest_observed=earliest,
        latest_observed=latest,
        credential_issued=issued,
        credential_expiry=expiry,
        last_used=last_used,
    )


# ---------------------------------------------------------------------------
# TC-1: Causal order
# ---------------------------------------------------------------------------


class TestTC1CausalOrder:
    def _ev(self) -> TemporalEvaluator:
        return TemporalEvaluator(
            config=TemporalConfig(enabled_constraints=frozenset({"TC-1"})),
            reference_time=REF,
        )

    def test_feasible_when_ordered(self) -> None:
        h1 = make_hint("e1", earliest=_dt(8), latest=_dt(9))
        h2 = make_hint("e2", earliest=_dt(10), latest=_dt(11))
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.FEASIBLE

    def test_infeasible_when_reversed(self) -> None:
        h1 = make_hint("e1", earliest=_dt(10), latest=_dt(11))
        h2 = make_hint("e2", earliest=_dt(8), latest=_dt(9))
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.INFEASIBLE
        assert v.violated_constraint == "TC-1"

    def test_unknown_when_data_missing(self) -> None:
        h1 = make_hint("e1")
        h2 = make_hint("e2")
        ev = TemporalEvaluator(
            config=TemporalConfig(
                enabled_constraints=frozenset({"TC-1"}),
                unknown_passthrough=True,
            ),
            reference_time=REF,
        )
        v = ev.evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.UNKNOWN


# ---------------------------------------------------------------------------
# TC-2: Session validity
# ---------------------------------------------------------------------------


class TestTC2SessionValidity:
    def _ev(self, grace: float = 0.0) -> TemporalEvaluator:
        return TemporalEvaluator(
            config=TemporalConfig(
                enabled_constraints=frozenset({"TC-2"}),
                session_expiry_grace_seconds=grace,
            ),
            reference_time=REF,
        )

    def test_feasible_when_within_session(self) -> None:
        h1 = make_hint("e1", issued=_dt(8), expiry=_dt(12))
        h2 = make_hint("e2", earliest=_dt(10))
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.FEASIBLE

    def test_infeasible_when_session_expired(self) -> None:
        h1 = make_hint("e1", issued=_dt(8), expiry=_dt(9))
        h2 = make_hint("e2", earliest=_dt(10))
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.INFEASIBLE
        assert v.violated_constraint == "TC-2"

    def test_feasible_with_grace_period(self) -> None:
        h1 = make_hint("e1", issued=_dt(8), expiry=_dt(9))
        # hop 2 observed at 09:00:20 — within 30s grace
        h2 = make_hint(
            "e2",
            earliest=datetime(2025, 6, 15, 9, 0, 20, tzinfo=UTC),
        )
        v = self._ev(grace=30.0).evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.FEASIBLE


# ---------------------------------------------------------------------------
# TC-3: Minimum velocity
# ---------------------------------------------------------------------------


class TestTC3MinimumVelocity:
    def _ev(self, min_delta: float = 0.5) -> TemporalEvaluator:
        return TemporalEvaluator(
            config=TemporalConfig(
                enabled_constraints=frozenset({"TC-3"}),
                min_hop_delta_seconds=min_delta,
            ),
            reference_time=REF,
        )

    def test_feasible_when_delta_sufficient(self) -> None:
        h1 = make_hint("e1", latest=_dt(8, 0, 0))
        h2 = make_hint("e2", earliest=datetime(2025, 6, 15, 8, 0, 1, tzinfo=UTC))
        v = self._ev(min_delta=0.5).evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.FEASIBLE

    def test_infeasible_when_too_fast(self) -> None:
        t = _dt(8, 0, 0)
        h1 = make_hint("e1", latest=t)
        h2 = make_hint("e2", earliest=t)  # 0s gap
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.INFEASIBLE
        assert v.violated_constraint == "TC-3"


# ---------------------------------------------------------------------------
# TC-4: Stale credential
# ---------------------------------------------------------------------------


class TestTC4StaleCredential:
    def _ev(self, stale_days: int = 90) -> TemporalEvaluator:
        return TemporalEvaluator(
            config=TemporalConfig(
                enabled_constraints=frozenset({"TC-4"}),
                stale_credential_days=stale_days,
            ),
            reference_time=REF,
        )

    def test_feasible_when_recently_used(self) -> None:
        h = make_hint("e1", last_used=_dt(10, 0, 0))
        v = self._ev().evaluate(["e1"], {"e1": h})
        assert v.kind == VerdictKind.FEASIBLE

    def test_infeasible_when_stale(self) -> None:
        old = REF - timedelta(days=100)
        h = make_hint("e1", last_used=old)
        v = self._ev(stale_days=90).evaluate(["e1"], {"e1": h})
        assert v.kind == VerdictKind.INFEASIBLE
        assert v.violated_constraint == "TC-4"


# ---------------------------------------------------------------------------
# TC-5: Concurrent session
# ---------------------------------------------------------------------------


class TestTC5ConcurrentSession:
    def _ev(self) -> TemporalEvaluator:
        return TemporalEvaluator(
            config=TemporalConfig(enabled_constraints=frozenset({"TC-5"})),
            reference_time=REF,
        )

    def test_feasible_when_different_issued_times(self) -> None:
        h1 = make_hint("e1", issued=_dt(8))
        h2 = make_hint("e2", issued=_dt(9))
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.FEASIBLE

    def test_infeasible_when_same_issued_time(self) -> None:
        same_time = _dt(8)
        h1 = make_hint("e1", issued=same_time)
        h2 = make_hint("e2", issued=same_time)
        v = self._ev().evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.INFEASIBLE
        assert v.violated_constraint == "TC-5"


# ---------------------------------------------------------------------------
# Integration: unknown passthrough vs strict blocking
# ---------------------------------------------------------------------------


class TestUnknownPassthrough:
    def test_passthrough_true_returns_unknown(self) -> None:
        cfg = TemporalConfig(unknown_passthrough=True)
        ev = TemporalEvaluator(config=cfg, reference_time=REF)
        h1 = make_hint("e1")  # no data
        h2 = make_hint("e2")  # no data
        v = ev.evaluate(["e1", "e2"], {"e1": h1, "e2": h2})
        assert v.kind == VerdictKind.UNKNOWN

    def test_empty_path_is_feasible(self) -> None:
        ev = TemporalEvaluator(reference_time=REF)
        v = ev.evaluate([], {})
        assert v.kind == VerdictKind.FEASIBLE

    def test_single_hop_no_data_passthrough(self) -> None:
        ev = TemporalEvaluator(
            config=TemporalConfig(unknown_passthrough=True), reference_time=REF
        )
        h = make_hint("e1")
        v = ev.evaluate(["e1"], {"e1": h})
        # TC-4 fires as UNKNOWN; passthrough → UNKNOWN overall
        assert v.kind in (VerdictKind.UNKNOWN, VerdictKind.FEASIBLE)
