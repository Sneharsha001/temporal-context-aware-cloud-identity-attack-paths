"""Hand-trace verification of the rich scenario.

Exercises:
  ✓ Branching paths (A→B→D→E vs A→C→D→E)
  ✓ Correlation grouping (SCP1 groups {A→B, B→D}, SCP2 groups {A→C, C→D})
  ✓ Frozen collision with conflict (D→E: DETERMINISTIC ALLOW then DIRECT DENY)
  ✓ N/M validation thresholds met (SCP1: 2 edges, 2 sources → VALIDATED)
  ✓ N/M thresholds NOT met (SCP2: only 1 qualifying edge → UNVALIDATED)
  ✓ TRUST_CONDITION validated (≥1 qualifying obs)
  ✓ Multiple objectives (A→E and B→E)
  ✓ Group representative selection (worst edge per group)
  ✓ Status tracks last polarity, not ratio (B→D: CONFIRMED despite beta>alpha)
"""

from __future__ import annotations

import math
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.snapshot import canonical_run_hash

SCENARIO = str(Path(__file__).parent.parent / "fixtures" / "rich_scenario.json")
Q8 = 100_000_000


def _state():
    conn, _ = run_full_pipeline(SCENARIO)
    edges = {}
    for e in conn.execute("""
        SELECT e.edge_id, n1.provider_id as src, n2.provider_id as dst,
               e.alpha_i, e.beta_i, e.status, e.frozen, e.flags_json
        FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
    """).fetchall():
        edges[f"{e['src']}->{e['dst']}"] = dict(e)

    updates = [dict(u) for u in conn.execute(
        "SELECT * FROM edge_updates ORDER BY update_id"
    ).fetchall()]

    tpl = dict(conn.execute(
        "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates"
    ).fetchone())

    topk = [dict(t) for t in conn.execute(
        "SELECT * FROM derived_topk ORDER BY objective_id, rank"
    ).fetchall()]

    constraints = [dict(c) for c in conn.execute(
        "SELECT constraint_type, status, validation_status, confidence_q "
        "FROM constraints ORDER BY constraint_id COLLATE BINARY"
    ).fetchall()]

    corr = compute_correlation(conn)

    return edges, updates, tpl, topk, constraints, corr, conn


# ===================================================================
# Belief updates — obs by obs
# ===================================================================


class TestRichBeliefUpdates:
    """Trace every observation's increment and edge state change."""

    def test_obs1_AB_allow_direct(self) -> None:
        """obs1: A→B, ALLOW/UNKNOWN, DIRECT, sq=85
        Polarity: SUPPORT. inc = floor(95 * 85 / 100) = 80.
        Edge: (1,1) → (81, 1, CONFIRMED)."""
        assert math.floor(95 * 85 / 100) == 80
        _, updates, _, _, _, _, _ = _state()
        u = updates[0]
        assert u["polarity"] == "SUPPORT"
        assert u["increment"] == 80
        assert u["alpha_before"] == 1 and u["alpha_after"] == 81
        assert u["beta_before"] == 1 and u["beta_after"] == 1

    def test_obs2_AB_deny_constraint(self) -> None:
        """obs2: A→B, DENY/CONSTRAINT_DENY, DIRECT, sq=90
        Polarity: AGAINST. inc = floor(95 * 90 / 100) = 85.
        Edge: (81,1) → (81, 86, REFUTED)."""
        assert math.floor(95 * 90 / 100) == 85
        _, updates, _, _, _, _, _ = _state()
        u = updates[1]
        assert u["polarity"] == "AGAINST"
        assert u["increment"] == 85
        assert u["alpha_before"] == 81 and u["alpha_after"] == 81
        assert u["beta_before"] == 1 and u["beta_after"] == 86

    def test_obs3_AC_deterministic_saturation(self) -> None:
        """obs3: A→C, ALLOW/UNKNOWN, DETERMINISTIC, sq=100
        Saturate: (9900, 100, CONFIRMED, frozen=1). inc = 100."""
        assert math.floor(100 * 100 / 100) == 100
        _, updates, _, _, _, _, _ = _state()
        u = updates[2]
        assert u["polarity"] == "SUPPORT"
        assert u["increment"] == 100
        assert u["alpha_after"] == 9900 and u["beta_after"] == 100
        assert u["frozen_before"] == 0 and u["frozen_after"] == 1

    def test_obs4_BD_deny_constraint(self) -> None:
        """obs4: B→D, DENY/CONSTRAINT_DENY, DIRECT, sq=95
        inc = floor(95 * 95 / 100) = 90.
        Edge: (1,1) → (1, 91, REFUTED)."""
        assert math.floor(95 * 95 / 100) == 90
        _, updates, _, _, _, _, _ = _state()
        u = updates[3]
        assert u["polarity"] == "AGAINST"
        assert u["increment"] == 90
        assert u["alpha_after"] == 1 and u["beta_after"] == 91

    def test_obs5_BD_allow_direct(self) -> None:
        """obs5: B→D, ALLOW/UNKNOWN, DIRECT, sq=70
        inc = floor(95 * 70 / 100) = 66.
        Edge: (1,91) → (67, 91, CONFIRMED).
        Note: CONFIRMED despite beta > alpha — status tracks last polarity."""
        assert math.floor(95 * 70 / 100) == 66
        _, updates, _, _, _, _, _ = _state()
        u = updates[4]
        assert u["polarity"] == "SUPPORT"
        assert u["increment"] == 66
        assert u["alpha_before"] == 1 and u["alpha_after"] == 67
        assert u["beta_before"] == 91 and u["beta_after"] == 91
        assert u["status_after"] == "CONFIRMED"  # despite 67 < 91!

    def test_obs6_CD_allow_direct(self) -> None:
        """obs6: C→D, ALLOW/UNKNOWN, DIRECT, sq=80
        inc = floor(95 * 80 / 100) = 76.
        Edge: (1,1) → (77, 1, CONFIRMED)."""
        assert math.floor(95 * 80 / 100) == 76
        _, updates, _, _, _, _, _ = _state()
        u = updates[5]
        assert u["polarity"] == "SUPPORT"
        assert u["increment"] == 76
        assert u["alpha_after"] == 77 and u["beta_after"] == 1

    def test_obs7_DE_deterministic_saturation(self) -> None:
        """obs7: D→E, ALLOW/UNKNOWN, DETERMINISTIC, sq=100
        Saturate: (9900, 100, CONFIRMED, frozen=1)."""
        _, updates, _, _, _, _, _ = _state()
        u = updates[6]
        assert u["alpha_after"] == 9900 and u["beta_after"] == 100
        assert u["frozen_after"] == 1

    def test_obs8_DE_frozen_collision_conflict(self) -> None:
        """obs8: D→E, DENY/MISSING_PERMISSION, DIRECT, sq=85
        D→E is frozen CONFIRMED. DIRECT DENY contradicts → conflict=true.
        Alpha/beta UNCHANGED (frozen collision rule).
        Increment computed (80) but not applied."""
        assert math.floor(95 * 85 / 100) == 80
        _, updates, _, _, _, _, _ = _state()
        u = updates[7]
        assert u["polarity"] == "AGAINST"
        assert u["increment"] == 80
        # Frozen: alpha/beta unchanged
        assert u["alpha_before"] == 9900 and u["alpha_after"] == 9900
        assert u["beta_before"] == 100 and u["beta_after"] == 100
        assert u["frozen_before"] == 1 and u["frozen_after"] == 1

    def test_obs9_CD_deny_constraint(self) -> None:
        """obs9: C→D, DENY/CONSTRAINT_DENY, DIRECT, sq=75
        inc = floor(95 * 75 / 100) = 71.
        Edge: (77,1) → (77, 72, REFUTED)."""
        assert math.floor(95 * 75 / 100) == 71
        _, updates, _, _, _, _, _ = _state()
        u = updates[8]
        assert u["polarity"] == "AGAINST"
        assert u["increment"] == 71
        assert u["alpha_before"] == 77 and u["alpha_after"] == 77
        assert u["beta_before"] == 1 and u["beta_after"] == 72


# ===================================================================
# Final edge states
# ===================================================================


class TestRichFinalEdges:
    def test_AB(self) -> None:
        edges, _, _, _, _, _, _ = _state()
        ab = edges["role-A->role-B"]
        assert ab["alpha_i"] == 81 and ab["beta_i"] == 86
        assert ab["status"] == "REFUTED" and ab["frozen"] == 0

    def test_AC_frozen(self) -> None:
        edges, _, _, _, _, _, _ = _state()
        ac = edges["role-A->role-C"]
        assert ac["alpha_i"] == 9900 and ac["beta_i"] == 100
        assert ac["status"] == "CONFIRMED" and ac["frozen"] == 1

    def test_BD_confirmed_despite_low_ratio(self) -> None:
        """B→D: alpha=67, beta=91 → p≈0.424. CONFIRMED because last obs was SUPPORT."""
        edges, _, _, _, _, _, _ = _state()
        bd = edges["role-B->role-D"]
        assert bd["alpha_i"] == 67 and bd["beta_i"] == 91
        assert bd["status"] == "CONFIRMED"
        assert bd["frozen"] == 0

    def test_CD(self) -> None:
        edges, _, _, _, _, _, _ = _state()
        cd = edges["role-C->role-D"]
        assert cd["alpha_i"] == 77 and cd["beta_i"] == 72
        assert cd["status"] == "REFUTED" and cd["frozen"] == 0

    def test_DE_frozen_with_conflict(self) -> None:
        edges, _, _, _, _, _, _ = _state()
        de = edges["role-D->role-E"]
        assert de["alpha_i"] == 9900 and de["beta_i"] == 100
        assert de["frozen"] == 1
        import json
        flags = json.loads(de["flags_json"])
        assert flags["conflict"] is True


# ===================================================================
# Template aggregation
# ===================================================================


class TestRichTemplate:
    def test_template_all_9_obs_eligible(self) -> None:
        """All 9 obs are eligible (non-cf, DIRECT/DETERMINISTIC, ALLOW/DENY).
        Even obs8 on frozen D→E still aggregates to template.

        alpha_agg: 1 + 80(obs1) + 100(obs3) + 66(obs5) + 76(obs6) + 100(obs7) = 423
        beta_agg:  1 + 85(obs2) + 90(obs4) + 80(obs8) + 71(obs9) = 327
        samples: 9"""
        hand_alpha = 1 + 80 + 100 + 66 + 76 + 100
        hand_beta = 1 + 85 + 90 + 80 + 71
        assert hand_alpha == 423
        assert hand_beta == 327

        _, _, tpl, _, _, _, _ = _state()
        assert tpl["alpha_agg_i"] == 423
        assert tpl["beta_agg_i"] == 327
        assert tpl["sample_count"] == 9


# ===================================================================
# Constraint validation
# ===================================================================


class TestRichConstraintValidation:
    def test_scp1_validated(self) -> None:
        """SCP1 (ou-prod-001) linked to {A→B, B→D}.
        Qualifying obs (relevance: reason_class=CONSTRAINT_DENY or cr=1):
          obs2 on A→B: DENY/CONSTRAINT_DENY/DIRECT/cr=1 → qualifies, src=A
          obs4 on B→D: DENY/CONSTRAINT_DENY/DIRECT/cr=1 → qualifies, src=B
        Distinct edges: 2, distinct sources: 2. N=2, M=2 → VALIDATED."""
        _, _, _, _, constraints, _, _ = _state()
        scp_validated = [c for c in constraints
                         if c["constraint_type"] == "SCP"
                         and c["validation_status"] == "VALIDATED"]
        assert len(scp_validated) == 1

    def test_scp2_unvalidated(self) -> None:
        """SCP2 (ou-dev-001) linked to {A→C, C→D}.
        Qualifying obs:
          A→C: obs3 is DETERMINISTIC/ALLOW/cr=0. NOT CONSTRAINT_DENY, cr=0 → not relevant.
          C→D: obs9 is CONSTRAINT_DENY/DIRECT/cr=1 → qualifies, src=C.
          C→D: obs6 is ALLOW/UNKNOWN/cr=0 → not relevant.
        Only 1 qualifying edge (C→D) < N=2 → UNVALIDATED."""
        _, _, _, _, constraints, _, _ = _state()
        scp_unvalidated = [c for c in constraints
                           if c["constraint_type"] == "SCP"
                           and c["validation_status"] == "UNVALIDATED"]
        assert len(scp_unvalidated) == 1

    def test_trust_condition_validated(self) -> None:
        """TC1 linked to D→E. TRUST_CONDITION needs ≥1 qualifying obs.
        obs7: DETERMINISTIC/ALLOW → qualifies. → VALIDATED."""
        _, _, _, _, constraints, _, _ = _state()
        tc = [c for c in constraints if c["constraint_type"] == "TRUST_CONDITION"]
        assert len(tc) == 1
        assert tc[0]["validation_status"] == "VALIDATED"


# ===================================================================
# Correlation grouping
# ===================================================================


class TestRichCorrelation:
    def test_scp1_groups_AB_and_BD(self) -> None:
        """SCP1 creates one component. A→B and B→D share same p_worst signature."""
        edges, _, _, _, _, corr, _ = _state()
        ab_id = edges["role-A->role-B"]["edge_id"]
        bd_id = edges["role-B->role-D"]["edge_id"]
        groups = corr["edge_groups"]
        assert groups[ab_id]["p_worst_sig"] == groups[bd_id]["p_worst_sig"]

    def test_scp2_groups_AC_and_CD(self) -> None:
        """SCP2 creates one component. A→C and C→D share same p_worst signature."""
        edges, _, _, _, _, corr, _ = _state()
        ac_id = edges["role-A->role-C"]["edge_id"]
        cd_id = edges["role-C->role-D"]["edge_id"]
        groups = corr["edge_groups"]
        assert groups[ac_id]["p_worst_sig"] == groups[cd_id]["p_worst_sig"]

    def test_groups_dont_cross(self) -> None:
        """SCP1 and SCP2 are separate components — signatures differ."""
        edges, _, _, _, _, corr, _ = _state()
        ab_id = edges["role-A->role-B"]["edge_id"]
        ac_id = edges["role-A->role-C"]["edge_id"]
        groups = corr["edge_groups"]
        assert groups[ab_id]["p_worst_sig"] != groups[ac_id]["p_worst_sig"]

    def test_de_has_own_group(self) -> None:
        """D→E is TC component — different from both SCPs."""
        edges, _, _, _, _, corr, _ = _state()
        de_id = edges["role-D->role-E"]["edge_id"]
        ab_id = edges["role-A->role-B"]["edge_id"]
        groups = corr["edge_groups"]
        assert groups[de_id]["p_worst_sig"] != groups[ab_id]["p_worst_sig"]

    def test_three_p_worst_groups(self) -> None:
        """3 correlation groups: SCP1, SCP2, TC1."""
        _, _, _, _, _, corr, _ = _state()
        assert len(corr["p_worst_reps"]) == 3


# ===================================================================
# Path probability — full hand computation
# ===================================================================


class TestRichPathProbability:
    def test_path_ABDE_probability(self) -> None:
        """Path A→B→D→E:
        Groups in path: SCP1 (rep=B→D: 67/158), TC1 (rep=D→E: 9900/10000)
        A→B and B→D share SCP1 group → counted once via representative B→D.

        p_BD_q8 = 67 * 10^8 // 158 = 42_405_063
        p_DE_q8 = 9900 * 10^8 // 10000 = 99_000_000
        p_path = 42_405_063 * 99_000_000 // 10^8 = 41_981_012"""
        p_BD_q8 = 67 * Q8 // 158
        p_DE_q8 = 9900 * Q8 // 10000
        hand_p = p_BD_q8 * p_DE_q8 // Q8
        assert p_BD_q8 == 42_405_063
        assert p_DE_q8 == 99_000_000
        assert hand_p == 41_981_012

        _, _, _, topk, _, _, _ = _state()
        # Find the A→B→D→E path (the one with lower probability)
        path_ABDE = [t for t in topk if t["p_worst_q8"] == 41_981_012]
        assert len(path_ABDE) >= 1
        assert path_ABDE[0]["p_worst_q8"] == hand_p

    def test_path_ACDE_probability(self) -> None:
        """Path A→C→D→E:
        Groups: SCP2 (rep=C→D: 77/149), TC1 (rep=D→E: 9900/10000)

        p_CD_q8 = 77 * 10^8 // 149 = 51_677_852
        p_DE_q8 = 99_000_000
        p_path = 51_677_852 * 99_000_000 // 10^8 = 51_161_073"""
        p_CD_q8 = 77 * Q8 // 149
        p_DE_q8 = 9900 * Q8 // 10000
        hand_p = p_CD_q8 * p_DE_q8 // Q8
        assert p_CD_q8 == 51_677_852
        assert p_DE_q8 == 99_000_000
        assert hand_p == 51_161_073

        _, _, _, topk, _, _, _ = _state()
        path_ACDE = [t for t in topk if t["p_worst_q8"] == 51_161_073]
        assert len(path_ACDE) >= 1
        assert path_ACDE[0]["p_worst_q8"] == hand_p

    def test_path_ranking_higher_prob_first(self) -> None:
        """A→C→D→E (51.2%) ranked above A→B→D→E (42.0%)."""
        _, _, _, topk, _, _, conn = _state()
        # Get objective A→E topk (objective with start node role-A)
        node_a = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'role-A'"
        ).fetchone()["node_id"]
        obj_ae = conn.execute(
            "SELECT objective_id FROM objectives WHERE start_nodes_json LIKE ?",
            (f'%{node_a}%',),
        ).fetchone()["objective_id"]
        obj_topk = [t for t in topk if t["objective_id"] == obj_ae]
        assert len(obj_topk) == 2
        assert obj_topk[0]["p_worst_q8"] > obj_topk[1]["p_worst_q8"]  # rank 1 > rank 2
        assert obj_topk[0]["p_worst_q8"] == 51_161_073  # A→C→D→E
        assert obj_topk[1]["p_worst_q8"] == 41_981_012  # A→B→D→E

    def test_p_worst_equals_p_best(self) -> None:
        """Each component has exactly 1 constraint → p_worst == p_best."""
        _, _, _, topk, _, _, _ = _state()
        for t in topk:
            assert t["p_worst_q8"] == t["p_best_q8"]

    def test_objective2_BDE_only_path(self) -> None:
        """Objective B→E has only B→D→E.
        p = 42_405_063 * 99_000_000 // 10^8 = 41_981_012"""
        _, _, _, topk, _, _, conn = _state()
        node_b = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'role-B'"
        ).fetchone()["node_id"]
        obj_be = conn.execute(
            "SELECT objective_id FROM objectives WHERE start_nodes_json LIKE ?",
            (f'%{node_b}%',),
        ).fetchone()["objective_id"]
        obj_topk = [t for t in topk if t["objective_id"] == obj_be]
        assert len(obj_topk) == 1
        assert obj_topk[0]["p_worst_q8"] == 41_981_012
        assert obj_topk[0]["path_length"] == 2

    def test_all_paths_have_conflict_flag(self) -> None:
        """All paths go through D→E which has conflict=true."""
        import json
        _, _, _, topk, _, _, _ = _state()
        for t in topk:
            flags = json.loads(t["flags_json"])
            assert flags["conflict"] is True

    def test_confidence_bands(self) -> None:
        """51.2% → MEDIUM (≥40%), 42.0% → MEDIUM (≥40%)."""
        _, _, _, topk, _, _, _ = _state()
        for t in topk:
            assert t["confidence_band"] == "MEDIUM"


# ===================================================================
# Group representative selection
# ===================================================================


class TestRichRepresentatives:
    def test_scp1_rep_is_BD(self) -> None:
        """SCP1 group {A→B, B→D}. p(A→B)=81/167≈0.485, p(B→D)=67/158≈0.424.
        B→D is worse → representative."""
        # Verify the math
        p_AB = 81 * Q8 // (81 + 86)  # 81/167
        p_BD = 67 * Q8 // (67 + 91)  # 67/158
        assert p_BD < p_AB  # B→D is worse

    def test_scp2_rep_is_CD(self) -> None:
        """SCP2 group {A→C, C→D}. p(A→C)=9900/10000=0.99, p(C→D)=77/149≈0.517.
        C→D is worse → representative."""
        p_AC = 9900 * Q8 // (9900 + 100)
        p_CD = 77 * Q8 // (77 + 72)
        assert p_CD < p_AC


# ===================================================================
# Determinism
# ===================================================================


class TestRichDeterminism:
    def test_hash_stable(self) -> None:
        hashes = set()
        for _ in range(5):
            conn, _ = run_full_pipeline(SCENARIO)
            hashes.add(canonical_run_hash(conn))
        assert len(hashes) == 1
