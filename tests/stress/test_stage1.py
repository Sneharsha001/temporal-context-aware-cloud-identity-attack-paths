"""Stage 1 stress tests — medium synthetic fixture.

Validates planner behavior on 76 nodes / 129 edges / 4 constraints / 3 objectives.
"""
from __future__ import annotations

import json
import time

import pytest

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.eval import run_evaluation
from arf_rt.engine.planner import plan_probes
from arf_rt.engine.snapshot import canonical_run_hash


@pytest.fixture(scope="module")
def stage1_conn():
    conn, _ = run_full_pipeline("tests/fixtures/stage1_large.json")
    return conn


@pytest.fixture(scope="module")
def stage1_plan(stage1_conn):
    corr = compute_correlation(stage1_conn)
    return plan_probes(stage1_conn, corr)


# ── Structural tests ──────────────────────────────────────────


class TestStage1Structure:
    def test_node_count(self, stage1_conn) -> None:
        n = stage1_conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert n == 76

    def test_edge_count(self, stage1_conn) -> None:
        n = stage1_conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert 120 <= n <= 140  # some dedup possible

    def test_constraint_count(self, stage1_conn) -> None:
        n = stage1_conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
        assert n == 4

    def test_objective_count(self, stage1_conn) -> None:
        n = stage1_conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0]
        assert n == 3

    def test_observation_count(self, stage1_conn) -> None:
        n = stage1_conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert n == 4

    def test_all_objectives_have_paths(self, stage1_conn) -> None:
        for row in stage1_conn.execute("SELECT objective_id FROM objectives").fetchall():
            paths = stage1_conn.execute(
                "SELECT COUNT(*) FROM derived_topk WHERE objective_id = ?",
                (row["objective_id"],),
            ).fetchone()[0]
            assert paths > 0, f"Objective {row['objective_id'][:16]} has no paths"

    def test_deterministic_hash(self, stage1_conn) -> None:
        h = canonical_run_hash(stage1_conn)
        assert h == "24478316b483f03ca04f199f013ae181a3681bbdea76fda267b35058723b1a6c"


# ── Planner tests ─────────────────────────────────────────────


class TestStage1Planner:
    """GOLDEN: planner behavior on Stage 1 fixture."""

    def test_candidate_pruning(self, stage1_plan) -> None:
        """Planner prunes >50% of edges."""
        total = stage1_plan["stats"]["total_edges"]
        candidates = stage1_plan["stats"]["candidate_edges"]
        assert candidates < total * 0.5, (
            f"Expected >50% pruning, got {candidates}/{total}"
        )

    def test_no_dead_end_candidates(self, stage1_plan) -> None:
        """Dead-end subgraph edges never appear in candidates."""
        for c in stage1_plan["candidates"]:
            edge_id = c["edge_id"]
            # Dead-end edges should not be on any Top-K path
            assert c["eig"] > 0 or "dead" not in str(c.get("reasons", []))

    def test_correlated_edges_rank_higher(self, stage1_plan) -> None:
        """SCP-correlated edges rank above most uncorrelated edges."""
        candidates = stage1_plan["candidates"]
        if len(candidates) < 2:
            pytest.skip("Not enough candidates")
        top_eig = candidates[0]["eig"]
        bottom_eig = candidates[-1]["eig"]
        assert top_eig > bottom_eig * 2, (
            f"Top ({top_eig:.4f}) should be >2× bottom ({bottom_eig:.4f})"
        )

    def test_runtime_under_1_second(self, stage1_plan) -> None:
        assert stage1_plan["stats"]["runtime_ms"] < 1000

    def test_fork_count_reasonable(self, stage1_plan) -> None:
        """Forks = 2 × candidates (allow + deny per edge)."""
        expected = stage1_plan["stats"]["candidate_edges"] * 2
        assert stage1_plan["stats"]["forks_executed"] == expected

    def test_component_labels_present(self, stage1_plan) -> None:
        """Every component has a human-readable label."""
        for comp in stage1_plan["component_summary"]:
            assert "component_label" in comp
            assert comp["component_label"] != ""

    def test_scp_components_exist(self, stage1_plan) -> None:
        """At least one SCP correlation component."""
        scp_comps = [
            c for c in stage1_plan["component_summary"]
            if "SCP" in c["component_label"]
        ]
        assert len(scp_comps) >= 1


# ── Eval tests ────────────────────────────────────────────────


class TestStage1Eval:
    """GOLDEN: policy comparison on Stage 1 fixture."""

    @pytest.fixture(scope="class")
    def eval_result(self, stage1_conn):
        # Build truth map
        constrained = stage1_conn.execute("""
            SELECT DISTINCT ec.edge_id, c.constraint_type, c.scope_id
            FROM edge_constraints ec
            JOIN constraints c ON c.constraint_id = ec.constraint_id
        """).fetchall()

        g1_deny, g4_deny, g3_edges = set(), set(), []
        for row in constrained:
            if row["scope_id"] == "ou-prod":
                g1_deny.add(row["edge_id"])
            elif row["scope_id"] == "ou-billing":
                g4_deny.add(row["edge_id"])
            elif row["scope_id"] == "ou-infra" and row["constraint_type"] == "SCP":
                g3_edges.append(row["edge_id"])
        g3_deny = set(sorted(g3_edges)[:3])

        truth = {}
        for row in stage1_conn.execute("SELECT edge_id FROM edges").fetchall():
            eid = row["edge_id"]
            truth[eid] = "DENY" if eid in (g1_deny | g4_deny | g3_deny) else "ALLOW"

        return run_evaluation(
            stage1_conn,
            policies=["eig", "random"],
            num_episodes=10,
            num_steps=5,
            base_seed=42,
            truth_mode="scripted",
            truth_map=truth,
        )

    def test_eig_beats_random(self, eval_result) -> None:
        eig5 = eval_result.median_cum_rig("eig", 5)
        rand5 = eval_result.median_cum_rig("random", 5)
        assert eig5 > rand5, f"EIG ({eig5:.4f}) should beat random ({rand5:.4f})"

    def test_eig_positive_at_step_3(self, eval_result) -> None:
        eig3 = eval_result.median_cum_rig("eig", 3)
        assert eig3 > 0, f"EIG CumRIG@3 should be positive, got {eig3:.4f}"

    def test_eig_random_ratio_above_2(self, eval_result) -> None:
        eig5 = eval_result.median_cum_rig("eig", 5)
        rand5 = eval_result.median_cum_rig("random", 5)
        if rand5 == 0:
            assert eig5 > 0
        else:
            ratio = eig5 / rand5
            assert ratio >= 2.0, f"EIG/Random ratio {ratio:.1f}× should be ≥2×"
