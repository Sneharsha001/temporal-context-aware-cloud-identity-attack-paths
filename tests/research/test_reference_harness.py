"""CCPF Offline Full-Prefix Reference Test Harness (Prompt 8B).

Validates the Restricted Deterministic Constraint Evaluator (RDCE) against
authoritative formal assumptions, counterexample fixtures (CE1-CE6, Test 18),
and path-level context feasibility semantics.

This harness serves as the offline correctness reference before any path-level
tracker or post-search annotation is integrated into production.

Key Architectural Safeguards:
- Uses RestrictedDeterministicConstraintEvaluator directly with complete PathEvaluationInput.
- Strictly isolated from production search engine (arf_rt/engine/paths.py untouched).
- Zero Q8 probability modification; zero active pruning.
- Demonstrates the differential gap between single-hop and joint multi-hop evaluation.
- No performance claims about production integration are derived from this harness.

Branch: temporal-context-dev
Workspace: C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL
Contract: docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0
Design: docs/CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md v1.1.0
"""

from __future__ import annotations

import ipaddress
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from research.ccpf.rdce import (
    ContextPredicate,
    ContextScope,
    FeasibilityStatus,
    HopContextSpec,
    PathEvaluationInput,
    PathEvaluationResult,
    ProducedStateModification,
    RestrictedDeterministicConstraintEvaluator,
    TransitionRelation,
)


@pytest.fixture
def evaluator() -> RestrictedDeterministicConstraintEvaluator:
    """Fixture providing a fresh RDCE instance."""
    return RestrictedDeterministicConstraintEvaluator()


# ============================================================================
# 1. Joint Two-Hop CIDR Contradiction (Prompt 8B Case 1)
# ============================================================================

def test_joint_two_hop_cidr_contradiction_with_static_origin(evaluator):
    """Case 1: Disjoint aws:SourceIp CIDRs across 2 hops evaluate to UNSAT under static origin.

    Validates:
      - Multi-hop counterexample (CE2 / Test 18).
      - Conjunction: 10.0.0.0/24 AND 192.168.1.0/24 is empty under static origin.
      - RDCE returns FeasibilityStatus.UNSAT with a constructive contradiction rationale.
    """
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

    hop1 = HopContextSpec(
        hop=1,
        edge_type="sts:AssumeRole",
        src_node_id="NodeA",
        dst_node_id="NodeB",
        required_context=[pred_hop1],
    )
    hop2 = HopContextSpec(
        hop=2,
        edge_type="sts:AssumeRole",
        src_node_id="NodeB",
        dst_node_id="NodeC",
        required_context=[pred_hop2],
    )

    eval_input = PathEvaluationInput(
        path_id="ref_case_1_disjoint_static",
        hops=[hop1, hop2],
        scenario_assumptions={"static_origin_assumption": True},
    )

    result = evaluator.evaluate(eval_input)

    assert result.status == FeasibilityStatus.UNSAT, (
        f"Expected UNSAT for disjoint static-origin CIDRs, got {result.status}"
    )
    assert result.contradiction_rationale is not None, "UNSAT result must carry contradiction rationale"
    assert "disjoint" in result.contradiction_rationale.lower(), (
        f"Contradiction rationale should explain disjoint subnets: {result.contradiction_rationale}"
    )
    assert result.witness is None, "UNSAT result must not carry a witness"
    assert result.evaluated_hops == 2, "Both hops must be evaluated"


# ============================================================================
# 2. No Static-Origin Assumption (Prompt 8B Case 2)
# ============================================================================

def test_disjoint_cidr_without_static_origin_assumption(evaluator):
    """Case 2: Without static origin assumption, disjoint IPs across hops are independent (SAT).

    Validates:
      - Assumptions are NOT silently inferred.
      - Without static_origin_assumption=True, REQUEST scope variables are mutable per API call.
      - RDCE returns FeasibilityStatus.SAT with separate hop-indexed witness IPs.
    """
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

    hop1 = HopContextSpec(
        hop=1,
        edge_type="sts:AssumeRole",
        src_node_id="NodeA",
        dst_node_id="NodeB",
        required_context=[pred_hop1],
    )
    hop2 = HopContextSpec(
        hop=2,
        edge_type="sts:AssumeRole",
        src_node_id="NodeB",
        dst_node_id="NodeC",
        required_context=[pred_hop2],
    )

    # Note: scenario_assumptions is empty (no static_origin_assumption)
    eval_input = PathEvaluationInput(
        path_id="ref_case_2_disjoint_no_assumption",
        hops=[hop1, hop2],
        scenario_assumptions={},
    )

    result = evaluator.evaluate(eval_input)

    assert result.status == FeasibilityStatus.SAT, (
        f"Expected SAT when static_origin_assumption is absent, got {result.status}"
    )
    assert result.witness is not None, "SAT result must provide a witness"
    assert "hop_1_SourceIp" in result.witness, "Witness must provide hop 1 IP"
    assert "hop_2_SourceIp" in result.witness, "Witness must provide hop 2 IP"

    # Verify synthesized IPs fall into their respective hop ranges
    ip1 = ipaddress.ip_address(result.witness["hop_1_SourceIp"])
    ip2 = ipaddress.ip_address(result.witness["hop_2_SourceIp"])
    assert ip1 in ipaddress.ip_network("10.0.0.0/24")
    assert ip2 in ipaddress.ip_network("192.168.1.0/24")


# ============================================================================
# 3. Differential and Oracle Strategy: Single-Hop vs. Joint Evaluation
# ============================================================================

def test_differential_oracle_single_hop_vs_joint_path(evaluator):
    """Demonstrate the differential gap between isolated single-hop and full-path evaluation.

    Formal Proof Obligation:
      Proves that Feasible(e1) AND Feasible(e2) does NOT imply Feasible(e1 o e2).
      Under Mode A (single-hop), both evaluate to SAT independently.
      Under full-prefix evaluation, the joint path evaluates to UNSAT.
    """
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

    hop1 = HopContextSpec(hop=1, edge_type="sts:AssumeRole", src_node_id="A", dst_node_id="B", required_context=[pred_hop1])
    hop2 = HopContextSpec(hop=2, edge_type="sts:AssumeRole", src_node_id="B", dst_node_id="C", required_context=[pred_hop2])

    assumptions = {"static_origin_assumption": True}

    # Isolated Evaluation of Hop 1
    res_hop1 = evaluator.evaluate(PathEvaluationInput(path_id="hop1_only", hops=[hop1], scenario_assumptions=assumptions))
    assert res_hop1.status == FeasibilityStatus.SAT

    # Isolated Evaluation of Hop 2
    res_hop2 = evaluator.evaluate(PathEvaluationInput(path_id="hop2_only", hops=[hop2], scenario_assumptions=assumptions))
    assert res_hop2.status == FeasibilityStatus.SAT

    # Joint Full-Prefix Evaluation
    res_joint = evaluator.evaluate(PathEvaluationInput(path_id="joint_1_2", hops=[hop1, hop2], scenario_assumptions=assumptions))
    assert res_joint.status == FeasibilityStatus.UNSAT

    # Assert the differential gap
    assert res_hop1.status == FeasibilityStatus.SAT and res_hop2.status == FeasibilityStatus.SAT
    assert res_joint.status == FeasibilityStatus.UNSAT


# ============================================================================
# 4. Compatible Persistent Request Context (Prompt 8B Case 3)
# ============================================================================

def test_compatible_persistent_request_context(evaluator):
    """Case 3: Compatible CIDR constraints across hops evaluate to SAT with valid intersection.

    Validates:
      - CE1 fixture semantics: 10.0.0.0/16 AND 10.0.1.0/24 intersect at 10.0.1.0/24.
      - RDCE synthesizes a valid witness inside the surviving subnet.
    """
    pred_hop1 = ContextPredicate(
        key="aws:SourceIp",
        operator="IpAddress",
        values=["10.0.0.0/16"],
        scope=ContextScope.REQUEST,
    )
    pred_hop2 = ContextPredicate(
        key="aws:SourceIp",
        operator="IpAddress",
        values=["10.0.1.0/24"],
        scope=ContextScope.REQUEST,
    )

    hop1 = HopContextSpec(hop=1, edge_type="iam:PassRole", src_node_id="A", dst_node_id="B", required_context=[pred_hop1])
    hop2 = HopContextSpec(hop=2, edge_type="iam:PassRole", src_node_id="B", dst_node_id="C", required_context=[pred_hop2])

    eval_input = PathEvaluationInput(
        path_id="ref_case_3_compatible_static",
        hops=[hop1, hop2],
        scenario_assumptions={"static_origin_assumption": True},
    )

    result = evaluator.evaluate(eval_input)

    assert result.status == FeasibilityStatus.SAT
    assert result.witness is not None
    assert "aws:SourceIp" in result.witness

    witness_ip = ipaddress.ip_address(result.witness["aws:SourceIp"])
    # Witness must be in both the wider and narrower CIDR
    assert witness_ip in ipaddress.ip_network("10.0.0.0/16")
    assert witness_ip in ipaddress.ip_network("10.0.1.0/24")


# ============================================================================
# 5. Hop-Local ExternalId Independence (Prompt 8B Case 4)
# ============================================================================

def test_hop_local_external_id_independence(evaluator):
    """Case 4: Distinct hop-local sts:ExternalId values do not clash across hops.

    Validates:
      - CE4 fixture semantics: sts:ExternalId is CONFIG-scoped (request parameter).
      - Different ExternalIds on consecutive hops do NOT produce UNSAT.
      - Witness provides distinct hop-indexed values.
    """
    pred_ext1 = ContextPredicate(
        key="sts:ExternalId",
        operator="StringEquals",
        values=["Client-Alpha-123"],
        scope=ContextScope.CONFIG,
    )
    pred_ext2 = ContextPredicate(
        key="sts:ExternalId",
        operator="StringEquals",
        values=["Client-Beta-456"],
        scope=ContextScope.CONFIG,
    )

    hop1 = HopContextSpec(hop=1, edge_type="sts:AssumeRole", src_node_id="A", dst_node_id="B", required_context=[pred_ext1])
    hop2 = HopContextSpec(hop=2, edge_type="sts:AssumeRole", src_node_id="B", dst_node_id="C", required_context=[pred_ext2])

    eval_input = PathEvaluationInput(path_id="ref_case_4_external_id", hops=[hop1, hop2])
    result = evaluator.evaluate(eval_input)

    assert result.status == FeasibilityStatus.SAT, (
        f"CONFIG scope variables must be hop-local; got status {result.status}"
    )
    assert result.witness is not None
    assert result.witness.get("hop_1_sts:ExternalId") == "Client-Alpha-123"
    assert result.witness.get("hop_2_sts:ExternalId") == "Client-Beta-456"


# ============================================================================
# 6. AssumeRole Transition: Session and Principal Lifecycle (Prompt 8B Case 5)
# ============================================================================

def test_assume_role_transition_lifecycle(evaluator):
    """Case 5: AssumeRole boundary correctly scopes session variables and principal tags.

    Validates:
      - Caller principal tags reset across sts:AssumeRole boundary.
      - Target role tags produced on AssumeRole become active principal tags on subsequent hop.
      - Contradiction with target role produced tag yields UNSAT.
    """
    # Hop 1: AssumeRole produces target tag Department='Security'
    hop1 = HopContextSpec(
        hop=1,
        edge_type="sts:AssumeRole",
        src_node_id="UserDev",
        dst_node_id="RoleSec",
        required_context=[
            ContextPredicate(key="aws:PrincipalTag/Department", operator="StringEquals", values=["Development"], scope=ContextScope.PRINCIPAL),
            ContextPredicate(key="aws:MultiFactorAuthPresent", operator="Bool", values=["true"], scope=ContextScope.SESSION),
        ],
        produced_context=[
            ProducedStateModification(key="active_principal", operation="SET", value="arn:aws:iam::123:role/RoleSec"),
            ProducedStateModification(key="aws:PrincipalTag/Department", operation="SET", value="Security"),
        ],
    )

    # Subcase 5A: Hop 2 requires the newly produced tag Department='Security' -> SAT
    hop2_match = HopContextSpec(
        hop=2,
        edge_type="s3:GetObject",
        src_node_id="RoleSec",
        dst_node_id="Resource",
        required_context=[
            ContextPredicate(key="aws:PrincipalTag/Department", operator="StringEquals", values=["Security"], scope=ContextScope.PRINCIPAL)
        ],
    )
    res_sat = evaluator.evaluate(PathEvaluationInput(path_id="p5a_match", hops=[hop1, hop2_match]))
    assert res_sat.status == FeasibilityStatus.SAT, f"Expected SAT for matching produced tag: {res_sat.contradiction_rationale}"
    assert res_sat.witness is not None

    # Subcase 5B: Hop 2 requires caller tag Department='Development' (which was reset to 'Security') -> UNSAT
    hop2_caller_tag = HopContextSpec(
        hop=2,
        edge_type="s3:GetObject",
        src_node_id="RoleSec",
        dst_node_id="Resource",
        required_context=[
            ContextPredicate(key="aws:PrincipalTag/Department", operator="StringEquals", values=["Development"], scope=ContextScope.PRINCIPAL)
        ],
    )
    res_unsat = evaluator.evaluate(PathEvaluationInput(path_id="p5b_caller_tag", hops=[hop1, hop2_caller_tag]))
    assert res_unsat.status == FeasibilityStatus.UNSAT, "Caller principal tags must not survive AssumeRole"
    assert "principal tag contradiction" in str(res_unsat.contradiction_rationale).lower()


# ============================================================================
# 7. Unsupported Scope Fallback (Prompt 8B Case 6)
# ============================================================================

def test_unsupported_scope_yields_unknown(evaluator):
    """Case 6: Unsupported or unknown scopes yield UNKNOWN and are never promoted to SAT/UNSAT.

    Validates:
      - ContextScope.UNKNOWN evaluates strictly to FeasibilityStatus.UNKNOWN.
      - Unknown rationale explicitly identifies the unsupported scope.
    """
    pred_unknown = ContextPredicate(
        key="custom:CorporateNetworkZone",
        operator="StringEquals",
        values=["Zone-DMZ"],
        scope=ContextScope.UNKNOWN,
    )
    hop = HopContextSpec(hop=1, edge_type="iam:PassRole", src_node_id="A", dst_node_id="B", required_context=[pred_unknown])

    result = evaluator.evaluate(PathEvaluationInput(path_id="ref_case_6_unknown_scope", hops=[hop]))

    assert result.status == FeasibilityStatus.UNKNOWN
    assert result.unknown_rationale is not None
    assert "UNSUPPORTED_OR_UNKNOWN_SCOPE" in result.unknown_rationale


# ============================================================================
# 8. Missing and Malformed Context Inputs (Prompt 8B Case 7)
# ============================================================================

@pytest.mark.parametrize(
    "path_id,hops,expected_rationale_substr",
    [
        ("empty_hops", [], "NO_CONTEXT_CONSTRAINTS_DEFINED"),
        (
            "unconstrained_hop",
            [HopContextSpec(hop=1, edge_type="iam:PassRole", src_node_id="A", dst_node_id="B", required_context=[])],
            "NO_CONTEXT_CONSTRAINTS_DEFINED",
        ),
        (
            "malformed_cidr_octets",
            [
                HopContextSpec(
                    hop=1,
                    edge_type="iam:PassRole",
                    src_node_id="A",
                    dst_node_id="B",
                    required_context=[
                        ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["999.999.999.999/99"], scope=ContextScope.REQUEST)
                    ],
                )
            ],
            "MALFORMED_CIDR_VALUE",
        ),
        (
            "unsupported_operator",
            [
                HopContextSpec(
                    hop=1,
                    edge_type="iam:PassRole",
                    src_node_id="A",
                    dst_node_id="B",
                    required_context=[
                        ContextPredicate(key="aws:PrincipalArn", operator="ArnEquals", values=["arn:aws:iam::123:role/R"], scope=ContextScope.PRINCIPAL)
                    ],
                )
            ],
            "UNSUPPORTED_OPERATOR",
        ),
        (
            "wildcard_in_stringlike",
            [
                HopContextSpec(
                    hop=1,
                    edge_type="iam:PassRole",
                    src_node_id="A",
                    dst_node_id="B",
                    required_context=[
                        ContextPredicate(key="aws:PrincipalTag/role", operator="StringLike", values=["admin*"], scope=ContextScope.PRINCIPAL)
                    ],
                )
            ],
            "UNSUPPORTED_WILDCARD_PATTERN_IN_STRINGLIKE",
        ),
    ],
)
def test_missing_and_malformed_context_yields_unknown(evaluator, path_id, hops, expected_rationale_substr):
    """Case 7: Missing, unannotated, or malformed constraints safely yield UNKNOWN."""
    result = evaluator.evaluate(PathEvaluationInput(path_id=path_id, hops=hops))

    assert result.status == FeasibilityStatus.UNKNOWN, (
        f"Malformed/missing input {path_id} must evaluate to UNKNOWN, got {result.status}"
    )
    assert result.unknown_rationale is not None
    assert expected_rationale_substr in result.unknown_rationale


# ============================================================================
# 9. Repeated Evaluation Determinism (Prompt 8B Case 8)
# ============================================================================

def test_repeated_evaluation_determinism(evaluator):
    """Case 8: Re-evaluating the identical input produces strictly deterministic results.

    Validates:
      - 20 repeated runs on both SAT and UNSAT inputs yield identical status,
        witnesses, and contradiction rationales.
    """
    pred_ip10 = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.0.0/24"], scope=ContextScope.REQUEST)
    pred_ip192 = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["192.168.1.0/24"], scope=ContextScope.REQUEST)
    pred_ip10_sub = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.0.128/25"], scope=ContextScope.REQUEST)

    h1 = HopContextSpec(hop=1, edge_type="sts:AssumeRole", src_node_id="A", dst_node_id="B", required_context=[pred_ip10])
    h2_unsat = HopContextSpec(hop=2, edge_type="sts:AssumeRole", src_node_id="B", dst_node_id="C", required_context=[pred_ip192])
    h2_sat = HopContextSpec(hop=2, edge_type="sts:AssumeRole", src_node_id="B", dst_node_id="C", required_context=[pred_ip10_sub])

    input_unsat = PathEvaluationInput(path_id="det_unsat", hops=[h1, h2_unsat], scenario_assumptions={"static_origin_assumption": True})
    input_sat = PathEvaluationInput(path_id="det_sat", hops=[h1, h2_sat], scenario_assumptions={"static_origin_assumption": True})

    first_unsat = evaluator.evaluate(input_unsat)
    first_sat = evaluator.evaluate(input_sat)

    for i in range(20):
        res_u = evaluator.evaluate(input_unsat)
        res_s = evaluator.evaluate(input_sat)

        assert res_u.status == first_unsat.status == FeasibilityStatus.UNSAT
        assert res_u.contradiction_rationale == first_unsat.contradiction_rationale

        assert res_s.status == first_sat.status == FeasibilityStatus.SAT
        assert res_s.witness == first_sat.witness


# ============================================================================
# 10. Witness and Rationale Contract Integrity (Prompt 8B Case 9)
# ============================================================================

def test_witness_and_rationale_contract_integrity(evaluator):
    """Case 9: Verify evaluator contract structural guarantees on result fields.

    Contractual Guarantees:
      - SAT: witness is a non-empty Dict; contradiction_rationale and unknown_rationale are None.
      - UNSAT: contradiction_rationale is a non-empty string; witness and unknown_rationale are None.
      - UNKNOWN: unknown_rationale is a non-empty string; witness and contradiction_rationale are None.
      - Decoupling: Zero probability fields or score multipliers exist in PathEvaluationResult.
    """
    pred_ip1 = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.0.0/16"], scope=ContextScope.REQUEST)
    pred_ip2 = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.2.0/24"], scope=ContextScope.REQUEST)
    pred_clash = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["172.16.0.0/12"], scope=ContextScope.REQUEST)

    h1 = HopContextSpec(hop=1, edge_type="iam:PassRole", src_node_id="A", dst_node_id="B", required_context=[pred_ip1])
    h2_sat = HopContextSpec(hop=2, edge_type="iam:PassRole", src_node_id="B", dst_node_id="C", required_context=[pred_ip2])
    h2_unsat = HopContextSpec(hop=2, edge_type="iam:PassRole", src_node_id="B", dst_node_id="C", required_context=[pred_clash])

    # SAT Contract
    r_sat = evaluator.evaluate(PathEvaluationInput("sat_path", [h1, h2_sat], scenario_assumptions={"static_origin_assumption": True}))
    assert r_sat.status == FeasibilityStatus.SAT
    assert isinstance(r_sat.witness, dict) and len(r_sat.witness) > 0
    assert r_sat.contradiction_rationale is None
    assert r_sat.unknown_rationale is None

    # UNSAT Contract
    r_unsat = evaluator.evaluate(PathEvaluationInput("unsat_path", [h1, h2_unsat], scenario_assumptions={"static_origin_assumption": True}))
    assert r_unsat.status == FeasibilityStatus.UNSAT
    assert r_unsat.witness is None
    assert isinstance(r_unsat.contradiction_rationale, str) and len(r_unsat.contradiction_rationale) > 0
    assert r_unsat.unknown_rationale is None

    # UNKNOWN Contract
    r_unk = evaluator.evaluate(PathEvaluationInput("unk_path", []))
    assert r_unk.status == FeasibilityStatus.UNKNOWN
    assert r_unk.witness is None
    assert r_unk.contradiction_rationale is None
    assert isinstance(r_unk.unknown_rationale, str) and len(r_unk.unknown_rationale) > 0

    # Decoupling Verification: No probability fields in PathEvaluationResult
    for f_name in ["probability", "p_best", "p_worst", "q8", "multiplier"]:
        assert not hasattr(r_sat, f_name), f"PathEvaluationResult must not have field {f_name}"
        assert not hasattr(r_unsat, f_name), f"PathEvaluationResult must not have field {f_name}"


# ============================================================================
# 11. Failure and Timeout Handling (Prompt 8B Case 10)
# ============================================================================

def test_iteration_ceiling_timeout_handling():
    """Case 10: Evaluator iteration ceiling triggers UNKNOWN with timeout_occurred=True.

    Validates:
      - When iteration_count > MAX_ITERATIONS, evaluation halts safely.
      - Result status is FeasibilityStatus.UNKNOWN.
      - timeout_occurred flag is True.
      - unknown_rationale is EVALUATOR_ITERATION_CEILING_EXCEEDED.
    """
    custom_eval = RestrictedDeterministicConstraintEvaluator()
    custom_eval.MAX_ITERATIONS = 2  # Low ceiling to trigger timeout

    pred1 = ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.0.0/16"], scope=ContextScope.REQUEST)
    pred2 = ContextPredicate(key="aws:PrincipalTag/env", operator="StringEquals", values=["prod"], scope=ContextScope.PRINCIPAL)
    pred3 = ContextPredicate(key="aws:MultiFactorAuthPresent", operator="Bool", values=["true"], scope=ContextScope.SESSION)

    hop1 = HopContextSpec(hop=1, edge_type="iam:PassRole", src_node_id="A", dst_node_id="B", required_context=[pred1, pred2, pred3])

    result = custom_eval.evaluate(PathEvaluationInput("timeout_path", [hop1]))

    assert result.status == FeasibilityStatus.UNKNOWN
    assert result.timeout_occurred is True
    assert result.unknown_rationale == "EVALUATOR_ITERATION_CEILING_EXCEEDED"
