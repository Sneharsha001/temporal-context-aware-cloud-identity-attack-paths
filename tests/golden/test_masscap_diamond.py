"""Hand-trace: mass-cap trigger and diamond correlation.

Mass-cap: 220 DIRECT ALLOW observations → edge mass exceeds 20000, cap fires.
Diamond: cross-constraint linking causes 55%→1.2% probability collapse.
"""

from __future__ import annotations

import math
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.config import MAX_EDGE_MASS, MAX_TEMPLATE_MASS
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.snapshot import canonical_run_hash

Q8 = 100_000_000
MASSCAP = str(Path(__file__).parent.parent / "fixtures" / "masscap_scenario.json")
DIAMOND = str(Path(__file__).parent.parent / "fixtures" / "diamond_scenario.json")


# ===================================================================
# Mass cap
# ===================================================================


class TestMassCapTrigger:
    """220 DIRECT ALLOW at signal_q=100 → inc=95 each.
    Raw alpha would be 1 + 220*95 = 20901. Mass = 20902 > 20000."""

    def test_raw_alpha_exceeds_cap(self) -> None:
        raw_alpha = 1 + 220 * math.floor(95 * 100 / 100)
        assert raw_alpha == 20901
        assert raw_alpha + 1 > MAX_EDGE_MASS

    def test_edge_capped_to_max_mass(self) -> None:
        conn, _ = run_full_pipeline(MASSCAP)
        e = conn.execute("SELECT alpha_i, beta_i FROM edges").fetchone()
        assert e["alpha_i"] + e["beta_i"] <= MAX_EDGE_MASS

    def test_edge_alpha_is_19999(self) -> None:
        """After cap: alpha = max(1, floor(raw_alpha * 20000 / mass)).
        At the cap boundary the ratio is ~0.99995, so alpha ≈ 19999."""
        conn, _ = run_full_pipeline(MASSCAP)
        e = conn.execute("SELECT alpha_i, beta_i FROM edges").fetchone()
        assert e["alpha_i"] == 19999
        assert e["beta_i"] == 1

    def test_cap_triggers_at_update_211(self) -> None:
        """First 210 updates: alpha goes 1→96→191→...→19951.
        Update 211: alpha_before=19951, +95=20046 > 20000 → cap fires."""
        conn, _ = run_full_pipeline(MASSCAP)
        # Update 210: alpha_after should be 1 + 210*95 = 19951
        u210 = conn.execute(
            "SELECT alpha_after, beta_after FROM edge_updates WHERE update_id = 210"
        ).fetchone()
        assert u210["alpha_after"] == 1 + 210 * 95  # 19951
        assert u210["alpha_after"] + u210["beta_after"] <= MAX_EDGE_MASS

        # Update 211: would be 19951+95=20046, but cap fires
        u211 = conn.execute(
            "SELECT alpha_before, alpha_after, beta_after FROM edge_updates WHERE update_id = 211"
        ).fetchone()
        assert u211["alpha_before"] == 19951
        assert u211["alpha_after"] == 19999  # capped
        assert u211["alpha_after"] + u211["beta_after"] == MAX_EDGE_MASS

    def test_subsequent_updates_stay_capped(self) -> None:
        """Updates 212-220 all produce capped results."""
        conn, _ = run_full_pipeline(MASSCAP)
        for uid in range(212, 221):
            u = conn.execute(
                "SELECT alpha_after, beta_after FROM edge_updates WHERE update_id = ?",
                (uid,),
            ).fetchone()
            assert u["alpha_after"] + u["beta_after"] <= MAX_EDGE_MASS

    def test_template_not_capped(self) -> None:
        """Template mass 20902 < MAX_TEMPLATE_MASS 200000 → no cap."""
        conn, _ = run_full_pipeline(MASSCAP)
        t = conn.execute("SELECT alpha_agg_i, beta_agg_i FROM templates").fetchone()
        assert t["alpha_agg_i"] == 1 + 220 * 95  # 20901
        assert t["beta_agg_i"] == 1
        assert t["alpha_agg_i"] + t["beta_agg_i"] < MAX_TEMPLATE_MASS

    def test_path_probability_uses_capped_values(self) -> None:
        """Path probability should use capped (19999, 1), not raw."""
        conn, _ = run_full_pipeline(MASSCAP)
        topk = conn.execute(
            "SELECT p_worst_q8 FROM derived_topk"
        ).fetchone()
        expected = 19999 * Q8 // (19999 + 1)  # 99995000
        assert topk["p_worst_q8"] == expected

    def test_deterministic(self) -> None:
        hashes = set()
        for _ in range(3):
            conn, _ = run_full_pipeline(MASSCAP)
            hashes.add(canonical_run_hash(conn))
        assert len(hashes) == 1


# ===================================================================
# Diamond correlation
# ===================================================================


class TestDiamondCorrelation:
    """Diamond: A→B→D and A→C→D.

    SCP links {A→B, C→D} — cross-constraint!
    A→B strong individually (91/163 ≈ 0.558), C→D weak (1/82 ≈ 0.012).
    Correlation forces A→B to use C→D as representative → 55% collapses to 1.2%.

    This is the core value proposition: an SCP that blocks C→D also
    governs A→B, so A→B's apparent strength is illusory.
    """

    # --- Belief updates ---

    def test_obs1_AB_allow(self) -> None:
        """obs1: A→B, ALLOW, DIRECT, sq=95. inc=floor(95*95/100)=90."""
        assert math.floor(95 * 95 / 100) == 90
        conn, _ = run_full_pipeline(DIAMOND)
        u = conn.execute(
            "SELECT increment, polarity FROM edge_updates WHERE update_id = 1"
        ).fetchone()
        assert u["increment"] == 90 and u["polarity"] == "SUPPORT"

    def test_obs4_CD_deny(self) -> None:
        """obs4: C→D, DENY/CONSTRAINT_DENY, DIRECT, sq=85. inc=floor(95*85/100)=80."""
        assert math.floor(95 * 85 / 100) == 80
        conn, _ = run_full_pipeline(DIAMOND)
        e = conn.execute("""
            SELECT e.alpha_i, e.beta_i FROM edges e
            JOIN nodes n1 ON n1.node_id=e.src_node_id
            JOIN nodes n2 ON n2.node_id=e.dst_node_id
            WHERE n1.provider_id='C' AND n2.provider_id='D'
        """).fetchone()
        assert e["alpha_i"] == 1 and e["beta_i"] == 81  # 1 + 80

    def test_obs5_AB_deny_makes_refuted(self) -> None:
        """obs5: A→B, DENY/CONSTRAINT_DENY, sq=75. inc=floor(95*75/100)=71.
        A→B goes from (91,1,CONFIRMED) → (91,72,REFUTED)."""
        assert math.floor(95 * 75 / 100) == 71
        conn, _ = run_full_pipeline(DIAMOND)
        e = conn.execute("""
            SELECT e.alpha_i, e.beta_i, e.status FROM edges e
            JOIN nodes n1 ON n1.node_id=e.src_node_id
            JOIN nodes n2 ON n2.node_id=e.dst_node_id
            WHERE n1.provider_id='A' AND n2.provider_id='B'
        """).fetchone()
        assert e["alpha_i"] == 91 and e["beta_i"] == 72
        assert e["status"] == "REFUTED"

    # --- Correlation grouping ---

    def test_scp_groups_AB_and_CD(self) -> None:
        """SCP links A→B and C→D into one group."""
        conn, _ = run_full_pipeline(DIAMOND)
        corr = compute_correlation(conn)
        import json
        eids = {}
        for e in conn.execute("""
            SELECT e.edge_id, n1.provider_id||'→'||n2.provider_id as name
            FROM edges e JOIN nodes n1 ON n1.node_id=e.src_node_id
            JOIN nodes n2 ON n2.node_id=e.dst_node_id
        """).fetchall():
            eids[e["name"]] = e["edge_id"]

        groups = corr["edge_groups"]
        ab_sig = groups[eids["A→B"]]["p_worst_sig"]
        cd_sig = groups[eids["C→D"]]["p_worst_sig"]
        assert ab_sig == cd_sig, "A→B and C→D should share SCP group"

    def test_BD_and_AC_are_standalone(self) -> None:
        """B→D and A→C have no constraints → NONE groups."""
        conn, _ = run_full_pipeline(DIAMOND)
        corr = compute_correlation(conn)
        import json
        for name in ("B", "C"):
            for e in conn.execute("""
                SELECT e.edge_id, n1.provider_id as src, n2.provider_id as dst
                FROM edges e JOIN nodes n1 ON n1.node_id=e.src_node_id
                JOIN nodes n2 ON n2.node_id=e.dst_node_id
            """).fetchall():
                sig = json.loads(corr["edge_groups"][e["edge_id"]]["p_worst_sig"])
                if e["src"] == "B" and e["dst"] == "D":
                    assert sig[0][0] == "NONE"
                if e["src"] == "A" and e["dst"] == "C":
                    assert sig[0][0] == "NONE"

    def test_representative_is_CD(self) -> None:
        """C→D (1/82) is weaker than A→B (91/163) → C→D is rep.
        Cross-multiply: 1*(91+72) vs 91*(1+81) → 163 vs 7462 → C→D wins."""
        assert 1 * (91 + 72) < 91 * (1 + 81)  # 163 < 7462

        conn, _ = run_full_pipeline(DIAMOND)
        corr = compute_correlation(conn)
        import json
        cd_eid = conn.execute("""
            SELECT e.edge_id FROM edges e
            JOIN nodes n1 ON n1.node_id=e.src_node_id
            JOIN nodes n2 ON n2.node_id=e.dst_node_id
            WHERE n1.provider_id='C' AND n2.provider_id='D'
        """).fetchone()["edge_id"]

        ab_sig = corr["edge_groups"][cd_eid]["p_worst_sig"]
        rep = corr["p_worst_reps"][ab_sig]
        assert rep == cd_eid, "Representative should be C→D (weakest)"

    # --- Path probability: naive vs correlated ---

    def test_naive_path_ABD_is_55pct(self) -> None:
        """Without correlation: p(A→B)*p(B→D) = (91/163)*(86/87) ≈ 55.2%."""
        p_AB_q8 = 91 * Q8 // 163  # 55828220
        p_BD_q8 = 86 * Q8 // 87   # 98850574
        naive = p_AB_q8 * p_BD_q8 // Q8
        assert naive > 50_000_000  # > 50%

    def test_correlated_path_ABD_is_1pct(self) -> None:
        """With correlation: rep(SCP)=C→D(1/82) × p(B→D)=(86/87) ≈ 1.2%.
        The 55% naive estimate collapses to 1.2% because A→B shares
        the SCP with the observed-blocked C→D."""
        p_CD_q8 = 1 * Q8 // 82    # 1219512
        p_BD_q8 = 86 * Q8 // 87   # 98850574
        correlated = p_CD_q8 * p_BD_q8 // Q8
        assert correlated < 2_000_000  # < 2%

        conn, _ = run_full_pipeline(DIAMOND)
        topk = conn.execute(
            "SELECT p_worst_q8 FROM derived_topk ORDER BY rank"
        ).fetchall()
        assert topk[0]["p_worst_q8"] == correlated

    def test_correlation_collapses_ratio(self) -> None:
        """Quantify the collapse: naive/correlated ratio > 40x."""
        p_AB_q8 = 91 * Q8 // 163
        p_BD_q8 = 86 * Q8 // 87
        naive = p_AB_q8 * p_BD_q8 // Q8

        p_CD_q8 = 1 * Q8 // 82
        correlated = p_CD_q8 * p_BD_q8 // Q8

        ratio = naive / correlated
        assert ratio > 40, f"Expected >40x collapse, got {ratio:.1f}x"

    def test_path_ranking_with_exact_values(self) -> None:
        """Path A→B→D (1.21%) edges out A→C→D (1.20%).
        A→B→D: rep(SCP)=C→D × B→D = (1/82)*(86/87)
        A→C→D: A→C × rep(SCP)=C→D = (77/78)*(1/82)"""
        p_CD_q8 = 1 * Q8 // 82      # 1219512
        p_BD_q8 = 86 * Q8 // 87     # 98850574
        p_AC_q8 = 77 * Q8 // 78     # 98717948

        path1 = p_CD_q8 * p_BD_q8 // Q8  # A→B→D
        path2 = p_AC_q8 * p_CD_q8 // Q8  # A→C→D

        assert path1 > path2, f"Path1={path1} should beat Path2={path2}"

        conn, _ = run_full_pipeline(DIAMOND)
        topk = conn.execute(
            "SELECT rank, p_worst_q8 FROM derived_topk ORDER BY rank"
        ).fetchall()
        assert topk[0]["p_worst_q8"] == path1
        assert topk[1]["p_worst_q8"] == path2

    def test_both_paths_very_low_band(self) -> None:
        """1.2% → VERY_LOW (≥1%, <15%)."""
        conn, _ = run_full_pipeline(DIAMOND)
        for row in conn.execute("SELECT confidence_band FROM derived_topk"):
            assert row["confidence_band"] == "VERY_LOW"

    def test_deterministic(self) -> None:
        hashes = set()
        for _ in range(5):
            conn, _ = run_full_pipeline(DIAMOND)
            hashes.add(canonical_run_hash(conn))
        assert len(hashes) == 1
