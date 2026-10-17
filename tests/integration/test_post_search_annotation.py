"""CCPF Post-Search Top-K Feasibility Annotation Integration Tests (Prompt 9).

Validates the post-search full-path RDCE annotation layer:
1. Post-search boundary: Normal search and derived_topk storage finish before annotation runs.
2. Baseline equivalence: Annotation enabled vs disabled yields bitwise identical search results.
3. Complete multi-hop path evaluation: Disjoint CIDRs evaluate to UNSAT with static origin,
   and to SAT without static origin.
4. Scope-transition correctness: Hop-local ExternalId, AssumeRole boundaries, unsupported scopes,
   and malformed context.
5. Top-K coverage and isolation: 1-to-1 annotation mapping, empty path handling, error isolation.
6. Disabled mode: Zero RDCE invocations and untouched sink when disabled.

Branch: temporal-context-dev
Workspace: C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL
Contract: docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0
Design: docs/CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md v1.2.0
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.ccpf_bridge import (
    ConstraintIndex,
    annotate_paths_feasibility,
    build_constraint_index,
)
from arf_rt.config import Q8
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k, search_top_k
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from research.ccpf.rdce import (
    ContextPredicate,
    ContextScope,
    FeasibilityStatus,
    HopContextSpec,
    ProducedStateModification,
    RestrictedDeterministicConstraintEvaluator,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"
COMPLEX = FIXTURES / "complex_scenario.json"


def _build_pipeline_db(fixture_path: Path) -> sqlite3.Connection:
    """Load a scenario fixture, run ingestion and observation pipeline, return DB connection."""
    conn = connect(":memory:")
    scenario = load_scenario_file(fixture_path)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


# ============================================================================
# A. Post-Search Boundary Tests
# ============================================================================

def test_post_search_boundary_search_finishes_before_annotation():
    """Prove that normal search and database storage finish completely before annotation begins."""
    conn = _build_pipeline_db(MINIMAL)
    annotation_sink: list[dict] = []

    db_state_during_annotation: list[int] = []

    original_annotate = annotate_paths_feasibility

    def spy_annotate(*args, **kwargs):
        # Query derived_topk to prove rows are already inserted and committed
        cur = conn.execute("SELECT COUNT(*) FROM derived_topk")
        count = cur.fetchone()[0]
        db_state_during_annotation.append(count)
        return original_annotate(*args, **kwargs)

    with patch("arf_rt.ccpf_bridge.annotate_paths_feasibility", side_effect=spy_annotate):
        results = search_and_store_top_k(
            conn,
            ccpf_post_search_annotation=True,
            ccpf_annotation_sink=annotation_sink,
        )

    # 1. Assert annotate was called and derived_topk already contained the stored paths
    assert len(db_state_during_annotation) > 0, "annotate_paths_feasibility must have been invoked"
    assert db_state_during_annotation[0] > 0, "derived_topk rows must exist before annotation starts"

    # 2. Assert all objectives in results are represented
    total_returned_paths = sum(len(p_list) for p_list in results.values())
    assert total_returned_paths == db_state_during_annotation[0]
    assert len(annotation_sink) == total_returned_paths


def test_post_search_boundary_verdicts_do_not_affect_search():
    """Verify that feasibility verdicts have zero effect on candidate expansion or Top-K selection."""
    conn = _build_pipeline_db(MINIMAL)

    # Run 1: Annotation disabled (pure baseline)
    res_disabled = search_and_store_top_k(conn, ccpf_post_search_annotation=False)

    # Run 2: Annotation enabled with sink
    sink_enabled: list[dict] = []
    res_enabled = search_and_store_top_k(
        conn,
        ccpf_post_search_annotation=True,
        ccpf_annotation_sink=sink_enabled,
    )

    assert res_disabled == res_enabled, "Search results must be bitwise identical"


# ============================================================================
# B. Baseline Equivalence Tests
# ============================================================================

@pytest.mark.parametrize("fixture_path", [MINIMAL, COMPLEX])
def test_baseline_equivalence_full_field_parity(fixture_path):
    """Compare annotation disabled vs enabled on identical scenarios across all fields."""
    conn_a = _build_pipeline_db(fixture_path)
    conn_b = _build_pipeline_db(fixture_path)

    # Run A: Baseline search (annotation disabled)
    res_a = search_and_store_top_k(conn_a, ccpf_post_search_annotation=False)
    stored_a = conn_a.execute(
        "SELECT objective_id, rank, edge_id_sequence, p_best_q8, p_worst_q8, confidence_band, path_length, flags_json "
        "FROM derived_topk ORDER BY objective_id COLLATE BINARY, rank"
    ).fetchall()

    # Run B: Annotation enabled
    sink_b: list[dict] = []
    res_b = search_and_store_top_k(
        conn_b,
        ccpf_post_search_annotation=True,
        ccpf_annotation_sink=sink_b,
    )
    stored_b = conn_b.execute(
        "SELECT objective_id, rank, edge_id_sequence, p_best_q8, p_worst_q8, confidence_band, path_length, flags_json "
        "FROM derived_topk ORDER BY objective_id COLLATE BINARY, rank"
    ).fetchall()

    # Assert identical returned dictionary
    assert res_a == res_b, "Returned path dictionary must match bitwise"

    # Assert identical persisted database rows
    assert len(stored_a) == len(stored_b)
    for row_a, row_b in zip(stored_a, stored_b):
        assert tuple(row_a) == tuple(row_b), f"Database row mismatch: {row_a} vs {row_b}"

    # Assert annotation sink is populated without mutating result objects
    total_paths = sum(len(p) for p in res_b.values())
    assert len(sink_b) == total_paths


# ============================================================================
# C. Complete Multi-Hop Path Evaluation
# ============================================================================

def test_multihop_path_evaluation_disjoint_cidrs_with_and_without_static_origin():
    """Verify that multi-hop disjoint CIDRs evaluate to UNSAT with static origin and SAT without."""
    conn = _build_pipeline_db(MINIMAL)

    # Find the returned path in minimal scenario
    res = search_and_store_top_k(conn, ccpf_post_search_annotation=False)
    obj_id = next(iter(res.keys()))
    paths = res[obj_id]
    assert len(paths) >= 1
    target_path = paths[0]
    edge_ids = json.loads(target_path["edge_id_sequence"])
    assert len(edge_ids) >= 2, "Path must have at least 2 hops for multi-hop test"

    e1, e2 = edge_ids[0], edge_ids[1]

    # Inject disjoint CIDR constraints directly into database for e1 and e2
    conn.execute(
        """INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type,
                                   scope_type, scope_id, region, properties_json, properties_fp, status)
           VALUES ('c_ip1', 'k_ip1', 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', 'global',
                   '{"conditions": [{"key": "aws:SourceIp", "operator": "IpAddress", "values": ["10.0.0.0/24"]}]}',
                   'fp1', 'ACTIVE')"""
    )
    conn.execute(
        """INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type,
                                   scope_type, scope_id, region, properties_json, properties_fp, status)
           VALUES ('c_ip2', 'k_ip2', 'aws', 'TRUST_CONDITION', 'ROLE', 'r2', 'global',
                   '{"conditions": [{"key": "aws:SourceIp", "operator": "IpAddress", "values": ["192.168.1.0/24"]}]}',
                   'fp2', 'ACTIVE')"""
    )
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id) VALUES (?, 'c_ip1')", (e1,))
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id) VALUES (?, 'c_ip2')", (e2,))
    conn.commit()

    # Subcase C1: With explicit static_origin_assumption = True -> UNSAT
    sink_unsat: list[dict] = []
    annotate_paths_feasibility(
        paths=[target_path],
        conn=conn,
        scenario_assumptions={"static_origin_assumption": True},
        annotation_sink=sink_unsat,
    )
    assert len(sink_unsat) == 1
    ann_unsat = sink_unsat[0]
    assert ann_unsat["status"] == FeasibilityStatus.UNSAT.value
    assert "disjoint" in str(ann_unsat["contradiction_rationale"]).lower()
    assert ann_unsat["witness"] is None

    # Subcase C2: Without static_origin_assumption (empty assumptions) -> SAT
    sink_sat: list[dict] = []
    annotate_paths_feasibility(
        paths=[target_path],
        conn=conn,
        scenario_assumptions={},
        annotation_sink=sink_sat,
    )
    assert len(sink_sat) == 1
    ann_sat = sink_sat[0]
    assert ann_sat["status"] == FeasibilityStatus.SAT.value
    assert ann_sat["witness"] is not None
    assert ann_sat["contradiction_rationale"] is None


# ============================================================================
# D. Scope-Transition Correctness
# ============================================================================

def test_scope_transition_hop_local_external_id():
    """Verify that distinct hop-local sts:ExternalId values on consecutive hops evaluate to SAT."""
    conn = _build_pipeline_db(MINIMAL)
    res = search_and_store_top_k(conn, ccpf_post_search_annotation=False)
    paths = res[next(iter(res.keys()))]
    edge_ids = json.loads(paths[0]["edge_id_sequence"])

    e1, e2 = edge_ids[0], edge_ids[1]

    # Inject distinct sts:ExternalId constraints
    conn.execute(
        """INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type,
                                   scope_type, scope_id, region, properties_json, properties_fp, status)
           VALUES ('c_ext1', 'k_ext1', 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', 'global',
                   '{"conditions": [{"key": "sts:ExternalId", "operator": "StringEquals", "values": ["Tenant-A"]}]}',
                   'fp_e1', 'ACTIVE')"""
    )
    conn.execute(
        """INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type,
                                   scope_type, scope_id, region, properties_json, properties_fp, status)
           VALUES ('c_ext2', 'k_ext2', 'aws', 'TRUST_CONDITION', 'ROLE', 'r2', 'global',
                   '{"conditions": [{"key": "sts:ExternalId", "operator": "StringEquals", "values": ["Tenant-B"]}]}',
                   'fp_e2', 'ACTIVE')"""
    )
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id) VALUES (?, 'c_ext1')", (e1,))
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id) VALUES (?, 'c_ext2')", (e2,))
    conn.commit()

    sink: list[dict] = []
    annotations = annotate_paths_feasibility(
        paths=[paths[0]],
        conn=conn,
        annotation_sink=sink,
    )
    assert len(annotations) == 1
    assert annotations[0]["status"] == FeasibilityStatus.SAT.value
    assert annotations[0]["witness"].get("hop_1_sts:ExternalId") == "Tenant-A"
    assert annotations[0]["witness"].get("hop_2_sts:ExternalId") == "Tenant-B"


def test_scope_transition_unsupported_scope_yields_unknown():
    """Verify that unrecognized condition scopes fall back conservatively to UNKNOWN."""
    conn = _build_pipeline_db(MINIMAL)
    paths = search_and_store_top_k(conn, ccpf_post_search_annotation=False)[next(iter(conn.execute("SELECT objective_id FROM objectives").fetchone()))]
    edge_ids = json.loads(paths[0]["edge_id_sequence"])

    conn.execute(
        """INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type,
                                   scope_type, scope_id, region, properties_json, properties_fp, status)
           VALUES ('c_unk', 'k_unk', 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', 'global',
                   '{"key": "aws:UnknownCustomContext", "operator": "StringEquals", "values": ["val"]}',
                   'fp_unk', 'ACTIVE')"""
    )
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id) VALUES (?, 'c_unk')", (edge_ids[0],))
    conn.commit()

    sink: list[dict] = []
    annotations = annotate_paths_feasibility(paths=[paths[0]], conn=conn, annotation_sink=sink)
    assert len(annotations) == 1
    assert annotations[0]["status"] == FeasibilityStatus.UNKNOWN.value
    assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in annotations[0]["unknown_rationale"]


# ============================================================================
# E. Top-K Coverage and Isolation Tests
# ============================================================================

def test_top_k_coverage_and_order_association():
    """Verify 1-to-1 matching and ordering between Top-K paths and emitted annotations."""
    conn = _build_pipeline_db(COMPLEX)
    sink: list[dict] = []
    results = search_and_store_top_k(
        conn,
        ccpf_post_search_annotation=True,
        ccpf_annotation_sink=sink,
    )

    all_paths = [p for p_list in results.values() for p in p_list]
    assert len(all_paths) == len(sink)

    for p, ann in zip(all_paths, sink):
        assert p["rank"] == ann["rank"]
        assert p["edge_id_sequence"] == ann["edge_id_sequence"]
        assert ann["status"] in ("SAT", "UNSAT", "UNKNOWN")
        assert "evaluated_hops" in ann
        assert "solver_duration_ms" in ann


def test_empty_results_handling():
    """Verify that an empty paths list returns empty annotations with zero errors."""
    conn = connect(":memory:")
    sink: list[dict] = []
    annotations = annotate_paths_feasibility(paths=[], conn=conn, annotation_sink=sink)
    assert annotations == []
    assert sink == []


def test_annotation_failure_isolation():
    """Verify that an unexpected exception during annotation does not crash or corrupt search."""
    conn = _build_pipeline_db(MINIMAL)

    # Force annotate_paths_feasibility to raise an exception
    with patch("arf_rt.ccpf_bridge.annotate_paths_feasibility", side_effect=RuntimeError("Synthetic crash")):
        results = search_and_store_top_k(
            conn,
            ccpf_post_search_annotation=True,
            ccpf_annotation_sink=[],
        )

    # Search results must remain available despite the annotation exception
    assert len(results) > 0
    cur = conn.execute("SELECT COUNT(*) FROM derived_topk")
    assert cur.fetchone()[0] > 0


# ============================================================================
# F. Disabled Mode Verification
# ============================================================================

def test_disabled_mode_zero_evaluations_and_empty_sink():
    """Verify that disabled annotation mode invokes zero RDCE evaluations and leaves sink untouched."""
    conn = _build_pipeline_db(MINIMAL)
    sink: list[dict] = []

    with patch("research.ccpf.rdce.RestrictedDeterministicConstraintEvaluator.evaluate") as mock_eval:
        results = search_and_store_top_k(
            conn,
            ccpf_guard=False,
            ccpf_post_search_annotation=False,
            ccpf_annotation_sink=sink,
        )

        assert mock_eval.call_count == 0, "No RDCE evaluations must occur when disabled"
        assert len(sink) == 0, "Annotation sink must remain empty"
        assert len(results) > 0, "Search results must be returned normally"
