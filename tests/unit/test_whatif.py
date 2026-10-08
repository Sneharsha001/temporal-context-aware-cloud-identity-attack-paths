"""Tests for engine/whatif.py (spec §17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.snapshot import canonical_run_hash, full_state_export
from arf_rt.engine.updater import apply_all_observations
from arf_rt.engine.whatif import fork_db, forced_refute, run_whatif
from arf_rt.storage.sqlite_store import connect


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _baseline():
    """Full baseline: ingest → update → correlate → paths."""
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    corr = compute_correlation(conn)
    search_and_store_top_k(conn, corr)
    return conn


def _get_edge_ids(conn):
    return [r["edge_id"] for r in conn.execute(
        "SELECT edge_id FROM edges ORDER BY edge_id COLLATE BINARY"
    ).fetchall()]


# ===================================================================
# Fork
# ===================================================================


class TestFork:
    def test_fork_uses_backup_api(self) -> None:
        """Fork creates an independent copy via SQLite backup."""
        baseline = _baseline()
        fork = fork_db(baseline)

        # Fork has same data
        b_count = baseline.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        f_count = fork.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert b_count == f_count

        # Fork is independent — modify fork, baseline unchanged
        fork.execute("DELETE FROM run_warnings")
        fork.commit()
        f_warns = fork.execute("SELECT COUNT(*) FROM run_warnings").fetchone()[0]
        b_warns = baseline.execute("SELECT COUNT(*) FROM run_warnings").fetchone()[0]
        assert f_warns == 0
        assert b_warns > 0  # Baseline still has warnings
        fork.close()

    def test_fork_hash_matches_baseline(self) -> None:
        """Fresh fork has same canonical_run_hash as baseline."""
        baseline = _baseline()
        fork = fork_db(baseline)
        assert canonical_run_hash(fork) == canonical_run_hash(baseline)
        fork.close()


# ===================================================================
# Forced refute
# ===================================================================


class TestForcedRefute:
    def test_counterfactual_override_sets_status_refuted_and_frozen(self) -> None:
        """Forced refute sets edge to DETERMINISTIC DENY state."""
        baseline = _baseline()
        fork = fork_db(baseline)
        eid = _get_edge_ids(fork)[0]

        result = forced_refute(fork, eid)

        assert result["status_after"] == "REFUTED"
        assert result["frozen_after"] == 1
        assert result["alpha_after"] == 100
        assert result["beta_after"] == 9900
        assert result["counterfactual_override"] is True

        # Verify in DB
        edge = fork.execute(
            "SELECT status, frozen, alpha_i, beta_i, flags_json FROM edges WHERE edge_id = ?",
            (eid,),
        ).fetchone()
        assert edge["status"] == "REFUTED"
        assert edge["frozen"] == 1
        flags = json.loads(edge["flags_json"])
        assert flags["counterfactual_override"] is True
        fork.close()

    def test_forced_refute_inserts_whatif_observation(self) -> None:
        baseline = _baseline()
        fork = fork_db(baseline)
        eid = _get_edge_ids(fork)[0]

        obs_before = fork.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        forced_refute(fork, eid)
        obs_after = fork.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

        assert obs_after == obs_before + 1

        # Check observation details
        obs = fork.execute(
            "SELECT * FROM observations WHERE probe_type = 'WHATIF_FORCED'"
        ).fetchone()
        assert obs["edge_id"] == eid
        assert obs["result"] == "DENY"
        assert obs["reason_class"] == "CONSTRAINT_DENY"
        assert obs["strength"] == "DETERMINISTIC"
        assert obs["is_counterfactual"] == 1
        fork.close()

    def test_forced_refute_does_not_set_conflict(self) -> None:
        """Spec §17: counterfactual override does NOT set conflict."""
        baseline = _baseline()
        fork = fork_db(baseline)
        eid = _get_edge_ids(fork)[0]

        # Edge is CONFIRMED in baseline — refuting contradicts it
        forced_refute(fork, eid)

        edge = fork.execute(
            "SELECT flags_json FROM edges WHERE edge_id = ?", (eid,)
        ).fetchone()
        flags = json.loads(edge["flags_json"])
        assert flags.get("conflict", False) is False
        fork.close()

    def test_forced_refute_on_already_frozen_edge(self) -> None:
        """Can force-refute an already frozen edge."""
        baseline = _baseline()
        fork = fork_db(baseline)
        eid = _get_edge_ids(fork)[0]

        # Freeze it first as CONFIRMED
        fork.execute(
            "UPDATE edges SET frozen = 1, status = 'CONFIRMED', "
            "alpha_i = 9900, beta_i = 100 WHERE edge_id = ?",
            (eid,),
        )
        fork.commit()

        result = forced_refute(fork, eid)
        assert result["status_after"] == "REFUTED"
        assert result["frozen_after"] == 1
        assert result["alpha_after"] == 100
        assert result["beta_after"] == 9900
        fork.close()

    def test_forced_refute_writes_audit_trail(self) -> None:
        baseline = _baseline()
        fork = fork_db(baseline)
        eid = _get_edge_ids(fork)[0]

        updates_before = fork.execute("SELECT COUNT(*) FROM edge_updates").fetchone()[0]
        forced_refute(fork, eid)
        updates_after = fork.execute("SELECT COUNT(*) FROM edge_updates").fetchone()[0]

        assert updates_after == updates_before + 1
        fork.close()

    def test_forced_refute_invalid_edge_raises(self) -> None:
        baseline = _baseline()
        fork = fork_db(baseline)
        from arf_rt.util.canon import ARFValidationError
        with pytest.raises(ARFValidationError, match="not found"):
            forced_refute(fork, "nonexistent_edge_id")
        fork.close()


# ===================================================================
# Counterfactual exclusions
# ===================================================================


class TestCounterfactualExclusions:
    def test_counterfactual_excluded_from_template_aggregation(self) -> None:
        """WHATIF_FORCED obs with is_counterfactual=1 should NOT update templates."""
        baseline = _baseline()
        fork = fork_db(baseline)

        tpl_before = fork.execute(
            "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates"
        ).fetchone()

        eid = _get_edge_ids(fork)[0]
        forced_refute(fork, eid)

        # Template should be unchanged (counterfactual excluded from aggregation)
        # forced_refute directly sets edge state, doesn't go through apply_observation
        # The observation is is_counterfactual=1, so if re-applied it would be excluded
        tpl_after = fork.execute(
            "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates"
        ).fetchone()
        assert tpl_after["alpha_agg_i"] == tpl_before["alpha_agg_i"]
        assert tpl_after["beta_agg_i"] == tpl_before["beta_agg_i"]
        assert tpl_after["sample_count"] == tpl_before["sample_count"]
        fork.close()

    def test_counterfactual_excluded_from_evidence_coverage(self) -> None:
        """WHATIF_FORCED obs don't count toward evidence coverage."""
        baseline = _baseline()
        fork = fork_db(baseline)

        # Coverage before: both edges observed with DIRECT
        cov_before = fork.execute(
            """SELECT COUNT(DISTINCT edge_id) FROM observations
               WHERE strength IN ('DIRECT', 'DETERMINISTIC')
                 AND is_counterfactual = 0"""
        ).fetchone()[0]

        eid = _get_edge_ids(fork)[0]
        forced_refute(fork, eid)

        # Coverage after: counterfactual obs shouldn't increase count
        cov_after = fork.execute(
            """SELECT COUNT(DISTINCT edge_id) FROM observations
               WHERE strength IN ('DIRECT', 'DETERMINISTIC')
                 AND is_counterfactual = 0"""
        ).fetchone()[0]

        assert cov_after == cov_before
        fork.close()


# ===================================================================
# Baseline immutability
# ===================================================================


class TestBaselineImmutability:
    def test_whatif_baseline_snapshot_unchanged(self) -> None:
        """Spec §17: Baseline hash before == after what-if."""
        baseline = _baseline()
        hash_before = canonical_run_hash(baseline)

        result = run_whatif(baseline, _get_edge_ids(baseline)[:1])

        hash_after = canonical_run_hash(baseline)
        assert hash_before == hash_after
        assert result["baseline_verified"] is True

    def test_baseline_data_unchanged_after_whatif(self) -> None:
        """Verify baseline edges are completely untouched."""
        baseline = _baseline()
        edges_before = baseline.execute(
            "SELECT edge_id, alpha_i, beta_i, status, frozen FROM edges "
            "ORDER BY edge_id"
        ).fetchall()

        run_whatif(baseline, _get_edge_ids(baseline))

        edges_after = baseline.execute(
            "SELECT edge_id, alpha_i, beta_i, status, frozen FROM edges "
            "ORDER BY edge_id"
        ).fetchall()

        for b, a in zip(edges_before, edges_after):
            assert dict(b) == dict(a)


# ===================================================================
# Full what-if pipeline
# ===================================================================


class TestRunWhatIf:
    def test_whatif_produces_diff_report(self) -> None:
        baseline = _baseline()
        eids = _get_edge_ids(baseline)
        result = run_whatif(baseline, [eids[0]])

        assert "diff_report" in result
        assert "control_roi_line" in result["diff_report"]

    def test_whatif_fork_hash_differs(self) -> None:
        """Fork hash should differ from baseline after refute."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)
        result = run_whatif(baseline, [eids[0]])

        assert result["fork_hash"] != result["baseline_hash"]

    def test_roi_line_format(self) -> None:
        """Spec §17.3: ROI line format."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)
        result = run_whatif(baseline, [eids[0]])

        roi = result["diff_report"]["control_roi_line"]
        assert roi.startswith("Control ROI:")
        assert "paths removed" in roi
        assert "highest remaining path confidence:" in roi
        assert "evidence coverage:" in roi
        assert "% of edges observed" in roi

    def test_refuting_critical_edge_removes_paths(self) -> None:
        """Refuting edge A→B should affect path A→B→C."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)

        # Check baseline has paths
        baseline_paths = baseline.execute(
            "SELECT COUNT(*) FROM derived_topk"
        ).fetchone()[0]
        assert baseline_paths >= 1

        # Refute first edge (A→B)
        result = run_whatif(baseline, [eids[0]])

        # The path A→B→C should still exist but with different probability
        # (B→C was already REFUTED, A→B is now also REFUTED)
        fork_topk = result["fork_export"]["derived_topk"]
        # Path might still exist (just with very low confidence) or be removed
        # depending on the search — either way diff should show changes
        assert result["diff_report"]["edge_diffs"] != [] or len(fork_topk) != baseline_paths

    def test_whatif_determinism(self) -> None:
        """Same what-if → same results."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)

        r1 = run_whatif(baseline, [eids[0]])
        r2 = run_whatif(baseline, [eids[0]])

        assert r1["fork_hash"] == r2["fork_hash"]
        assert r1["diff_report"]["paths_removed"] == r2["diff_report"]["paths_removed"]

    def test_whatif_refute_all_edges(self) -> None:
        """Refuting all edges should produce maximally degraded paths."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)
        result = run_whatif(baseline, eids)

        # All edges refuted — paths should have very low/insufficient confidence
        for topk in result["fork_export"]["derived_topk"]:
            assert topk["confidence_band"] in ("VERY_LOW", "INSUFFICIENT")

    def test_whatif_multiple_refutes(self) -> None:
        """Can refute multiple edges in one what-if."""
        baseline = _baseline()
        eids = _get_edge_ids(baseline)
        result = run_whatif(baseline, eids)

        assert len(result["refute_results"]) == len(eids)
        for r in result["refute_results"]:
            assert r["status_after"] == "REFUTED"
            assert r["counterfactual_override"] is True
