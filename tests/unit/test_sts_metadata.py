"""
tests/unit/test_sts_metadata.py - Unit tests for arf_rt.temporal.sts_metadata.

Covers SessionSpec construction, validity checks, expiry computation,
effective-duration logic, and causal chain validation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.sts_metadata import (
    SessionSpec,
    compute_effective_max_duration,
    infer_expiry_from_cloudtrail,
    validate_path_session_chain,
)

UTC = timezone.utc


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2025, 6, 15, hour, minute, second, tzinfo=UTC)


# ---------------------------------------------------------------------------
# SessionSpec
# ---------------------------------------------------------------------------


class TestSessionSpec:
    def test_expiry_computed_correctly(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.expiry == _dt(11)

    def test_is_valid_at_midpoint(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.is_valid_at(_dt(10, 30)) is True

    def test_not_valid_at_expiry(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.is_valid_at(_dt(11)) is False

    def test_not_valid_before_issued(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.is_valid_at(_dt(9)) is False

    def test_remaining_seconds_positive(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.remaining_seconds(_dt(10, 30)) == pytest.approx(1800.0)

    def test_remaining_seconds_negative_when_expired(self) -> None:
        spec = SessionSpec(duration_seconds=3600, issued_at=_dt(10))
        assert spec.remaining_seconds(_dt(12)) < 0

    def test_raises_on_too_short_duration(self) -> None:
        with pytest.raises(ValueError, match="bounds"):
            SessionSpec(duration_seconds=100, issued_at=_dt(10))

    def test_raises_on_too_long_duration(self) -> None:
        with pytest.raises(ValueError, match="bounds"):
            SessionSpec(duration_seconds=99_999, issued_at=_dt(10))

    def test_minimum_duration_is_valid(self) -> None:
        spec = SessionSpec(duration_seconds=900, issued_at=_dt(10))
        assert spec.duration_seconds == 900

    def test_maximum_duration_is_valid(self) -> None:
        spec = SessionSpec(duration_seconds=43_200, issued_at=_dt(10))
        assert spec.duration_seconds == 43_200


# ---------------------------------------------------------------------------
# compute_effective_max_duration
# ---------------------------------------------------------------------------


class TestComputeEffectiveMaxDuration:
    def test_returns_min_of_role_and_requested(self) -> None:
        assert compute_effective_max_duration(3600, 7200) == 3600
        assert compute_effective_max_duration(7200, 3600) == 3600

    def test_equal_values_returned_unchanged(self) -> None:
        assert compute_effective_max_duration(3600, 3600) == 3600

    def test_raises_on_out_of_bounds_role(self) -> None:
        with pytest.raises(ValueError):
            compute_effective_max_duration(100, 3600)

    def test_raises_on_out_of_bounds_requested(self) -> None:
        with pytest.raises(ValueError):
            compute_effective_max_duration(3600, 100)


# ---------------------------------------------------------------------------
# infer_expiry_from_cloudtrail
# ---------------------------------------------------------------------------


class TestInferExpiryFromCloudtrail:
    def test_uses_response_expiration_when_present(self) -> None:
        event_time = _dt(10)
        expiry = _dt(11)
        assert infer_expiry_from_cloudtrail(event_time, expiry) == expiry

    def test_falls_back_to_role_max_when_none(self) -> None:
        event_time = _dt(10)
        result = infer_expiry_from_cloudtrail(event_time, None, role_max_duration_seconds=3600)
        assert result == _dt(11)

    def test_fallback_uses_custom_role_max(self) -> None:
        event_time = _dt(10)
        result = infer_expiry_from_cloudtrail(event_time, None, role_max_duration_seconds=1800)
        assert result == _dt(10, 30)


# ---------------------------------------------------------------------------
# validate_path_session_chain
# ---------------------------------------------------------------------------


class TestValidatePathSessionChain:
    def _make(self, issued_hour: int, duration: int = 3600) -> SessionSpec:
        return SessionSpec(duration_seconds=duration, issued_at=_dt(issued_hour))

    def test_valid_chain_returns_no_violations(self) -> None:
        # Session 0: issued at 8, expires at 9
        # Session 1: issued at 8:30 (while session 0 still valid)
        chain = [self._make(8), self._make(8)]
        chain[1] = SessionSpec(duration_seconds=3600, issued_at=_dt(8, 30))
        violations = validate_path_session_chain(chain)
        assert violations == []

    def test_broken_chain_returns_violation(self) -> None:
        # Session 0: issued at 8, expires at 9
        # Session 1: issued at 10 (after session 0 expired, no grace)
        chain = [self._make(8), self._make(10)]
        violations = validate_path_session_chain(chain, grace_seconds=0.0)
        assert len(violations) == 1
        assert "expired" in violations[0].lower() or "session" in violations[0].lower()

    def test_grace_period_saves_borderline_chain(self) -> None:
        # Session 0 expires at 9:00:00; Session 1 issued at 9:00:20 (within 30s)
        s0 = SessionSpec(duration_seconds=3600, issued_at=_dt(8))
        s1 = SessionSpec(
            duration_seconds=3600,
            issued_at=datetime(2025, 6, 15, 9, 0, 20, tzinfo=UTC),
        )
        violations = validate_path_session_chain([s0, s1], grace_seconds=30.0)
        assert violations == []

    def test_single_session_is_valid(self) -> None:
        assert validate_path_session_chain([self._make(8)]) == []

    def test_empty_chain_is_valid(self) -> None:
        assert validate_path_session_chain([]) == []
