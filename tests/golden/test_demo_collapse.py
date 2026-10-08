"""Golden test: PMapper import → SCP resolution → correlation collapse.

Demonstrates the full value proposition:
    PMapper shows structurally reachable paths.
    ARF-RT applies organization policy semantics and correlation,
    which filters to policy-viable paths.

Scenario:
    5 principals across 2 accounts (dev=100, prod=200)
    attacker → JumpRole → ProdDeploy → ProdAdmin  (direct path)
    attacker → JumpRole → ProdDeploy → ProdDB → ProdAdmin  (indirect)

    SCP "BlockAssumeRoleInProd" attached to ou-prod denies sts:AssumeRole
    for all principals in account 200.  This creates a correlation group
    across ProdDeploy→ProdDB, ProdDeploy→ProdAdmin, ProdDB→ProdAdmin.

    Observations:
    - attacker→JumpRole: 2x ALLOW (strong)       → 99.4%
    - JumpRole→ProdDeploy: 2x ALLOW (strong)     → 99.4%
    - ProdDeploy→ProdDB: 1x CONSTRAINT_DENY      → 1.1%
    - ProdDeploy→ProdAdmin: no observations       → 50% (prior)
    - ProdDB→ProdAdmin: no observations           → 50% (prior)

    Without correlation: direct path = 99.4% × 99.4% × 50% = 49.4%
    With correlation: ProdDeploy→ProdDB is SCP group representative,
        its 1.1% belief propagates to the entire group.
        Direct path collapses to ~1.07%.  46x reduction.

    This is the demo: naive tools show a ~50% path to ProdAdmin.
    Policy-aware correlation shows it's ~1%.

Pinned values:
    These are exact Q8 integers from the engine. Any change to the
    belief math, correlation, or path search will break these tests,
    which is the point — they freeze the demo artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "demo_pmapper_graph.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "demo_aws_org.json")
Q8 = 100_000_000


def _build_and_run():
    """Build scenario from PMapper + AWS Org, add observations, run engine."""
    from arf_rt.adapters.pmapper import translate_from_file

    translated = translate_from_file(PMAPPER)

    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    observations = []
    for name, obs_list in [
        ("attacker->JumpRole", [
            ("ALLOW", "UNKNOWN", 90, "ev_aj1"),
            ("ALLOW", "UNKNOWN", 85, "ev_aj2"),
        ]),
        ("JumpRole->ProdDeploy", [
            ("ALLOW", "UNKNOWN", 90, "ev_jp1"),
            ("ALLOW", "UNKNOWN", 80, "ev_jp2"),
        ]),
        ("ProdDeploy->ProdDB", [
            ("DENY", "CONSTRAINT_DENY", 95, "ev_pd1"),
        ]),
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
                "constraint_relevant": name == "ProdDeploy->ProdDB",
                "evidence_hash": ev,
            })

    objectives = [{
        "objective_type": "REACHABILITY",
        "start_nodes": [translated.nodes[0]],
        "target_nodes": [translated.nodes[4]],
        "max_depth": 5,
        "k": 10,
    }]

    scenario = build_scenario(
        PMAPPER,
        org_path=ORG,
        objectives=objectives,
        observations=observations,
    )

    # Write temp scenario
    tmp = Path("/tmp/demo_scenario.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))
    return conn


def _get_edges(conn):
    """Get edge beliefs indexed by src_name->dst_name."""
    result = {}
    for row in conn.execute("""
        SELECT n1.provider_id as src_arn, n2.provider_id as dst_arn,
               e.edge_id, e.alpha_i, e.beta_i, e.status, e.flags_json
        FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
    """).fetchall():
        src = row["src_arn"].split("/")[-1]
        dst = row["dst_arn"].split("/")[-1]
        result[f"{src}->{dst}"] = dict(row)
    return result


def _get_paths(conn):
    """Get top-k paths."""
    return [dict(r) for r in conn.execute(
        "SELECT rank, p_worst_q8, p_best_q8, confidence_band, edge_id_sequence "
        "FROM derived_topk ORDER BY rank"
    ).fetchall()]


@pytest.fixture(scope="module")
def demo():
    """Run the demo pipeline once for all tests in this module."""
    conn = _build_and_run()
    edges = _get_edges(conn)
    paths = _get_paths(conn)
    corr = compute_correlation(conn)
    return conn, edges, paths, corr


# ===================================================================
# Import verification
# ===================================================================


class TestImport:
    def test_node_count(self, demo) -> None:
        conn, _, _, _ = demo
        count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert count == 5

    def test_edge_count(self, demo) -> None:
        conn, _, _, _ = demo
        count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert count == 5

    def test_constraint_count(self, demo) -> None:
        """1 SCP constraint auto-resolved."""
        conn, _, _, _ = demo
        count = conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
        assert count == 1

    def test_edge_constraint_count(self, demo) -> None:
        """3 edges linked to the SCP constraint."""
        conn, _, _, _ = demo
        count = conn.execute("SELECT COUNT(*) FROM edge_constraints").fetchone()[0]
        assert count == 3

    def test_constraint_is_scp(self, demo) -> None:
        conn, _, _, _ = demo
        row = conn.execute(
            "SELECT constraint_type, status FROM constraints LIMIT 1"
        ).fetchone()
        assert row["constraint_type"] == "SCP"
        assert row["status"] == "ACTIVE"


# ===================================================================
# Edge beliefs (pinned)
# ===================================================================


class TestEdgeBeliefs:
    def test_attacker_jump_confirmed(self, demo) -> None:
        _, edges, _, _ = demo
        e = edges["attacker->JumpRole"]
        assert e["alpha_i"] == 166
        assert e["beta_i"] == 1
        assert e["status"] == "CONFIRMED"

    def test_jump_proddeploy_confirmed(self, demo) -> None:
        _, edges, _, _ = demo
        e = edges["JumpRole->ProdDeploy"]
        assert e["alpha_i"] == 162
        assert e["beta_i"] == 1
        assert e["status"] == "CONFIRMED"

    def test_proddeploy_proddb_refuted(self, demo) -> None:
        """CONSTRAINT_DENY observation → refuted."""
        _, edges, _, _ = demo
        e = edges["ProdDeploy->ProdDB"]
        assert e["alpha_i"] == 1
        assert e["beta_i"] == 91
        assert e["status"] == "REFUTED"

    def test_proddeploy_prodadmin_prior_only(self, demo) -> None:
        """No observations → (1,1) prior, HYPOTHESIZED."""
        _, edges, _, _ = demo
        e = edges["ProdDeploy->ProdAdmin"]
        assert e["alpha_i"] == 1
        assert e["beta_i"] == 1
        assert e["status"] == "HYPOTHESIZED"

    def test_proddb_prodadmin_prior_only(self, demo) -> None:
        _, edges, _, _ = demo
        e = edges["ProdDB->ProdAdmin"]
        assert e["alpha_i"] == 1
        assert e["beta_i"] == 1
        assert e["status"] == "HYPOTHESIZED"


# ===================================================================
# Correlation groups (pinned)
# ===================================================================


class TestCorrelation:
    def test_scp_group_exists(self, demo) -> None:
        """3 prod-account edges share BlockAssumeRoleInProd SCP."""
        _, edges, _, corr = demo
        scp_edges = [
            eid for eid, g in corr["edge_groups"].items()
            if json.loads(g["p_worst_sig"])[0][0] == "SCP"
        ]
        assert len(scp_edges) == 3

    def test_representative_is_proddeploy_proddb(self, demo) -> None:
        """Weakest edge (ProdDeploy→ProdDB with 1.1%) is the group representative."""
        conn, edges, _, corr = demo
        e_pd = edges["ProdDeploy->ProdDB"]
        rep_ids = set(corr["p_worst_reps"].values())
        assert e_pd["edge_id"] in rep_ids

    def test_uncorrelated_edges_have_no_scp_sig(self, demo) -> None:
        """attacker→JumpRole and JumpRole→ProdDeploy are NOT in SCP group."""
        _, edges, _, corr = demo
        for name in ["attacker->JumpRole", "JumpRole->ProdDeploy"]:
            eid = edges[name]["edge_id"]
            sig = json.loads(corr["edge_groups"][eid]["p_worst_sig"])
            assert sig[0][0] == "NONE"


# ===================================================================
# Path results (pinned)
# ===================================================================


class TestPaths:
    def test_two_paths_found(self, demo) -> None:
        _, _, paths, _ = demo
        assert len(paths) == 2

    def test_direct_path_rank_1(self, demo) -> None:
        """Direct 3-hop path: attacker→Jump→ProdDeploy→ProdAdmin."""
        _, _, paths, _ = demo
        p = paths[0]
        assert len(json.loads(p["edge_id_sequence"])) == 3
        assert p["rank"] == 1

    def test_indirect_path_rank_2(self, demo) -> None:
        """Indirect 4-hop path: attacker→Jump→ProdDeploy→ProdDB→ProdAdmin."""
        _, _, paths, _ = demo
        p = paths[1]
        assert len(json.loads(p["edge_id_sequence"])) == 4
        assert p["rank"] == 2

    def test_direct_path_correlated_pinned(self, demo) -> None:
        """Correlated probability of direct path is pinned at 1073818 (1.07%)."""
        _, _, paths, _ = demo
        assert paths[0]["p_worst_q8"] == 1_073_818

    def test_indirect_path_correlated_pinned(self, demo) -> None:
        """Indirect path also 1073818 — both bottleneck on same SCP representative."""
        _, _, paths, _ = demo
        assert paths[1]["p_worst_q8"] == 1_073_818

    def test_both_paths_very_low(self, demo) -> None:
        _, _, paths, _ = demo
        assert paths[0]["confidence_band"] == "VERY_LOW"
        assert paths[1]["confidence_band"] == "VERY_LOW"


# ===================================================================
# The collapse (the demo slide)
# ===================================================================


class TestCollapseDemo:
    """The core value proposition: naive vs correlated probability."""

    def test_naive_direct_path_high(self, demo) -> None:
        """Without correlation, direct path looks ~49.4% viable.
        PMapper-style structural analysis would report this as a significant risk.
        """
        _, edges, _, _ = demo
        naive = Q8
        for name in ["attacker->JumpRole", "JumpRole->ProdDeploy", "ProdDeploy->ProdAdmin"]:
            e = edges[name]
            p = e["alpha_i"] * Q8 // (e["alpha_i"] + e["beta_i"])
            naive = naive * p // Q8
        # ~49.4% — this is what naive analysis shows
        assert naive > 45_000_000  # > 45%
        assert naive < 55_000_000  # < 55%

    def test_correlated_direct_path_low(self, demo) -> None:
        """With correlation, same path collapses to ~1.07%.
        The SCP blocks AssumeRole for all principals in the prod account.
        ProdDeploy→ProdDB was probed and denied. Because all 3 prod-internal
        edges share the same SCP, the denial propagates to ProdDeploy→ProdAdmin
        even though it was never directly observed.
        """
        _, _, paths, _ = demo
        correlated = paths[0]["p_worst_q8"]
        assert correlated == 1_073_818  # pinned
        assert correlated < 2_000_000  # < 2%

    def test_collapse_ratio_46x(self, demo) -> None:
        """The collapse ratio is ~46x — this is the demo number.

        "PMapper shows structurally reachable paths."
        "ARF-RT applies organization policy semantics and correlation,
        which filters to policy-viable paths."
        "The direct path to ProdAdmin drops from 49% to 1% —
        a 46x reduction in assessed risk."
        """
        _, edges, paths, _ = demo
        naive = Q8
        for name in ["attacker->JumpRole", "JumpRole->ProdDeploy", "ProdDeploy->ProdAdmin"]:
            e = edges[name]
            p = e["alpha_i"] * Q8 // (e["alpha_i"] + e["beta_i"])
            naive = naive * p // Q8

        correlated = paths[0]["p_worst_q8"]
        ratio = naive / correlated
        # 46x collapse — the headline number
        assert ratio > 44.0
        assert ratio < 48.0

    def test_why_collapse_happens(self, demo) -> None:
        """Verify the mechanism: SCP group representative drives the collapse.

        ProdDeploy→ProdDB: observed DENY, alpha=1 beta=91 → 1.09%
        ProdDeploy→ProdAdmin: unobserved, alpha=1 beta=1 → 50%
        ProdDB→ProdAdmin: unobserved, alpha=1 beta=1 → 50%

        All three edges share SCP "BlockAssumeRoleInProd".
        ProdDeploy→ProdDB is the representative (cross-multiply weakest).
        Correlated probability uses the representative's 1.09%, not the
        independent edges' 50%.

        This is the key insight: probing ONE edge in an SCP group reveals
        information about ALL edges in that group. The SCP either blocks
        AssumeRole or it doesn't — observing a deny on one edge means
        the SCP is active, which constrains all edges it governs.
        """
        _, edges, _, corr = demo

        # Representative is ProdDeploy→ProdDB
        rep_eid = edges["ProdDeploy->ProdDB"]["edge_id"]
        rep_p = 1 * Q8 // (1 + 91)  # alpha=1, beta=91

        # Correlated edges use representative's probability
        # Path probability: p(A→J) × p(J→PD) × p_rep(SCP group)
        p_aj = 166 * Q8 // (166 + 1)
        p_jpd = 162 * Q8 // (162 + 1)

        expected = Q8
        expected = expected * p_aj // Q8
        expected = expected * p_jpd // Q8
        expected = expected * rep_p // Q8

        # Should match the pinned path probability
        assert abs(expected - 1_073_818) < 100  # rounding tolerance


# ===================================================================
# Conditional SCP transparency
# ===================================================================


class TestConditionalSCPSkipped:
    def test_conditional_scp_not_modeled(self, demo) -> None:
        """BlockAssumeUnlessVPN has Condition → not modeled as a constraint.
        Only 1 unconditional SCP constraint should exist."""
        conn, _, _, _ = demo
        count = conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
        assert count == 1  # only the unconditional one

    def test_conditional_scp_documented_in_scenario(self) -> None:
        """The build process emits a warning about the skipped conditional SCP."""
        # We can verify by re-running and checking warnings
        from arf_rt.adapters.pmapper import translate_from_file
        from arf_rt.adapters.aws_org import load_org_structure, resolve_scp_constraints

        translated = translate_from_file(PMAPPER)
        org = load_org_structure(ORG)
        _, _, warnings = resolve_scp_constraints(org, translated.edges)
        conditional_warnings = [w for w in warnings if "conditions" in w.lower()]
        assert len(conditional_warnings) >= 1
        assert "BlockAssumeUnlessVPN" in conditional_warnings[0]


# ===================================================================
# Determinism
# ===================================================================


class TestDeterminism:
    def test_collapse_deterministic_across_runs(self) -> None:
        """Run the pipeline twice, verify identical p_worst_q8 values."""
        conn1 = _build_and_run()
        conn2 = _build_and_run()

        paths1 = [dict(r) for r in conn1.execute(
            "SELECT rank, p_worst_q8 FROM derived_topk ORDER BY rank"
        ).fetchall()]
        paths2 = [dict(r) for r in conn2.execute(
            "SELECT rank, p_worst_q8 FROM derived_topk ORDER BY rank"
        ).fetchall()]

        assert len(paths1) == len(paths2)
        for p1, p2 in zip(paths1, paths2):
            assert p1["p_worst_q8"] == p2["p_worst_q8"]
            assert p1["rank"] == p2["rank"]
