"""Golden checks for recovered paper-support artifacts.

These tests pin the recovered artifacts that were missing from earlier archive
lineages: complex multi-BU fixture, OIDC/GhostGates enrichment, and synthetic
scaling snapshot. They intentionally do not assert the camera-ready complex
Table IV 0.64/76% value because the hardened fork-replay engine preserves
non-uniform fixture priors and yields ~1.092/59.6%; the reproduction driver
records that reconciliation item explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.planner import _get_entropy, _get_topk_paths, plan_probes

ROOT = Path(__file__).resolve().parents[2]
Q8 = 100_000_000


def test_complex_fixture_baseline_and_planner():
    conn, _ = run_full_pipeline(str(ROOT / "tests/fixtures/complex_scenario.json"))
    summary = conn.execute(
        "SELECT (SELECT COUNT(*) FROM nodes), (SELECT COUNT(*) FROM edges), "
        "(SELECT COUNT(*) FROM constraints), (SELECT COUNT(*) FROM observations)"
    ).fetchone()
    assert tuple(summary) == (24, 33, 6, 0)
    assert len(_get_topk_paths(conn)) == 15
    assert abs(_get_entropy(conn) - 2.7008) < 0.001

    plan = plan_probes(conn, compute_correlation(conn), signal_q=95)
    assert abs(plan["top_recommendation"]["eig"] - 1.0724) < 0.001
    assert any(
        comp.get("edge_count") == 10 and abs(comp.get("best_eig", 0) - 1.0724) < 0.001
        for comp in plan["component_summary"]
    )


def test_oidc_enriched_scenario_matches_paper_table_vi():
    scenario_path = ROOT / "tests/fixtures/oidc/scenario_enriched.json"
    scenario = json.loads(scenario_path.read_text())
    meta = scenario["metadata"]["ghostgates_enrichment"]
    assert meta["oidc_constraints_found"] == 3
    assert meta["compromised"] == 3
    assert meta["edges_prior_adjusted"] == 3
    assert meta["ghostgates_findings_total"] == 4

    conn, _ = run_full_pipeline(str(scenario_path))
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert abs(_get_entropy(conn) - 1.2130) < 0.001
    probs = [round(p["p_worst_q8"] / Q8, 6) for p in _get_topk_paths(conn)]
    assert probs == [0.375, 0.333333, 0.25]


def test_synthetic_scaling_snapshot_rows():
    rows = json.loads((ROOT / "tests/fixtures/scaling/scaling_results.json").read_text())
    by_config = {row["config"]: row for row in rows}
    assert len(rows) == 6
    assert by_config["A1: 100e, no corr"]["plan_runtime_ms"] == 87.1
    assert by_config["A3: 10Ke, no corr"]["plan_runtime_ms"] == 6313.5
    assert by_config["B3: 10Ke, 10-edge SCP"]["plan_runtime_ms"] == 6449.2
    assert by_config["B1: 100e, 10-edge SCP"]["top_eig"] == 0.172795
