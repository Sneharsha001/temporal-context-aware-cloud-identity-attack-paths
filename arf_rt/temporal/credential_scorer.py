"""
arf_rt/temporal/credential_scorer.py - Risk scoring for temporal credential windows.

Assigns a numeric risk score (0.0 – 1.0) to each credential edge based on
its remaining validity window, staleness, and historical renewal frequency.
Higher scores indicate greater temporal exploitation risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


@dataclass
class CredentialRiskScore:
    """Risk scoring result for a single credential edge."""

    edge_id: str
    score: float                    # 0.0 (safe) – 1.0 (critical risk)
    expiry_factor: float            # contribution from remaining TTL
    staleness_factor: float         # contribution from time since last rotation
    short_lived_bonus: float        # penalty for ephemeral credentials (high churn)
    label: str = ""                 # human-readable risk tier

    def __post_init__(self) -> None:
        tiers = [
            (0.80, "CRITICAL"),
            (0.60, "HIGH"),
            (0.40, "MEDIUM"),
            (0.20, "LOW"),
            (0.0,  "MINIMAL"),
        ]
        for threshold, tier in tiers:
            if self.score >= threshold:
                self.label = tier
                break


@dataclass
class ScoringConfig:
    """Tunable weights for the credential risk scoring formula."""

    expiry_weight: float = 0.50       # weight for TTL-based component
    staleness_weight: float = 0.30    # weight for staleness component
    churn_weight: float = 0.20        # weight for short-lived/high-churn component
    reference_ttl_seconds: float = 3600.0     # 1 h — baseline "normal" TTL
    reference_stale_seconds: float = 86400.0  # 24 h — baseline "normal" rotation gap
    reference_churn_count: int = 5            # rotations/renewals that trigger max bonus


class CredentialScorer:
    """
    Scores credential edges on temporal exploitation risk.

    Parameters
    ----------
    config:
        Scoring weights and reference values. Uses defaults when omitted.
    reference_time:
        Evaluation instant. Defaults to ``datetime.now(tz=timezone.utc)``.
    """

    def __init__(
        self,
        config: ScoringConfig | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        self.config = config or ScoringConfig()
        self.reference_time = reference_time or datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, hint: TemporalHint) -> CredentialRiskScore:
        """Compute a risk score for a single :class:`TemporalHint`."""
        expiry_factor = self._expiry_factor(hint)
        staleness_factor = self._staleness_factor(hint)
        short_lived_bonus = self._churn_factor(hint)

        cfg = self.config
        raw = (
            cfg.expiry_weight * expiry_factor
            + cfg.staleness_weight * staleness_factor
            + cfg.churn_weight * short_lived_bonus
        )
        score = max(0.0, min(1.0, raw))

        return CredentialRiskScore(
            edge_id=hint.edge_id,
            score=round(score, 4),
            expiry_factor=round(expiry_factor, 4),
            staleness_factor=round(staleness_factor, 4),
            short_lived_bonus=round(short_lived_bonus, 4),
        )

    def score_all(
        self,
        hints: Sequence[TemporalHint],
    ) -> list[CredentialRiskScore]:
        """Score every hint and return results sorted by descending risk."""
        results = [self.score(h) for h in hints]
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def top_k(
        self,
        hints: Sequence[TemporalHint],
        k: int = 5,
    ) -> list[CredentialRiskScore]:
        """Return the *k* highest-risk credentials."""
        return self.score_all(hints)[:k]

    # ------------------------------------------------------------------
    # Factor calculations
    # ------------------------------------------------------------------

    def _expiry_factor(self, hint: TemporalHint) -> float:
        """
        High score when the credential expires soon relative to reference TTL.
        Returns 1.0 when already expired, 0.0 when TTL >> reference_ttl.
        """
        if hint.credential_expiry is None:
            return 0.0  # no expiry metadata → neutral

        now = self.reference_time
        # Normalise to UTC-aware if needed
        valid_until = hint.credential_expiry
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)

        remaining_seconds = (valid_until - now).total_seconds()
        if remaining_seconds <= 0:
            return 1.0  # already expired

        ref = self.config.reference_ttl_seconds
        # Sigmoid-like decay: score ≈ 1 when remaining ≈ 0, → 0 when remaining >> ref
        # Use exponential decay: f = exp(-remaining / ref)
        factor = math.exp(-remaining_seconds / ref)
        return min(1.0, factor)

    def _staleness_factor(self, hint: TemporalHint) -> float:
        """
        High score when a credential has not been rotated recently.
        Returns 1.0 when stale beyond reference_stale_seconds, 0.0 when freshly issued.
        """
        if hint.last_used is None:
            return 0.5  # unknown rotation age → medium risk

        now = self.reference_time
        last_used = hint.last_used
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)

        age_seconds = (now - last_used).total_seconds()
        if age_seconds <= 0:
            return 0.0  # freshly used

        ref = self.config.reference_stale_seconds
        # Linear ramp capped at 1.0
        factor = min(1.0, age_seconds / ref)
        return factor

    def _churn_factor(self, hint: TemporalHint) -> float:
        """
        Penalty for high-churn ephemeral credentials (many short-lived tokens).
        Uses renewal_count on the hint if available, else 0.
        """
        renewal_count = getattr(hint, "renewal_count", 0) or 0
        ref = self.config.reference_churn_count
        if ref <= 0:
            return 0.0
        factor = min(1.0, renewal_count / ref)
        return factor
