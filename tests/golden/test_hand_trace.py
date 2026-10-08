"""Hand-trace verification of the minimal scenario.

Every computation is done by hand (inline Python math, no engine imports)
and compared against the actual engine output. If ANY assertion fails,
the engine math is wrong.

Scenario:
  3 nodes: A (role-alpha), B (role-bravo), C (role-charlie)
  2 edges: A→B, B→C (both sts:AssumeRole)
  1 SCP constraint linked to both edges
  3 observations:
    obs1: A→B, ALLOW, UNKNOWN, DIRECT, signal_q=80, evidence_hash=abc123
    obs2: B→C, DENY, CONSTRAINT_DENY, DIRECT, signal_q=90, evidence_hash=def456
    obs3: A→B, ALLOW, UNKNOWN, DIRECT, signal_q=70, evidence_hash=null
         → DOWNGRADED to INFERRED (no evidence_hash)
"""

from __future__ import annotations

import math
from pathlib import Path

from arf_rt.cli import run_full_pipeline


SCENARIO = str(Path(__file__).parent.parent / "fixtures" / "minimal_scenario.json")


def _engine_state():
    conn, _ = run_full_pipeline(SCENARIO)
    edges = {}
    for e in conn.execute(
        "SELECT e.edge_id, n1.provider_id as src, n2.provider_id as dst, "
        "e.alpha_i, e.beta_i, e.status, e.frozen "
        "FROM edges e "
        "JOIN nodes n1 ON n1.node_id = e.src_node_id "
        "JOIN nodes n2 ON n2.node_id = e.dst_node_id "
        "ORDER BY e.edge_id"
    ).fetchall():
        edges[f"{e['src']}->{e['dst']}"] = dict(e)

    tpl = conn.execute(
        "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates"
    ).fetchone()

    updates = conn.execute(
        "SELECT * FROM edge_updates ORDER BY update_id"
    ).fetchall()

    topk = conn.execute(
        "SELECT * FROM derived_topk ORDER BY rank"
    ).fetchall()

    obs = conn.execute(
        "SELECT * FROM observations ORDER BY observation_id"
    ).fetchall()

    return edges, dict(tpl), [dict(u) for u in updates], [dict(t) for t in topk], [dict(o) for o in obs]


class TestHandTrace:
    """Every value computed by hand, then compared to engine."""

    def test_observation_downgrade(self) -> None:
        """Obs3 had strength=DIRECT but evidence_hash=null.
        Spec §18.4: downgrade to INFERRED, emit warning."""
        _, _, _, _, obs = _engine_state()
        # Obs3 is the third observation
        assert obs[2]["strength"] == "INFERRED"  # was DIRECT, downgraded
        assert obs[2]["evidence_hash"] is None

    def test_obs1_polarity_and_increment(self) -> None:
        """Obs1: ALLOW + UNKNOWN → SUPPORT polarity.
        DIRECT base_w_q = 95.
        inc = floor(95 * 80 / 100) = floor(76.0) = 76."""
        hand_base_w = 95  # DIRECT
        hand_signal_q = 80
        hand_inc = math.floor(hand_base_w * hand_signal_q / 100)
        assert hand_inc == 76

        _, _, updates, _, _ = _engine_state()
        assert updates[0]["polarity"] == "SUPPORT"
        assert updates[0]["increment"] == 76

    def test_obs1_edge_update(self) -> None:
        """After obs1 on A→B:
        alpha: 1 + 76 = 77
        beta: 1 (unchanged, SUPPORT doesn't touch beta)
        status: CONFIRMED (polarity=SUPPORT)"""
        _, _, updates, _, _ = _engine_state()
        assert updates[0]["alpha_before"] == 1
        assert updates[0]["beta_before"] == 1
        assert updates[0]["alpha_after"] == 77
        assert updates[0]["beta_after"] == 1

    def test_obs2_polarity_and_increment(self) -> None:
        """Obs2: DENY + CONSTRAINT_DENY → AGAINST polarity.
        DIRECT base_w_q = 95.
        inc = floor(95 * 90 / 100) = floor(85.5) = 85."""
        hand_inc = math.floor(95 * 90 / 100)
        assert hand_inc == 85

        _, _, updates, _, _ = _engine_state()
        assert updates[1]["polarity"] == "AGAINST"
        assert updates[1]["increment"] == 85

    def test_obs2_edge_update(self) -> None:
        """After obs2 on B→C:
        alpha: 1 (unchanged, AGAINST doesn't touch alpha)
        beta: 1 + 85 = 86
        status: REFUTED (polarity=AGAINST)"""
        _, _, updates, _, _ = _engine_state()
        assert updates[1]["alpha_before"] == 1
        assert updates[1]["beta_before"] == 1
        assert updates[1]["alpha_after"] == 1
        assert updates[1]["beta_after"] == 86

    def test_obs3_downgraded_polarity_and_increment(self) -> None:
        """Obs3: ALLOW + UNKNOWN → SUPPORT.
        But strength was downgraded DIRECT → INFERRED.
        INFERRED base_w_q = 60.
        inc = floor(60 * 70 / 100) = floor(42.0) = 42."""
        hand_inc = math.floor(60 * 70 / 100)
        assert hand_inc == 42

        _, _, updates, _, _ = _engine_state()
        assert updates[2]["polarity"] == "SUPPORT"
        assert updates[2]["increment"] == 42

    def test_obs3_edge_update(self) -> None:
        """After obs3 on A→B (second update to this edge):
        alpha: 77 + 42 = 119
        beta: 1 (unchanged)"""
        _, _, updates, _, _ = _engine_state()
        assert updates[2]["alpha_before"] == 77
        assert updates[2]["beta_before"] == 1
        assert updates[2]["alpha_after"] == 119
        assert updates[2]["beta_after"] == 1

    def test_final_edge_ab(self) -> None:
        """Edge A→B final state: alpha=119, beta=1, CONFIRMED, not frozen.
        Mass cap check: 119+1=120 < 20000, so no capping."""
        edges, _, _, _, _ = _engine_state()
        ab = edges["role-alpha->role-bravo"]
        assert ab["alpha_i"] == 119
        assert ab["beta_i"] == 1
        assert ab["status"] == "CONFIRMED"
        assert ab["frozen"] == 0

    def test_final_edge_bc(self) -> None:
        """Edge B→C final state: alpha=1, beta=86, REFUTED, not frozen.
        Mass cap check: 1+86=87 < 20000, so no capping."""
        edges, _, _, _, _ = _engine_state()
        bc = edges["role-bravo->role-charlie"]
        assert bc["alpha_i"] == 1
        assert bc["beta_i"] == 86
        assert bc["status"] == "REFUTED"
        assert bc["frozen"] == 0

    def test_template_aggregation(self) -> None:
        """Template aggregation:
        Initial: alpha_agg=1, beta_agg=1, samples=0

        Obs1: eligible (DIRECT, ALLOW, not counterfactual)
          polarity=SUPPORT, inc=76 → alpha_agg = 1+76 = 77, samples=1

        Obs2: eligible (DIRECT, DENY, not counterfactual)
          polarity=AGAINST, inc=85 → beta_agg = 1+85 = 86, samples=2

        Obs3: eligible (INFERRED, ALLOW, not counterfactual)
          INFERRED is in {DIRECT, DETERMINISTIC, INFERRED} → eligible
          polarity=SUPPORT, inc=42 → alpha_agg = 77+42 = 119, samples=3

        Final: alpha_agg=119, beta_agg=86, samples=3
        Mass cap: 119+86=205 < 200000, no capping."""
        _, tpl, _, _, _ = _engine_state()
        assert tpl["alpha_agg_i"] == 119
        assert tpl["beta_agg_i"] == 86
        assert tpl["sample_count"] == 3

    def test_path_probability_q8(self) -> None:
        """Path A→B→C probability:
        No eligible constraints (SCP confidence_q=0 < 500 threshold)
        → each edge gets its own group → no correlation grouping
        → p = product of individual edge probabilities

        Edge A→B: p = alpha/(alpha+beta) = 119/120
        Edge B→C: p = alpha/(alpha+beta) = 1/87

        In Q8 (multiply by 100_000_000):
          p_AB_q8 = floor(119 * 100_000_000 / 120) = floor(99166666.67) = 99166666
          p_BC_q8 = floor(1 * 100_000_000 / 87)   = floor(1149425.29)  = 1149425

        Path product in Q8:
          p_path_q8 = floor(p_AB_q8 * p_BC_q8 / 100_000_000)
                    = floor(99166666 * 1149425 / 100_000_000)
                    = floor(113996839...)
                    
        Let me compute this more carefully."""

        Q8 = 100_000_000

        # Edge A→B
        ab_alpha, ab_beta = 119, 1
        p_ab_q8 = ab_alpha * Q8 // (ab_alpha + ab_beta)
        # 119 * 100000000 // 120 = 11900000000 // 120 = 99166666
        assert p_ab_q8 == 99166666

        # Edge B→C
        bc_alpha, bc_beta = 1, 86
        p_bc_q8 = bc_alpha * Q8 // (bc_alpha + bc_beta)
        # 1 * 100000000 // 87 = 100000000 // 87 = 1149425
        assert p_bc_q8 == 1149425

        # Path product
        p_path_q8 = p_ab_q8 * p_bc_q8 // Q8
        # 99166666 * 1149425 // 100000000 = 113989273...
        # let me compute: 99166666 * 1149425 = ?
        product = 99166666 * 1149425
        p_path_q8 = product // Q8

        _, _, _, topk, _ = _engine_state()
        engine_pw = topk[0]["p_worst_q8"]
        engine_pb = topk[0]["p_best_q8"]

        assert engine_pw == p_path_q8, \
            f"Hand: {p_path_q8}, Engine: {engine_pw}, product={product}"
        # p_best = p_worst when no correlation grouping
        assert engine_pb == engine_pw

    def test_confidence_band(self) -> None:
        """p_worst_q8 ~ 1.14M out of 100M = ~1.14%
        Band thresholds: >=90%=VERY_HIGH, >=70%=HIGH, >=40%=MEDIUM,
                         >=15%=LOW, >=1%=VERY_LOW, <1%=INSUFFICIENT
        1.14% → VERY_LOW"""
        Q8 = 100_000_000
        _, _, _, topk, _ = _engine_state()
        pw = topk[0]["p_worst_q8"]
        pct = pw * 100 // Q8
        # pct = 1139846 * 100 // 100000000 = 113984600 // 100000000 = 1
        assert pct >= 1  # ≥1% → VERY_LOW
        assert pct < 15  # <15% → not LOW
        assert topk[0]["confidence_band"] == "VERY_LOW"

    def test_constraint_validation(self) -> None:
        """SCP validation:
        Relevance rule: count obs where reason_class=CONSTRAINT_DENY
          or constraint_relevant=1.
        Qualifying obs must be non-counterfactual, DIRECT or DETERMINISTIC.

        Obs1 on A→B: ALLOW, UNKNOWN, cr=0 → NOT relevant (not CONSTRAINT_DENY, cr=0)
        Obs2 on B→C: DENY, CONSTRAINT_DENY, cr=1 → RELEVANT, qualifying
        Obs3 on A→B: ALLOW, UNKNOWN, cr=0 → NOT relevant
          (also INFERRED after downgrade, so wouldn't qualify anyway)

        Distinct qualifying edges: 1 (B→C only)
        Distinct sources: 1 (role-bravo only)
        Threshold: N=2, M=2
        1 < 2 → UNVALIDATED"""
        # This is just checking the engine agrees
        conn, _ = run_full_pipeline(SCENARIO)
        cst = conn.execute(
            "SELECT validation_status FROM constraints"
        ).fetchone()
        assert cst["validation_status"] == "UNVALIDATED"

    def test_evidence_coverage(self) -> None:
        """Coverage: edges with ≥1 DIRECT/DETERMINISTIC non-counterfactual obs.
        
        A→B: obs1 is DIRECT, non-cf → OBSERVED
        B→C: obs2 is DIRECT, non-cf → OBSERVED
        (obs3 on A→B is INFERRED after downgrade, but obs1 already counts)
        
        2 of 2 edges = 100%"""
        conn, _ = run_full_pipeline(SCENARIO)
        observed = conn.execute(
            """SELECT COUNT(DISTINCT edge_id) FROM observations
               WHERE strength IN ('DIRECT', 'DETERMINISTIC')
                 AND is_counterfactual = 0"""
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert observed == 2
        assert total == 2
        assert round(100 * observed / total) == 100
