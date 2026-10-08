"""Tests for Session 13: belief decay.

Decay is opt-in via --as-of. When not provided, all behavior is identical
to pre-Session-13 (verified by existing 714 tests passing unchanged).
"""

from __future__ import annotations

import math

import pytest

from arf_rt.engine.decay import (
    apply_decay_to_increment,
    compute_decay_factor,
    _parse_iso,
)
from arf_rt.config import DECAY_HALF_LIFE_DAYS, DECAY_MIN_WEIGHT


# ===================================================================
# compute_decay_factor
# ===================================================================


class TestComputeDecayFactor:
    def test_no_as_of_returns_1(self) -> None:
        """No --as-of → no decay."""
        assert compute_decay_factor("2025-01-01T00:00:00Z", None) == 1.0

    def test_no_observed_at_returns_1(self) -> None:
        """Missing observed_at → no decay."""
        assert compute_decay_factor(None, "2025-06-01T00:00:00Z") == 1.0

    def test_both_none_returns_1(self) -> None:
        assert compute_decay_factor(None, None) == 1.0

    def test_same_day_returns_1(self) -> None:
        assert compute_decay_factor("2025-06-01T00:00:00Z", "2025-06-01T00:00:00Z") == 1.0

    def test_future_observed_at_returns_1(self) -> None:
        """observed_at after as_of → age is negative → no decay."""
        f = compute_decay_factor("2025-07-01T00:00:00Z", "2025-06-01T00:00:00Z")
        assert f == 1.0

    def test_one_half_life_returns_0_5(self) -> None:
        """After exactly one half-life (90 days), factor = 0.5."""
        # 2025-01-01 to 2025-04-01 = 90 days
        f = compute_decay_factor("2025-01-01T00:00:00Z", "2025-04-01T00:00:00Z")
        assert abs(f - 0.5) < 0.01

    def test_two_half_lives_returns_0_25(self) -> None:
        """After 180 days, factor = 0.25."""
        f = compute_decay_factor("2025-01-01T00:00:00Z", "2025-06-30T00:00:00Z")
        assert abs(f - 0.25) < 0.02

    def test_three_half_lives_returns_0_125(self) -> None:
        """After 270 days, factor ≈ 0.125."""
        f = compute_decay_factor("2025-01-01T00:00:00Z", "2025-09-28T00:00:00Z")
        assert abs(f - 0.125) < 0.02

    def test_very_old_clamps_to_min(self) -> None:
        """After many half-lives, factor clamps to DECAY_MIN_WEIGHT."""
        f = compute_decay_factor("2020-01-01T00:00:00Z", "2025-06-01T00:00:00Z")
        assert f == DECAY_MIN_WEIGHT

    def test_30_days_partial_decay(self) -> None:
        """30 days < 90 day half-life → factor > 0.5."""
        f = compute_decay_factor("2025-05-01T00:00:00Z", "2025-05-31T00:00:00Z")
        expected = math.pow(2.0, -30.0 / 90.0)
        assert abs(f - expected) < 0.001
        assert f > 0.75  # should be ~0.79

    def test_custom_half_life(self) -> None:
        """Custom half-life of 30 days."""
        f = compute_decay_factor(
            "2025-01-01T00:00:00Z",
            "2025-01-31T00:00:00Z",
            half_life_days=30.0,
        )
        assert abs(f - 0.5) < 0.02

    def test_custom_min_weight(self) -> None:
        """Custom min weight of 0.1."""
        f = compute_decay_factor(
            "2020-01-01T00:00:00Z",
            "2025-06-01T00:00:00Z",
            min_weight=0.1,
        )
        assert f == 0.1

    def test_monotonic_decay(self) -> None:
        """Older observations always have equal or lower factor."""
        ref = "2025-06-01T00:00:00Z"
        factors = []
        for month in range(1, 7):
            obs = f"2025-{month:02d}-01T00:00:00Z"
            factors.append(compute_decay_factor(obs, ref))
        # factors[0] is oldest (Jan), factors[5] is newest (Jun=same day)
        for i in range(len(factors) - 1):
            assert factors[i] <= factors[i + 1]

    def test_invalid_timestamp_returns_1(self) -> None:
        assert compute_decay_factor("not-a-date", "2025-06-01T00:00:00Z") == 1.0
        assert compute_decay_factor("2025-01-01T00:00:00Z", "bad") == 1.0


# ===================================================================
# apply_decay_to_increment
# ===================================================================


class TestApplyDecayToIncrement:
    def test_no_decay_preserves_increment(self) -> None:
        assert apply_decay_to_increment(95, None, None) == 95

    def test_no_as_of_preserves_increment(self) -> None:
        assert apply_decay_to_increment(95, "2025-01-01T00:00:00Z", None) == 95

    def test_one_half_life_halves_increment(self) -> None:
        result = apply_decay_to_increment(
            100, "2025-01-01T00:00:00Z", "2025-04-01T00:00:00Z"
        )
        assert result == 50  # 100 * 0.5

    def test_never_reduces_to_zero(self) -> None:
        """Even with extreme decay, increment stays at least 1."""
        result = apply_decay_to_increment(
            1, "2020-01-01T00:00:00Z", "2025-06-01T00:00:00Z"
        )
        assert result == 1

    def test_zero_increment_stays_zero(self) -> None:
        result = apply_decay_to_increment(
            0, "2025-01-01T00:00:00Z", "2025-04-01T00:00:00Z"
        )
        assert result == 0

    def test_large_increment_decays_proportionally(self) -> None:
        """95 * 0.5 = 47.5 → rounded to 48."""
        result = apply_decay_to_increment(
            95, "2025-01-01T00:00:00Z", "2025-04-01T00:00:00Z"
        )
        assert result == 48  # round(95 * 0.5)

    def test_recent_observation_minimal_decay(self) -> None:
        """7-day-old observation with 90-day half-life → ~95% weight."""
        result = apply_decay_to_increment(
            95, "2025-05-24T00:00:00Z", "2025-05-31T00:00:00Z"
        )
        # 95 * 2^(-7/90) ≈ 95 * 0.947 ≈ 90
        assert result >= 88
        assert result <= 92


# ===================================================================
# ISO parsing
# ===================================================================


class TestParseISO:
    def test_utc_z(self) -> None:
        dt = _parse_iso("2025-01-15T12:00:00Z")
        assert dt.year == 2025
        assert dt.month == 1

    def test_offset(self) -> None:
        dt = _parse_iso("2025-01-15T12:00:00+05:00")
        assert dt.year == 2025

    def test_no_time(self) -> None:
        dt = _parse_iso("2025-01-15")
        assert dt.year == 2025
