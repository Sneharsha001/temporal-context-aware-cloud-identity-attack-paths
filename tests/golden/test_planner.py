"""Golden test: probe planner (Expected Information Gain).

Uses a 5-node, 5-edge fixture with two paths to ProdAdmin:
  Path A: attacker→JumpRole→ProdDeploy→ProdAdmin (SCP blocked, ~1%)
  Path B: attacker→JumpRole→LambdaExec→ProdAdmin (uncertain, ~25%)

The SCP "BlockAssumeRoleInProd" blocks ProdDeploy→ProdAdmin in prod account.
The Lambda path bypasses the SCP because LambdaExec is in the dev account.

Key planner behaviors validated:
  1. Unobserved Lambda path edges have highest EIG (resolve Path B uncertainty)
  2. Confirmed edges have near-zero EIG (already known)
  3. SCP-blocked edge has small EIG (unlikely to change, but informative if it does)
  4. Correlation component edge is a candidate even if not on Top-K
  5. Explanations include reasons like "never directly probed" and "high uncertainty"
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.planner import (
    compute_candidates,
    compute_eig,
    plan_probes,
    _get_topk_paths,
    _edges_on_topk,
    _get_entropy,
)

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "planner_pmapper.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "demo_aws_org.json")
Q8 = 100_000_000


@pytest.fixture(scope="module")
def planner_env():
    """Build planner-specific scenario and run pipeline."""
    translated = translate_from_file(PMAPPER)
    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    observations = []
    for name, obs_list in [
        ("attacker->JumpRole", [
            ("ALLOW", "UNKNOWN", 90, "ev1"),
            ("ALLOW", "UNKNOWN", 85, "ev2"),
        ]),
        ("JumpRole->ProdDeploy", [("ALLOW", "UNKNOWN", 85, "ev3")]),
        ("ProdDeploy->ProdAdmin", [("DENY", "CONSTRAINT_DENY", 95, "ev4")]),
    ]:
        edge = edge_map[name]
        for result, reason, sq, ev in obs_list:
            observations.append({
                "edge_ref": {
                    "edge_type": edge["edge_type"],
                    "src": edge["src"],
                    "dst": edge["dst"],
                    "region": edge.get("region", "-"),
                },
                "probe_type": "REPLAY_SCRIPTED",
                "result": result,
                "reason_class": reason,
                "strength": "DIRECT",
                "signal_q": sq,
                "is_counterfactual": False,
                "constraint_relevant": name == "ProdDeploy->ProdAdmin",
                "evidence_hash": ev,
            })

    objectives = [{
        "objective_type": "REACHABILITY",
        "start_nodes": [translated.nodes[0]],
        "target_nodes": [translated.nodes[3]],
        "max_depth": 5,
        "k": 10,
    }]

    scenario = build_scenario(
        PMAPPER, org_path=ORG,
        objectives=objectives, observations=observations,
    )
    tmp = Path("/tmp/planner_golden_scenario.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))
    corr = compute_correlation(conn)
    return conn, corr


def _eid(conn, name):
    """Get edge_id from 'SrcName->DstName' format."""
    src_name, dst_name = name.split("->")
    row = conn.execute("""
        SELECT e.edge_id FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
        WHERE n1.provider_id LIKE ? AND n2.provider_id LIKE ?
    """, (f"%/{src_name}", f"%/{dst_name}")).fetchone()
    return row["edge_id"] if row else None


class TestBaselineState:
    def test_two_paths_found(self, planner_env):
        conn, _ = planner_env
        assert len(_get_topk_paths(conn)) == 2

    def test_lambda_path_dominant(self, planner_env):
        conn, _ = planner_env
        paths = _get_topk_paths(conn)
        assert paths[0]["p_worst_q8"] > paths[1]["p_worst_q8"]
        assert paths[0]["p_worst_q8"] > 20_000_000
        assert paths[1]["p_worst_q8"] < 2_000_000

    def test_baseline_entropy_moderate(self, planner_env):
        conn, _ = planner_env
        h = _get_entropy(conn)
        assert 0.3 < h < 1.2


class TestCandidates:
    def test_all_edges_are_candidates(self, planner_env):
        conn, corr = planner_env
        assert len(compute_candidates(conn, corr)) == 5

    def test_lambda_edges_are_candidates(self, planner_env):
        conn, corr = planner_env
        candidates = compute_candidates(conn, corr)
        assert _eid(conn, "JumpRole->LambdaExec") in candidates
        assert _eid(conn, "LambdaExec->ProdAdmin") in candidates


class TestEIGRanking:
    def test_all_eig_non_negative(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        for eid in compute_candidates(conn, corr):
            assert compute_eig(conn, eid, h)["eig"] >= -0.001

    def test_uncertain_edges_highest_eig(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        eig_lambda = compute_eig(conn, _eid(conn, "JumpRole->LambdaExec"), h)["eig"]
        eig_confirmed = compute_eig(conn, _eid(conn, "attacker->JumpRole"), h)["eig"]
        assert eig_lambda > eig_confirmed
        assert eig_lambda > 0.1

    def test_confirmed_edges_near_zero_eig(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        for name in ["attacker->JumpRole", "JumpRole->ProdDeploy"]:
            assert compute_eig(conn, _eid(conn, name), h)["eig"] < 0.01

    def test_scp_blocked_edge_small_eig(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        r = compute_eig(conn, _eid(conn, "ProdDeploy->ProdAdmin"), h)
        assert 0.001 < r["eig"] < 0.1

    def test_lambda_edges_tied(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        eig_jl = compute_eig(conn, _eid(conn, "JumpRole->LambdaExec"), h)["eig"]
        eig_la = compute_eig(conn, _eid(conn, "LambdaExec->ProdAdmin"), h)["eig"]
        assert abs(eig_jl - eig_la) < 0.01


class TestProbeOutcomes:
    def test_deny_on_lambda_reduces_entropy(self, planner_env):
        conn, _ = planner_env
        h_base = _get_entropy(conn)
        r = compute_eig(conn, _eid(conn, "JumpRole->LambdaExec"), h_base)
        assert r["h_deny"] < h_base

    def test_allow_vs_deny_differ(self, planner_env):
        conn, _ = planner_env
        r = compute_eig(conn, _eid(conn, "JumpRole->LambdaExec"), _get_entropy(conn))
        assert r["h_allow"] != r["h_deny"]


class TestCorrelationLeverage:
    def test_scp_edge_has_nonzero_eig(self, planner_env):
        conn, corr = planner_env
        h = _get_entropy(conn)
        assert compute_eig(conn, _eid(conn, "ProdDeploy->ProdAdmin"), h)["eig"] > 0

    def test_scp_edge_allow_has_high_entropy(self, planner_env):
        """ALLOW on SCP edge would mean SCP isn't active → both paths viable → higher entropy."""
        conn, _ = planner_env
        h = _get_entropy(conn)
        r = compute_eig(conn, _eid(conn, "ProdDeploy->ProdAdmin"), h)
        assert r["h_allow"] > h


class TestFullPlanner:
    def test_returns_all_candidates(self, planner_env):
        conn, corr = planner_env
        assert len(plan_probes(conn, corr)["candidates"]) == 5

    def test_top_recommendation_is_lambda_edge(self, planner_env):
        conn, corr = planner_env
        top_eid = plan_probes(conn, corr)["top_recommendation"]["edge_id"]
        lambda_eids = {_eid(conn, "JumpRole->LambdaExec"), _eid(conn, "LambdaExec->ProdAdmin")}
        assert top_eid in lambda_eids

    def test_confirmed_edges_ranked_last(self, planner_env):
        conn, corr = planner_env
        candidates = plan_probes(conn, corr)["candidates"]
        confirmed_eids = {_eid(conn, "attacker->JumpRole"), _eid(conn, "JumpRole->ProdDeploy")}
        bottom_eids = {c["edge_id"] for c in candidates[-2:]}
        assert confirmed_eids == bottom_eids

    def test_explanations_present(self, planner_env):
        conn, corr = planner_env
        for c in plan_probes(conn, corr)["candidates"]:
            assert len(c["reasons"]) >= 1

    def test_top_explains_uncertainty(self, planner_env):
        conn, corr = planner_env
        reasons = " ".join(plan_probes(conn, corr)["top_recommendation"]["reasons"])
        assert "uncertainty" in reasons or "never" in reasons

    def test_component_summary(self, planner_env):
        conn, corr = planner_env
        assert len(plan_probes(conn, corr)["component_summary"]) >= 2

    def test_deterministic(self, planner_env):
        conn, corr = planner_env
        r1 = plan_probes(conn, corr)
        r2 = plan_probes(conn, corr)
        assert r1["top_recommendation"]["edge_id"] == r2["top_recommendation"]["edge_id"]
        for c1, c2 in zip(r1["candidates"], r2["candidates"]):
            assert abs(c1["eig"] - c2["eig"]) < 0.0001


# ===================================================================
# Property: EIG ≥ 0 for all candidates (hard assertion)
# ===================================================================


class TestEIGProperty:
    """Hard property: EIG must be non-negative for every candidate edge.
    This prevents future refactors from reintroducing negative EIG
    (which happened before the null complement fix)."""

    def test_eig_non_negative_all_candidates(self, planner_env):
        conn, corr = planner_env
        result = plan_probes(conn, corr)
        for c in result["candidates"]:
            assert c["eig"] >= 0.0, (
                f"Negative EIG for edge {c['edge_id'][:16]}...: {c['eig']}"
            )

    def test_eig_non_negative_on_repeated_runs(self, planner_env):
        """Run planner 3 times, assert non-negative every time."""
        conn, corr = planner_env
        for _ in range(3):
            result = plan_probes(conn, corr)
            for c in result["candidates"]:
                assert c["eig"] >= 0.0


# ===================================================================
# Symmetry test
# ===================================================================


class TestSymmetry:
    """Two paths with identical structure and edge beliefs should
    produce symmetric EIG scores for the corresponding edges."""

    def test_symmetric_edges_equal_eig(self, planner_env):
        """JumpRole→LambdaExec and LambdaExec→ProdAdmin are both
        unobserved (50/50) and both on the same Top-K path.
        They should have very similar EIG."""
        conn, corr = planner_env
        h = _get_entropy(conn)
        eig_jl = compute_eig(conn, _eid(conn, "JumpRole->LambdaExec"), h)
        eig_la = compute_eig(conn, _eid(conn, "LambdaExec->ProdAdmin"), h)

        # Same p_edge
        assert abs(eig_jl["p_edge"] - eig_la["p_edge"]) < 0.001

        # Same EIG (within float tolerance)
        assert abs(eig_jl["eig"] - eig_la["eig"]) < 0.001

        # Same h_allow and h_deny (symmetric outcomes)
        assert abs(eig_jl["h_allow"] - eig_la["h_allow"]) < 0.001
        assert abs(eig_jl["h_deny"] - eig_la["h_deny"]) < 0.001


# ===================================================================
# No-impact edge property
# ===================================================================


class TestNoImpactEdge:
    """An edge not on any Top-K path and not in any Top-K component
    should not be a candidate (pruned out)."""

    def test_isolated_edge_not_candidate(self):
        """Build a scenario with an extra isolated edge that connects
        two nodes not on any path to the objective target."""
        from arf_rt.adapters.pmapper import translate_from_file
        from arf_rt.adapters.scenario_builder import build_scenario

        # Load planner fixture and add an isolated edge
        translated = translate_from_file(PMAPPER)

        # Add isolated node
        isolated_node = {
            "provider": "aws",
            "node_type": "IAMRole",
            "provider_id": "arn:aws:iam::300000000003:role/Isolated",
            "region": "-",
        }

        edge_map = {}
        for e in translated.edges:
            src = e["src"]["provider_id"].split("/")[-1]
            dst = e["dst"]["provider_id"].split("/")[-1]
            edge_map[f"{src}->{dst}"] = e

        observations = []
        for name, obs_list in [
            ("attacker->JumpRole", [("ALLOW", "UNKNOWN", 90, "ev1"), ("ALLOW", "UNKNOWN", 85, "ev2")]),
            ("JumpRole->ProdDeploy", [("ALLOW", "UNKNOWN", 85, "ev3")]),
            ("ProdDeploy->ProdAdmin", [("DENY", "CONSTRAINT_DENY", 95, "ev4")]),
        ]:
            edge = edge_map[name]
            for result, reason, sq, ev in obs_list:
                observations.append({
                    "edge_ref": {"edge_type": edge["edge_type"], "src": edge["src"],
                                 "dst": edge["dst"], "region": edge.get("region", "-")},
                    "probe_type": "REPLAY_SCRIPTED", "result": result,
                    "reason_class": reason, "strength": "DIRECT", "signal_q": sq,
                    "is_counterfactual": False,
                    "constraint_relevant": name == "ProdDeploy->ProdAdmin",
                    "evidence_hash": ev,
                })

        objectives = [{
            "objective_type": "REACHABILITY",
            "start_nodes": [translated.nodes[0]],
            "target_nodes": [translated.nodes[3]],
            "max_depth": 5, "k": 10,
        }]

        scenario = build_scenario(
            PMAPPER, org_path=ORG,
            objectives=objectives, observations=observations,
        )

        # Manually inject isolated node and edge
        scenario["nodes"].append(isolated_node)
        scenario["edges"].append({
            "edge_type": "sts:AssumeRole",
            "src": translated.nodes[0],  # attacker
            "dst": isolated_node,
            "region": "-",
        })

        tmp = Path("/tmp/isolated_edge_scenario.json")
        with open(tmp, "w") as f:
            json.dump(scenario, f, indent=2)

        conn, _ = run_full_pipeline(str(tmp))
        corr = compute_correlation(conn)

        # Find the isolated edge
        isolated_eid = conn.execute("""
            SELECT e.edge_id FROM edges e
            JOIN nodes n2 ON n2.node_id = e.dst_node_id
            WHERE n2.provider_id LIKE '%/Isolated'
        """).fetchone()

        assert isolated_eid is not None, "Isolated edge should exist in DB"
        eid = isolated_eid["edge_id"]

        # It should NOT be a candidate
        candidates = compute_candidates(conn, corr)
        assert eid not in candidates, (
            "Isolated edge should be pruned from candidates"
        )

        # Total edges = 6 (5 original + 1 isolated), candidates = 5
        all_edges = {r["edge_id"] for r in conn.execute("SELECT edge_id FROM edges").fetchall()}
        assert len(all_edges) == 6
        assert len(candidates) == 5


# ===================================================================
# Performance instrumentation
# ===================================================================


class TestPlannerStats:
    def test_stats_present(self, planner_env):
        conn, corr = planner_env
        result = plan_probes(conn, corr)
        stats = result["stats"]
        assert "total_edges" in stats
        assert "candidate_edges" in stats
        assert "forks_executed" in stats
        assert "runtime_ms" in stats

    def test_stats_correct_counts(self, planner_env):
        conn, corr = planner_env
        result = plan_probes(conn, corr)
        stats = result["stats"]
        assert stats["total_edges"] == 5
        assert stats["candidate_edges"] == 5
        assert stats["forks_executed"] == 10  # 5 candidates × 2 forks each

    def test_runtime_reasonable(self, planner_env):
        """5 candidates × 2 forks should complete in <5 seconds."""
        conn, corr = planner_env
        result = plan_probes(conn, corr)
        assert result["stats"]["runtime_ms"] < 5000
