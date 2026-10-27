"""
arf_rt/temporal/risk_aggregator.py - Multi-hop attack path risk aggregation.

Aggregates individual credential risk scores across sequence of path edges
using bottleneck, geometric mean, and probabilistic product models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Sequence

from arf_rt.temporal.credential_scorer import CredentialRiskScore


class AggregationStrategy(str, Enum):
    BOTTLENECK = "BOTTLENECK"              # max single edge risk
    GEOMETRIC_MEAN = "GEOMETRIC_MEAN"      # geometric mean of edge risks
    PATH_PRODUCT = "PATH_PRODUCT"          # 1 - prod(1 - risk_i)
    WEIGHTED_HOP = "WEIGHTED_HOP"          # later hops weighted more heavily


@dataclass(frozen=True)
class PathRiskProfile:
    """Aggregated risk summary for a candidate attack path."""

    path_edges: tuple[str, ...]
    aggregate_score: float
    bottleneck_edge: str
    bottleneck_score: float
    strategy: AggregationStrategy
    hop_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "hop_count", len(self.path_edges))

    @property
    def label(self) -> str:
        if self.aggregate_score >= 0.80:
            return "CRITICAL"
        if self.aggregate_score >= 0.60:
            return "HIGH"
        if self.aggregate_score >= 0.35:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "path_edges": list(self.path_edges),
            "hop_count": self.hop_count,
            "aggregate_score": round(self.aggregate_score, 4),
            "label": self.label,
            "bottleneck_edge": self.bottleneck_edge,
            "bottleneck_score": round(self.bottleneck_score, 4),
            "strategy": self.strategy.value,
        }


class TemporalRiskAggregator:
    """
    Computes aggregated risk scores for multi-hop privilege escalation paths.

    Parameters
    ----------
    default_strategy:
        Strategy used when none specified in aggregation call.
    """

    def __init__(
        self,
        default_strategy: AggregationStrategy = AggregationStrategy.BOTTLENECK,
    ) -> None:
        self.default_strategy = default_strategy

    def aggregate_path(
        self,
        path: Sequence[str],
        scores_by_edge: dict[str, CredentialRiskScore | float],
        strategy: AggregationStrategy | None = None,
    ) -> PathRiskProfile:
        """
        Aggregate risk for a single path given edge-to-score mappings.
        """
        strat = strategy or self.default_strategy
        if not path:
            return PathRiskProfile(
                path_edges=(),
                aggregate_score=0.0,
                bottleneck_edge="",
                bottleneck_score=0.0,
                strategy=strat,
            )

        edge_scores: list[float] = []
        for e in path:
            val = scores_by_edge.get(e, 0.0)
            score = val.score if isinstance(val, CredentialRiskScore) else float(val)
            edge_scores.append(max(0.0, min(1.0, score)))

        # Identify bottleneck
        max_idx = max(range(len(edge_scores)), key=lambda i: edge_scores[i])
        bottleneck_edge = path[max_idx]
        bottleneck_score = edge_scores[max_idx]

        agg_score = self._compute_strategy(edge_scores, strat)

        return PathRiskProfile(
            path_edges=tuple(path),
            aggregate_score=agg_score,
            bottleneck_edge=bottleneck_edge,
            bottleneck_score=bottleneck_score,
            strategy=strat,
        )

    def rank_paths(
        self,
        paths: Sequence[Sequence[str]],
        scores_by_edge: dict[str, CredentialRiskScore | float],
        strategy: AggregationStrategy | None = None,
    ) -> list[PathRiskProfile]:
        """Aggregate and rank multiple paths in descending order of risk."""
        profiles = [
            self.aggregate_path(p, scores_by_edge, strategy=strategy)
            for p in paths
        ]
        return sorted(profiles, key=lambda p: p.aggregate_score, reverse=True)

    def _compute_strategy(
        self,
        scores: list[float],
        strategy: AggregationStrategy,
    ) -> float:
        if not scores:
            return 0.0

        if strategy == AggregationStrategy.BOTTLENECK:
            return max(scores)

        if strategy == AggregationStrategy.GEOMETRIC_MEAN:
            # Handle zeros with epsilon floor
            eps = 1e-6
            log_sum = sum(math.log(max(s, eps)) for s in scores)
            return float(math.exp(log_sum / len(scores)))

        if strategy == AggregationStrategy.PATH_PRODUCT:
            # Joint unreliability / attack success probability
            prod_safe = 1.0
            for s in scores:
                prod_safe *= (1.0 - s)
            return float(1.0 - prod_safe)

        if strategy == AggregationStrategy.WEIGHTED_HOP:
            # Later hops (target proximity) have higher weights: weight_i = i + 1
            total_w = 0.0
            weighted_s = 0.0
            for i, s in enumerate(scores):
                w = float(i + 1)
                weighted_s += w * s
                total_w += w
            return weighted_s / total_w if total_w > 0 else 0.0

        return max(scores)
