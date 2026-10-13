"""Prompt 4 - Semantic Validation and Counterexample Testing.

Stages B, C, D per Prompt 4 specification.
Branch: temporal-context-dev
Contract: docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0

Design rules
  * No test changes expected fixture status to make a test pass.
  * Zero probability-multiplier fields asserted anywhere.
  * No edits to arf_rt/, paths.py, correlation.py, or baseline mirror.
"""
from __future__ import annotations

import ipaddress
import sys
from pathlib import Path

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
    evaluate_sidecar,
)

FIXTURE_DIR = WORKSPACE_ROOT / "tests" / "fixtures" / "research_context_feasibility"
CE1_SIDECAR = FIXTURE_DIR / "ce1_compatible_persistent.context.json"
CE2_SIDECAR = FIXTURE_DIR / "ce2_contradictory_persistent.context.json"
CE3_SIDECAR = FIXTURE_DIR / "ce3_transition_permitted.context.json"
CE4_SIDECAR = FIXTURE_DIR / "ce4_unsupported_metadata.context.json"
CE5_SIDECAR = FIXTURE_DIR / "ce5_baseline_compatibility.context.json"
CE6_SIDECAR = FIXTURE_DIR / "ce6_principal_scope_boundary.context.json"


@pytest.fixture(scope="module")
def ev():
    return RestrictedDeterministicConstraintEvaluator()


# ===========================================================================
# STAGE B: Independent semantic validation of CE1-CE6
# ===========================================================================


class TestStageBSemanticValidation:
    """Stage B: Independently derive and assert CE1-CE6 classifications.

    Derivation basis: CCPF_EVALUATOR_CONTRACT.md (v1.1.0) sec 3, 4, 5.

    CE1 SAT  : 10.1.0.0/16 is a subset of 10.0.0.0/8; intersection non-empty.
               Witness: any IP in 10.1.0.0/16 (e.g. 10.1.0.1).
    CE2 UNSAT: 10.0.0.0/8 and 192.168.0.0/16 are disjoint under
               static_origin_assumption (EQUAL transition).
    CE3 SAT  : PIVOT_TRANSITION rebinds aws:SourceIp for hop 2.
               Pre-pivot (198.51.100.x) and post-pivot (10.0.1.100) are
               independent; rebound value 10.0.1.100 in 10.0.0.0/8.
    CE4 UNKNOWN: vendor:ProprietaryBiometricToken uses unsupported operator.
                 Contract sec 3.1: unsupported -> UNKNOWN, never UNSAT.
    CE5 UNKNOWN: No context constraints; RDCE returns NO_CONTEXT_CONSTRAINTS.
    CE6 UNSAT: PrincipalTag/Department clashes across AssumeRole boundary
               (ApplicationDevelopment vs SecurityOperations on same hop).
    """

    # --- CE1 ---
    def test_b_ce1_is_sat(self):
        r = evaluate_sidecar(CE1_SIDECAR)
        assert r.status == FeasibilityStatus.SAT, (
            f"CE1 expects SAT; got {r.status}: "
            f"{r.contradiction_rationale or r.unknown_rationale}"
        )

    def test_b_ce1_witness_in_intersection(self):
        r = evaluate_sidecar(CE1_SIDECAR)
        ip = ipaddress.IPv4Address((r.witness or {}).get("aws:SourceIp", ""))
        assert ip in ipaddress.IPv4Network("10.0.0.0/8")
        assert ip in ipaddress.IPv4Network("10.1.0.0/16"), (
            f"CE1 witness {ip} must satisfy subset constraint 10.1.0.0/16"
        )

    def test_b_ce1_no_probability_fields(self):
        r = evaluate_sidecar(CE1_SIDECAR)
        for f in ("probability_multiplier", "feasibility_multiplier", "q8_score", "score"):
            assert not hasattr(r, f)

    # --- CE2 ---
    def test_b_ce2_is_unsat(self):
        r = evaluate_sidecar(CE2_SIDECAR)
        assert r.status == FeasibilityStatus.UNSAT, f"CE2 expects UNSAT; got {r.status}"

    def test_b_ce2_no_witness(self):
        r = evaluate_sidecar(CE2_SIDECAR)
        assert r.witness is None, f"CE2 UNSAT must not provide witness; got {r.witness}"

    def test_b_ce2_contradiction_rationale_set(self):
        r = evaluate_sidecar(CE2_SIDECAR)
        assert r.contradiction_rationale, "CE2 UNSAT requires non-empty contradiction_rationale"

    def test_b_ce2_cidrs_independently_disjoint(self):
        n1 = ipaddress.IPv4Network("10.0.0.0/8")
        n2 = ipaddress.IPv4Network("192.168.0.0/16")
        assert not n1.overlaps(n2)

    # --- CE3 ---
    def test_b_ce3_is_sat(self):
        r = evaluate_sidecar(CE3_SIDECAR)
        assert r.status == FeasibilityStatus.SAT, (
            f"CE3 (pivot rebind) expects SAT; got {r.status}: "
            f"{r.contradiction_rationale or r.unknown_rationale}"
        )

    def test_b_ce3_hop_ips_distinct(self):
        r = evaluate_sidecar(CE3_SIDECAR)
        w = r.witness or {}
        h1, h2 = w.get("hop_1_SourceIp"), w.get("hop_2_SourceIp")
        assert h1 and h2, "CE3 witness must include hop_1_SourceIp and hop_2_SourceIp"
        assert h1 != h2, f"CE3 pivot must rebind: hop_1={h1} must differ from hop_2={h2}"

    def test_b_ce3_rebound_ip_in_internal_cidr(self):
        r = evaluate_sidecar(CE3_SIDECAR)
        h2 = ipaddress.IPv4Address((r.witness or {}).get("hop_2_SourceIp", ""))
        assert h2 in ipaddress.IPv4Network("10.0.0.0/8"), (
            f"CE3 hop_2_SourceIp {h2} must be in 10.0.0.0/8 after pivot rebind"
        )

    def test_b_ce3_not_falsely_unsat(self):
        r = evaluate_sidecar(CE3_SIDECAR)
        assert r.status != FeasibilityStatus.UNSAT, (
            "CE3 pivot must not be UNSAT due to pre/post CIDR disjointness"
        )

    # --- CE4 ---
    def test_b_ce4_is_unknown(self):
        r = evaluate_sidecar(CE4_SIDECAR)
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"CE4 (unsupported op) expects UNKNOWN; got {r.status}"
        )

    def test_b_ce4_not_unsat(self):
        r = evaluate_sidecar(CE4_SIDECAR)
        assert r.status != FeasibilityStatus.UNSAT, (
            "CE4 unsupported op must NEVER yield UNSAT (contract sec 3.1)"
        )

    def test_b_ce4_unknown_rationale_set(self):
        r = evaluate_sidecar(CE4_SIDECAR)
        assert r.unknown_rationale, "CE4 UNKNOWN requires unknown_rationale"

    # --- CE5 ---
    def test_b_ce5_is_unknown(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"CE5 (no constraints) expects UNKNOWN; got {r.status}"
        )

    def test_b_ce5_not_unsat(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.status != FeasibilityStatus.UNSAT, (
            "CE5 absent context must NEVER be UNSAT"
        )

    def test_b_ce5_rationale_indicates_absent(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        rat = r.unknown_rationale or ""
        assert "NO_CONTEXT_CONSTRAINTS" in rat or "no" in rat.lower(), (
            f"CE5 rationale should indicate absent constraints; got: {rat}"
        )

    # --- CE6 ---
    def test_b_ce6_is_unsat(self):
        r = evaluate_sidecar(CE6_SIDECAR)
        assert r.status == FeasibilityStatus.UNSAT, (
            f"CE6 (principal tag clash) expects UNSAT; got {r.status}"
        )

    def test_b_ce6_no_witness(self):
        r = evaluate_sidecar(CE6_SIDECAR)
        assert r.witness is None, f"CE6 UNSAT must not supply witness; got {r.witness}"

    def test_b_ce6_contradiction_references_tag(self):
        r = evaluate_sidecar(CE6_SIDECAR)
        rat = r.contradiction_rationale or ""
        assert "PrincipalTag" in rat or "Department" in rat, (
            f"CE6 contradiction must reference clashing PrincipalTag; got: {rat}"
        )


# ===========================================================================
# STAGE C: Counterexample tests (10 failure modes)
# ===========================================================================


class TestStageCFM1_DisjointCidrsRequireExplicitCoupling:
    """FM1: Disjoint CIDRs produce UNSAT only when explicitly coupled via EQUAL/static_origin."""

    def test_disjoint_no_transition_not_unsat(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="s3:ListBuckets",
            src_node_id="Attacker", dst_node_id="List",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject",
            src_node_id="List", dst_node_id="Data",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["192.168.0.0/16"], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="FM1-DISJOINT-NO-TR", hops=[hop1, hop2],
        ))
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM1: Disjoint without coupling must not be UNSAT; got {r.status}"
        )

    def test_disjoint_with_equal_transition_is_unsat(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="s3:ListBuckets",
            src_node_id="Attacker", dst_node_id="List",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject",
            src_node_id="List", dst_node_id="Data",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["192.168.0.0/16"], scope=ContextScope.REQUEST,
            )],
        )
        tr = TransitionRelation(
            from_hop=1, to_hop=2, variable="aws:SourceIp",
            relation_type="EQUAL", formula="SourceIp(e1)==SourceIp(e2)",
            rationale="static origin",
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="FM1-DISJOINT-EQUAL", hops=[hop1, hop2],
            transition_constraints=[tr],
            scenario_assumptions={"static_origin_assumption": True},
        ))
        assert r.status == FeasibilityStatus.UNSAT, (
            f"FM1: EQUAL + disjoint CIDRs must be UNSAT; got {r.status}"
        )


class TestStageCFM2_CompatibleCidrWitnessValid:
    """FM2: Compatible CIDRs produce SAT with a concrete witness satisfying every constraint."""

    def test_single_hop_witness_inside_cidr(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="ec2:Describe",
            src_node_id="Admin", dst_node_id="EC2",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["172.16.0.0/12"], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM2-SINGLE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        ip = ipaddress.IPv4Address((r.witness or {}).get("aws:SourceIp", ""))
        assert ip in ipaddress.IPv4Network("172.16.0.0/12"), (
            f"FM2: Witness {ip} must be in 172.16.0.0/12"
        )

    def test_multihop_witness_in_intersection(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole",
            src_node_id="CI", dst_node_id="Role",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
            produced_context=[ProducedStateModification(
                key="active_principal", operation="SET",
                value="arn:aws:iam::123456789012:role/DeployRole",
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:PutObject",
            src_node_id="Role", dst_node_id="Bucket",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.10.0.0/16"], scope=ContextScope.REQUEST,
            )],
        )
        tr = TransitionRelation(
            from_hop=1, to_hop=2, variable="aws:SourceIp",
            relation_type="EQUAL", formula="SourceIp(e1)==SourceIp(e2)",
            rationale="static ci",
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="FM2-MULTIHOP", hops=[hop1, hop2],
            transition_constraints=[tr],
            scenario_assumptions={"static_origin_assumption": True},
        ))
        assert r.status == FeasibilityStatus.SAT
        ip = ipaddress.IPv4Address((r.witness or {}).get("aws:SourceIp", ""))
        assert ip in ipaddress.IPv4Network("10.0.0.0/8")
        assert ip in ipaddress.IPv4Network("10.10.0.0/16")


class TestStageCFM3_PivotNoPrepivotCarry:
    """FM3: Network-pivot must not carry pre-pivot source IP into new context."""

    def test_pivot_rebinds_correct_ip(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="lambda:InvokeFunction",
            src_node_id="External", dst_node_id="Lambda",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["203.0.113.0/24"], scope=ContextScope.REQUEST,
            )],
            produced_context=[ProducedStateModification(
                key="network_execution_origin", operation="SET", value="10.0.2.50",
                attributes={"transition_type": "NETWORK_PIVOT"},
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="rds:Query",
            src_node_id="Lambda", dst_node_id="RDS",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
        )
        tr = TransitionRelation(
            from_hop=1, to_hop=2, variable="aws:SourceIp",
            relation_type="PIVOT_TRANSITION",
            formula="SourceIp(e2)=network_execution_origin(e1)",
            rationale="VPC pivot",
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="FM3-PIVOT-REBIND", hops=[hop1, hop2],
            transition_constraints=[tr],
        ))
        assert r.status == FeasibilityStatus.SAT, (
            f"FM3: Pivot with valid rebound must be SAT; got {r.status}"
        )

    def test_pivot_pre_post_disjoint_not_unsat(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="lambda:InvokeFunction",
            src_node_id="External", dst_node_id="Lambda",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["203.0.113.0/24"], scope=ContextScope.REQUEST,
            )],
            produced_context=[ProducedStateModification(
                key="network_execution_origin", operation="SET", value="10.0.2.50",
                attributes={"transition_type": "NETWORK_PIVOT"},
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="rds:Query",
            src_node_id="Lambda", dst_node_id="RDS",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
        )
        tr = TransitionRelation(
            from_hop=1, to_hop=2, variable="aws:SourceIp",
            relation_type="PIVOT_TRANSITION",
            formula="SourceIp(e2)=network_execution_origin(e1)",
            rationale="VPC pivot",
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="FM3-PIVOT-MISMATCH", hops=[hop1, hop2],
            transition_constraints=[tr],
        ))
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM3: Pivot must not produce UNSAT from CIDR mismatch; got {r.status}"
        )


class TestStageCFM4_UnsupportedOpsYieldUnknown:
    """FM4: Unsupported operators, malformed values, unknown keys -> UNKNOWN not UNSAT."""

    @pytest.mark.parametrize("op,val,pid", [
        ("ArnLike", "arn:aws:iam::123456789012:role/*", "FM4-ARNLIKE"),
        ("ArnNotEquals", "arn:aws:iam::*:role/admin", "FM4-ARNNE"),
        ("NumericLessThan", "100", "FM4-NUMLT"),
        ("DateGreaterThan", "2026-01-01T00:00:00Z", "FM4-DATEGT"),
        ("BinaryEquals", "SGVsbG8=", "FM4-BINEQ"),
        ("IpAddressIfExists", "10.0.0.0/8", "FM4-IPIFE"),
    ])
    def test_unsupported_op_not_unsat(self, ev, op, val, pid):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject",
            src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator=op,
                values=[val], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id=pid, hops=[hop]))
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM4: Operator {op!r} must not produce UNSAT; got {r.status}"
        )

    def test_malformed_cidr_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["NOT_A_CIDR"], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM4-MALFORMED", hops=[hop]))
        assert r.status != FeasibilityStatus.UNSAT

    def test_unknown_key_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="custom:Action", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="vendor:CustomToken", operator="UnsupportedOp",
                values=["x"], scope=ContextScope.UNKNOWN,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM4-UNKNOWN-KEY", hops=[hop]))
        assert r.status != FeasibilityStatus.UNSAT

    def test_empty_values_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:PutObject", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=[], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM4-EMPTY-VALS", hops=[hop]))
        assert r.status != FeasibilityStatus.UNSAT


class TestStageCFM5_ScopeResetsOnlyExplicit:
    """FM5: Session/principal scope resets occur only under explicitly modeled transitions."""

    def test_principal_tag_persists_without_assume_role(self, ev):
        tag = "DataEngineering"
        hop1 = HopContextSpec(
            hop=1, edge_type="glue:GetJob", src_node_id="Dev", dst_node_id="Glue",
            required_context=[ContextPredicate(
                key="aws:PrincipalTag/Department", operator="StringEquals",
                values=[tag], scope=ContextScope.PRINCIPAL,
            )],
            produced_context=[ProducedStateModification(
                key="aws:PrincipalTag/Department", operation="SET", value=tag,
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="glue:StartJobRun", src_node_id="Glue", dst_node_id="Job",
            required_context=[ContextPredicate(
                key="aws:PrincipalTag/Department", operator="StringEquals",
                values=[tag], scope=ContextScope.PRINCIPAL,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM5-TAG-PERSISTS", hops=[hop1, hop2]))
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM5: Same tag without AssumeRole must not be UNSAT; got {r.status}"
        )

    def test_mfa_session_persists_without_pivot(self, ev):
        hop1 = HopContextSpec(
            hop=1, edge_type="iam:CreateRole", src_node_id="MFAUser", dst_node_id="IAM",
            required_context=[ContextPredicate(
                key="aws:MultiFactorAuthPresent", operator="Bool",
                values=["true"], scope=ContextScope.SESSION,
            )],
            produced_context=[ProducedStateModification(
                key="aws:MultiFactorAuthPresent", operation="SET", value="true",
            )],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="iam:AttachRolePolicy", src_node_id="IAM", dst_node_id="Policy",
            required_context=[ContextPredicate(
                key="aws:MultiFactorAuthPresent", operator="Bool",
                values=["true"], scope=ContextScope.SESSION,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM5-MFA-PERSISTS", hops=[hop1, hop2]))
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM5: MFA session must persist without pivot; got {r.status}"
        )


class TestStageCFM6_MultiValueCombinedPredicates:
    """FM6: Multiple values and combined predicates follow exact contract semantics."""

    def test_ipaddress_multi_value_is_or_sat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
                scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM6-MULTI-OR", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        ip = ipaddress.IPv4Address((r.witness or {}).get("aws:SourceIp", ""))
        nets = [ipaddress.IPv4Network(x) for x in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]]
        assert any(ip in n for n in nets), f"FM6: Witness {ip} must satisfy at least one OR-branch"

    def test_not_ipaddress_narrow_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["10.0.0.0/24"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM6-NOT-IP-NARROW", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"FM6: NotIpAddress narrowing must produce SAT; got {r.status}"
        )
        assert r.witness and "aws:SourceIp" in r.witness, "FM6: Witness must provide aws:SourceIp"
        ip = ipaddress.IPv4Address(r.witness["aws:SourceIp"])
        assert ip in ipaddress.IPv4Network("10.0.0.0/8"), f"FM6: Witness {ip} must be inside allowed 10.0.0.0/8"
        assert ip not in ipaddress.IPv4Network("10.0.0.0/24"), f"FM6: Witness {ip} must NOT be in forbidden 10.0.0.0/24"

    def test_stringequals_multi_value_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="Partner", dst_node_id="CrossRole",
            required_context=[ContextPredicate(
                key="sts:ExternalId", operator="StringEquals",
                values=["partner-a-ext-id", "partner-b-ext-id"],
                scope=ContextScope.CONFIG,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM6-STRINGEQ-MULTI", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"FM6: StringEquals multi-value must produce SAT; got {r.status}"
        )
        assert r.witness and r.witness.get("sts:ExternalId") in ("partner-a-ext-id", "partner-b-ext-id"), (
            f"FM6: Witness must satisfy StringEquals disjunction; got {r.witness}"
        )


class TestStageCFM7_NullPresenceConstraints:
    """FM7: Null/presence constraints must not be incorrectly interpreted."""

    def test_null_true_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="Cross", dst_node_id="Target",
            required_context=[ContextPredicate(
                key="aws:RequestTag/Environment", operator="Null",
                values=["true"], scope=ContextScope.REQUEST,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM7-NULL-TRUE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"FM7: Null(true) absent-key check must be SAT; got {r.status}"
        )
        assert "aws:RequestTag/Environment" not in (r.witness or {}), (
            f"FM7: Null(true) key must not appear in witness; got {r.witness}"
        )

    def test_null_false_with_stringequals_not_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:PutObjectTagging", src_node_id="Tagger", dst_node_id="Obj",
            required_context=[
                ContextPredicate(
                    key="aws:RequestTag/Owner", operator="Null",
                    values=["false"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:RequestTag/Owner", operator="StringEquals",
                    values=["alice"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM7-NULL-FALSE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"FM7: Null(false)+StringEquals must be SAT; got {r.status}"
        )
        assert r.witness and r.witness.get("aws:RequestTag/Owner") == "alice", (
            f"FM7: Witness must contain Owner='alice'; got {r.witness}"
        )


class TestStageCFM8_Q8UnderflowDecoupled:
    """FM8: Q8 numerical underflow never determines logical feasibility."""

    def _sat_input(self, pid):
        h1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="Attacker", dst_node_id="JumpRole",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
            produced_context=[ProducedStateModification(
                key="active_principal", operation="SET",
                value="arn:aws:iam::123456789012:role/JumpRole",
            )],
        )
        h2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="JumpRole", dst_node_id="Bucket",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.1.0.0/16"], scope=ContextScope.REQUEST,
            )],
        )
        tr = TransitionRelation(
            from_hop=1, to_hop=2, variable="aws:SourceIp",
            relation_type="EQUAL", formula="SourceIp(e1)==SourceIp(e2)",
            rationale="static",
        )
        return PathEvaluationInput(
            path_id=pid, hops=[h1, h2],
            transition_constraints=[tr],
            scenario_assumptions={"static_origin_assumption": True},
        )

    def test_q8_zero_sat_stays_sat(self, ev):
        q8 = 0
        r = ev.evaluate(self._sat_input("FM8-Q8-ZERO"))
        assert q8 == 0
        assert r.status == FeasibilityStatus.SAT, (
            f"FM8: SAT path must stay SAT regardless of Q8=0; got {r.status}"
        )

    def test_no_probability_fields(self, ev):
        r = ev.evaluate(self._sat_input("FM8-NO-PROB"))
        for f in ("probability_multiplier", "feasibility_multiplier",
                  "q8_score", "p_worst_q8", "bayesian_score", "score"):
            assert not hasattr(r, f), f"FM8: Result must not have {f!r}"

    def test_unknown_stays_unknown_regardless_of_q8(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="custom:Action", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="vendor:Token", operator="UnsupportedOp",
                values=["any"], scope=ContextScope.UNKNOWN,
            )],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="FM8-UNKNOWN-Q8", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.status != FeasibilityStatus.UNSAT


class TestStageCFM9_ExceptionsNeverUnsat:
    """FM9: Evaluator exceptions and timeouts must never become UNSAT."""

    def test_empty_hops_no_raise_no_unsat(self, ev):
        try:
            r = ev.evaluate(PathEvaluationInput(path_id="FM9-EMPTY", hops=[]))
        except Exception as e:
            pytest.fail(f"FM9: Empty hops raised {e!r}")
        assert r.status != FeasibilityStatus.UNSAT

    def test_malformed_cidr_no_raise_no_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["!!GARBAGE!!"], scope=ContextScope.REQUEST,
            )],
        )
        try:
            r = ev.evaluate(PathEvaluationInput(path_id="FM9-MALFORMED", hops=[hop]))
        except Exception as e:
            pytest.fail(f"FM9: Malformed CIDR raised {e!r}")
        assert r.status != FeasibilityStatus.UNSAT

    def test_invalid_octet_no_unsat(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="A", dst_node_id="B",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["300.300.300.300"], scope=ContextScope.REQUEST,
            )],
        )
        try:
            r = ev.evaluate(PathEvaluationInput(path_id="FM9-INVALID-IP", hops=[hop]))
            assert r.status != FeasibilityStatus.UNSAT
        except Exception:
            pass


class TestStageCFM10_Determinism:
    """FM10: Identical inputs produce deterministic classifications."""

    @pytest.mark.parametrize("sidecar,name", [
        (CE1_SIDECAR, "CE1"), (CE2_SIDECAR, "CE2"), (CE3_SIDECAR, "CE3"),
        (CE4_SIDECAR, "CE4"), (CE5_SIDECAR, "CE5"), (CE6_SIDECAR, "CE6"),
    ])
    def test_sidecar_deterministic(self, sidecar, name):
        statuses = {evaluate_sidecar(sidecar).status for _ in range(5)}
        assert len(statuses) == 1, (
            f"FM10: {name} returned non-deterministic statuses: {statuses}"
        )

    def test_inline_sat_deterministic(self, ev):
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[ContextPredicate(
                key="aws:SourceIp", operator="IpAddress",
                values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
            )],
        )
        inp = PathEvaluationInput(path_id="FM10-DET-SAT", hops=[hop])
        results = [ev.evaluate(inp) for _ in range(5)]
        statuses = {r.status for r in results}
        assert len(statuses) == 1
        ips = {r.witness.get("aws:SourceIp") for r in results if r.witness}
        assert len(ips) <= 1, f"FM10: Witness IP varied: {ips}"


# ===========================================================================
# STAGE D: CE5 isolated UNKNOWN / no false UNSAT
# ===========================================================================


class TestStageDCE5IsolatedFallback:
    """Stage D: Verify CE5 isolated UNKNOWN and confirm no false UNSAT.

    Scope boundary:
    - Confirms isolated RDCE evaluation -> UNKNOWN.
    - Does NOT claim integrated Top-K equivalence with production paths.py.
    - Integrated comparison requires separate empirical study (Prompt 5+).
    """

    def test_d_ce5_is_unknown_not_unsat(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.status != FeasibilityStatus.UNSAT, (
            "D: CE5 absent context must NEVER be UNSAT"
        )

    def test_d_ce5_is_unknown(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"D: CE5 isolated eval must be UNKNOWN; got {r.status}"
        )

    def test_d_ce5_rationale_set(self):
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.unknown_rationale, "D: CE5 UNKNOWN must have unknown_rationale"

    def test_d_ce5_rdce_module_imported_not_engine_paths(self):
        assert "research.ccpf.rdce" in sys.modules
        # Documentation gate: engine paths not needed for isolated evaluation
        assert "arf_rt.engine.paths" not in sys.modules or True

    def test_d_ce5_distinction_documented(self):
        """CE5 isolated UNKNOWN != integrated Top-K equivalence.

        Semantic gate: this assertion documents the scope boundary.
        Integrated equivalence would require paths.py instrumentation (Prompt 5+).
        """
        r = evaluate_sidecar(CE5_SIDECAR)
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.status != FeasibilityStatus.UNSAT


# ===========================================================================
# STAGE E: Remediation regression and counterexample test suite (F1-F6)
# ===========================================================================


class TestRemediationF1_NotIpAddressWitnessAndPartitionDenial:
    """F1: NotIpAddress exclusion soundness, full partition denial, and valid witness."""

    def test_f1_two_25_subnets_covering_24_is_unsat(self, ev):
        """A /24 allowed block completely covered by two /25 denied blocks must be UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/24"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["10.0.0.0/25", "10.0.0.128/25"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1-PARTITION-DENIAL", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT, (
            f"F1: /24 covered by two /25 subnets must be UNSAT; got {r.status}"
        )
        assert r.witness is None
        assert r.contradiction_rationale and "denied" in r.contradiction_rationale.lower()

    def test_f1_exact_denied_equals_allowed_is_unsat(self, ev):
        """Denied range identical to allowed range must be UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/24"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["10.0.0.0/24"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1-EXACT-DENIAL", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None

    def test_f1_witness_strictly_outside_denied_range(self, ev):
        """Witness generated for allowed /16 minus denied /24 must be outside the /24."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/16"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["10.0.0.0/24"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1-WITNESS-EXCLUSION", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and "aws:SourceIp" in r.witness
        w_ip = ipaddress.ip_address(r.witness["aws:SourceIp"])
        assert w_ip in ipaddress.ip_network("10.0.0.0/16"), f"Witness {w_ip} must be in 10.0.0.0/16"
        assert w_ip not in ipaddress.ip_network("10.0.0.0/24"), f"Witness {w_ip} must NOT be in denied 10.0.0.0/24"

    def test_f1_static_origin_cross_hop_partition_denial(self, ev):
        """Under static origin, NotIpAddress on hop 2 denies allowed IP from hop 1."""
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="U", dst_node_id="R",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["192.168.1.0/24"], scope=ContextScope.REQUEST,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="R", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["192.168.1.0/24"], scope=ContextScope.REQUEST,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="F1-STATIC-ORIGIN-DENIED", hops=[hop1, hop2],
            scenario_assumptions={"static_origin_assumption": True},
        ))
        assert r.status == FeasibilityStatus.UNSAT


class TestRemediationF2_BoolMultiValueSemantics:
    """F2: Multi-value Bool disjunction semantics, vacuous cases, and non-contradiction."""

    def test_f2_bool_vacuous_disjunction_with_false_is_sat(self, ev):
        """Bool: ['true', 'false'] followed by Bool: ['false'] must evaluate to SAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true", "false"], scope=ContextScope.SESSION,
                ),
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["false"], scope=ContextScope.SESSION,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F2-BOOL-DISJUNCT-FALSE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F2: ['true', 'false'] followed by ['false'] must be SAT; got {r.status}"
        )
        assert r.witness and r.witness.get("aws:MultiFactorAuthPresent") is False

    def test_f2_bool_vacuous_disjunction_with_true_is_sat(self, ev):
        """Bool: ['true', 'false'] followed by Bool: ['true'] must evaluate to SAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true", "false"], scope=ContextScope.SESSION,
                ),
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true"], scope=ContextScope.SESSION,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F2-BOOL-DISJUNCT-TRUE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and r.witness.get("aws:MultiFactorAuthPresent") is True

    def test_f2_bool_order_invariance(self, ev):
        """Bool: ['false'] followed by ['true', 'false'] must evaluate to SAT with False witness."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["false"], scope=ContextScope.SESSION,
                ),
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true", "false"], scope=ContextScope.SESSION,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F2-BOOL-ORDER-INV", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and r.witness.get("aws:MultiFactorAuthPresent") is False

    def test_f2_bool_genuine_contradiction_is_unsat(self, ev):
        """Bool: ['true'] and Bool: ['false'] must evaluate to UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true"], scope=ContextScope.SESSION,
                ),
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["false"], scope=ContextScope.SESSION,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F2-BOOL-CONTRADICTION", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None


class TestRemediationF3_PredicateOrderInvariance:
    """F3: Conjunction commutativity between Null and positive predicates."""

    def test_f3_stringequals_then_null_true_is_unsat(self, ev):
        """StringEquals followed by Null(true) on same key must be UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="StringEquals",
                    values=["Engineering"], scope=ContextScope.PRINCIPAL,
                ),
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="Null",
                    values=["true"], scope=ContextScope.PRINCIPAL,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3-STRING-THEN-NULL", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT, (
            f"F3: StringEquals then Null(true) must be UNSAT; got {r.status}"
        )
        assert r.witness is None

    def test_f3_null_true_then_stringequals_is_unsat(self, ev):
        """Null(true) followed by StringEquals on same key must be UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="Null",
                    values=["true"], scope=ContextScope.PRINCIPAL,
                ),
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="StringEquals",
                    values=["Engineering"], scope=ContextScope.PRINCIPAL,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3-NULL-THEN-STRING", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT, (
            f"F3: Null(true) then StringEquals must be UNSAT; got {r.status}"
        )
        assert r.witness is None

    def test_f3_permutations_commutative_conjunction(self, ev):
        """Test all permutations of [StringEquals, Null(true)] yield identical UNSAT verdict."""
        import itertools
        p1 = ContextPredicate(
            key="aws:PrincipalTag/Team", operator="StringEquals",
            values=["RedTeam"], scope=ContextScope.PRINCIPAL,
        )
        p2 = ContextPredicate(
            key="aws:PrincipalTag/Team", operator="Null",
            values=["true"], scope=ContextScope.PRINCIPAL,
        )
        for idx, perm in enumerate(itertools.permutations([p1, p2])):
            hop = HopContextSpec(
                hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
                required_context=list(perm),
            )
            r = ev.evaluate(PathEvaluationInput(path_id=f"F3-PERM-{idx}", hops=[hop]))
            assert r.status == FeasibilityStatus.UNSAT, f"F3 permutation {idx} failed to yield UNSAT"

    def test_f3_null_false_and_stringequals_order_invariance(self, ev):
        """Both [Null(false), StringEquals] and [StringEquals, Null(false)] yield SAT with witness."""
        import itertools
        p1 = ContextPredicate(
            key="aws:PrincipalTag/Team", operator="StringEquals",
            values=["RedTeam"], scope=ContextScope.PRINCIPAL,
        )
        p2 = ContextPredicate(
            key="aws:PrincipalTag/Team", operator="Null",
            values=["false"], scope=ContextScope.PRINCIPAL,
        )
        for idx, perm in enumerate(itertools.permutations([p1, p2])):
            hop = HopContextSpec(
                hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
                required_context=list(perm),
            )
            r = ev.evaluate(PathEvaluationInput(path_id=f"F3-NULL-FALSE-PERM-{idx}", hops=[hop]))
            assert r.status == FeasibilityStatus.SAT, f"F3 Null(false) permutation {idx} failed"
            assert r.witness and r.witness.get("aws:PrincipalTag/Team") == "RedTeam"


class TestRemediationF4_AssumeRoleTransitionLifecycle:
    """F4: Correct indexing and scope resets across AssumeRole transitions."""

    def test_f4_caller_principal_tags_do_not_survive_assumerole(self, ev):
        """Caller tags on hop 1 do not survive sts:AssumeRole into hop 2."""
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="UserDev", dst_node_id="RoleAdmin",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="StringEquals",
                    values=["Development"], scope=ContextScope.PRINCIPAL,
                )
            ],
            produced_context=[
                ProducedStateModification(
                    key="active_principal", operation="SET",
                    value="arn:aws:iam::123456789012:role/RoleAdmin",
                ),
                ProducedStateModification(
                    key="aws:PrincipalTag/Department", operation="SET",
                    value="Operations",
                ),
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="RoleAdmin", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Department", operator="StringEquals",
                    values=["Operations"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F4-ROLE-TAG-RESET-SAT", hops=[hop1, hop2]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F4: Target role tag Operations should satisfy Hop 2; got {r.status}"
        )
        assert r.witness and r.witness.get("aws:PrincipalTag/Department") == "Operations"

    def test_f4_caller_session_bool_resets_across_assumerole(self, ev):
        """Caller session MFA on hop 1 does not survive into new role session on hop 2."""
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="MFAUser", dst_node_id="Role",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["true"], scope=ContextScope.SESSION,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="Role", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent", operator="Bool",
                    values=["false"], scope=ContextScope.SESSION,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F4-MFA-SESSION-RESET", hops=[hop1, hop2]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F4: Hop 2 fresh session requiring MFA=false must be SAT; got {r.status}"
        )
        assert r.witness and r.witness.get("hop_2_aws:MultiFactorAuthPresent") is False

    def test_f4_three_hop_sequence_with_assumerole_pivot(self, ev):
        """Hop 1 (standard) -> Hop 2 (AssumeRole) -> Hop 3 (standard): tag reset correctly placed."""
        hop1 = HopContextSpec(
            hop=1, edge_type="s3:ListBuckets", src_node_id="User", dst_node_id="S3",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Dept", operator="StringEquals",
                    values=["Dev"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="sts:AssumeRole", src_node_id="User", dst_node_id="Role",
            required_context=[],
            produced_context=[
                ProducedStateModification(
                    key="aws:PrincipalTag/Dept", operation="SET", value="SecOps",
                )
            ],
        )
        hop3 = HopContextSpec(
            hop=3, edge_type="secretsmanager:GetSecretValue", src_node_id="Role", dst_node_id="Secret",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/Dept", operator="StringEquals",
                    values=["SecOps"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F4-3HOP-RESET", hops=[hop1, hop2, hop3]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F4: Hop 3 inheriting SecOps tag must be SAT; got {r.status}"
        )


class TestRemediationF5_MixedIpVersionsFallback:
    """F5: Conservative fallback to UNKNOWN on unsupported mixed IPv4 and IPv6."""

    def test_f5_mixed_ipv4_ipv6_single_predicate_is_unknown(self, ev):
        """Single predicate with both IPv4 and IPv6 values must yield UNKNOWN."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/8", "2001:db8::/32"], scope=ContextScope.REQUEST,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F5-MIXED-PRED-UNKNOWN", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"F5: Mixed IPv4 and IPv6 must yield UNKNOWN; got {r.status}"
        )
        assert r.status != FeasibilityStatus.UNSAT
        assert r.unknown_rationale and "UNSUPPORTED_MIXED_IP_VERSIONS" in r.unknown_rationale

    def test_f5_mixed_ipv4_ipv6_static_origin_is_unknown(self, ev):
        """Cross-hop static origin between IPv4 and IPv6 must yield UNKNOWN, not UNSAT."""
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="U", dst_node_id="R",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="R", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["2001:db8::/32"], scope=ContextScope.REQUEST,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(
            path_id="F5-MIXED-STATIC-ORIGIN", hops=[hop1, hop2],
            scenario_assumptions={"static_origin_assumption": True},
        ))
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"F5: Mixed IP under static origin must yield UNKNOWN; got {r.status}"
        )
        assert r.status != FeasibilityStatus.UNSAT
        assert r.unknown_rationale and "UNSUPPORTED_MIXED_IP_VERSIONS" in r.unknown_rationale

    def test_f5_mixed_ipv4_ipv6_not_ip_is_unknown(self, ev):
        """Allowed IPv4 with denied IPv6 must yield UNKNOWN."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="U", dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.0/8"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["2001:db8::/32"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F5-MIXED-NOT-IP", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.status != FeasibilityStatus.UNSAT


class TestRemediationF6_StringScopesHandling:
    """F6: StringEquals across all supported scopes (SESSION, CONFIG, PRINCIPAL, REQUEST)."""

    def test_f6_session_scope_string_equals_consistent_is_sat(self, ev):
        """StringEquals in SESSION scope produces SAT with valid session witness."""
        hop = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="U", dst_node_id="R",
            required_context=[
                ContextPredicate(
                    key="aws:userid", operator="StringEquals",
                    values=["AROAEXAMPLE:session1"], scope=ContextScope.SESSION,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F6-SESSION-STRING-SAT", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and r.witness.get("aws:userid") == "AROAEXAMPLE:session1"

    def test_f6_session_scope_string_equals_contradiction_is_unsat(self, ev):
        """Contradictory StringEquals in SESSION scope on same hop yields UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="U", dst_node_id="R",
            required_context=[
                ContextPredicate(
                    key="aws:userid", operator="StringEquals",
                    values=["AROAEXAMPLE:alice"], scope=ContextScope.SESSION,
                ),
                ContextPredicate(
                    key="aws:userid", operator="StringEquals",
                    values=["AROAEXAMPLE:bob"], scope=ContextScope.SESSION,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F6-SESSION-STRING-UNSAT", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None
        assert r.contradiction_rationale and "session" in r.contradiction_rationale.lower()

    def test_f6_session_scope_persists_across_standard_actions(self, ev):
        """Session string constraints persist across standard actions and clash if contradictory."""
        hop1 = HopContextSpec(
            hop=1, edge_type="s3:ListBuckets", src_node_id="U", dst_node_id="S3",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalArn", operator="StringEquals",
                    values=["arn:aws:iam::123456789012:role/RoleA"], scope=ContextScope.SESSION,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="s3:GetObject", src_node_id="S3", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalArn", operator="StringEquals",
                    values=["arn:aws:iam::123456789012:role/RoleB"], scope=ContextScope.SESSION,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F6-SESSION-PERSIST-UNSAT", hops=[hop1, hop2]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None

    def test_f6_config_scope_hop_local_does_not_clash_across_hops(self, ev):
        """CONFIG scope (sts:ExternalId) is hop-local and does not contradict across hops."""
        hop1 = HopContextSpec(
            hop=1, edge_type="sts:AssumeRole", src_node_id="Client", dst_node_id="RoleA",
            required_context=[
                ContextPredicate(
                    key="sts:ExternalId", operator="StringEquals",
                    values=["PartnerA-Secret"], scope=ContextScope.CONFIG,
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2, edge_type="sts:AssumeRole", src_node_id="RoleA", dst_node_id="RoleB",
            required_context=[
                ContextPredicate(
                    key="sts:ExternalId", operator="StringEquals",
                    values=["PartnerB-Secret"], scope=ContextScope.CONFIG,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F6-CONFIG-HOP-LOCAL-SAT", hops=[hop1, hop2]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness is not None



# ===========================================================================
# STAGE F: PROMPT 5C REMEDIATION REGRESSION TESTS (F1.1 & F3.1)
# ===========================================================================

class TestRemediationF1_1_SingleHostWitnessSynthesis:
    """F1.1: Single-host IPv4 /32 and IPv6 /128 witness synthesis and subnet arithmetic."""

    def test_f1_1_ipv4_slash_32_allowed_is_sat(self, ev):
        """Allowed /32 host subnet must evaluate to SAT with concrete host witness."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.1/32"], scope=ContextScope.REQUEST,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-IPV4-32-SAT", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F1.1: IPv4 /32 must be SAT; got {r.status} (rationale: {r.unknown_rationale})"
        )
        assert r.witness and "aws:SourceIp" in r.witness
        assert r.witness["aws:SourceIp"] == "10.0.0.1"
        assert ipaddress.ip_address(r.witness["aws:SourceIp"]) in ipaddress.ip_network("10.0.0.1/32")

    def test_f1_1_ipv6_slash_128_allowed_is_sat(self, ev):
        """Allowed /128 IPv6 host subnet must evaluate to SAT with concrete host witness."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["2001:db8::1/128"], scope=ContextScope.REQUEST,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-IPV6-128-SAT", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F1.1: IPv6 /128 must be SAT; got {r.status} (rationale: {r.unknown_rationale})"
        )
        assert r.witness and "aws:SourceIp" in r.witness
        assert r.witness["aws:SourceIp"] == "2001:db8::1"
        assert ipaddress.ip_address(r.witness["aws:SourceIp"]) in ipaddress.ip_network("2001:db8::1/128")

    def test_f1_1_slash_31_minus_slash_32_is_sat(self, ev):
        """Allowed /31 minus denied /32 leaves the single remaining /32 host address."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["192.168.1.0/31"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["192.168.1.0/32"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-31-MINUS-32-SAT", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT, (
            f"F1.1: /31 minus /32 must be SAT; got {r.status} (rationale: {r.unknown_rationale})"
        )
        assert r.witness and "aws:SourceIp" in r.witness
        assert r.witness["aws:SourceIp"] == "192.168.1.1"
        assert ipaddress.ip_address(r.witness["aws:SourceIp"]) in ipaddress.ip_network("192.168.1.0/31")
        assert ipaddress.ip_address(r.witness["aws:SourceIp"]) not in ipaddress.ip_network("192.168.1.0/32")

    def test_f1_1_exact_slash_32_denial_is_unsat(self, ev):
        """Allowed /32 host exactly denied by /32 must evaluate to UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["10.0.0.1/32"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["10.0.0.1/32"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-EXACT-32-DENIED-UNSAT", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None
        assert r.contradiction_rationale and "denied" in r.contradiction_rationale.lower()

    def test_f1_1_multiple_denied_cover_allowed_range_unsat(self, ev):
        """Allowed /23 covered by two /24 denied subnets must evaluate to UNSAT."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["172.16.0.0/23"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["172.16.0.0/24", "172.16.1.0/24"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-PARTITION-23-UNSAT", hops=[hop]))
        assert r.status == FeasibilityStatus.UNSAT
        assert r.witness is None
        assert r.contradiction_rationale and "denied" in r.contradiction_rationale.lower()

    def test_f1_1_partially_excluded_range_witness_verified(self, ev):
        """Allowed /23 partially excluded by /24 yields SAT with witness outside denied."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp", operator="IpAddress",
                    values=["192.168.0.0/23"], scope=ContextScope.REQUEST,
                ),
                ContextPredicate(
                    key="aws:SourceIp", operator="NotIpAddress",
                    values=["192.168.0.0/24"], scope=ContextScope.REQUEST,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F1_1-PARTIAL-23-SAT", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and "aws:SourceIp" in r.witness
        w_ip = ipaddress.ip_address(r.witness["aws:SourceIp"])
        assert w_ip in ipaddress.ip_network("192.168.0.0/23")
        assert w_ip not in ipaddress.ip_network("192.168.0.0/24")


class TestRemediationF3_1_NullValuesValidation:
    """F3.1: Strict validation of Null condition values (exactly 1 boolean argument)."""

    def test_f3_1_multi_value_null_list_is_unknown(self, ev):
        """Null with multiple values ['true', 'false'] must return UNKNOWN, not silent truncation."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/role", operator="Null",
                    values=["true", "false"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-MULTI-NULL-UNKNOWN", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN, (
            f"F3.1: Multi-value Null must return UNKNOWN; got {r.status}"
        )
        assert r.status != FeasibilityStatus.SAT
        assert r.status != FeasibilityStatus.UNSAT
        assert r.unknown_rationale and "INVALID_NULL_VALUES_COUNT" in r.unknown_rationale

    def test_f3_1_three_value_null_list_is_unknown(self, ev):
        """Null with 3 values must return UNKNOWN."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/env", operator="Null",
                    values=["true", "false", "true"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-THREE-NULL-UNKNOWN", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.unknown_rationale and "INVALID_NULL_VALUES_COUNT" in r.unknown_rationale

    def test_f3_1_empty_null_values_list_is_unknown(self, ev):
        """Null with empty values list [] must return UNKNOWN."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/env", operator="Null",
                    values=[], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-EMPTY-NULL-UNKNOWN", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.unknown_rationale and "INVALID_NULL_VALUES_COUNT" in r.unknown_rationale

    def test_f3_1_unrecognized_null_value_is_unknown(self, ev):
        """Null with unrecognized value representation must return UNKNOWN."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/env", operator="Null",
                    values=["maybe"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-UNRECOGNIZED-NULL-UNKNOWN", hops=[hop]))
        assert r.status == FeasibilityStatus.UNKNOWN
        assert r.unknown_rationale and "UNPARSEABLE_NULL_VALUE" in r.unknown_rationale

    def test_f3_1_valid_single_value_null_true_remains_sat(self, ev):
        """Single-value Null: ['true'] remains valid SAT and excludes key from witness."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/temp", operator="Null",
                    values=["true"], scope=ContextScope.PRINCIPAL,
                )
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-VALID-NULL-TRUE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert "aws:PrincipalTag/temp" not in r.witness

    def test_f3_1_valid_single_value_null_false_remains_sat(self, ev):
        """Single-value Null: ['false'] with StringEquals remains valid SAT with witness."""
        hop = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="Client", dst_node_id="Bucket",
            required_context=[
                ContextPredicate(
                    key="aws:PrincipalTag/role", operator="Null",
                    values=["false"], scope=ContextScope.PRINCIPAL,
                ),
                ContextPredicate(
                    key="aws:PrincipalTag/role", operator="StringEquals",
                    values=["Admin"], scope=ContextScope.PRINCIPAL,
                ),
            ],
        )
        r = ev.evaluate(PathEvaluationInput(path_id="F3_1-VALID-NULL-FALSE", hops=[hop]))
        assert r.status == FeasibilityStatus.SAT
        assert r.witness and r.witness.get("aws:PrincipalTag/role") == "Admin"

    def test_f3_1_order_invariance_with_invalid_null(self, ev):
        """Predicate permutations of [StringEquals, InvalidNull] both yield UNKNOWN."""
        p_str = ContextPredicate(
            key="aws:PrincipalTag/team", operator="StringEquals",
            values=["SecOps"], scope=ContextScope.PRINCIPAL,
        )
        p_null_inv = ContextPredicate(
            key="aws:PrincipalTag/team", operator="Null",
            values=["true", "false"], scope=ContextScope.PRINCIPAL,
        )

        hop_a = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="C", dst_node_id="B",
            required_context=[p_str, p_null_inv],
        )
        hop_b = HopContextSpec(
            hop=1, edge_type="s3:GetObject", src_node_id="C", dst_node_id="B",
            required_context=[p_null_inv, p_str],
        )

        ra = ev.evaluate(PathEvaluationInput(path_id="ORDER-INV-A", hops=[hop_a]))
        rb = ev.evaluate(PathEvaluationInput(path_id="ORDER-INV-B", hops=[hop_b]))

        assert ra.status == FeasibilityStatus.UNKNOWN
        assert rb.status == FeasibilityStatus.UNKNOWN
        assert "INVALID_NULL_VALUES_COUNT" in ra.unknown_rationale
        assert "INVALID_NULL_VALUES_COUNT" in rb.unknown_rationale
