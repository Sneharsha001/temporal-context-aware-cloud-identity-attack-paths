"""
tests/unit/test_temporal_hints.py - Unit tests for arf_rt.temporal.hints.

Covers TemporalHint construction, predicate methods, and edge cases with
missing data (None fields).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint


UTC = timezone.utc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    """Create a UTC datetime on a fixed reference date."""
    return datetime(2025, 6, 15, hour, minute, second, tzinfo=UTC)


@pytest.fixture
def full_hint() -> TemporalHint:
    """A TemporalHint with all fields populated."""
    issued = _dt(10, 0, 0)
    expiry = issued + timedelta(hours=1)
    return TemporalHint(
        edge_id="e1",
        earliest_observed=_dt(10, 5, 0),
        latest_observed=_dt(10, 10, 0),
        credential_issued=issued,
        credential_expiry=expiry,
        last_used=_dt(10, 0, 0),
    )


@pytest.fixture
def empty_hint() -> TemporalHint:
    """A TemporalHint with no timestamp data (all None)."""
    return TemporalHint(edge_id="e_empty")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestTemporalHintConstruction:
    def test_default_fields_are_none(self, empty_hint: TemporalHint) -> None:
        assert empty_hint.earliest_observed is None
        assert empty_hint.latest_observed is None
        assert empty_hint.credential_issued is None
        assert empty_hint.credential_expiry is None
        assert empty_hint.last_used is None

    def test_edge_id_stored(self, full_hint: TemporalHint) -> None:
        assert full_hint.edge_id == "e1"

    def test_immutable(self, full_hint: TemporalHint) -> None:
        with pytest.raises((AttributeError, TypeError)):
            full_hint.edge_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# has_observation_window
# ---------------------------------------------------------------------------


class TestHasObservationWindow:
    def test_true_when_both_present(self, full_hint: TemporalHint) -> None:
        assert full_hint.has_observation_window() is True

    def test_false_when_earliest_missing(self) -> None:
        h = TemporalHint(latest_observed=_dt(10))
        assert h.has_observation_window() is False

    def test_false_when_latest_missing(self) -> None:
        h = TemporalHint(earliest_observed=_dt(10))
        assert h.has_observation_window() is False

    def test_false_when_both_missing(self, empty_hint: TemporalHint) -> None:
        assert empty_hint.has_observation_window() is False


# ---------------------------------------------------------------------------
# has_credential_lifetime
# ---------------------------------------------------------------------------


class TestHasCredentialLifetime:
    def test_true_when_both_present(self, full_hint: TemporalHint) -> None:
        assert full_hint.has_credential_lifetime() is True

    def test_false_when_issued_missing(self) -> None:
        h = TemporalHint(credential_expiry=_dt(11))
        assert h.has_credential_lifetime() is False

    def test_false_when_expiry_missing(self) -> None:
        h = TemporalHint(credential_issued=_dt(10))
        assert h.has_credential_lifetime() is False


# ---------------------------------------------------------------------------
# session_duration_seconds
# ---------------------------------------------------------------------------


class TestSessionDurationSeconds:
    def test_returns_correct_duration(self, full_hint: TemporalHint) -> None:
        # issued at 10:00, expiry at 11:00 = 3600s
        assert full_hint.session_duration_seconds() == pytest.approx(3600.0)

    def test_returns_none_when_incomplete(self, empty_hint: TemporalHint) -> None:
        assert empty_hint.session_duration_seconds() is None


# ---------------------------------------------------------------------------
# is_expired_at
# ---------------------------------------------------------------------------


class TestIsExpiredAt:
    def test_not_expired_before_expiry(self, full_hint: TemporalHint) -> None:
        # Reference is 10:30 — expiry is 11:00
        ref = _dt(10, 30, 0)
        assert full_hint.is_expired_at(ref) is False

    def test_expired_at_expiry_time(self, full_hint: TemporalHint) -> None:
        # Reference equals expiry timestamp
        assert full_hint.is_expired_at(full_hint.credential_expiry) is True  # type: ignore[arg-type]

    def test_expired_after_expiry(self, full_hint: TemporalHint) -> None:
        ref = _dt(12, 0, 0)
        assert full_hint.is_expired_at(ref) is True

    def test_returns_none_when_no_lifetime(self, empty_hint: TemporalHint) -> None:
        assert empty_hint.is_expired_at(_dt(12)) is None


# ---------------------------------------------------------------------------
# days_since_last_use
# ---------------------------------------------------------------------------


class TestDaysSinceLastUse:
    def test_zero_when_same_time(self, full_hint: TemporalHint) -> None:
        # last_used is _dt(10,0,0) — reference is also _dt(10,0,0)
        assert full_hint.days_since_last_use(_dt(10, 0, 0)) == pytest.approx(0.0)

    def test_one_day(self, full_hint: TemporalHint) -> None:
        ref = _dt(10, 0, 0) + timedelta(days=1)
        assert full_hint.days_since_last_use(ref) == pytest.approx(1.0)

    def test_ninety_days(self, full_hint: TemporalHint) -> None:
        ref = _dt(10, 0, 0) + timedelta(days=90)
        assert full_hint.days_since_last_use(ref) == pytest.approx(90.0)

    def test_returns_none_when_last_used_missing(
        self, empty_hint: TemporalHint
    ) -> None:
        assert empty_hint.days_since_last_use(_dt(12)) is None


# ---------------------------------------------------------------------------
# Serialization (to_dict / from_dict)
# ---------------------------------------------------------------------------


class TestTemporalHintSerialization:
    def test_roundtrip_full_hint(self, full_hint: TemporalHint) -> None:
        d = full_hint.to_dict()
        assert d["edge_id"] == "e1"
        assert d["earliest_observed"] is not None
        assert d["credential_expiry"] is not None
        reconstructed = TemporalHint.from_dict(d)
        assert reconstructed == full_hint

    def test_roundtrip_empty_hint(self, empty_hint: TemporalHint) -> None:
        d = empty_hint.to_dict()
        assert d["edge_id"] == "e_empty"
        assert d["earliest_observed"] is None
        reconstructed = TemporalHint.from_dict(d)
        assert reconstructed == empty_hint

    def test_from_dict_handles_z_suffix(self) -> None:
        payload = {
            "edge_id": "role_assume",
            "earliest_observed": "2025-06-15T10:00:00Z",
            "credential_expiry": "2025-06-15T11:00:00Z",
        }
        hint = TemporalHint.from_dict(payload)
        assert hint.edge_id == "role_assume"
        assert hint.earliest_observed == _dt(10, 0, 0)
        assert hint.credential_expiry == _dt(11, 0, 0)
        assert hint.last_used is None

    def test_from_dict_preserves_existing_datetime_objects(self) -> None:
        now = _dt(12, 0, 0)
        payload = {"edge_id": "e_dt", "last_used": now}
        hint = TemporalHint.from_dict(payload)
        assert hint.last_used == now

