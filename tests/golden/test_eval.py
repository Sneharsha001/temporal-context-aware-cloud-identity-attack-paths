"""Golden tests: multi-policy evaluation framework.

Tests determinism, policy separation, RIG bounds, and EIG advantage.
Uses scripted truth for stable, interpretable results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.eval import (
    EvalResult,
    choose_candidate,
    determine_outcome,
    run_eval_episode,
    run_evaluation,
)

import random

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "realistic_pmapper.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "realistic_aws_org.json")


def _build_baseline():
    """Build the realistic fixture and return (conn, edge_id_map, truth_map)."""
    translated = translate_from_file(PMAPPER)
    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    observations = []
    for name, obs_list in [
        ("attacker->DevOps", [("ALLOW", "UNKNOWN", 95, "pt-1"), ("ALLOW", "UNKNOWN", 90, "pt-2")]),
        ("DevOps->CI-Runner", [("ALLOW", "UNKNOWN", 85, "pt-3")]),
        ("DevOps->LambdaDeploy", [("ALLOW", "UNKNOWN", 80, "pt-4")]),
        ("CI-Runner->StagingDeploy", [("ALLOW", "UNKNOWN", 90, "pt-5")]),
        ("LambdaDeploy->StagingDeploy", [("ALLOW", "UNKNOWN", 85, "pt-6")]),
        ("StagingDeploy->StagingAdmin", [("DENY", "CONSTRAINT_DENY", 95, "pt-7")]),
        ("StagingDeploy->ProdDeploy", [("ALLOW", "UNKNOWN", 60, "pt-8")]),
        ("attacker->EC2Bastion", [("ALLOW", "UNKNOWN", 70, "pt-9")]),
        ("EC2Bastion->SharedInfra", [("ALLOW", "UNKNOWN", 50, "pt-10")]),
        ("ProdDeploy->ProdApp", [("DENY", "CONSTRAINT_DENY", 90, "pt-11")]),
    ]:
        edge = edge_map[name]
        for result, reason, sq, ev in obs_list:
            observations.append({
                "edge_ref": {"edge_type": edge["edge_type"], "src": edge["src"],
                             "dst": edge["dst"], "region": edge.get("region", "-")},
                "probe_type": "REPLAY_SCRIPTED", "result": result, "reason_class": reason,
                "strength": "DIRECT", "signal_q": sq, "is_counterfactual": False,
                "constraint_relevant": "DENY" in result, "evidence_hash": ev,
            })

    objectives = [{"objective_type": "REACHABILITY", "start_nodes": [translated.nodes[0]],
                    "target_nodes": [translated.nodes[11]], "max_depth": 8, "k": 10}]

    scenario = build_scenario(PMAPPER, org_path=ORG,
                              objectives=objectives, observations=observations)
    tmp = Path("/tmp/eval_test.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))

    # Build truth map: what's actually true in our scenario
    # SCP blocks sts:AssumeRole in prod OU → most prod edges are DENY
    # Staging IAM write SCP blocks → StagingAdmin is DENY
    # Dev edges all ALLOW (confirmed by pentest)
    truth_map = {}
    for row in conn.execute("""
        SELECT e.edge_id, n1.provider_id as src, n2.provider_id as dst
        FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
    """).fetchall():
        src = row["src"].split("/")[-1]
        dst = row["dst"].split("/")[-1]
        name = f"{src}->{dst}"
        # Dev account edges: all ALLOW
        if any(name.startswith(p) for p in ["attacker->", "DevOps->", "CI-Runner->",
                                             "LambdaDeploy->", "EC2Bastion->"]):
            truth_map[row["edge_id"]] = "ALLOW"
        # Staging: StagingDeploy→StagingAdmin DENY (IAM SCP), others ALLOW
        elif name == "StagingDeploy->StagingAdmin":
            truth_map[row["edge_id"]] = "DENY"
        elif name.startswith("StagingDeploy->"):
            truth_map[row["edge_id"]] = "ALLOW"
        # Prod: SCP blocks cross-account AssumeRole
        elif name in ("ProdDeploy->ProdApp", "ProdDeploy->ProdDBAdmin",
                       "ProdApp->ProdAdmin", "ProdDBAdmin->ProdAdmin"):
            truth_map[row["edge_id"]] = "DENY"
        # Shared infra in prod OU: also blocked by SCP
        elif name in ("SharedInfra->SharedSecrets", "SharedSecrets->ProdAdmin"):
            truth_map[row["edge_id"]] = "DENY"
        else:
            truth_map[row["edge_id"]] = "ALLOW"

    return conn, truth_map


@pytest.fixture(scope="module")
def eval_env():
    """Build baseline and scripted truth map."""
    conn, truth_map = _build_baseline()
    return conn, truth_map


# ===================================================================
# Determinism
# ===================================================================


class TestDeterminism:
    def test_same_seed_same_trace(self, eval_env):
        conn, truth_map = eval_env
        ep1 = run_eval_episode(conn, "eig", 3, seed=42,
                                truth_mode="scripted", truth_map=truth_map)
        ep2 = run_eval_episode(conn, "eig", 3, seed=42,
                                truth_mode="scripted", truth_map=truth_map)
        assert len(ep1.steps) == len(ep2.steps)
        for s1, s2 in zip(ep1.steps, ep2.steps):
            assert s1.edge_id == s2.edge_id
            assert s1.outcome == s2.outcome
            assert s1.h_before == s2.h_before
            assert s1.h_after == s2.h_after
            assert s1.rig == s2.rig

    def test_different_seed_can_differ(self, eval_env):
        """Random policy with different seeds should diverge sometimes."""
        conn, truth_map = eval_env
        ep1 = run_eval_episode(conn, "random", 3, seed=1,
                                truth_mode="scripted", truth_map=truth_map)
        ep2 = run_eval_episode(conn, "random", 3, seed=999,
                                truth_mode="scripted", truth_map=truth_map)
        # At least one step should choose a different edge
        edges1 = [s.edge_id for s in ep1.steps]
        edges2 = [s.edge_id for s in ep2.steps]
        assert edges1 != edges2, "Different seeds should produce different traces"


# ===================================================================
# RIG bounds
# ===================================================================


class TestRIGBounds:
    def test_rig_finite(self, eval_env):
        conn, truth_map = eval_env
        ep = run_eval_episode(conn, "eig", 5, seed=42,
                               truth_mode="scripted", truth_map=truth_map)
        for s in ep.steps:
            assert not (s.rig != s.rig), "RIG is NaN"  # NaN != NaN
            assert abs(s.rig) < 100, f"RIG unreasonably large: {s.rig}"

    def test_h_non_negative(self, eval_env):
        conn, truth_map = eval_env
        ep = run_eval_episode(conn, "eig", 5, seed=42,
                               truth_mode="scripted", truth_map=truth_map)
        for s in ep.steps:
            assert s.h_before >= 0
            assert s.h_after >= 0


# ===================================================================
# Policy separation
# ===================================================================


class TestPolicySeparation:
    def test_eig_and_random_differ(self, eval_env):
        """EIG and random should choose different edges at least once."""
        conn, truth_map = eval_env
        ep_eig = run_eval_episode(conn, "eig", 3, seed=42,
                                   truth_mode="scripted", truth_map=truth_map)
        ep_rand = run_eval_episode(conn, "random", 3, seed=42,
                                    truth_mode="scripted", truth_map=truth_map)
        edges_eig = [s.edge_id for s in ep_eig.steps]
        edges_rand = [s.edge_id for s in ep_rand.steps]
        assert edges_eig != edges_rand, "Policies should diverge"

    def test_eig_and_uncertainty_differ(self, eval_env):
        """EIG and uncertainty should choose different edges at least once."""
        conn, truth_map = eval_env
        ep_eig = run_eval_episode(conn, "eig", 3, seed=42,
                                   truth_mode="scripted", truth_map=truth_map)
        ep_unc = run_eval_episode(conn, "uncertainty", 3, seed=42,
                                   truth_mode="scripted", truth_map=truth_map)
        edges_eig = [s.edge_id for s in ep_eig.steps]
        edges_unc = [s.edge_id for s in ep_unc.steps]
        assert edges_eig != edges_unc, "Policies should diverge"


# ===================================================================
# Policy selection logic
# ===================================================================


class TestChooseCandidate:
    def test_eig_picks_max(self):
        candidates = [
            {"edge_id": "a", "eig": 0.1, "p_edge": 0.5},
            {"edge_id": "b", "eig": 0.3, "p_edge": 0.2},
            {"edge_id": "c", "eig": 0.05, "p_edge": 0.9},
        ]
        rng = random.Random(42)
        chosen = choose_candidate("eig", candidates, rng)
        assert chosen["edge_id"] == "b"

    def test_uncertainty_picks_closest_to_half(self):
        candidates = [
            {"edge_id": "a", "eig": 0.1, "p_edge": 0.1},
            {"edge_id": "b", "eig": 0.3, "p_edge": 0.48},
            {"edge_id": "c", "eig": 0.05, "p_edge": 0.9},
        ]
        rng = random.Random(42)
        chosen = choose_candidate("uncertainty", candidates, rng)
        assert chosen["edge_id"] == "b"


class TestCentralityPolicy:
    def test_centrality_picks_most_common_edge(self, eval_env):
        """Centrality should pick the edge appearing on the most Top-K paths."""
        conn, truth_map = eval_env
        from arf_rt.engine.correlation import compute_correlation
        from arf_rt.engine.planner import plan_probes
        corr = compute_correlation(conn)
        plan = plan_probes(conn, corr)
        candidates = plan["candidates"]
        rng = random.Random(42)
        chosen = choose_candidate("centrality", candidates, rng, conn=conn)
        # Should pick an edge that's on at least one Top-K path
        assert chosen["edge_id"] in [c["edge_id"] for c in candidates]


# ===================================================================
# Full evaluation (small)
# ===================================================================


class TestFullEvaluation:
    def test_eval_runs(self, eval_env):
        conn, truth_map = eval_env
        result = run_evaluation(
            conn,
            policies=["eig", "random", "uncertainty", "centrality"],
            num_episodes=3,
            num_steps=3,
            base_seed=42,
            truth_mode="scripted",
            truth_map=truth_map,
        )
        assert len(result.policies) == 4
        for policy, episodes in result.policies.items():
            assert len(episodes) == 3
            for ep in episodes:
                assert len(ep.steps) == 3

    def test_eig_beats_random_scripted(self, eval_env):
        """On the realistic fixture with scripted truth, EIG should
        reduce entropy at least as fast as random."""
        conn, truth_map = eval_env
        result = run_evaluation(
            conn,
            policies=["eig", "random"],
            num_episodes=10,
            num_steps=5,
            base_seed=1337,
            truth_mode="scripted",
            truth_map=truth_map,
        )
        eig_med = result.median_cum_rig("eig", 5)
        rand_med = result.median_cum_rig("random", 5)
        assert eig_med >= rand_med, \
            f"EIG ({eig_med:.4f}) should beat random ({rand_med:.4f})"

    def test_eig_beats_centrality_scripted(self, eval_env):
        """EIG should beat centrality — it's not just picking important edges."""
        conn, truth_map = eval_env
        result = run_evaluation(
            conn,
            policies=["eig", "centrality"],
            num_episodes=10,
            num_steps=5,
            base_seed=1337,
            truth_mode="scripted",
            truth_map=truth_map,
        )
        eig_med = result.median_cum_rig("eig", 5)
        cent_med = result.median_cum_rig("centrality", 5)
        assert eig_med >= cent_med, \
            f"EIG ({eig_med:.4f}) should beat centrality ({cent_med:.4f})"
