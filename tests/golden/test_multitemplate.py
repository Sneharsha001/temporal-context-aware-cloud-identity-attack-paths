"""Multi-template routing verification (Session 11).

Scenario: 4 nodes, 3 edges with 2 distinct edge types.
  attacker →(AssumeRole)→ pivot →(GetObject)→ target-bucket
  pivot →(AssumeRole)→ admin

Proves:
  ✓ Distinct templates created for different feature fingerprints
  ✓ Same-type edges share a template
  ✓ Observations route to correct template (aggregation isolated)
  ✓ Template aggregation math correct per type
  ✓ Path probability uses edge beliefs (not template)
  ✓ Two objectives find correct paths through heterogeneous edges
  ✓ Deterministic across runs
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.snapshot import canonical_run_hash

SCENARIO = str(Path(__file__).parent.parent / "fixtures" / "multitemplate_scenario.json")
Q8 = 100_000_000


def _state():
    conn, _ = run_full_pipeline(SCENARIO)

    edges = {}
    for e in conn.execute("""
        SELECT e.edge_id, n1.provider_id as src, n2.provider_id as dst,
               e.edge_type, e.template_id, e.alpha_i, e.beta_i, e.status,
               e.flags_json
        FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
    """).fetchall():
        edges[f"{e['src']}->{e['dst']}"] = dict(e)

    templates = {}
    for t in conn.execute(
        "SELECT * FROM templates ORDER BY template_id COLLATE BINARY"
    ).fetchall():
        templates[t["template_id"]] = dict(t)

    topk = [dict(t) for t in conn.execute(
        "SELECT * FROM derived_topk ORDER BY objective_id, rank"
    ).fetchall()]

    return edges, templates, topk, conn


# ===================================================================
# Template creation and isolation
# ===================================================================


class TestTemplateCreation:
    def test_two_distinct_templates_created(self) -> None:
        """AssumeRole and GetObject get different templates."""
        _, templates, _, _ = _state()
        assert len(templates) == 2

    def test_templates_have_different_edge_types(self) -> None:
        _, templates, _, _ = _state()
        edge_types = {t["edge_type"] for t in templates.values()}
        assert edge_types == {"sts:AssumeRole", "s3:GetObject"}

    def test_assume_role_edges_share_template(self) -> None:
        """attacker→pivot and pivot→admin both use the AssumeRole template."""
        edges, _, _, _ = _state()
        assert edges["attacker->pivot"]["template_id"] == edges["pivot->admin"]["template_id"]

    def test_getobject_edge_has_own_template(self) -> None:
        """pivot→target-bucket uses a different template than AssumeRole edges."""
        edges, _, _, _ = _state()
        assert edges["pivot->target-bucket"]["template_id"] != edges["attacker->pivot"]["template_id"]


# ===================================================================
# Template aggregation — hand-traced
# ===================================================================


class TestTemplateAggregation:
    def test_assume_role_template_receives_3_obs(self) -> None:
        """obs1: attacker→pivot ALLOW inc=85 → SUPPORT
        obs2: attacker→pivot ALLOW inc=80 → SUPPORT
        obs4: pivot→admin ALLOW inc=76 → SUPPORT
        All 3 go to AssumeRole template.
        alpha_agg = 1 + 85 + 80 + 76 = 242, beta_agg = 1, samples = 3."""
        hand_alpha = 1 + math.floor(95 * 90 / 100) + math.floor(95 * 85 / 100) + math.floor(95 * 80 / 100)
        assert hand_alpha == 1 + 85 + 80 + 76
        assert hand_alpha == 242

        _, templates, _, _ = _state()
        ar_tpl = [t for t in templates.values() if t["edge_type"] == "sts:AssumeRole"][0]
        assert ar_tpl["alpha_agg_i"] == 242
        assert ar_tpl["beta_agg_i"] == 1
        assert ar_tpl["sample_count"] == 3

    def test_getobject_template_receives_1_obs(self) -> None:
        """obs3: pivot→target-bucket DENY/MISSING_PERMISSION inc=90 → AGAINST
        alpha_agg = 1, beta_agg = 1 + 90 = 91, samples = 1."""
        assert math.floor(95 * 95 / 100) == 90

        _, templates, _, _ = _state()
        s3_tpl = [t for t in templates.values() if t["edge_type"] == "s3:GetObject"][0]
        assert s3_tpl["alpha_agg_i"] == 1
        assert s3_tpl["beta_agg_i"] == 91
        assert s3_tpl["sample_count"] == 1

    def test_templates_are_fully_independent(self) -> None:
        """Modifying one template doesn't affect the other.
        The s3:GetObject DENY observation does NOT touch AssumeRole template."""
        _, templates, _, _ = _state()
        ar_tpl = [t for t in templates.values() if t["edge_type"] == "sts:AssumeRole"][0]
        s3_tpl = [t for t in templates.values() if t["edge_type"] == "s3:GetObject"][0]
        # AssumeRole has no AGAINST observations
        assert ar_tpl["beta_agg_i"] == 1
        # GetObject has no SUPPORT observations
        assert s3_tpl["alpha_agg_i"] == 1


# ===================================================================
# Edge beliefs — hand-traced
# ===================================================================


class TestEdgeBeliefs:
    def test_attacker_pivot(self) -> None:
        """obs1: ALLOW inc=85, obs2: ALLOW inc=80.
        alpha = 1 + 85 + 80 = 166, beta = 1."""
        edges, _, _, _ = _state()
        e = edges["attacker->pivot"]
        assert e["alpha_i"] == 166 and e["beta_i"] == 1
        assert e["status"] == "CONFIRMED"

    def test_pivot_target_bucket(self) -> None:
        """obs3: DENY/MISSING_PERMISSION inc=90.
        alpha = 1, beta = 1 + 90 = 91. REFUTED."""
        edges, _, _, _ = _state()
        e = edges["pivot->target-bucket"]
        assert e["alpha_i"] == 1 and e["beta_i"] == 91
        assert e["status"] == "REFUTED"

    def test_pivot_admin(self) -> None:
        """obs4: ALLOW inc=76.
        alpha = 1 + 76 = 77, beta = 1. CONFIRMED."""
        edges, _, _, _ = _state()
        e = edges["pivot->admin"]
        assert e["alpha_i"] == 77 and e["beta_i"] == 1
        assert e["status"] == "CONFIRMED"


# ===================================================================
# Path search across heterogeneous edge types
# ===================================================================


class TestMultiTypePaths:
    def test_objective1_finds_data_exfil_path(self) -> None:
        """attacker → pivot → target-bucket.
        Two edge types in one path: AssumeRole then GetObject."""
        _, _, topk, conn = _state()
        node_bucket = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'target-bucket'"
        ).fetchone()["node_id"]
        obj1 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_bucket}%',),
        ).fetchone()["objective_id"]
        paths = [t for t in topk if t["objective_id"] == obj1]
        assert len(paths) == 1
        assert paths[0]["path_length"] == 2

    def test_objective2_finds_privesc_path(self) -> None:
        """attacker → pivot → admin. Both edges AssumeRole."""
        _, _, topk, conn = _state()
        node_admin = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'admin'"
        ).fetchone()["node_id"]
        obj2 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_admin}%',),
        ).fetchone()["objective_id"]
        paths = [t for t in topk if t["objective_id"] == obj2]
        assert len(paths) == 1
        assert paths[0]["path_length"] == 2

    def test_data_exfil_path_probability(self) -> None:
        """attacker→pivot: 166/167. pivot→target-bucket: 1/92.
        p = (166*Q8//167) * (1*Q8//92) // Q8"""
        p_ap = 166 * Q8 // 167  # 99401197
        p_pb = 1 * Q8 // 92     # 1086956
        path_p = p_ap * p_pb // Q8  # 1080447
        assert path_p == 1080447

        _, _, topk, conn = _state()
        node_bucket = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'target-bucket'"
        ).fetchone()["node_id"]
        obj1 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_bucket}%',),
        ).fetchone()["objective_id"]
        paths = [t for t in topk if t["objective_id"] == obj1]
        assert paths[0]["p_worst_q8"] == path_p

    def test_privesc_path_probability(self) -> None:
        """attacker→pivot: 166/167. pivot→admin: 77/78.
        p = (166*Q8//167) * (77*Q8//78) // Q8"""
        p_ap = 166 * Q8 // 167  # 99401197
        p_pa = 77 * Q8 // 78    # 98717948
        path_p = p_ap * p_pa // Q8
        assert path_p == 98126821

        _, _, topk, conn = _state()
        node_admin = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'admin'"
        ).fetchone()["node_id"]
        obj2 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_admin}%',),
        ).fetchone()["objective_id"]
        paths = [t for t in topk if t["objective_id"] == obj2]
        assert paths[0]["p_worst_q8"] == path_p

    def test_privesc_high_confidence_exfil_very_low(self) -> None:
        """Privesc path ~98% → VERY_HIGH. Data exfil ~1% → VERY_LOW."""
        _, _, topk, conn = _state()
        node_bucket = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'target-bucket'"
        ).fetchone()["node_id"]
        node_admin = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'admin'"
        ).fetchone()["node_id"]
        obj1 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_bucket}%',),
        ).fetchone()["objective_id"]
        obj2 = conn.execute(
            "SELECT objective_id FROM objectives WHERE target_nodes_json LIKE ?",
            (f'%{node_admin}%',),
        ).fetchone()["objective_id"]

        exfil = [t for t in topk if t["objective_id"] == obj1][0]
        privesc = [t for t in topk if t["objective_id"] == obj2][0]
        assert exfil["confidence_band"] == "VERY_LOW"
        assert privesc["confidence_band"] == "VERY_HIGH"


# ===================================================================
# Determinism
# ===================================================================


class TestMultiTemplateDeterminism:
    def test_hash_stable(self) -> None:
        hashes = set()
        for _ in range(5):
            conn, _ = run_full_pipeline(SCENARIO)
            hashes.add(canonical_run_hash(conn))
        assert len(hashes) == 1
