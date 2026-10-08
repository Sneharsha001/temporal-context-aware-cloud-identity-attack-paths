"""Tests for reporting (spec §16)."""

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
from arf_rt.reporting.diff_report import generate_diff_report
from arf_rt.reporting.json_output import SEMANTICS_VERSION, generate_json_output
from arf_rt.reporting.markdown_report import generate_markdown_report
from arf_rt.storage.sqlite_store import connect


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _full_pipeline_with_paths():
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    corr = compute_correlation(conn)
    search_and_store_top_k(conn, corr)
    return conn


# ===================================================================
# Markdown report
# ===================================================================


class TestMarkdownReport:
    def test_renders_without_error(self) -> None:
        conn = _full_pipeline_with_paths()
        md = generate_markdown_report(conn)
        assert isinstance(md, str)
        assert len(md) > 100

    def test_contains_header(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "# ARF-RT Analysis Report" in md

    def test_contains_summary_table(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "| Nodes |" in md
        assert "| Edges |" in md

    def test_markdown_uses_bands_not_decimals(self) -> None:
        """Spec §16: No decimals in Markdown. Use confidence bands."""
        md = generate_markdown_report(_full_pipeline_with_paths())
        # Should contain band names, not decimal probabilities
        bands = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW", "INSUFFICIENT"]
        has_band = any(b in md for b in bands)
        assert has_band, "Report should contain confidence bands"
        # Should not contain decimal probability values like 0.xxx
        assert "0." not in md.split("coverage")[0]  # Before coverage section

    def test_contains_evidence_coverage(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Evidence Coverage" in md
        assert "%" in md

    def test_contains_objective_section(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Objective: REACHABILITY" in md

    def test_contains_path_details(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Path 1" in md

    def test_contains_constraint_validation(self) -> None:
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Constraint Validation" in md

    def test_contains_warnings_section(self) -> None:
        """Minimal scenario has a downgrade warning."""
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Warnings" in md
        assert "DOWNGRADED_DIRECT_NO_EVIDENCE" in md

    def test_no_conflict_section_when_none(self) -> None:
        """No conflict section if no edges have conflict=true."""
        md = generate_markdown_report(_full_pipeline_with_paths())
        assert "Conflicts Detected" not in md


class TestMarkdownConflicts:
    def test_conflict_section_when_conflict_exists(self) -> None:
        conn = _full_pipeline_with_paths()
        # Set a conflict flag
        conn.execute(
            "UPDATE edges SET flags_json = "
            "json_set(flags_json, '$.conflict', json('true')) "
            "WHERE rowid = 1"
        )
        conn.commit()

        md = generate_markdown_report(conn)
        assert "Conflicts Detected" in md


# ===================================================================
# JSON output
# ===================================================================


class TestJsonOutput:
    def test_generates_valid_json(self) -> None:
        conn = _full_pipeline_with_paths()
        output = generate_json_output(conn)
        # Should be serializable
        serialized = json.dumps(output)
        assert len(serialized) > 100

    def test_json_output_includes_semantics_version(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert "semantics_version" in output
        assert output["semantics_version"] == SEMANTICS_VERSION

    def test_includes_canonical_run_hash(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert "canonical_run_hash" in output
        assert len(output["canonical_run_hash"]) == 64

    def test_includes_summary(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        summary = output["summary"]
        assert summary["node_count"] == 3
        assert summary["edge_count"] == 2
        assert summary["constraint_count"] == 1
        assert summary["objective_count"] == 1
        assert summary["observation_count"] == 3

    def test_includes_objectives_with_paths(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert len(output["objectives"]) == 1
        obj = output["objectives"][0]
        assert obj["objective_type"] == "REACHABILITY"
        assert len(obj["paths"]) >= 1
        path = obj["paths"][0]
        assert "rank" in path
        assert "confidence_band" in path
        assert "p_worst_q8" in path
        assert "flags" in path

    def test_includes_evidence_coverage(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        cov = output["evidence_coverage"]
        assert "total_edges" in cov
        assert "observed_edges" in cov
        assert "coverage_percent" in cov
        assert cov["total_edges"] == 2
        assert cov["observed_edges"] == 2  # Both edges have DIRECT obs
        assert cov["coverage_percent"] == 100

    def test_includes_constraint_validation(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        csts = output["constraint_validation"]
        assert len(csts) == 1
        assert csts[0]["constraint_type"] == "SCP"

    def test_includes_warnings(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert len(output["warnings"]) >= 1
        assert output["warnings"][0]["code"] == "DOWNGRADED_DIRECT_NO_EVIDENCE"

    def test_includes_obs_digests(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert len(output["obs_digests"]) == 2

    def test_no_conflicts_in_minimal(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert output["conflicts"] == []

    def test_conflict_surfacing_in_json(self) -> None:
        conn = _full_pipeline_with_paths()
        conn.execute(
            "UPDATE edges SET flags_json = "
            "json_set(flags_json, '$.conflict', json('true')) "
            "WHERE rowid = 1"
        )
        conn.commit()

        output = generate_json_output(conn)
        assert len(output["conflicts"]) == 1
        assert "edge_id" in output["conflicts"][0]


# ===================================================================
# Evidence coverage
# ===================================================================


class TestEvidenceCoverage:
    def test_coverage_100_when_all_edges_observed(self) -> None:
        output = generate_json_output(_full_pipeline_with_paths())
        assert output["evidence_coverage"]["coverage_percent"] == 100

    def test_coverage_excludes_counterfactual(self) -> None:
        """Counterfactual observations don't count toward coverage.

        We use an ingest-only DB (no edge_updates FK issues) and replace
        observations to test the coverage query logic.
        """
        conn = connect(":memory:")
        scenario = load_scenario_file(MINIMAL)
        adapter = ReplayAdapter(conn)
        adapter.ingest(scenario)
        # Don't apply observations — just manipulate obs table directly

        # Remove all observations, add back only counterfactual on first edge
        conn.execute("DELETE FROM observations")
        eid = conn.execute("SELECT edge_id FROM edges ORDER BY edge_id LIMIT 1").fetchone()["edge_id"]
        eid2 = conn.execute("SELECT edge_id FROM edges ORDER BY edge_id LIMIT 1 OFFSET 1").fetchone()["edge_id"]

        # Counterfactual on edge 1 — shouldn't count
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'WHATIF_FORCED', 'DENY', 'CONSTRAINT_DENY',
                       'DIRECT', 100, 1, 0, 'cf')""",
            (eid,),
        )
        # Real observation on edge 2
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'CONSTRAINT_DENY',
                       'DIRECT', 80, 0, 0, 'real')""",
            (eid2,),
        )
        conn.commit()

        output = generate_json_output(conn)
        assert output["evidence_coverage"]["observed_edges"] == 1
        assert output["evidence_coverage"]["coverage_percent"] == 50

    def test_coverage_excludes_heuristic(self) -> None:
        """HEURISTIC strength doesn't count toward coverage."""
        conn = connect(":memory:")
        scenario = load_scenario_file(MINIMAL)
        adapter = ReplayAdapter(conn)
        adapter.ingest(scenario)

        conn.execute("DELETE FROM observations")
        eid = conn.execute("SELECT edge_id FROM edges ORDER BY edge_id LIMIT 1").fetchone()["edge_id"]
        eid2 = conn.execute("SELECT edge_id FROM edges ORDER BY edge_id LIMIT 1 OFFSET 1").fetchone()["edge_id"]

        # HEURISTIC on edge 1 — shouldn't count
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'HEURISTIC', 50, 0, 0, 'heur')""",
            (eid,),
        )
        # DIRECT on edge 2 — should count
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'DIRECT', 80, 0, 0, 'real')""",
            (eid2,),
        )
        conn.commit()

        output = generate_json_output(conn)
        assert output["evidence_coverage"]["observed_edges"] == 1


# ===================================================================
# Diff report (stub)
# ===================================================================


class TestDiffReport:
    def test_diff_identical_exports(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)
        diff = generate_diff_report(export, export)
        assert diff["paths_removed"] == 0
        assert diff["edge_diffs"] == []

    def test_diff_detects_edge_changes(self) -> None:
        conn1 = _full_pipeline_with_paths()
        e1 = full_state_export(conn1)

        conn2 = _full_pipeline_with_paths()
        conn2.execute("UPDATE edges SET alpha_i = 9999 WHERE rowid = 1")
        conn2.commit()
        e2 = full_state_export(conn2)

        diff = generate_diff_report(e1, e2)
        assert len(diff["edge_diffs"]) >= 1
        assert diff["edge_diffs"][0]["change"] == "belief_changed"

    def test_control_roi_line_format(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)
        diff = generate_diff_report(export, export)
        assert "Control ROI:" in diff["control_roi_line"]
        assert "paths removed" in diff["control_roi_line"]
        assert "evidence coverage:" in diff["control_roi_line"]


# ===================================================================
# Read-only contract
# ===================================================================


class TestReportingReadOnly:
    def test_reporting_does_not_modify_db(self) -> None:
        """Reporting must not change any DB state."""
        conn = _full_pipeline_with_paths()

        hash_before = canonical_run_hash(conn)

        # Run all reporting
        generate_markdown_report(conn)
        generate_json_output(conn)

        hash_after = canonical_run_hash(conn)
        assert hash_before == hash_after

    def test_json_output_deterministic(self) -> None:
        o1 = generate_json_output(_full_pipeline_with_paths())
        o2 = generate_json_output(_full_pipeline_with_paths())
        assert o1["canonical_run_hash"] == o2["canonical_run_hash"]
        assert o1["summary"] == o2["summary"]
        assert o1["evidence_coverage"] == o2["evidence_coverage"]
