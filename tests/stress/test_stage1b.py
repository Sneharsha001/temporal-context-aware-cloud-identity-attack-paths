"""Stage 1b stress tests — realistic multi-account AWS topology.

Validates planner on ~26 nodes / ~41 edges / 2 constraints / 2 objectives
with bypass path, SCP correlation group (6 edges), and trust condition (4 edges).

Key design: one path to ProdAdmin bypasses the SCP entirely. This means
uncertainty policy (which sees all p=0.50 edges as equal) wastes probes on
low-value bypass edges, while EIG correctly prioritizes the SCP representative
(which resolves 6 edges in one probe).
"""
from __future__ import annotations

import json

import pytest

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.eval import run_evaluation
from arf_rt.engine.planner import plan_probes
from arf_rt.engine.snapshot import canonical_run_hash


@pytest.fixture(scope="module")
def s1b_conn():
    conn, _ = run_full_pipeline("tests/fixtures/stage1b_realistic.json")
    return conn


@pytest.fixture(scope="module")
def s1b_plan(s1b_conn):
    corr = compute_correlation(s1b_conn)
    return plan_probes(s1b_conn, corr)


# ── Structure ─────────────────────────────────────────────────


class TestStage1bStructure:
    def test_node_count(self, s1b_conn) -> None:
        n = s1b_conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert n == 26

    def test_edge_count(self, s1b_conn) -> None:
        n = s1b_conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert n == 41

    def test_three_accounts(self, s1b_conn) -> None:
        """Nodes span 3 AWS accounts."""
        rows = s1b_conn.execute("SELECT DISTINCT provider_id FROM nodes").fetchall()
        accts = {r["provider_id"].split(":")[4] for r in rows}
        assert len(accts) == 3

    def test_two_constraints(self, s1b_conn) -> None:
        n = s1b_conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
        assert n == 2

    def test_two_objectives(self, s1b_conn) -> None:
        n = s1b_conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0]
        assert n == 2

    def test_both_objectives_have_paths(self, s1b_conn) -> None:
        for row in s1b_conn.execute("SELECT objective_id FROM objectives").fetchall():
            paths = s1b_conn.execute(
                "SELECT COUNT(*) FROM derived_topk WHERE objective_id = ?",
                (row["objective_id"],),
            ).fetchone()[0]
            assert paths > 0

    def test_bypass_path_exists(self, s1b_conn) -> None:
        """At least one path to ProdAdminRole avoids all SCP-governed edges."""
        gov_ids = {
            r["edge_id"]
            for r in s1b_conn.execute("""
                SELECT DISTINCT ec.edge_id
                FROM edge_constraints ec
                JOIN constraints c ON c.constraint_id = ec.constraint_id
                WHERE c.constraint_type = 'SCP'
            """).fetchall()
        }
        # Find objective targeting ProdAdminRole
        prod_obj = None
        for row in s1b_conn.execute("SELECT objective_id, target_nodes_json FROM objectives").fetchall():
            target_ids = json.loads(row["target_nodes_json"])
            for tid in target_ids:
                node = s1b_conn.execute(
                    "SELECT provider_id FROM nodes WHERE node_id = ?", (tid,)
                ).fetchone()
                if node and "ProdAdmin" in node["provider_id"]:
                    prod_obj = row["objective_id"]
                    break
        assert prod_obj, "No objective targeting ProdAdminRole found"

        rows = s1b_conn.execute(
            "SELECT edge_id_sequence FROM derived_topk WHERE objective_id = ?",
            (prod_obj,),
        ).fetchall()
        bypass_found = False
        for row in rows:
            path_edges = set(json.loads(row["edge_id_sequence"]))
            if not path_edges.intersection(gov_ids):
                bypass_found = True
                break
        assert bypass_found, "No bypass path found that avoids all SCP edges"

    def test_deterministic_hash(self, s1b_conn) -> None:
        h = canonical_run_hash(s1b_conn)
        assert h == "27c39f7bcc74caaddb294e5852401b19e1700efa9349a71732585c4f780a54da"


# ── Planner ───────────────────────────────────────────────────


class TestStage1bPlanner:
    """GOLDEN: planner behavior on realistic multi-account fixture."""

    def test_candidate_pruning(self, s1b_plan) -> None:
        """Planner prunes ≥40% of edges."""
        total = s1b_plan["stats"]["total_edges"]
        cands = s1b_plan["stats"]["candidate_edges"]
        assert cands < total * 0.6, f"Expected ≥40% pruning, got {cands}/{total}"

    def test_scp_group_highest_eig(self, s1b_plan) -> None:
        """SCP-governed correlation component has highest EIG."""
        comps = s1b_plan["component_summary"]
        top = max(comps, key=lambda c: c["best_eig"])
        assert "SCP" in top["component_label"]
        assert top["best_eig"] > 0.2

    def test_scp_group_has_6_edges(self, s1b_plan) -> None:
        """The SCP group should have 6 governed edges."""
        scp_comps = [
            c for c in s1b_plan["component_summary"]
            if "SCP" in c["component_label"]
        ]
        assert len(scp_comps) >= 1
        assert scp_comps[0]["edge_count"] == 6

    def test_trust_condition_component_exists(self, s1b_plan) -> None:
        tc = [
            c for c in s1b_plan["component_summary"]
            if "TRUST" in c["component_label"].upper()
        ]
        assert len(tc) >= 1

    def test_trust_condition_has_4_edges(self, s1b_plan) -> None:
        tc = [
            c for c in s1b_plan["component_summary"]
            if "TRUST" in c["component_label"].upper()
        ]
        assert tc[0]["edge_count"] == 4

    def test_trust_condition_lower_eig_than_scp(self, s1b_plan) -> None:
        """Trust condition group has lower EIG than SCP group."""
        comps = s1b_plan["component_summary"]
        scp_eigs = [c["best_eig"] for c in comps if "SCP" in c["component_label"]]
        tc_eigs = [
            c["best_eig"] for c in comps
            if "TRUST" in c["component_label"].upper()
        ]
        if scp_eigs and tc_eigs:
            assert max(scp_eigs) > max(tc_eigs)

    def test_runtime_under_500ms(self, s1b_plan) -> None:
        assert s1b_plan["stats"]["runtime_ms"] < 500

    def test_recommendation_is_scp_representative(self, s1b_plan) -> None:
        """Top recommendation should be from the SCP group."""
        rec = s1b_plan["top_recommendation"]
        reasons = rec["reasons"]
        assert any("SCP" in r or "correlation" in r for r in reasons)


# ── Eval ──────────────────────────────────────────────────────


class TestStage1bEval:
    """GOLDEN: EIG vs baselines on correlated multi-account fixture."""

    @pytest.fixture(scope="class")
    def eval_result(self, s1b_conn):
        constrained = s1b_conn.execute("""
            SELECT DISTINCT ec.edge_id, c.constraint_type
            FROM edge_constraints ec
            JOIN constraints c ON c.constraint_id = ec.constraint_id
            WHERE c.constraint_type = 'SCP'
        """).fetchall()
        scp_deny = {r["edge_id"] for r in constrained}

        truth = {}
        for row in s1b_conn.execute("SELECT edge_id FROM edges").fetchall():
            eid = row["edge_id"]
            truth[eid] = "DENY" if eid in scp_deny else "ALLOW"

        return run_evaluation(
            s1b_conn,
            policies=["eig", "random", "uncertainty"],
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

    def test_eig_beats_uncertainty(self, eval_result) -> None:
        """EIG should beat naive uncertainty (which ignores correlation)."""
        eig5 = eval_result.median_cum_rig("eig", 5)
        unc5 = eval_result.median_cum_rig("uncertainty", 5)
        assert eig5 >= unc5, f"EIG ({eig5:.4f}) should ≥ uncertainty ({unc5:.4f})"

    def test_eig_positive_cumrig(self, eval_result) -> None:
        eig5 = eval_result.median_cum_rig("eig", 5)
        assert eig5 > 0

    def test_eig_front_loads_information(self, eval_result) -> None:
        """EIG CumRIG@3 should be significant — not backloaded."""
        eig3 = eval_result.median_cum_rig("eig", 3)
        eig5 = eval_result.median_cum_rig("eig", 5)
        assert eig3 > eig5 * 0.5, (
            f"EIG@3={eig3:.4f} should be >50% of EIG@5={eig5:.4f}"
        )
