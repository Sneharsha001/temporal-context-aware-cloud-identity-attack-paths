"""Golden test: belief decay end-to-end.

Uses the demo scenario with timestamps added to observations.
Runs pipeline with and without --as-of to verify:
  1. No --as-of → identical to Session 12 golden values (no regression)
  2. With --as-of close to observations → minimal decay, similar beliefs
  3. With --as-of far from observations → heavy decay, weakened beliefs

The key demo: a 90-day-old ALLOW observation and a recent DENY.
The ALLOW decays, the DENY stays strong → path probability drops further.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "demo_pmapper_graph.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "demo_aws_org.json")
Q8 = 100_000_000


def _build_scenario_with_timestamps():
    """Build demo scenario with observed_at timestamps."""
    translated = translate_from_file(PMAPPER)

    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    # Observations with timestamps:
    #   attacker→JumpRole: 2x ALLOW, 90 days ago (will decay heavily at +180d)
    #   JumpRole→ProdDeploy: 2x ALLOW, 30 days ago (mild decay at +180d)
    #   ProdDeploy→ProdDB: 1x DENY, recent (minimal decay at +180d)
    observations = []
    for name, obs_list in [
        ("attacker->JumpRole", [
            ("ALLOW", "UNKNOWN", 90, "ev_aj1", "2025-01-01T00:00:00Z"),
            ("ALLOW", "UNKNOWN", 85, "ev_aj2", "2025-01-01T00:00:00Z"),
        ]),
        ("JumpRole->ProdDeploy", [
            ("ALLOW", "UNKNOWN", 90, "ev_jp1", "2025-03-01T00:00:00Z"),
            ("ALLOW", "UNKNOWN", 80, "ev_jp2", "2025-03-01T00:00:00Z"),
        ]),
        ("ProdDeploy->ProdDB", [
            ("DENY", "CONSTRAINT_DENY", 95, "ev_pd1", "2025-06-25T00:00:00Z"),
        ]),
    ]:
        edge = edge_map[name]
        for result, reason, sq, ev, ts in obs_list:
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
                "constraint_relevant": name == "ProdDeploy->ProdDB",
                "evidence_hash": ev,
                "observed_at": ts,
            })

    objectives = [{
        "objective_type": "REACHABILITY",
        "start_nodes": [translated.nodes[0]],
        "target_nodes": [translated.nodes[4]],
        "max_depth": 5,
        "k": 10,
    }]

    scenario = build_scenario(
        PMAPPER, org_path=ORG, objectives=objectives, observations=observations,
    )
    return scenario


def _run(as_of=None):
    """Write scenario, run pipeline, return conn."""
    scenario = _build_scenario_with_timestamps()
    tmp = Path("/tmp/decay_test_scenario.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)
    conn, _ = run_full_pipeline(str(tmp), as_of=as_of)
    return conn


def _get_edges(conn):
    result = {}
    for row in conn.execute("""
        SELECT n1.provider_id as src_arn, n2.provider_id as dst_arn,
               e.alpha_i, e.beta_i, e.status
        FROM edges e
        JOIN nodes n1 ON n1.node_id=e.src_node_id
        JOIN nodes n2 ON n2.node_id=e.dst_node_id
    """).fetchall():
        src = row["src_arn"].split("/")[-1]
        dst = row["dst_arn"].split("/")[-1]
        result[f"{src}->{dst}"] = dict(row)
    return result


def _get_path_p_worst(conn):
    return [r["p_worst_q8"] for r in conn.execute(
        "SELECT p_worst_q8 FROM derived_topk ORDER BY rank"
    ).fetchall()]


# ===================================================================
# No decay (regression check)
# ===================================================================


class TestNoDecayRegression:
    """Without --as-of, timestamps are ignored and results match Session 12."""

    def test_no_as_of_matches_session_12_beliefs(self) -> None:
        conn = _run(as_of=None)
        edges = _get_edges(conn)
        # Identical to Session 12 pinned values
        assert edges["attacker->JumpRole"]["alpha_i"] == 166
        assert edges["attacker->JumpRole"]["beta_i"] == 1
        assert edges["JumpRole->ProdDeploy"]["alpha_i"] == 162
        assert edges["ProdDeploy->ProdDB"]["beta_i"] == 91

    def test_no_as_of_matches_session_12_path(self) -> None:
        conn = _run(as_of=None)
        p = _get_path_p_worst(conn)
        assert p[0] == 1_073_818  # pinned from Session 12


# ===================================================================
# Recent as_of (minimal decay)
# ===================================================================


class TestRecentAsOf:
    """as_of = 2025-07-01, observations are 0-180 days old."""

    def test_deny_barely_decays(self) -> None:
        """ProdDeploy→ProdDB deny is 6 days old → ~96% weight."""
        conn = _run(as_of="2025-07-01T00:00:00Z")
        edges = _get_edges(conn)
        # Without decay: beta_i = 91 (1 + 90 increment)
        # With 6-day decay on 90-day half-life: factor ≈ 0.955
        # Decayed increment: round(90 * 0.955) = 86
        # beta_i = 1 + 86 = 87
        e = edges["ProdDeploy->ProdDB"]
        assert e["beta_i"] >= 85  # still strongly denied
        assert e["beta_i"] <= 91  # some decay possible

    def test_old_allows_decay_more(self) -> None:
        """attacker→JumpRole ALLOWs are 181 days old → ~25% weight."""
        conn = _run(as_of="2025-07-01T00:00:00Z")
        edges = _get_edges(conn)
        # Without decay: alpha = 166 (1 + 85 + 80)
        # 181 days / 90 half-life = ~2 half-lives → factor ≈ 0.25
        # Decayed increments: round(85*0.25)=21, round(80*0.25)=20
        # alpha = 1 + 21 + 20 = 42
        e = edges["attacker->JumpRole"]
        assert e["alpha_i"] < 166  # decayed
        assert e["alpha_i"] > 20   # not collapsed to near-1
        assert e["status"] == "CONFIRMED"  # still confirmed (alpha > beta)


# ===================================================================
# Distant as_of (heavy decay)
# ===================================================================


class TestDistantAsOf:
    """as_of = 2026-01-01, observations are 180-365 days old."""

    def test_all_observations_heavily_decayed(self) -> None:
        """All observations are 6-12 months old → significant decay."""
        conn = _run(as_of="2026-01-01T00:00:00Z")
        edges = _get_edges(conn)
        # attacker→JumpRole: 365 days old → ~4 half-lives → factor ≈ 0.06
        e_aj = edges["attacker->JumpRole"]
        assert e_aj["alpha_i"] < 30  # heavily decayed from 166

    def test_deny_also_decays(self) -> None:
        """ProdDeploy→ProdDB deny is 190 days old → ~25% weight."""
        conn = _run(as_of="2026-01-01T00:00:00Z")
        edges = _get_edges(conn)
        e = edges["ProdDeploy->ProdDB"]
        # 190 days / 90 half-life → ~2.1 half-lives → factor ≈ 0.23
        # Decayed increment: round(90 * 0.23) = 21
        # beta = 1 + 21 = 22
        assert e["beta_i"] < 91
        assert e["beta_i"] > 5

    def test_path_probability_changes(self) -> None:
        """Path probability should differ from no-decay run."""
        conn_no_decay = _run(as_of=None)
        conn_decay = _run(as_of="2026-01-01T00:00:00Z")
        p_no = _get_path_p_worst(conn_no_decay)
        p_dec = _get_path_p_worst(conn_decay)
        assert p_no[0] != p_dec[0]


# ===================================================================
# Determinism
# ===================================================================


class TestDecayDeterminism:
    def test_same_as_of_same_result(self) -> None:
        """Same --as-of produces identical results."""
        conn1 = _run(as_of="2025-07-01T00:00:00Z")
        conn2 = _run(as_of="2025-07-01T00:00:00Z")
        p1 = _get_path_p_worst(conn1)
        p2 = _get_path_p_worst(conn2)
        assert p1 == p2

    def test_different_as_of_different_result(self) -> None:
        """Different --as-of produces different results."""
        conn1 = _run(as_of="2025-07-01T00:00:00Z")
        conn2 = _run(as_of="2026-01-01T00:00:00Z")
        p1 = _get_path_p_worst(conn1)
        p2 = _get_path_p_worst(conn2)
        assert p1 != p2
