"""
tests/unit/test_temporal_risk_aggregator.py - Tests for TemporalRiskAggregator.
"""

from __future__ import annotations

import math
import pytest

from arf_rt.temporal.risk_aggregator import (
    AggregationStrategy,
    PathRiskProfile,
    TemporalRiskAggregator,
)
from arf_rt.temporal.credential_scorer import CredentialRiskScore


class TestTemporalRiskAggregator:
    def test_empty_path(self) -> None:
        agg = TemporalRiskAggregator()
        profile = agg.aggregate_path([], {})
        assert profile.aggregate_score == 0.0
        assert profile.hop_count == 0
        assert profile.bottleneck_edge == ""
        assert profile.label == "LOW"

    def test_bottleneck_strategy(self) -> None:
        agg = TemporalRiskAggregator(default_strategy=AggregationStrategy.BOTTLENECK)
        path = ["edge1", "edge2", "edge3"]
        scores = {"edge1": 0.20, "edge2": 0.85, "edge3": 0.40}
        profile = agg.aggregate_path(path, scores)
        assert profile.aggregate_score == 0.85
        assert profile.bottleneck_edge == "edge2"
        assert profile.bottleneck_score == 0.85
        assert profile.label == "CRITICAL"
        assert profile.hop_count == 3

    def test_path_product_strategy(self) -> None:
        agg = TemporalRiskAggregator()
        path = ["e1", "e2"]
        scores = {"e1": 0.50, "e2": 0.50}
        # 1 - (1 - 0.5)*(1 - 0.5) = 1 - 0.25 = 0.75
        profile = agg.aggregate_path(path, scores, strategy=AggregationStrategy.PATH_PRODUCT)
        assert pytest.approx(profile.aggregate_score, 0.001) == 0.75
        assert profile.label == "HIGH"

    def test_geometric_mean_strategy(self) -> None:
        agg = TemporalRiskAggregator()
        path = ["e1", "e2"]
        scores = {"e1": 0.25, "e2": 1.00}
        # sqrt(0.25 * 1.00) = 0.50
        profile = agg.aggregate_path(path, scores, strategy=AggregationStrategy.GEOMETRIC_MEAN)
        assert pytest.approx(profile.aggregate_score, 0.001) == 0.50
        assert profile.label == "MEDIUM"

    def test_weighted_hop_strategy(self) -> None:
        agg = TemporalRiskAggregator()
        path = ["e1", "e2"]
        scores = {"e1": 0.10, "e2": 0.70}
        # weights: e1: 1, e2: 2. Sum = (1*0.10 + 2*0.70) / 3 = 1.50 / 3 = 0.50
        profile = agg.aggregate_path(path, scores, strategy=AggregationStrategy.WEIGHTED_HOP)
        assert pytest.approx(profile.aggregate_score, 0.001) == 0.50

    def test_with_credential_risk_score_instances(self) -> None:
        agg = TemporalRiskAggregator()
        score_obj = CredentialRiskScore(
            edge_id="e_obj",
            score=0.92,
            expiry_factor=0.95,
            staleness_factor=0.80,
            short_lived_bonus=0.10,
        )
        profile = agg.aggregate_path(["e_obj"], {"e_obj": score_obj})
        assert profile.aggregate_score == 0.92
        assert profile.bottleneck_edge == "e_obj"
        assert profile.label == "CRITICAL"

    def test_rank_paths(self) -> None:
        agg = TemporalRiskAggregator()
        paths = [
            ["a", "b"],
            ["c", "d"],
            ["e"],
        ]
        scores = {
            "a": 0.10, "b": 0.20,
            "c": 0.90, "d": 0.30,
            "e": 0.60,
        }
        ranked = agg.rank_paths(paths, scores)
        assert len(ranked) == 3
        # Path ["c", "d"] has bottleneck 0.90 -> rank 1
        assert ranked[0].path_edges == ("c", "d")
        # Path ["e"] has bottleneck 0.60 -> rank 2
        assert ranked[1].path_edges == ("e",)
        # Path ["a", "b"] has bottleneck 0.20 -> rank 3
        assert ranked[2].path_edges == ("a", "b")

    def test_to_dict_roundtrip(self) -> None:
        agg = TemporalRiskAggregator()
        profile = agg.aggregate_path(["x", "y"], {"x": 0.3, "y": 0.7})
        d = profile.to_dict()
        assert d["path_edges"] == ["x", "y"]
        assert d["hop_count"] == 2
        assert d["aggregate_score"] == 0.7
        assert d["bottleneck_edge"] == "y"
        assert d["label"] == "HIGH"
