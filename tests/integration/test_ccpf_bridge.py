"""CCPF Passive Audit Bridge Integration Tests (Prompt 7 Mode A: Zero Pruning).

These tests verify the 10 mandatory integration and failure-isolation criteria:
1. Feature disabled: baseline outputs and scores unchanged.
2. Feature enabled (SAT): SAT is logged but does not alter search behavior or scores.
3. Feature enabled (UNSAT): UNSAT is logged but does NOT prune (ZERO PRUNING).
4. Feature enabled (UNKNOWN): UNKNOWN is logged and does not prune.
5. Unsupported or missing metadata falls back conservatively to UNKNOWN.
6. RDCE/bridge failure does not alter candidate eligibility or abort search.
7. Q8 values, heap priority tuples and existing tie-break behavior remain unchanged.
8. Alternative Allow statements and ambiguous statement provenance do not cause pruning.
9. The diagnostic record contains complete tracing context without sensitive values.
10. Repeated evaluations do not mutate underlying constraints, edges, or scores.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.ccpf_bridge import (
    build_constraint_index,
    evaluate_candidate_hop,
    extract_predicates_from_constraint,
    infer_scope,
)
from arf_rt.config import Q8
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_top_k
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from research.ccpf.rdce import ContextScope, FeasibilityStatus


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"
COMPLEX = FIXTURES / "complex_scenario.json"


def _build_pipeline_db(fixture_path: Path):
    """Load a scenario fixture, run ingestion and observation pipeline, return DB connection."""
    conn = connect(":memory:")
    scenario = load_scenario_file(fixture_path)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


def _get_first_objective(conn):
    row = conn.execute("SELECT objective_id FROM objectives ORDER BY objective_id").fetchone()
    return row["objective_id"] if row else None


# ===================================================================
# Test 1: Feature Disabled Baseline Invariance
# ===================================================================
def test_feature_disabled_baseline_unchanged():
    """Verify that when ccpf_guard is False, search_top_k matches baseline."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    # 1. Baseline search
    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)

    # 2. Audit sink passed but guard disabled
    sink = []
    guard_off_paths = search_top_k(conn, oid, ccpf_guard=False, ccpf_audit_sink=sink)

    assert len(sink) == 0, "No audit records should be emitted when guard is disabled"
    assert len(baseline_paths) == len(guard_off_paths)
    for p1, p2 in zip(baseline_paths, guard_off_paths):
        assert p1["edge_id_sequence"] == p2["edge_id_sequence"]
        assert p1["p_worst_q8"] == p2["p_worst_q8"]
        assert p1["p_best_q8"] == p2["p_best_q8"]
        assert p1["rank"] == p2["rank"]


# ===================================================================
# Test 2: Feature Enabled SAT Observational Only
# ===================================================================
def test_feature_enabled_sat_observational_only():
    """Verify that a SAT condition is logged in audit sink without modifying search."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    # Attach a SAT constraint to an edge: aws:SourceIp in 10.0.0.0/8
    edge_row = conn.execute("SELECT edge_id FROM edges LIMIT 1").fetchone()
    eid = edge_row["edge_id"]

    conn.execute(
        """
        INSERT INTO constraints
        (constraint_id, constraint_key, provider, constraint_type, scope_type, scope_id, region,
         properties_json, properties_fp, status, validation_status, confidence_q)
        VALUES (?, ?, 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', '-', ?, 'fp1', 'ACTIVE', 'VALIDATED', 800)
        """,
        (
            "c_sat_1",
            "trust|sat|ip",
            json.dumps({
                "conditions": [
                    {"key": "aws:SourceIp", "operator": "IpAddress", "values": ["10.0.0.0/8"]}
                ]
            }),
        ),
    )
    conn.execute(
        "INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')",
        (eid, "c_sat_1"),
    )
    conn.commit()

    sink = []
    paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    assert len(paths) > 0
    sat_records = [r for r in sink if r["edge_id"] == eid and r["status"] == "SAT"]
    assert len(sat_records) >= 1, "Expected SAT evaluation recorded for edge with valid IP constraint"
    assert sat_records[0]["contradiction_rationale"] is None


# ===================================================================
# Test 3: Feature Enabled UNSAT ZERO PRUNING
# ===================================================================
def test_feature_enabled_unsat_zero_pruning():
    """CRITICAL: An UNSAT hop MUST be logged but MUST NOT BE PRUNED under Mode A."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    # Find the edge used by the target path in minimal scenario
    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)
    assert len(baseline_paths) > 0
    target_edge_id = json.loads(baseline_paths[0]["edge_id_sequence"])[0]

    # Attach contradictory disjoint CIDR constraints to this edge (yields UNSAT)
    conn.execute(
        """
        INSERT INTO constraints
        (constraint_id, constraint_key, provider, constraint_type, scope_type, scope_id, region,
         properties_json, properties_fp, status, validation_status, confidence_q)
        VALUES (?, ?, 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', '-', ?, 'fp2', 'ACTIVE', 'VALIDATED', 900)
        """,
        (
            "c_unsat_disjoint",
            "trust|unsat|disjoint",
            json.dumps({
                "conditions": [
                    {"key": "aws:SourceIp", "operator": "IpAddress", "values": ["10.0.0.0/8"]},
                    {"key": "aws:SourceIp", "operator": "IpAddress", "values": ["192.168.0.0/16"]},
                ]
            }),
        ),
    )
    conn.execute(
        "INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')",
        (target_edge_id, "c_unsat_disjoint"),
    )
    conn.commit()

    sink = []
    audit_paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    # 1. Verify UNSAT was diagnosed and recorded
    unsat_records = [r for r in sink if r["edge_id"] == target_edge_id and r["status"] == "UNSAT"]
    assert len(unsat_records) >= 1, "Expected UNSAT logged for contradictory constraint"
    assert unsat_records[0]["contradiction_rationale"] is not None
    assert "Disjoint" in unsat_records[0]["contradiction_rationale"]

    # 2. ZERO PRUNING INVARIANT: Path containing target_edge_id MUST STILL BE PRESENT in audit_paths!
    assert len(audit_paths) == len(baseline_paths), "Zero pruning invariant violated: path count changed"
    assert audit_paths[0]["edge_id_sequence"] == baseline_paths[0]["edge_id_sequence"]
    assert audit_paths[0]["p_worst_q8"] == baseline_paths[0]["p_worst_q8"]
    assert audit_paths[0]["rank"] == baseline_paths[0]["rank"]


# ===================================================================
# Test 4: Feature Enabled UNKNOWN ZERO PRUNING
# ===================================================================
def test_feature_enabled_unknown_zero_pruning():
    """Verify that an UNKNOWN condition is logged and does not alter path eligibility."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    edge_row = conn.execute("SELECT edge_id FROM edges LIMIT 1").fetchone()
    eid = edge_row["edge_id"]

    # Attach an unsupported condition: aws:SourceVpc (maps to UNKNOWN scope)
    conn.execute(
        """
        INSERT INTO constraints
        (constraint_id, constraint_key, provider, constraint_type, scope_type, scope_id, region,
         properties_json, properties_fp, status, validation_status, confidence_q)
        VALUES (?, ?, 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', '-', ?, 'fp3', 'ACTIVE', 'VALIDATED', 800)
        """,
        (
            "c_unknown_vpc",
            "trust|unknown|vpc",
            json.dumps({
                "condition_key": "aws:SourceVpc",
                "condition_operator": "StringEquals",
                "values": ["vpc-12345678"],
            }),
        ),
    )
    conn.execute(
        "INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')",
        (eid, "c_unknown_vpc"),
    )
    conn.commit()

    sink = []
    paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    assert len(paths) > 0
    unk_records = [r for r in sink if r["edge_id"] == eid and r["status"] == "UNKNOWN"]
    assert len(unk_records) >= 1
    assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in unk_records[0]["unknown_rationale"]


# ===================================================================
# Test 5: Unsupported or Missing Metadata Fallback
# ===================================================================
def test_unsupported_or_missing_metadata_fallback():
    """Verify that malformed or incomplete metadata falls back gracefully to UNKNOWN."""
    # 1. Unrecognized scope
    assert infer_scope("aws:random_custom_key") == ContextScope.UNKNOWN
    assert infer_scope(None) == ContextScope.UNKNOWN

    # 2. Malformed properties
    preds_malformed = extract_predicates_from_constraint("c1", "TRUST", "not-a-dict")
    assert len(preds_malformed) == 1
    assert preds_malformed[0].scope == ContextScope.UNKNOWN

    # 3. Empty properties
    preds_empty = extract_predicates_from_constraint("c2", "TRUST", {})
    assert len(preds_empty) == 1
    assert preds_empty[0].scope == ContextScope.UNKNOWN


# ===================================================================
# Test 6: RDCE and Bridge Failure Isolation
# ===================================================================
def test_bridge_failure_isolation():
    """Verify that an unexpected exception in RDCE does not crash search or prune edges."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)

    sink = []
    # Deliberately mock RestrictedDeterministicConstraintEvaluator.evaluate to raise RuntimeError
    with patch("research.ccpf.rdce.RestrictedDeterministicConstraintEvaluator.evaluate", side_effect=RuntimeError("Simulated solver crash")):
        audit_paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    # Search must complete successfully and return identical results
    assert len(audit_paths) == len(baseline_paths)
    assert audit_paths[0]["edge_id_sequence"] == baseline_paths[0]["edge_id_sequence"]

    # The exception must be caught and recorded as UNKNOWN with BRIDGE_EXCEPTION
    assert len(sink) > 0
    for rec in sink:
        assert rec["status"] == "UNKNOWN"
        assert "BRIDGE_EXCEPTION" in rec["unknown_rationale"]


# ===================================================================
# Test 7: Q8 Value, Priority Tuple, and Tie-Break Invariance
# ===================================================================
def test_q8_score_heap_priority_and_tiebreak_invariance():
    """Verify bit-identical scores and tie-breaking across complex graph."""
    conn = _build_pipeline_db(COMPLEX)
    oid = _get_first_objective(conn)

    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)
    audit_paths = search_top_k(conn, oid, ccpf_guard=True)

    assert len(baseline_paths) == len(audit_paths)
    assert len(baseline_paths) > 0

    for b, a in zip(baseline_paths, audit_paths):
        assert b["rank"] == a["rank"]
        assert b["edge_id_sequence"] == a["edge_id_sequence"]
        assert b["p_worst_q8"] == a["p_worst_q8"]
        assert b["p_best_q8"] == a["p_best_q8"]
        assert b["confidence_band"] == a["confidence_band"]
        assert b["path_length"] == a["path_length"]
        assert b["flags_json"] == a["flags_json"]


# ===================================================================
# Test 8: Alternative Allow Statements (No False Pruning)
# ===================================================================
def test_alternative_allow_statements_no_false_pruning():
    """Verify that multiple alternative statements do not cause false pruning."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)
    eid = json.loads(baseline_paths[0]["edge_id_sequence"])[0]

    # Statement 1 (Office IP) and Statement 2 (VPN IP) attached to same edge
    conn.execute(
        """
        INSERT INTO constraints
        (constraint_id, constraint_key, provider, constraint_type, scope_type, scope_id, region,
         properties_json, properties_fp, status, validation_status, confidence_q)
        VALUES (?, ?, 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', '-', ?, 'fp4', 'ACTIVE', 'VALIDATED', 800)
        """,
        (
            "c_stmt1_office",
            "trust|s1",
            json.dumps({"condition_key": "aws:SourceIp", "condition_operator": "IpAddress", "values": ["10.0.1.0/24"]}),
        ),
    )
    conn.execute(
        """
        INSERT INTO constraints
        (constraint_id, constraint_key, provider, constraint_type, scope_type, scope_id, region,
         properties_json, properties_fp, status, validation_status, confidence_q)
        VALUES (?, ?, 'aws', 'TRUST_CONDITION', 'ROLE', 'r1', '-', ?, 'fp5', 'ACTIVE', 'VALIDATED', 800)
        """,
        (
            "c_stmt2_vpn",
            "trust|s2",
            json.dumps({"condition_key": "aws:SourceIp", "condition_operator": "IpAddress", "values": ["192.168.1.0/24"]}),
        ),
    )
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')", (eid, "c_stmt1_office"))
    conn.execute("INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')", (eid, "c_stmt2_vpn"))
    conn.commit()

    sink = []
    paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    # In passive audit mode, even if RDCE found the disjoint intersection UNSAT,
    # the candidate edge MUST NOT be pruned!
    assert len(paths) == len(baseline_paths)
    assert paths[0]["edge_id_sequence"] == baseline_paths[0]["edge_id_sequence"]


# ===================================================================
# Test 9: Diagnostic Record Completeness and Privacy Boundaries
# ===================================================================
def test_diagnostic_record_context_and_privacy():
    """Verify that diagnostic records contain tracing context and do not expose secrets."""
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    sink = []
    search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink)

    assert len(sink) > 0
    for rec in sink:
        # Check required tracing fields
        assert "edge_id" in rec
        assert "edge_type" in rec
        assert "src_node_id" in rec
        assert "dst_node_id" in rec
        assert "status" in rec
        assert rec["status"] in ("SAT", "UNSAT", "UNKNOWN")
        assert "solver_duration_ms" in rec
        assert isinstance(rec["solver_duration_ms"], float)
        assert "predicates_count" in rec

        # Check privacy boundary: no raw credential or secret keys in top-level record
        for forbidden in ("password", "secret", "private_key", "token_value"):
            assert forbidden not in rec


# ===================================================================
# Test 10: Repeated Evaluations Idempotence
# ===================================================================
def test_repeated_evaluations_idempotence():
    """Verify that repeated search executions with CCPF guard do not mutate DB or results."""
    conn = _build_pipeline_db(COMPLEX)
    oid = _get_first_objective(conn)

    # Check baseline row counts
    edges_count_before = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
    constraints_count_before = conn.execute("SELECT count(*) FROM constraints").fetchone()[0]

    # Run 5 consecutive iterations
    all_runs = []
    for _ in range(5):
        res = search_top_k(conn, oid, ccpf_guard=True)
        all_runs.append(res)

    # Assert row counts have not changed
    edges_count_after = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
    constraints_count_after = conn.execute("SELECT count(*) FROM constraints").fetchone()[0]
    assert edges_count_before == edges_count_after
    assert constraints_count_before == constraints_count_after

    # Assert all 5 runs produced byte-for-byte identical results
    run0 = all_runs[0]
    for r in all_runs[1:]:
        assert len(r) == len(run0)
        for p0, p in zip(run0, r):
            assert p0["edge_id_sequence"] == p["edge_id_sequence"]
            assert p0["p_worst_q8"] == p["p_worst_q8"]
            assert p0["p_best_q8"] == p["p_best_q8"]
