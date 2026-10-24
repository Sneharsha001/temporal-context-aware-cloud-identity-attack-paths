"""
tests/unit/test_credential_scorer.py - Unit tests for CredentialScorer.

Validates risk score computation, tier labelling, factor decomposition,
and edge-case handling for missing hint metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.credential_scorer import (
    CredentialRiskScore,
    CredentialScorer,
    ScoringConfig,
)
from arf_rt.temporal.hints import TemporalHint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def _scorer(**kwargs) -> CredentialScorer:
    cfg = ScoringConfig(**kwargs) if kwargs else None
    return CredentialScorer(config=cfg, reference_time=NOW)


def _hint(
    edge_id: str = "edge-1",
    expiry_offset_seconds: float | None = None,
    last_used_offset_seconds: float | None = None,
) -> TemporalHint:
    """Build a TemporalHint relative to NOW."""
    credential_expiry = (
        NOW + timedelta(seconds=expiry_offset_seconds)
        if expiry_offset_seconds is not None
        else None
    )
    last_used = (
        NOW - timedelta(seconds=abs(last_used_offset_seconds))
        if last_used_offset_seconds is not None
        else None
    )
    return TemporalHint(
        edge_id=edge_id,
        credential_expiry=credential_expiry,
        last_used=last_used,
    )


# ---------------------------------------------------------------------------
# CredentialRiskScore - tier labelling
# ---------------------------------------------------------------------------

class TestRiskScoreLabelling:
    def test_critical_label(self):
        r = CredentialRiskScore("e", 0.90, 0.9, 0.9, 0.9)
        assert r.label == "CRITICAL"

    def test_high_label(self):
        r = CredentialRiskScore("e", 0.65, 0.65, 0.65, 0.65)
        assert r.label == "HIGH"

    def test_medium_label(self):
        r = CredentialRiskScore("e", 0.45, 0.45, 0.45, 0.45)
        assert r.label == "MEDIUM"

    def test_low_label(self):
        r = CredentialRiskScore("e", 0.25, 0.25, 0.25, 0.25)
        assert r.label == "LOW"

    def test_minimal_label(self):
        r = CredentialRiskScore("e", 0.05, 0.05, 0.05, 0.05)
        assert r.label == "MINIMAL"

    def test_boundary_critical(self):
        r = CredentialRiskScore("e", 0.80, 0.8, 0.8, 0.8)
        assert r.label == "CRITICAL"


# ---------------------------------------------------------------------------
# CredentialScorer - expiry factor
# ---------------------------------------------------------------------------

class TestExpiryFactor:
    def test_already_expired_returns_one(self):
        scorer = _scorer()
        hint = _hint(expiry_offset_seconds=-600)  # expired 10 min ago
        result = scorer.score(hint)
        assert result.expiry_factor == 1.0

    def test_no_expiry_metadata_returns_zero(self):
        scorer = _scorer()
        hint = _hint(expiry_offset_seconds=None)
        result = scorer.score(hint)
        assert result.expiry_factor == 0.0

    def test_long_ttl_low_expiry_factor(self):
        scorer = _scorer(reference_ttl_seconds=3600.0)
        hint = _hint(expiry_offset_seconds=36000)  # 10x the reference
        result = scorer.score(hint)
        assert result.expiry_factor < 0.05

    def test_short_ttl_high_expiry_factor(self):
        scorer = _scorer(reference_ttl_seconds=3600.0)
        hint = _hint(expiry_offset_seconds=300)  # 5 min remaining
        result = scorer.score(hint)
        assert result.expiry_factor > 0.90


# ---------------------------------------------------------------------------
# CredentialScorer - staleness factor
# ---------------------------------------------------------------------------

class TestStalenessFactor:
    def test_no_last_used_returns_medium(self):
        scorer = _scorer()
        hint = _hint(last_used_offset_seconds=None)
        result = scorer.score(hint)
        assert result.staleness_factor == 0.5

    def test_fresh_credential_low_staleness(self):
        scorer = _scorer(reference_stale_seconds=86400.0)
        hint = _hint(last_used_offset_seconds=60)   # used 1 min ago
        result = scorer.score(hint)
        assert result.staleness_factor < 0.01

    def test_very_stale_returns_one(self):
        scorer = _scorer(reference_stale_seconds=3600.0)
        hint = _hint(last_used_offset_seconds=7200)  # 2× reference
        result = scorer.score(hint)
        assert result.staleness_factor == 1.0

    def test_half_reference_returns_half(self):
        scorer = _scorer(reference_stale_seconds=3600.0)
        hint = _hint(last_used_offset_seconds=1800)  # exactly ½ reference
        result = scorer.score(hint)
        assert abs(result.staleness_factor - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# CredentialScorer - churn factor
# ---------------------------------------------------------------------------

class TestChurnFactor:
    def test_no_renewal_count_returns_zero(self):
        """TemporalHint has no renewal_count field; scorer should default to 0."""
        scorer = _scorer()
        hint = _hint()
        result = scorer.score(hint)
        assert result.short_lived_bonus == 0.0

    def test_zero_churn_weight_no_bonus(self):
        scorer = _scorer(churn_weight=0.0)
        hint = _hint(expiry_offset_seconds=100)
        result = scorer.score(hint)
        assert result.short_lived_bonus == 0.0

    def test_churn_weight_does_not_exceed_composite_cap(self):
        """Even with full churn weight, composite score stays <= 1.0."""
        scorer = _scorer(churn_weight=1.0, expiry_weight=0.0, staleness_weight=0.0)
        hint = _hint()
        result = scorer.score(hint)
        assert result.score <= 1.0

    def test_reference_churn_zero_returns_zero_factor(self):
        scorer = _scorer(reference_churn_count=0)
        hint = _hint()
        result = scorer.score(hint)
        assert result.short_lived_bonus == 0.0


# ---------------------------------------------------------------------------
# CredentialScorer - composite scoring
# ---------------------------------------------------------------------------

class TestCompositeScoring:
    def test_score_in_unit_interval(self):
        scorer = _scorer()
        hint = _hint(expiry_offset_seconds=1800, last_used_offset_seconds=43200)
        result = scorer.score(hint)
        assert 0.0 <= result.score <= 1.0

    def test_worst_case_approaches_one(self):
        scorer = _scorer(reference_ttl_seconds=3600.0, reference_stale_seconds=3600.0)
        hint = _hint(expiry_offset_seconds=-1, last_used_offset_seconds=7200)
        result = scorer.score(hint)
        assert result.score > 0.7

    def test_best_case_approaches_zero(self):
        scorer = _scorer(reference_ttl_seconds=3600.0, reference_stale_seconds=3600.0)
        hint = _hint(expiry_offset_seconds=36000, last_used_offset_seconds=60)
        result = scorer.score(hint)
        assert result.score < 0.15

    def test_edge_id_preserved(self):
        scorer = _scorer()
        hint = _hint(edge_id="my-special-edge")
        result = scorer.score(hint)
        assert result.edge_id == "my-special-edge"

    def test_score_rounded_to_four_decimals(self):
        scorer = _scorer()
        hint = _hint(expiry_offset_seconds=500)
        result = scorer.score(hint)
        assert result.score == round(result.score, 4)


# ---------------------------------------------------------------------------
# CredentialScorer - score_all and top_k
# ---------------------------------------------------------------------------

class TestScoreAllAndTopK:
    def _hints(self) -> list[TemporalHint]:
        return [
            _hint("low-risk", expiry_offset_seconds=36000, last_used_offset_seconds=10),
            _hint("high-risk", expiry_offset_seconds=-1, last_used_offset_seconds=7200),
            _hint("mid-risk", expiry_offset_seconds=1800, last_used_offset_seconds=1800),
        ]

    def test_score_all_sorted_descending(self):
        scorer = _scorer()
        results = scorer.score_all(self._hints())
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_returns_k_items(self):
        scorer = _scorer()
        results = scorer.top_k(self._hints(), k=2)
        assert len(results) == 2

    def test_top_k_has_highest_scores(self):
        scorer = _scorer()
        all_results = scorer.score_all(self._hints())
        top2 = scorer.top_k(self._hints(), k=2)
        assert top2[0].edge_id == all_results[0].edge_id
        assert top2[1].edge_id == all_results[1].edge_id

    def test_top_k_larger_than_list(self):
        scorer = _scorer()
        results = scorer.top_k(self._hints(), k=100)
        assert len(results) == 3
