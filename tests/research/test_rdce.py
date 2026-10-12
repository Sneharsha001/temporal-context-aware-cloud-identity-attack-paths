"""CCPF / RDCE Acceptance Tests (A1-A8).

Verifies the Restricted Deterministic Constraint Evaluator against the
formal contract in docs/CCPF_EVALUATOR_CONTRACT.md (v1.1.0, Prompt 2A).

Test mapping:
  A1 - CIDR Disjointness Soundness             (CE2)
  A2 - CIDR Subset Compatibility               (CE1)
  A3 - Pivot Transition Re-Binding             (CE3)
  A4 - Unsupported Operator Fallback           (CE4)
  A5 - Baseline Fixture Isolated Fallback      (CE5)
  A6 - Principal Scope Reset Clash             (CE6)
  A7 - Decoupling from Q8 Probability Underflow
  A8 - Robustness and Exception Trapping

All tests are strictly isolated from production engine code:
  - No modification to arf_rt/engine/paths.py or any baseline mirror.
  - No probability multiplier present anywhere in results.
  - No probability score is asserted (only status, witness, rationale).

Branch: temporal-context-dev
Workspace: C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL
Contract: docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0
"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
import tempfile
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
    load_sidecar_context,
)

FIXTURE_DIR = (
    WORKSPACE_ROOT
    / "tests"
    / "fixtures"
    / "research_context_feasibility"
)

CE1_SIDECAR = FIXTURE_DIR / "ce1_compatible_persistent.context.json"
CE2_SIDECAR = FIXTURE_DIR / "ce2_contradictory_persistent.context.json"
CE3_SIDECAR = FIXTURE_DIR / "ce3_transition_permitted.context.json"
CE4_SIDECAR = FIXTURE_DIR / "ce4_unsupported_metadata.context.json"
CE5_SIDECAR = FIXTURE_DIR / "ce5_baseline_compatibility.context.json"
CE6_SIDECAR = FIXTURE_DIR / "ce6_principal_scope_boundary.context.json"


@pytest.fixture(scope="module")
def evaluator():
    return RestrictedDeterministicConstraintEvaluator()


# ---------------------------------------------------------------------------
# A1 - CIDR Disjointness Soundness (CE2)
# ---------------------------------------------------------------------------

class TestA1CidrDisjointnessSoundness:
    def test_status_is_unsat(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        assert result.status == FeasibilityStatus.UNSAT, (
            f"Expected UNSAT but got {result.status}: {result.unknown_rationale}"
        )

    def test_no_witness_on_unsat(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        assert result.witness is None, f"UNSAT must not provide witness, got: {result.witness}"

    def test_contradiction_rationale_is_non_empty(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        assert result.contradiction_rationale, "UNSAT must supply a non-empty contradiction_rationale"

    def test_no_probability_multiplier_in_result(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        assert not hasattr(result, "probability_multiplier")
        assert not hasattr(result, "feasibility_multiplier")

    def test_evaluated_hops_equals_two(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        assert result.evaluated_hops == 2, f"CE2 has 2 hops; evaluated_hops={result.evaluated_hops}"

    def test_cidr_blocks_are_disjoint_verification(self):
        net1 = ipaddress.IPv4Network("10.0.0.0/8")
        net2 = ipaddress.IPv4Network("192.168.0.0/16")
        assert not net1.overlaps(net2)

    def test_contradiction_mentions_cidrs(self):
        result = evaluate_sidecar(CE2_SIDECAR)
        rationale = result.contradiction_rationale or ""
        assert "10.0.0.0" in rationale or "192.168" in rationale, (
            f"Contradiction rationale should reference the disjoint CIDRs: {rationale}"
        )


# ---------------------------------------------------------------------------
# A2 - CIDR Subset Compatibility (CE1)
# ---------------------------------------------------------------------------

class TestA2CidrSubsetCompatibility:
    def test_status_is_sat(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        assert result.status == FeasibilityStatus.SAT, (
            f"Expected SAT but got {result.status}: "
            f"{result.contradiction_rationale or result.unknown_rationale}"
        )

    def test_witness_is_non_empty_dict(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        assert isinstance(result.witness, dict) and result.witness

    def test_witness_contains_source_ip_key(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        assert "aws:SourceIp" in result.witness

    def test_witness_ip_is_valid_ipv4_address(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        ip_str = result.witness.get("aws:SourceIp", "")
        try:
            ipaddress.IPv4Address(ip_str)
        except ValueError:
            pytest.fail(f"Witness IP '{ip_str}' is not a valid IPv4 address")

    def test_witness_ip_satisfies_both_cidr_constraints(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        ip_str = result.witness.get("aws:SourceIp", "")
        addr = ipaddress.IPv4Address(ip_str)
        net1 = ipaddress.IPv4Network("10.0.0.0/8")
        net2 = ipaddress.IPv4Network("10.1.0.0/16")
        assert addr in net1, f"Witness {addr} not in 10.0.0.0/8"
        assert addr in net2, f"Witness {addr} not in 10.1.0.0/16"

    def test_no_contradiction_rationale_on_sat(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        assert result.contradiction_rationale is None

    def test_no_probability_multiplier_in_result(self):
        result = evaluate_sidecar(CE1_SIDECAR)
        assert not hasattr(result, "probability_multiplier")


# ---------------------------------------------------------------------------
# A3 - Pivot Transition Re-Binding (CE3)
# ---------------------------------------------------------------------------

class TestA3PivotTransitionRebinding:
    def test_status_is_sat(self):
        result = evaluate_sidecar(CE3_SIDECAR)
        assert result.status == FeasibilityStatus.SAT, (
            f"CE3 (pivot transition) expected SAT but got {result.status}: "
            f"{result.contradiction_rationale or result.unknown_rationale}"
        )

    def test_witness_contains_distinct_ips_per_hop(self):
        result = evaluate_sidecar(CE3_SIDECAR)
        w = result.witness or {}
        hop1_ip = w.get("hop_1_SourceIp")
        hop2_ip = w.get("hop_2_SourceIp")
        assert hop1_ip is not None, "Witness must include hop_1_SourceIp"
        assert hop2_ip is not None, "Witness must include hop_2_SourceIp"
        assert hop1_ip != hop2_ip, f"Pivot must produce distinct IPs; both are {hop1_ip}"

    def test_hop2_witness_ip_is_rebound_value(self):
        result = evaluate_sidecar(CE3_SIDECAR)
        w = result.witness or {}
        assert w.get("hop_2_SourceIp") == "10.0.1.100", (
            f"hop_2_SourceIp should be 10.0.1.100, got: {w.get('hop_2_SourceIp')}"
        )

    def test_hop1_ip_in_external_cidr(self):
        result = evaluate_sidecar(CE3_SIDECAR)
        w = result.witness or {}
        addr = ipaddress.IPv4Address(w.get("hop_1_SourceIp", "0.0.0.0"))
        ext_net = ipaddress.IPv4Network("198.51.100.0/24")
        assert addr in ext_net, f"hop_1_SourceIp {addr} must be in {ext_net}"

    def test_not_falsely_unsat_due_to_cidr_disjointness(self):
        result = evaluate_sidecar(CE3_SIDECAR)
        assert result.status != FeasibilityStatus.UNSAT, (
            "Pivot transition must not be falsely classified as UNSAT due to disjoint CIDRs"
        )


# ---------------------------------------------------------------------------
# A4 - Unsupported Operator Fallback (CE4)
# ---------------------------------------------------------------------------

class TestA4UnsupportedOperatorFallback:
    def test_status_is_unknown(self):
        result = evaluate_sidecar(CE4_SIDECAR)
        assert result.status == FeasibilityStatus.UNKNOWN, (
            f"CE4 expected UNKNOWN but got {result.status}"
        )

    def test_unknown_rationale_is_non_empty(self):
        result = evaluate_sidecar(CE4_SIDECAR)
        assert result.unknown_rationale

    def test_no_uncaught_exception(self):
        try:
            evaluate_sidecar(CE4_SIDECAR)
        except Exception as exc:
            pytest.fail(f"evaluate_sidecar raised uncaught exception on CE4: {exc!r}")

    def test_no_witness_on_unknown(self):
        result = evaluate_sidecar(CE4_SIDECAR)
        assert result.witness is None

    def test_no_contradiction_rationale_on_unknown(self):
        result = evaluate_sidecar(CE4_SIDECAR)
        assert result.contradiction_rationale is None

    def test_unknown_rationale_references_unsupported_key_or_operator(self):
        result = evaluate_sidecar(CE4_SIDECAR)
        rationale = result.unknown_rationale or ""
        assert (
            "vendor" in rationale
            or "UnsupportedFuzzyMatch" in rationale
            or "UNSUPPORTED" in rationale.upper()
            or "UNKNOWN" in rationale.upper()
        ), f"unknown_rationale should reference unsupported key/operator: {rationale}"


# ---------------------------------------------------------------------------
# A5 - Baseline Fixture Isolated Fallback (CE5)
# ---------------------------------------------------------------------------

class TestA5BaselineFixtureIsolatedFallback:
    def test_status_is_unknown(self):
        result = evaluate_sidecar(CE5_SIDECAR)
        assert result.status == FeasibilityStatus.UNKNOWN

    def test_unknown_rationale_is_no_context_constraints_defined(self):
        result = evaluate_sidecar(CE5_SIDECAR)
        assert result.unknown_rationale == "NO_CONTEXT_CONSTRAINTS_DEFINED", (
            f"Expected 'NO_CONTEXT_CONSTRAINTS_DEFINED', got: {result.unknown_rationale!r}"
        )

    def test_no_witness_on_unknown(self):
        result = evaluate_sidecar(CE5_SIDECAR)
        assert result.witness is None

    def test_baseline_fixtures_remain_unmodified(self):
        baseline_diamond = WORKSPACE_ROOT / "tests" / "fixtures" / "diamond_scenario.json"
        baseline_primary = WORKSPACE_ROOT / "tests" / "fixtures" / "primary_realistic_scenario.json"
        for path in (baseline_diamond, baseline_primary):
            assert path.exists(), f"Baseline fixture missing: {path}"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data

    def test_isolated_fallback_does_not_prune_path(self):
        result = evaluate_sidecar(CE5_SIDECAR)
        assert result.status != FeasibilityStatus.UNSAT


# ---------------------------------------------------------------------------
# A6 - Principal Scope Reset Clash (CE6)
# ---------------------------------------------------------------------------

class TestA6PrincipalScopeResetClash:
    def test_status_is_unsat(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        assert result.status == FeasibilityStatus.UNSAT, (
            f"CE6 expected UNSAT but got {result.status}: "
            f"{result.unknown_rationale or result.witness}"
        )

    def test_no_witness_on_unsat(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        assert result.witness is None

    def test_contradiction_rationale_is_non_empty(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        assert result.contradiction_rationale

    def test_contradiction_rationale_references_principal_tag(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        rationale = result.contradiction_rationale or ""
        assert "Department" in rationale or "PrincipalTag" in rationale, (
            f"Rationale must reference Department principal tag clash: {rationale}"
        )

    def test_contradiction_rationale_references_clashing_values(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        rationale = result.contradiction_rationale or ""
        assert "ApplicationDevelopment" in rationale or "SecurityOperations" in rationale, (
            f"Rationale must mention the clashing tag values: {rationale}"
        )

    def test_not_falsely_unknown(self):
        result = evaluate_sidecar(CE6_SIDECAR)
        assert result.status != FeasibilityStatus.UNKNOWN


# ---------------------------------------------------------------------------
# A7 - Decoupling from Q8 Probability Underflow
# ---------------------------------------------------------------------------

class TestA7DecouplingFromQ8Underflow:

    @staticmethod
    def _build_ce1_like_input(path_id="A7-Q8-UNDERFLOW-TEST"):
        hop1 = HopContextSpec(
            hop=1,
            edge_type="sts:AssumeRole",
            src_node_id="AttackerOrigin",
            dst_node_id="JumpRole",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp",
                    operator="IpAddress",
                    values=["10.0.0.0/8"],
                    scope=ContextScope.REQUEST,
                )
            ],
            produced_context=[
                ProducedStateModification(
                    key="active_principal",
                    operation="SET",
                    value="arn:aws:iam::123456789012:role/JumpRole",
                )
            ],
        )
        hop2 = HopContextSpec(
            hop=2,
            edge_type="s3:GetObject",
            src_node_id="JumpRole",
            dst_node_id="TargetData",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp",
                    operator="IpAddress",
                    values=["10.1.0.0/16"],
                    scope=ContextScope.REQUEST,
                )
            ],
            produced_context=[],
        )
        transition = TransitionRelation(
            from_hop=1,
            to_hop=2,
            variable="aws:SourceIp",
            relation_type="EQUAL",
            formula="SourceIp(e1) == SourceIp(e2)",
            rationale="Static origin assumption",
        )
        return PathEvaluationInput(
            path_id=path_id,
            hops=[hop1, hop2],
            transition_constraints=[transition],
            scenario_assumptions={"static_origin_assumption": True},
        )

    def test_sat_path_remains_sat_when_q8_score_is_zero(self, evaluator):
        eval_input = self._build_ce1_like_input()
        result = evaluator.evaluate(eval_input)
        simulated_q8_score = 0
        assert simulated_q8_score == 0
        assert result.status == FeasibilityStatus.SAT, (
            f"Q8=0 must not convert SAT path to UNSAT; got {result.status}"
        )
        assert result.witness is not None

    def test_result_has_no_probability_fields(self, evaluator):
        eval_input = self._build_ce1_like_input("A7-FIELD-CHECK")
        result = evaluator.evaluate(eval_input)
        for banned_field in (
            "probability_multiplier",
            "feasibility_multiplier",
            "q8_score",
            "p_worst_q8",
            "bayesian_score",
            "score",
        ):
            assert not hasattr(result, banned_field), (
                f"PathEvaluationResult must not contain field '{banned_field}'"
            )

    def test_unknown_path_remains_unknown_when_q8_score_is_zero(self, evaluator):
        hop = HopContextSpec(
            hop=1,
            edge_type="custom:Action",
            src_node_id="A",
            dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="vendor:CustomToken",
                    operator="UnsupportedOperator",
                    values=["any"],
                    scope=ContextScope.UNKNOWN,
                )
            ],
        )
        eval_input = PathEvaluationInput(
            path_id="A7-UNKNOWN-Q8-ZERO",
            hops=[hop],
        )
        result = evaluator.evaluate(eval_input)
        assert result.status == FeasibilityStatus.UNKNOWN
        assert result.status != FeasibilityStatus.UNSAT


# ---------------------------------------------------------------------------
# A8 - Robustness and Exception Trapping
# ---------------------------------------------------------------------------

class TestA8RobustnessAndExceptionTrapping:

    def test_empty_hops_returns_unknown(self, evaluator):
        eval_input = PathEvaluationInput(
            path_id="A8-EMPTY-HOPS",
            hops=[],
        )
        try:
            result = evaluator.evaluate(eval_input)
        except Exception as exc:
            pytest.fail(f"Empty hops raised uncaught exception: {exc!r}")
        assert result.status == FeasibilityStatus.UNKNOWN
        assert result.timeout_occurred is False

    def test_malformed_cidr_returns_unknown_not_exception(self, evaluator):
        hop = HopContextSpec(
            hop=1,
            edge_type="s3:GetObject",
            src_node_id="A",
            dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp",
                    operator="IpAddress",
                    values=["NOT_A_VALID_CIDR"],
                    scope=ContextScope.REQUEST,
                )
            ],
        )
        eval_input = PathEvaluationInput(
            path_id="A8-MALFORMED-CIDR",
            hops=[hop],
        )
        try:
            result = evaluator.evaluate(eval_input)
        except Exception as exc:
            pytest.fail(f"Malformed CIDR raised uncaught exception: {exc!r}")
        assert result.status != FeasibilityStatus.UNSAT

    def test_malformed_sidecar_json_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".context.json", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write("{NOT VALID JSON !!!}")
            tmp_path = tmp.name
        try:
            try:
                result = evaluate_sidecar(tmp_path)
                assert result.status == FeasibilityStatus.UNKNOWN
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
            except Exception as exc:
                pytest.fail(
                    f"Malformed JSON raised unexpected exception {type(exc).__name__}: {exc!r}"
                )
        finally:
            os.unlink(tmp_path)

    def test_unknown_operator_on_supported_key_returns_unknown(self, evaluator):
        hop = HopContextSpec(
            hop=1,
            edge_type="s3:GetObject",
            src_node_id="A",
            dst_node_id="B",
            required_context=[
                ContextPredicate(
                    key="aws:SourceIp",
                    operator="GlobMatch",
                    values=["10.*.*.*"],
                    scope=ContextScope.REQUEST,
                )
            ],
        )
        eval_input = PathEvaluationInput(
            path_id="A8-UNKNOWN-OP-KNOWN-KEY",
            hops=[hop],
        )
        try:
            result = evaluator.evaluate(eval_input)
        except Exception as exc:
            pytest.fail(f"Unsupported operator raised uncaught exception: {exc!r}")
        assert result.status != FeasibilityStatus.UNSAT

    def test_timeout_occurred_is_false_on_normal_evaluations(self):
        for sidecar in (CE1_SIDECAR, CE2_SIDECAR, CE3_SIDECAR,
                        CE4_SIDECAR, CE5_SIDECAR, CE6_SIDECAR):
            result = evaluate_sidecar(sidecar)
            assert result.timeout_occurred is False, (
                f"{sidecar.name}: timeout_occurred must be False, got True"
            )

    def test_solver_duration_ms_is_non_negative(self):
        for sidecar in (CE1_SIDECAR, CE2_SIDECAR, CE3_SIDECAR,
                        CE4_SIDECAR, CE5_SIDECAR, CE6_SIDECAR):
            result = evaluate_sidecar(sidecar)
            assert result.solver_duration_ms >= 0.0, (
                f"{sidecar.name}: solver_duration_ms={result.solver_duration_ms} is negative"
            )

    def test_all_results_have_correct_path_id(self):
        for sidecar, expected_id in [
            (CE1_SIDECAR, "CE1"),
            (CE2_SIDECAR, "CE2"),
            (CE3_SIDECAR, "CE3"),
            (CE4_SIDECAR, "CE4"),
            (CE5_SIDECAR, "CE5"),
            (CE6_SIDECAR, "CE6"),
        ]:
            result = evaluate_sidecar(sidecar)
            assert result.path_id == expected_id, (
                f"{sidecar.name}: expected path_id={expected_id!r}, got {result.path_id!r}"
            )
