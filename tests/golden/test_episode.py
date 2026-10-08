"""Golden tests: Realized Information Gain episodes.

Runs two forced episodes on the realistic fixture:
  Episode A: Force DENY on the planner's top recommendation (the SCP representative)
  Episode B: Force ALLOW on the same edge

Validates:
  1. RIG matches predicted direction (DENY reduces entropy, ALLOW increases it)
  2. Planner prediction error is small (predicted H ≈ actual H)
  3. Representative behavior is correct per outcome
  4. Hashes differ between baseline and episode
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.episode import run_episode, format_episode_report
from arf_rt.engine.planner import plan_probes

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "realistic_pmapper.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "realistic_aws_org.json")


@pytest.fixture(scope="module")
def episode_env():
    """Build realistic scenario, get top probe recommendation."""
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
    tmp = Path("/tmp/episode_test.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))
    corr = compute_correlation(conn)
    plan = plan_probes(conn, corr)
    top_edge = plan["top_recommendation"]["edge_id"]

    return conn, corr, plan, top_edge


# ===================================================================
# Episode A: Force DENY on representative
# ===================================================================


class TestEpisodeDeny:
    def test_rig_positive(self, episode_env):
        """DENY on the SCP representative confirms the block → entropy drops."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert ep["rig"] > 0, f"Expected positive RIG for DENY, got {ep['rig']}"

    def test_entropy_decreases(self, episode_env):
        """H_after < H_before when DENY confirms the block."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert ep["h_after"] < ep["h_before"]

    def test_prediction_accurate(self, episode_env):
        """Planner's predicted H for DENY should match actual H closely."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert ep["prediction_error"] < 0.01, \
            f"Prediction error {ep['prediction_error']:.4f} > 0.01"

    def test_representative_unchanged(self, episode_env):
        """DENY on the current rep should keep it as representative."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert not ep["rep_changed"]

    def test_hashes_differ(self, episode_env):
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert ep["baseline_hash"] != ep["episode_hash"]


# ===================================================================
# Episode B: Force ALLOW on representative
# ===================================================================


class TestEpisodeAllow:
    def test_rig_negative(self, episode_env):
        """ALLOW on SCP rep contradicts the block → entropy rises."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "ALLOW")
        assert ep["rig"] < 0, f"Expected negative RIG for ALLOW, got {ep['rig']}"

    def test_entropy_increases(self, episode_env):
        """H_after > H_before when ALLOW surprises the model."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "ALLOW")
        assert ep["h_after"] > ep["h_before"]

    def test_prediction_accurate(self, episode_env):
        """Planner's predicted H for ALLOW should match actual H closely."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "ALLOW")
        assert ep["prediction_error"] < 0.01, \
            f"Prediction error {ep['prediction_error']:.4f} > 0.01"

    def test_hashes_differ(self, episode_env):
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "ALLOW")
        assert ep["baseline_hash"] != ep["episode_hash"]


# ===================================================================
# Cross-episode properties
# ===================================================================


class TestCrossEpisode:
    def test_eig_non_negative(self, episode_env):
        """EIG is always ≥ 0 because it is an expectation over entropy reductions."""
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        assert ep["eig"] >= 0, f"EIG must be ≥ 0, got {ep['eig']}"

    def test_deny_rig_greater_than_allow_rig(self, episode_env):
        """DENY is 99% likely → DENY outcome has higher RIG than ALLOW.
        (RIG for ALLOW is negative because entropy goes up.)"""
        conn, _, _, top_edge = episode_env
        ep_deny = run_episode(conn, top_edge, "DENY")
        ep_allow = run_episode(conn, top_edge, "ALLOW")
        assert ep_deny["rig"] > ep_allow["rig"]

    def test_eig_equals_weighted_rig(self, episode_env):
        """EIG ≈ p(allow) * RIG_allow + p(deny) * RIG_deny.
        Since RIG = H_before - H_after, and EIG = H_before - E[H_after]:
            EIG = p * (H_before - H_allow) + (1-p) * (H_before - H_deny)
                = p * RIG_allow + (1-p) * RIG_deny
        """
        conn, _, _, top_edge = episode_env
        ep_deny = run_episode(conn, top_edge, "DENY")
        ep_allow = run_episode(conn, top_edge, "ALLOW")
        p = ep_deny["eig"]  # EIG is same for both (same edge)

        # Get p(allow) from either episode
        from arf_rt.engine.planner import _get_edge_p
        p_allow = _get_edge_p(conn, top_edge)

        weighted_rig = p_allow * ep_allow["rig"] + (1 - p_allow) * ep_deny["rig"]
        eig = ep_deny["eig"]  # same as ep_allow["eig"]

        assert abs(weighted_rig - eig) < 0.001, \
            f"Weighted RIG ({weighted_rig:.4f}) != EIG ({eig:.4f})"

    def test_episodes_deterministic(self, episode_env):
        """Same input → same episode result."""
        conn, _, _, top_edge = episode_env
        ep1 = run_episode(conn, top_edge, "DENY")
        ep2 = run_episode(conn, top_edge, "DENY")
        assert ep1["h_after"] == ep2["h_after"]
        assert ep1["rig"] == ep2["rig"]
        assert ep1["episode_hash"] == ep2["episode_hash"]

    def test_baseline_not_modified(self, episode_env):
        """Running episodes must not modify the baseline DB."""
        conn, _, plan, top_edge = episode_env
        from arf_rt.engine.snapshot import canonical_run_hash
        hash_before = canonical_run_hash(conn)
        run_episode(conn, top_edge, "DENY")
        run_episode(conn, top_edge, "ALLOW")
        hash_after = canonical_run_hash(conn)
        assert hash_before == hash_after


# ===================================================================
# Report formatting
# ===================================================================


class TestEpisodeReport:
    def test_report_is_string(self, episode_env):
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        report = format_episode_report(ep, conn)
        assert isinstance(report, str)
        assert len(report) > 200

    def test_report_contains_rig(self, episode_env):
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        report = format_episode_report(ep, conn)
        assert "Realized Information Gain" in report

    def test_report_contains_interpretation(self, episode_env):
        conn, _, _, top_edge = episode_env
        ep = run_episode(conn, top_edge, "DENY")
        report = format_episode_report(ep, conn)
        assert "entropy" in report.lower() or "uncertainty" in report.lower()
