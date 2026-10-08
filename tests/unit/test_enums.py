"""Tests for ARF-RT enums — spec §5.

Verify:
  - All enums have canonical string values (str(e) == e.value)
  - Enum membership is correct
  - SEMANTICS_VERSION is pinned
"""

import pytest

from arf_rt.models.enums import (
    SEMANTICS_VERSION,
    ConfidenceBand,
    ConstraintStatus,
    ConstraintValidationStatus,
    EdgeStatus,
    ObservationResult,
    ObservationStrength,
    ObsPolarity,
    ProbeType,
    ReasonClass,
    RelationType,
    RunMode,
    WarningSeverity,
)


class TestSemanticsVersion:
    def test_pinned(self):
        assert SEMANTICS_VERSION == "1.0.0"

    def test_is_string(self):
        assert isinstance(SEMANTICS_VERSION, str)


class TestAllEnumsHaveCanonicalStringValues:
    """Every enum value must be a string, and str(e) must equal e.value."""

    @pytest.mark.parametrize("enum_cls", [
        ProbeType, ObservationStrength, ObservationResult, ReasonClass,
        EdgeStatus, ConstraintStatus, ConstraintValidationStatus,
        RelationType, ObsPolarity, RunMode, WarningSeverity, ConfidenceBand,
    ])
    def test_str_equals_value(self, enum_cls):
        for member in enum_cls:
            assert isinstance(member.value, str), f"{enum_cls.__name__}.{member.name} value is not str"
            assert str(member) == member.value, f"str({enum_cls.__name__}.{member.name}) != value"


class TestProbeType:
    def test_members(self):
        assert set(ProbeType) == {ProbeType.REPLAY_SCRIPTED, ProbeType.WHATIF_FORCED}


class TestObservationStrength:
    def test_members(self):
        assert set(ObservationStrength) == {
            ObservationStrength.DETERMINISTIC,
            ObservationStrength.DIRECT,
            ObservationStrength.INFERRED,
            ObservationStrength.HEURISTIC,
        }


class TestObservationResult:
    def test_members(self):
        assert set(ObservationResult) == {
            ObservationResult.ALLOW,
            ObservationResult.DENY,
            ObservationResult.ERROR,
            ObservationResult.INCONCLUSIVE,
        }


class TestReasonClass:
    def test_members(self):
        assert set(ReasonClass) == {
            ReasonClass.CONSTRAINT_DENY,
            ReasonClass.MISSING_PERMISSION,
            ReasonClass.CONDITION_MISMATCH,
            ReasonClass.TRANSIENT,
            ReasonClass.THROTTLED,
            ReasonClass.UNKNOWN,
        }


class TestEdgeStatus:
    def test_members(self):
        assert set(EdgeStatus) == {
            EdgeStatus.HYPOTHESIZED,
            EdgeStatus.CONFIRMED,
            EdgeStatus.REFUTED,
            EdgeStatus.UNKNOWN_CONDITION,
        }


class TestConstraintStatus:
    def test_members(self):
        assert set(ConstraintStatus) == {
            ConstraintStatus.ACTIVE,
            ConstraintStatus.INVALIDATED,
        }


class TestConstraintValidationStatus:
    def test_members(self):
        assert set(ConstraintValidationStatus) == {
            ConstraintValidationStatus.UNVALIDATED,
            ConstraintValidationStatus.VALIDATED,
            ConstraintValidationStatus.ASSUMED,
        }

    def test_assumed_is_not_validated(self):
        """Spec §13.3: ASSUMED counts as unvalidated for CONSTRAINT_UNVALIDATED."""
        assert ConstraintValidationStatus.ASSUMED != ConstraintValidationStatus.VALIDATED


class TestObsPolarity:
    def test_members(self):
        assert set(ObsPolarity) == {
            ObsPolarity.SUPPORT,
            ObsPolarity.AGAINST,
            ObsPolarity.NEUTRAL,
        }


class TestEnumStringUsability:
    """Enums must work as dict keys, in f-strings, and in JSON."""

    def test_dict_key(self):
        d = {ProbeType.REPLAY_SCRIPTED: 1}
        assert d["REPLAY_SCRIPTED"] == 1

    def test_fstring(self):
        assert f"type={ProbeType.REPLAY_SCRIPTED}" == "type=REPLAY_SCRIPTED"

    def test_equality_with_string(self):
        assert ProbeType.REPLAY_SCRIPTED == "REPLAY_SCRIPTED"

    def test_in_string_comparison(self):
        assert EdgeStatus.CONFIRMED == "CONFIRMED"
