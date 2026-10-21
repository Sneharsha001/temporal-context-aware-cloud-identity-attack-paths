"""
tests/unit/test_temporal_verdict.py - Unit tests for arf_rt.temporal.verdict.

Verifies TemporalVerdict construction via convenience factories, predicate
methods, and immutability.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


class TestVerdictKind:
    def test_three_variants_exist(self) -> None:
        assert hasattr(VerdictKind, "FEASIBLE")
        assert hasattr(VerdictKind, "INFEASIBLE")
        assert hasattr(VerdictKind, "UNKNOWN")


class TestTemporalVerdictFeasible:
    def test_kind_is_feasible(self) -> None:
        v = TemporalVerdict.feasible()
        assert v.kind == VerdictKind.FEASIBLE

    def test_is_feasible_predicate(self) -> None:
        assert TemporalVerdict.feasible().is_feasible() is True

    def test_is_infeasible_is_false(self) -> None:
        assert TemporalVerdict.feasible().is_infeasible() is False

    def test_is_unknown_is_false(self) -> None:
        assert TemporalVerdict.feasible().is_unknown() is False

    def test_no_violated_constraint(self) -> None:
        assert TemporalVerdict.feasible().violated_constraint is None

    def test_no_missing_data(self) -> None:
        assert len(TemporalVerdict.feasible().missing_data_constraints) == 0


class TestTemporalVerdictInfeasible:
    def test_kind_is_infeasible(self) -> None:
        v = TemporalVerdict.infeasible("TC-1", "causal order violated")
        assert v.kind == VerdictKind.INFEASIBLE

    def test_violated_constraint_stored(self) -> None:
        v = TemporalVerdict.infeasible("TC-3", "too fast")
        assert v.violated_constraint == "TC-3"

    def test_reason_stored(self) -> None:
        v = TemporalVerdict.infeasible("TC-2", "session expired")
        assert "session expired" in v.reason

    def test_is_infeasible_predicate(self) -> None:
        assert TemporalVerdict.infeasible("TC-4", "stale").is_infeasible() is True

    def test_is_feasible_is_false(self) -> None:
        assert TemporalVerdict.infeasible("TC-1", "x").is_feasible() is False


class TestTemporalVerdictUnknown:
    def test_kind_is_unknown(self) -> None:
        v = TemporalVerdict.unknown(frozenset({"TC-1"}))
        assert v.kind == VerdictKind.UNKNOWN

    def test_missing_constraints_stored(self) -> None:
        missing = frozenset({"TC-1", "TC-4"})
        v = TemporalVerdict.unknown(missing)
        assert v.missing_data_constraints == missing

    def test_is_unknown_predicate(self) -> None:
        assert TemporalVerdict.unknown(frozenset({"TC-3"})).is_unknown() is True

    def test_reason_contains_constraint_ids(self) -> None:
        v = TemporalVerdict.unknown(frozenset({"TC-2", "TC-5"}))
        assert "TC-2" in v.reason
        assert "TC-5" in v.reason

    def test_immutable(self) -> None:
        v = TemporalVerdict.feasible()
        with pytest.raises((AttributeError, TypeError)):
            v.kind = VerdictKind.INFEASIBLE  # type: ignore[misc]
