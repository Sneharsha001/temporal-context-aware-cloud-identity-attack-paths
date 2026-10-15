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
import sqlite3

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.ccpf_bridge import (
    ConstraintIndex,
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
from research.ccpf.rdce import (
    ContextScope,
    FeasibilityStatus,
    RestrictedDeterministicConstraintEvaluator,
)


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

# ===================================================================
# Test 11: Constraint Index Failure Distinguished from Empty Index
# ===================================================================
def test_constraint_index_query_failure_distinguished_from_empty():
    """Verify that a database query failure during index construction produces UNKNOWN

    and does NOT masquerade as an unconstrained edge or confirmed absence of constraints.
    """
    conn = _build_pipeline_db(MINIMAL)
    oid = _get_first_objective(conn)

    # 1. Valid empty metadata: query succeeds, index has load_error=None
    index_valid = build_constraint_index(conn)
    assert index_valid.load_error is None
    assert isinstance(index_valid, ConstraintIndex)
    assert isinstance(index_valid, dict)

    # Edge evaluated with valid empty index has rationale NO_CONTEXT_CONSTRAINTS_DEFINED
    sink_valid = []
    res_valid = evaluate_candidate_hop(
        eid="edge-test-1",
        edge_data={"edge_type": "STS_ASSUME_ROLE", "src": "src1", "dst": "dst1"},
        constraint_index=index_valid,
        audit_sink=sink_valid,
    )
    assert res_valid.status == FeasibilityStatus.UNKNOWN
    assert res_valid.unknown_rationale == "NO_CONTEXT_CONSTRAINTS_DEFINED"
    assert sink_valid[0]["unknown_rationale"] == "NO_CONTEXT_CONSTRAINTS_DEFINED"

    # 2. Query failure: simulate SQLite exception during constraint query
    class FailingConn:
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("disk I/O failure")

    index_failed = build_constraint_index(FailingConn())  # type: ignore
    assert index_failed.load_error is not None
    assert "OperationalError" in index_failed.load_error
    assert "disk I/O failure" in index_failed.load_error

    # Edge evaluated with failed index MUST produce CONSTRAINT_INDEX_LOAD_FAILURE
    sink_failed = []
    res_failed = evaluate_candidate_hop(
        eid="edge-test-1",
        edge_data={"edge_type": "STS_ASSUME_ROLE", "src": "src1", "dst": "dst1"},
        constraint_index=index_failed,
        audit_sink=sink_failed,
    )
    assert res_failed.status == FeasibilityStatus.UNKNOWN
    assert "CONSTRAINT_INDEX_LOAD_FAILURE" in res_failed.unknown_rationale
    assert sink_failed[0]["unknown_rationale"] == res_failed.unknown_rationale

    # 3. In full search, failed index must preserve baseline search behavior (ZERO PRUNING)
    baseline_paths = search_top_k(conn, oid, ccpf_guard=False)
    with patch("arf_rt.ccpf_bridge.build_constraint_index", return_value=index_failed):
        sink_search = []
        audit_paths = search_top_k(conn, oid, ccpf_guard=True, ccpf_audit_sink=sink_search)

    assert len(audit_paths) == len(baseline_paths)
    assert audit_paths[0]["edge_id_sequence"] == baseline_paths[0]["edge_id_sequence"]
    assert len(sink_search) > 0
    for rec in sink_search:
        assert rec["status"] == "UNKNOWN"
        assert "CONSTRAINT_INDEX_LOAD_FAILURE" in rec["unknown_rationale"]


# ===================================================================
# Test 12: Real Trust Policy Parser Integration and Condition Mapping
# ===================================================================
def test_real_trust_policy_parser_output_integration():
    """Verify condition mapping using real output from trust_policy_parser.py."""
    from arf_rt.adapters.trust_policy_parser import (
        parse_trust_conditions,
        resolve_trust_constraints,
    )

    trust_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "IpAddress": {"aws:SourceIp": ["203.0.113.0/24"]},
                    "Bool": {"aws:MultiFactorAuthPresent": "true"},
                    "StringEquals": {
                        "sts:ExternalId": "my-client-secret-12345",
                        "aws:PrincipalTag/department": "finance",
                        "aws:SourceVpc": "vpc-0123456789abcdef0",
                    },
                    "NumericLessThan": {"aws:MultiFactorAuthAge": "3600"},
                },
            }
        ],
    }
    role_arn = "arn:aws:iam::123456789012:role/AuditTargetRole"
    edges = [
        {
            "edge_type": "STS_ASSUME_ROLE",
            "src": {"provider_id": "arn:aws:iam::123456789012:user/Alice"},
            "dst": {"provider_id": role_arn},
            "region": "us-east-1",
        }
    ]

    constraints, edge_constraints, warnings = resolve_trust_constraints(
        {role_arn: trust_doc}, edges
    )
    assert len(constraints) > 0
    assert len(edge_constraints) > 0

    evaluator = RestrictedDeterministicConstraintEvaluator()

    for c in constraints:
        props = c["properties"]
        preds = extract_predicates_from_constraint(c["scope_id"], c["constraint_type"], props)
        assert len(preds) == 1
        p = preds[0]

        if p.key == "aws:SourceIp":
            assert p.scope == ContextScope.REQUEST
            assert p.operator == "IpAddress"
            assert p.values == ["203.0.113.0/24"]
            # Feasibility test: valid IP constraint yields SAT with witness
            r_sat = evaluate_candidate_hop(
                "e1",
                {"edge_type": "STS_ASSUME_ROLE"},
                {"e1": [p]},
                evaluator=evaluator,
            )
            assert r_sat.status == FeasibilityStatus.SAT
            assert r_sat.witness is not None

            # Conflicting disjoint IP constraints on the same hop yield UNSAT
            from research.ccpf.rdce import ContextPredicate
            p_conflict = ContextPredicate(
                key="aws:SourceIp",
                operator="IpAddress",
                values=["10.0.0.0/8"],
                scope=ContextScope.REQUEST,
            )
            r_unsat = evaluate_candidate_hop(
                "e1",
                {"edge_type": "STS_ASSUME_ROLE"},
                {"e1": [p, p_conflict]},
                evaluator=evaluator,
            )
            assert r_unsat.status == FeasibilityStatus.UNSAT
            assert r_unsat.contradiction_rationale is not None

        elif p.key == "aws:MultiFactorAuthPresent":
            assert p.scope == ContextScope.SESSION
            assert p.operator == "Bool"
            assert p.values == ["true"]

        elif p.key == "sts:ExternalId":
            assert p.scope == ContextScope.CONFIG
            assert p.operator == "StringEquals"
            assert p.values == ["my-client-secret-12345"]

        elif p.key.startswith("aws:PrincipalTag/"):
            assert p.scope == ContextScope.PRINCIPAL
            assert p.operator == "StringEquals"
            assert p.values == ["finance"]

        elif p.key == "aws:SourceVpc":
            # Unsupported condition key -> UNKNOWN scope
            assert p.scope == ContextScope.UNKNOWN
            r_unk = evaluate_candidate_hop(
                "e1",
                {"edge_type": "STS_ASSUME_ROLE"},
                {"e1": [p]},
                evaluator=evaluator,
            )
            assert r_unk.status == FeasibilityStatus.UNKNOWN
            assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in r_unk.unknown_rationale


# ===================================================================
# Test 13: Malformed and Edge-Case Condition Mapping
# ===================================================================
def test_malformed_and_edge_case_condition_mapping():
    """Verify conservative, safe handling of malformed, missing, and wildcarded metadata."""
    # 1. Invalid JSON string error representation
    preds = extract_predicates_from_constraint("c1", "TRUST_CONDITION", {"__malformed_json_error__": "Expecting ',' delimiter"})
    assert len(preds) == 1
    assert preds[0].key == "malformed_constraint_json"
    assert preds[0].scope == ContextScope.UNKNOWN

    # 2. Non-dict properties
    preds_nd = extract_predicates_from_constraint("c2", "TRUST_CONDITION", ["not", "a", "dict"])  # type: ignore
    assert len(preds_nd) == 1
    assert preds_nd[0].key == "malformed_properties"
    assert preds_nd[0].scope == ContextScope.UNKNOWN

    # 3. Empty conditions list interpretation
    # Non-contextual constraint with empty conditions list = verified absence
    preds_empty_scp = extract_predicates_from_constraint("c3", "ORGANIZATION_SCP", {"conditions": []})
    assert preds_empty_scp == []

    # TRUST_CONDITION with empty conditions list = ambiguous/missing metadata (UNKNOWN)
    preds_empty_trust = extract_predicates_from_constraint("c4", "TRUST_CONDITION", {"conditions": []})
    assert len(preds_empty_trust) == 1
    assert preds_empty_trust[0].key == "empty_trust_conditions_list"
    assert preds_empty_trust[0].scope == ContextScope.UNKNOWN

    # 4. Missing key or values in conditions list
    preds_miss = extract_predicates_from_constraint(
        "c5",
        "TRUST_CONDITION",
        {"conditions": [{"key": "", "operator": "StringEquals", "values": ["val"]}]},
    )
    assert len(preds_miss) == 1
    assert preds_miss[0].key == "missing_condition_key"
    assert preds_miss[0].scope == ContextScope.UNKNOWN

    preds_miss_val = extract_predicates_from_constraint(
        "c6",
        "TRUST_CONDITION",
        {"conditions": [{"key": "aws:SourceIp", "operator": "IpAddress", "values": []}]},
    )
    assert len(preds_miss_val) == 1
    assert preds_miss_val[0].scope == ContextScope.UNKNOWN

    # 5. ExternalId shortcut removal: never invent StringEquals(["*"])
    # Format 2 with wildcard
    preds_ext_wild = extract_predicates_from_constraint(
        "c7",
        "TRUST_CONDITION",
        {"condition_key": "sts:ExternalId", "condition_operator": "StringEquals", "required_values": ["*"]},
    )
    assert len(preds_ext_wild) == 1
    assert preds_ext_wild[0].scope == ContextScope.UNKNOWN
    assert preds_ext_wild[0].operator == "Unsupported"

    # Format 3 string flag
    preds_ext_flag = extract_predicates_from_constraint(
        "c8",
        "TRUST_CONDITION",
        {"condition": "sts:externalid"},
    )
    assert len(preds_ext_flag) == 1
    assert preds_ext_flag[0].scope == ContextScope.UNKNOWN
    assert preds_ext_flag[0].operator == "Unsupported"
    assert "unavailable" in preds_ext_flag[0].description


# ===================================================================
# Test 14: Audit Output Accessible via search_and_store_top_k Entry Point
# ===================================================================
def test_audit_output_accessible_via_search_and_store_top_k():
    """Verify that search_and_store_top_k forwards and populates the audit sink."""
    from arf_rt.engine.paths import search_and_store_top_k

    conn = _build_pipeline_db(MINIMAL)

    # 1. Feature disabled: sink receives 0 records
    sink_disabled = []
    results_off = search_and_store_top_k(conn, ccpf_guard=False, ccpf_audit_sink=sink_disabled)
    assert len(sink_disabled) == 0
    assert len(results_off) > 0

    # 2. Feature enabled: sink receives diagnostic records
    sink_enabled = []
    results_on = search_and_store_top_k(conn, ccpf_guard=True, ccpf_audit_sink=sink_enabled)
    assert len(results_on) == len(results_off)
    assert len(sink_enabled) > 0

    # Inspect record fields
    for rec in sink_enabled:
        assert "edge_id" in rec
        assert "edge_type" in rec
        assert "src_node_id" in rec
        assert "dst_node_id" in rec
        assert rec["status"] in ("SAT", "UNSAT", "UNKNOWN")
        assert "predicates_count" in rec
        assert "solver_duration_ms" in rec
        # Ensure no raw credentials or sensitive data are logged
        assert "password" not in rec
        assert "secret" not in str(rec.values()).lower()

    # 3. Faulty audit sink (robustness): an append exception does not disrupt search
    class FaultySink:
        def append(self, item):
            raise RuntimeError("Audit log disk buffer full")

    faulty_sink = FaultySink()
    results_faulty = search_and_store_top_k(conn, ccpf_guard=True, ccpf_audit_sink=faulty_sink)
    assert len(results_faulty) == len(results_off)
    for oid in results_off:
        assert len(results_faulty[oid]) == len(results_off[oid])


# ===================================================================
# Test 15: Baseline vs Audit Full Field Comparison
# ===================================================================
def test_baseline_vs_audit_full_field_comparison_on_fixtures():
    """Compare all path fields between disabled and enabled guard on minimal & complex."""
    from arf_rt.engine.paths import search_and_store_top_k

    for fixture in (MINIMAL, COMPLEX):
        conn = _build_pipeline_db(fixture)

        paths_disabled = search_and_store_top_k(conn, ccpf_guard=False)
        paths_enabled = search_and_store_top_k(conn, ccpf_guard=True)

        assert set(paths_disabled.keys()) == set(paths_enabled.keys())

        for oid in paths_disabled:
            dis_list = paths_disabled[oid]
            en_list = paths_enabled[oid]
            assert len(dis_list) == len(en_list)

            for d_p, e_p in zip(dis_list, en_list):
                # Verify bit-identical scores and identical fields
                assert d_p["edge_id_sequence"] == e_p["edge_id_sequence"]
                assert d_p["p_worst_q8"] == e_p["p_worst_q8"]
                assert d_p["p_best_q8"] == e_p["p_best_q8"]
                assert d_p["rank"] == e_p["rank"]
                assert d_p["confidence_band"] == e_p["confidence_band"]
                assert d_p["path_length"] == e_p["path_length"]
                assert d_p["flags_json"] == e_p["flags_json"]


# ===================================================================
# Test 16: Real Parser to SQLite Storage to RDCE Pipeline (Prompt 7B)
# ===================================================================
def test_real_parser_to_sqlite_storage_to_rdce_pipeline():
    """Verify condition transformation across actual parser -> storage -> RDCE pipeline."""
    from arf_rt.storage.migrations import run_migrations
    from arf_rt.models.core import ScenarioInput, NodeInput, EdgeInput, TemplateInput, ObjectiveInput
    from arf_rt.adapters.trust_policy_parser import resolve_trust_constraints
    from arf_rt.adapters.replay import ReplayAdapter

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    role_arn = "arn:aws:iam::123456789012:role/PipelineVerifiedRole"
    user_arn = "arn:aws:iam::123456789012:user/Engineer"

    trust_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "IpAddress": {"aws:SourceIp": ["198.51.100.0/24"]},
                    "Bool": {"aws:MultiFactorAuthPresent": "true"},
                    "StringEquals": {
                        "sts:ExternalId": "client-confidential-extid",
                        "aws:PrincipalTag/Department": "Finance",
                        "aws:SourceVpc": "vpc-0987654321fedcba0",
                        "aws:PrincipalOrgID": "o-abcdef1234",
                    },
                    "NumericLessThan": {"aws:MultiFactorAuthAge": "1800"},
                },
            }
        ],
    }

    edges_in = [
        {
            "edge_type": "STS_ASSUME_ROLE",
            "src": {"provider": "aws", "node_type": "USER", "provider_id": user_arn, "region": "-"},
            "dst": {"provider": "aws", "node_type": "ROLE", "provider_id": role_arn, "region": "-"},
            "region": "-",
        }
    ]

    constraints, edge_constraints, warnings = resolve_trust_constraints(
        {role_arn: trust_doc}, edges_in
    )
    assert len(constraints) == 7
    assert len(edge_constraints) == 7

    scenario = ScenarioInput(
        nodes=[
            NodeInput(provider="aws", node_type="USER", provider_id=user_arn, region="-"),
            NodeInput(provider="aws", node_type="ROLE", provider_id=role_arn, region="-"),
        ],
        templates=[
            TemplateInput(provider="aws", edge_type="STS_ASSUME_ROLE", features={}),
        ],
        edges=[
            EdgeInput(
                edge_type="STS_ASSUME_ROLE",
                src={"provider": "aws", "node_type": "USER", "provider_id": user_arn, "region": "-"},
                dst={"provider": "aws", "node_type": "ROLE", "provider_id": role_arn, "region": "-"},
                region="-",
                features={},
            )
        ],
        constraints=constraints,
        edge_constraints=edge_constraints,
        objectives=[
            ObjectiveInput(
                objective_type="ADMIN_ACCESS",
                start_nodes=[{"provider": "aws", "node_type": "USER", "provider_id": user_arn, "region": "-"}],
                target_nodes=[{"provider": "aws", "node_type": "ROLE", "provider_id": role_arn, "region": "-"}],
                max_depth=3,
                k=5,
            )
        ],
        observations=[],
    )

    adapter = ReplayAdapter(conn)
    ingest_warnings = adapter.ingest(scenario)
    assert len(ingest_warnings) == 0

    # Verify SQLite rows created by pipeline
    cursor = conn.cursor()
    cursor.execute("SELECT constraint_id, constraint_type, properties_json FROM constraints")
    stored_constraints = cursor.fetchall()
    assert len(stored_constraints) == 7

    # Load via build_constraint_index from the actual SQLite tables
    index = build_constraint_index(conn)
    assert index.load_error is None
    assert len(index) == 1

    edge_id = list(index.keys())[0]
    preds = index[edge_id]
    assert len(preds) == 7

    pred_by_key = {p.key: p for p in preds}

    # Verify supported condition keys and mappings
    assert pred_by_key["aws:SourceIp"].scope == ContextScope.REQUEST
    assert pred_by_key["aws:SourceIp"].operator == "IpAddress"
    assert pred_by_key["aws:SourceIp"].values == ["198.51.100.0/24"]

    assert pred_by_key["aws:MultiFactorAuthPresent"].scope == ContextScope.SESSION
    assert pred_by_key["aws:MultiFactorAuthPresent"].operator == "Bool"
    assert pred_by_key["aws:MultiFactorAuthPresent"].values == ["true"]

    assert pred_by_key["sts:ExternalId"].scope == ContextScope.CONFIG
    assert pred_by_key["sts:ExternalId"].operator == "StringEquals"
    assert pred_by_key["sts:ExternalId"].values == ["client-confidential-extid"]

    assert pred_by_key["aws:PrincipalTag/Department"].scope == ContextScope.PRINCIPAL
    assert pred_by_key["aws:PrincipalTag/Department"].operator == "StringEquals"
    assert pred_by_key["aws:PrincipalTag/Department"].values == ["Finance"]

    # Verify unsupported condition keys correctly map to UNKNOWN
    assert pred_by_key["aws:SourceVpc"].scope == ContextScope.UNKNOWN
    assert pred_by_key["aws:PrincipalOrgID"].scope == ContextScope.UNKNOWN
    assert pred_by_key["aws:MultiFactorAuthAge"].scope == ContextScope.UNKNOWN

    # Evaluate hop with unsupported conditions -> returns UNKNOWN with diagnostic
    evaluator = RestrictedDeterministicConstraintEvaluator()
    sink: list[dict] = []
    res = evaluate_candidate_hop(
        eid=edge_id,
        edge_data={"edge_type": "STS_ASSUME_ROLE", "src": user_arn, "dst": role_arn},
        constraint_index=index,
        evaluator=evaluator,
        audit_sink=sink,
    )
    assert res.status == FeasibilityStatus.UNKNOWN
    assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in res.unknown_rationale
    assert len(sink) == 1
    assert sink[0]["status"] == "UNKNOWN"

    # Evaluate edge with only supported predicates -> yields SAT with witness
    supported_preds = [
        pred_by_key["aws:SourceIp"],
        pred_by_key["aws:MultiFactorAuthPresent"],
        pred_by_key["sts:ExternalId"],
        pred_by_key["aws:PrincipalTag/Department"],
    ]
    res_sat = evaluate_candidate_hop(
        eid="edge_supported",
        edge_data={"edge_type": "STS_ASSUME_ROLE"},
        constraint_index={"edge_supported": supported_preds},
        evaluator=evaluator,
    )
    assert res_sat.status == FeasibilityStatus.SAT
    assert res_sat.witness is not None

    # Condition_type vs condition_key separation:
    # A property with condition_type but missing condition_key must return UNKNOWN
    isolated_preds = extract_predicates_from_constraint(
        "c_type_only",
        "TRUST_CONDITION",
        {"condition_type": "EXTERNAL_ID", "condition_operator": "StringEquals", "required_values": ["val"]},
    )
    assert len(isolated_preds) == 1
    assert isolated_preds[0].scope == ContextScope.UNKNOWN
    assert "internal category 'EXTERNAL_ID' without actual condition_key" in isolated_preds[0].description


# ===================================================================
# Test 17: Distinguishable Diagnostic Signatures (Prompt 7B)
# ===================================================================
def test_distinguishable_diagnostic_signatures_for_four_edge_states():
    """Verify that all four edge evaluation states have mutually distinct diagnostic signatures."""
    from research.ccpf.rdce import ContextPredicate
    evaluator = RestrictedDeterministicConstraintEvaluator()

    # 1. Successfully loaded edge with no contextual predicates
    sink_unconstrained: list[dict] = []
    res_unconstrained = evaluate_candidate_hop(
        eid="e_unconstrained",
        edge_data={"edge_type": "STS_ASSUME_ROLE"},
        constraint_index={"e_unconstrained": []},
        evaluator=evaluator,
        audit_sink=sink_unconstrained,
    )
    # RDCE contract: total_constraints == 0 returns UNKNOWN with NO_CONTEXT_CONSTRAINTS_DEFINED
    assert res_unconstrained.status == FeasibilityStatus.UNKNOWN
    assert sink_unconstrained[0]["status"] == "UNKNOWN"
    assert sink_unconstrained[0]["predicates_count"] == 0
    assert sink_unconstrained[0]["unknown_rationale"] == "NO_CONTEXT_CONSTRAINTS_DEFINED"
    assert sink_unconstrained[0]["contradiction_rationale"] is None

    # 2. Edge with valid contextual condition
    valid_pred = ContextPredicate(
        key="aws:SourceIp",
        operator="IpAddress",
        values=["10.0.0.0/16"],
        scope=ContextScope.REQUEST,
    )
    sink_valid: list[dict] = []
    res_valid = evaluate_candidate_hop(
        eid="e_valid",
        edge_data={"edge_type": "STS_ASSUME_ROLE"},
        constraint_index={"e_valid": [valid_pred]},
        evaluator=evaluator,
        audit_sink=sink_valid,
    )
    assert res_valid.status == FeasibilityStatus.SAT
    assert res_valid.witness is not None
    assert sink_valid[0]["status"] == "SAT"
    assert sink_valid[0]["predicates_count"] == 1
    assert sink_valid[0]["unknown_rationale"] is None

    # 3. Edge with malformed contextual condition
    malformed_pred = ContextPredicate(
        key="malformed_constraint_json",
        operator="Unsupported",
        values=[],
        scope=ContextScope.UNKNOWN,
        description="constraint:c_bad: malformed JSON",
    )
    sink_malformed: list[dict] = []
    res_malformed = evaluate_candidate_hop(
        eid="e_malformed",
        edge_data={"edge_type": "STS_ASSUME_ROLE"},
        constraint_index={"e_malformed": [malformed_pred]},
        evaluator=evaluator,
        audit_sink=sink_malformed,
    )
    assert res_malformed.status == FeasibilityStatus.UNKNOWN
    assert sink_malformed[0]["status"] == "UNKNOWN"
    assert sink_malformed[0]["predicates_count"] == 1
    assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in sink_malformed[0]["unknown_rationale"]

    # 4. Failed constraint query
    index_failure = ConstraintIndex(
        predicates_by_edge={},
        load_error="sqlite3.OperationalError: disk I/O error",
    )
    sink_failure: list[dict] = []
    res_failure = evaluate_candidate_hop(
        eid="e_failure",
        edge_data={"edge_type": "STS_ASSUME_ROLE"},
        constraint_index=index_failure,
        evaluator=evaluator,
        audit_sink=sink_failure,
    )
    assert res_failure.status == FeasibilityStatus.UNKNOWN
    assert sink_failure[0]["status"] == "UNKNOWN"
    assert sink_failure[0]["predicates_count"] == 0
    assert "CONSTRAINT_INDEX_LOAD_FAILURE" in sink_failure[0]["unknown_rationale"]
    assert "disk I/O error" in sink_failure[0]["unknown_rationale"]

    # Assert mutual distinctness across all 4 diagnostic signatures
    signatures = [
        (
            s[0]["status"],
            s[0]["predicates_count"],
            s[0]["unknown_rationale"],
            "LOAD_FAILURE" in str(s[0]["unknown_rationale"]),
        )
        for s in (sink_unconstrained, sink_valid, sink_malformed, sink_failure)
    ]
    assert len(set(signatures)) == 4, f"Signatures not mutually distinct: {signatures}"


# ===================================================================
# Test 18: Multi-Hop Counterexample Evaluation Limitation (Prompt 7C)
# ===================================================================
def test_multihop_counterexample_joint_unsat_evaluated_independently_as_sat():
    """Demonstrate that joint multi-hop UNSAT is evaluated independently as SAT by bridge."""
    from research.ccpf.rdce import (
        ContextPredicate,
        ContextScope,
        FeasibilityStatus,
        HopContextSpec,
        PathEvaluationInput,
        RestrictedDeterministicConstraintEvaluator,
    )

    evaluator = RestrictedDeterministicConstraintEvaluator()

    pred_hop1 = ContextPredicate(
        key="aws:SourceIp",
        operator="IpAddress",
        values=["10.0.0.0/24"],
        scope=ContextScope.REQUEST,
    )

    pred_hop2 = ContextPredicate(
        key="aws:SourceIp",
        operator="IpAddress",
        values=["192.168.1.0/24"],
        scope=ContextScope.REQUEST,
    )

    # 1. Direct RDCE evaluation of the joint 2-hop path under static origin assumption
    hop1_spec = HopContextSpec(
        hop=1, edge_type="STS_ASSUME_ROLE", src_node_id="NodeA", dst_node_id="NodeB", required_context=[pred_hop1]
    )
    hop2_spec = HopContextSpec(
        hop=2, edge_type="STS_ASSUME_ROLE", src_node_id="NodeB", dst_node_id="NodeC", required_context=[pred_hop2]
    )

    joint_input = PathEvaluationInput(
        path_id="path_joint_1_2",
        hops=[hop1_spec, hop2_spec],
        scenario_assumptions={"static_origin_assumption": True},
    )
    joint_result = evaluator.evaluate(joint_input)

    # Formal joint result: UNSAT due to disjoint CIDRs under static origin
    assert joint_result.status == FeasibilityStatus.UNSAT
    assert "disjoint" in str(joint_result.contradiction_rationale).lower()

    # 2. What integrated evaluate_candidate_hop does: each hop evaluated in isolation
    audit_sink: list[dict] = []
    res1 = evaluate_candidate_hop(
        eid="edge_hop1",
        edge_data={"edge_type": "STS_ASSUME_ROLE", "src": "NodeA", "dst": "NodeB"},
        constraint_index={"edge_hop1": [pred_hop1]},
        evaluator=evaluator,
        audit_sink=audit_sink,
        scenario_assumptions={"static_origin_assumption": True},
    )
    res2 = evaluate_candidate_hop(
        eid="edge_hop2",
        edge_data={"edge_type": "STS_ASSUME_ROLE", "src": "NodeB", "dst": "NodeC"},
        constraint_index={"edge_hop2": [pred_hop2]},
        evaluator=evaluator,
        audit_sink=audit_sink,
        scenario_assumptions={"static_origin_assumption": True},
    )

    # Empirical limitation proof: both independent hops evaluate to SAT!
    assert res1.status == FeasibilityStatus.SAT
    assert res2.status == FeasibilityStatus.SAT
    assert [s["status"] for s in audit_sink] == ["SAT", "SAT"]


# ===================================================================
# Test 19: Feature-Disabled Mode Zero Evaluations and Untouched Sink (Prompt 7C)
# ===================================================================
def test_feature_disabled_mode_zero_evaluations_and_sink_untouched():
    """Verify that when ccpf_guard=False, no RDCE calls occur and audit sink is untouched."""
    from unittest.mock import patch
    from arf_rt.engine.paths import search_and_store_top_k

    conn = _build_pipeline_db(COMPLEX)
    sink: list[dict] = []

    with patch("arf_rt.ccpf_bridge.build_constraint_index") as mock_build_idx, \
         patch("research.ccpf.rdce.RestrictedDeterministicConstraintEvaluator") as mock_evaluator, \
         patch("arf_rt.ccpf_bridge.evaluate_candidate_hop") as mock_eval_hop:

        results = search_and_store_top_k(conn, ccpf_guard=False, ccpf_audit_sink=sink)

        # Assert zero invocations of bridge and solver components
        assert mock_build_idx.call_count == 0
        assert mock_evaluator.call_count == 0
        assert mock_eval_hop.call_count == 0

        # Assert audit sink is untouched
        assert len(sink) == 0

        # Assert search executed and produced results
        assert len(results) > 0
