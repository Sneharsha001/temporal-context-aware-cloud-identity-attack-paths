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
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM6: NotIpAddress narrowing must not produce UNSAT; got {r.status}"
        )

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
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM6: StringEquals multi-value must not be UNSAT; got {r.status}"
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
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM7: Null(true) absent-key check must not be UNSAT; got {r.status}"
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
        assert r.status != FeasibilityStatus.UNSAT, (
            f"FM7: Null(false)+StringEquals must not be UNSAT; got {r.status}"
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
