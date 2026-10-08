"""Tests for Session 14: probe planner (Expected Information Gain).

Validates that the planner:
  1. Correctly computes entropy on normalized Top-K weights
  2. Prunes candidates using Top-K paths AND correlation components
  3. Simulates ALLOW/DENY outcomes via full pipeline fork
  4. Understands correlation: edges not on Top-K but in same component matter
  5. Detects when probing can flip the representative
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.planner import entropy_from_weights
from arf_rt.engine.planner import plan_probes
from scripts.generate_fixture import generate_scenario


FIXTURES = Path(__file__).parent.parent / "fixtures"


# ===================================================================
# Entropy computation
# ===================================================================


class TestEntropy:
    def test_empty_returns_zero(self) -> None:
        assert entropy_from_weights([], include_null=False) == 0.0

    def test_all_zero_returns_zero(self) -> None:
        assert entropy_from_weights([0, 0, 0], include_null=False) == 0.0

    def test_single_path_zero_entropy(self) -> None:
        """One path with all the mass → zero entropy (no uncertainty)."""
        assert entropy_from_weights([100], include_null=False) == 0.0

    def test_two_equal_paths(self) -> None:
        """Two equal paths → ln(2) ≈ 0.693."""
        h = entropy_from_weights([50, 50], include_null=False)
        assert abs(h - math.log(2)) < 0.001

    def test_three_equal_paths(self) -> None:
        """Three equal paths → ln(3) ≈ 1.099."""
        h = entropy_from_weights([100, 100, 100], include_null=False)
        assert abs(h - math.log(3)) < 0.001

    def test_concentrated_low_entropy(self) -> None:
        """One dominant path → low entropy."""
        h = entropy_from_weights([1000, 1, 1], include_null=False)
        assert h < 0.1

    def test_uniform_max_entropy(self) -> None:
        """Uniform distribution → maximum entropy for n paths."""
        n = 5
        h = entropy_from_weights([100] * n, include_null=False)
        assert abs(h - math.log(n)) < 0.001

    def test_entropy_non_negative(self) -> None:
        """Entropy is always non-negative."""
        for weights in [[1], [1, 2], [1, 2, 3], [100, 1], [1, 1, 1, 1]]:
            assert entropy_from_weights(weights, include_null=False) >= 0.0

    def test_scale_invariant(self) -> None:
        """Entropy doesn't change with uniform scaling of weights."""
        h1 = entropy_from_weights([10, 20, 30], include_null=False)
        h2 = entropy_from_weights([100, 200, 300], include_null=False)
        assert abs(h1 - h2) < 0.001

    # --- Null complement tests ---

    def test_null_complement_high_probability_low_entropy(self) -> None:
        """One path at 90% of Q8 → most mass on path → low entropy."""
        from arf_rt.config import Q8
        h = entropy_from_weights([int(Q8 * 0.9)], include_null=True)
        # Almost all mass on path, tiny null → low entropy
        assert h < 0.5

    def test_null_complement_low_probability_low_entropy(self) -> None:
        """Paths at 1% of Q8 → most mass on null → low entropy."""
        from arf_rt.config import Q8
        h = entropy_from_weights([int(Q8 * 0.01)], include_null=True)
        # Almost all mass on null → low entropy
        assert h < 0.15

    def test_null_complement_50_50_max_entropy(self) -> None:
        """One path at 50% → balanced with null → ln(2)."""
        from arf_rt.config import Q8
        h = entropy_from_weights([Q8 // 2], include_null=True)
        assert abs(h - math.log(2)) < 0.01

    def test_null_complement_decreases_entropy_when_paths_weaken(self) -> None:
        """When all paths have LOW probability, null dominates → low entropy.
        This is the key property: reducing path viability = less uncertainty."""
        from arf_rt.config import Q8
        h_strong = entropy_from_weights([int(Q8 * 0.3), int(Q8 * 0.2)], include_null=True)
        h_weak = entropy_from_weights([int(Q8 * 0.01), int(Q8 * 0.01)], include_null=True)
        assert h_weak < h_strong


def _assert_plan_equivalent(full: dict, optimized: dict) -> None:
    assert optimized["baseline_entropy"] == pytest.approx(full["baseline_entropy"], abs=1e-12)
    assert optimized["top_recommendation"]["edge_id"] == full["top_recommendation"]["edge_id"]
    assert optimized["top_recommendation"]["eig"] == pytest.approx(
        full["top_recommendation"]["eig"], abs=1e-12
    )
    assert optimized["top_recommendation"]["reasons"] == full["top_recommendation"]["reasons"]

    assert optimized["stats"]["total_edges"] == full["stats"]["total_edges"]
    assert optimized["stats"]["candidate_edges"] == full["stats"]["candidate_edges"]
    assert optimized["stats"]["forks_executed"] == full["stats"]["forks_executed"]

    full_candidates = full["candidates"]
    opt_candidates = optimized["candidates"]
    assert [c["edge_id"] for c in opt_candidates] == [c["edge_id"] for c in full_candidates]
    for opt, expected in zip(opt_candidates, full_candidates):
        assert opt["eig"] == pytest.approx(expected["eig"], abs=1e-12)
        assert opt["h_allow"] == pytest.approx(expected["h_allow"], abs=1e-12)
        assert opt["h_deny"] == pytest.approx(expected["h_deny"], abs=1e-12)
        assert opt["p_edge"] == pytest.approx(expected["p_edge"], abs=1e-12)
        assert opt["paths_allow"] == expected["paths_allow"]
        assert opt["paths_deny"] == expected["paths_deny"]
        assert opt["reasons"] == expected["reasons"]
        assert opt["on_topk"] == expected["on_topk"]
        assert opt["in_component"] == expected["in_component"]

    assert len(optimized["component_summary"]) == len(full["component_summary"])
    for opt, expected in zip(optimized["component_summary"], full["component_summary"]):
        assert opt["component_sig"] == expected["component_sig"]
        assert opt["component_label"] == expected["component_label"]
        assert opt["edge_count"] == expected["edge_count"]
        assert opt["best_probe_edge"] == expected["best_probe_edge"]
        assert opt["best_eig"] == pytest.approx(expected["best_eig"], abs=1e-12)


def _compare_full_and_optimized_plan(scenario_path: str) -> None:
    conn, _ = run_full_pipeline(scenario_path)
    corr = compute_correlation(conn)
    full = plan_probes(conn, corr, reuse_static_correlation=False)
    optimized = plan_probes(conn, corr)
    _assert_plan_equivalent(full, optimized)


class TestStaticCorrelationPlannerEquivalence:
    def test_primary_realistic_scenario_equivalent(self) -> None:
        _compare_full_and_optimized_plan(str(FIXTURES / "primary_realistic_scenario.json"))

    def test_complex_scenario_equivalent(self) -> None:
        _compare_full_and_optimized_plan(str(FIXTURES / "complex_scenario.json"))

    def test_diamond_scenario_equivalent(self) -> None:
        _compare_full_and_optimized_plan(str(FIXTURES / "diamond_scenario.json"))

    def test_generated_1k_scenario_equivalent(self, tmp_path: Path) -> None:
        scenario = generate_scenario(1000, "medium", seed=42)
        scenario_path = tmp_path / "scenario_1k.json"
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        _compare_full_and_optimized_plan(str(scenario_path))

    def test_optimized_path_does_not_full_recompute_fork_correlation(self, monkeypatch) -> None:
        conn, _ = run_full_pipeline(str(FIXTURES / "diamond_scenario.json"))
        corr = compute_correlation(conn)

        def fail_full_recompute(_conn):
            raise AssertionError("optimized planner should reuse static correlation membership")

        monkeypatch.setattr("arf_rt.engine.planner.compute_correlation", fail_full_recompute)
        result = plan_probes(conn, corr)

        assert result["top_recommendation"] is not None
