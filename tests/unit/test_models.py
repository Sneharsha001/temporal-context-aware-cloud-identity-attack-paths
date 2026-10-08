"""Tests for ARF-RT Pydantic models.

Covers:
  - NodeInput: region normalization, extra field rejection
  - EdgeInput: status validation, alpha/beta validation
  - ConstraintInput: confidence_q domain, constraint_type
  - ObservationInput: signal_q int-only, strength enum
  - ObjectiveInput: positive int validation
  - ScenarioInput: structure validation, objectives required
"""

import pytest
from pydantic import ValidationError

from arf_rt.config import REGION_NULL_SENTINEL
from arf_rt.models.core import (
    ConstraintInput,
    EdgeConstraintInput,
    EdgeInput,
    NodeInput,
    NodeRef,
    ObjectiveInput,
    ObservationInput,
    RunWarningInput,
    ScenarioInput,
    TemplateInput,
)


# ===================================================================
# NodeInput
# ===================================================================


class TestNodeInput:
    """Tests for NodeInput model."""

    def test_valid_node(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="arn:aws:iam::123:role/Admin",
            region="us-east-1",
        )
        assert n.provider == "aws"
        assert n.region == "us-east-1"

    def test_region_none_normalized(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin", region=None,
        )
        assert n.region == REGION_NULL_SENTINEL

    def test_region_empty_normalized(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin", region="",
        )
        assert n.region == REGION_NULL_SENTINEL

    def test_region_whitespace_normalized(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin", region="   ",
        )
        assert n.region == REGION_NULL_SENTINEL

    def test_region_stripped(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin", region="  us-east-1  ",
        )
        assert n.region == "us-east-1"

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            NodeInput(
                provider="aws", node_type="identity",
                provider_id="admin", unknown_field="bad",
            )

    def test_default_display_name(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin",
        )
        assert n.display_name == ""

    def test_properties_optional(self):
        n = NodeInput(
            provider="aws", node_type="identity",
            provider_id="admin",
        )
        assert n.properties is None


# ===================================================================
# EdgeInput
# ===================================================================


class TestEdgeInput:
    """Tests for EdgeInput model."""

    def test_valid_edge(self):
        e = EdgeInput(
            edge_type="assume_role",
            src="node_a", dst="node_b",
        )
        assert e.edge_type == "assume_role"
        assert e.alpha_i == 1
        assert e.beta_i == 1
        assert e.frozen is False

    def test_region_normalized(self):
        e = EdgeInput(
            edge_type="assume_role",
            src="a", dst="b", region=None,
        )
        assert e.region == REGION_NULL_SENTINEL

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            EdgeInput(
                edge_type="assume_role",
                src="a", dst="b", status="INVALID",
            )

    def test_valid_statuses(self):
        for status in ["HYPOTHESIZED", "CONFIRMED", "REFUTED", "UNKNOWN_CONDITION"]:
            e = EdgeInput(edge_type="x", src="a", dst="b", status=status)
            assert e.status == status

    def test_alpha_rejects_float(self):
        with pytest.raises(ValidationError):
            EdgeInput(
                edge_type="x", src="a", dst="b", alpha_i=1.5,
            )

    def test_alpha_rejects_bool(self):
        with pytest.raises(ValidationError):
            EdgeInput(
                edge_type="x", src="a", dst="b", alpha_i=True,
            )

    def test_alpha_rejects_negative(self):
        with pytest.raises(ValidationError):
            EdgeInput(
                edge_type="x", src="a", dst="b", alpha_i=-1,
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            EdgeInput(
                edge_type="x", src="a", dst="b", bogus=42,
            )


# ===================================================================
# ConstraintInput
# ===================================================================


class TestConstraintInput:
    """Tests for ConstraintInput model."""

    def test_valid_constraint(self):
        c = ConstraintInput(
            provider="aws", constraint_type="SCP",
            scope_type="ACCOUNT", scope_id="123456",
        )
        assert c.status == "ACTIVE"
        assert c.validation_status == "UNVALIDATED"
        assert c.confidence_q == 0

    def test_confidence_q_valid(self):
        c = ConstraintInput(
            provider="aws", constraint_type="SCP",
            scope_type="ACCOUNT", scope_id="123",
            confidence_q=750,
        )
        assert c.confidence_q == 750

    def test_confidence_q_rejects_float(self):
        with pytest.raises(ValidationError):
            ConstraintInput(
                provider="aws", constraint_type="SCP",
                scope_type="ACCOUNT", scope_id="123",
                confidence_q=50.0,
            )

    def test_confidence_q_rejects_out_of_range(self):
        with pytest.raises(ValidationError):
            ConstraintInput(
                provider="aws", constraint_type="SCP",
                scope_type="ACCOUNT", scope_id="123",
                confidence_q=1001,
            )

    def test_region_normalized(self):
        c = ConstraintInput(
            provider="aws", constraint_type="SCP",
            scope_type="ACCOUNT", scope_id="123",
            region=None,
        )
        assert c.region == REGION_NULL_SENTINEL


# ===================================================================
# ObservationInput
# ===================================================================


class TestObservationInput:
    """Tests for ObservationInput model."""

    def test_valid_observation(self):
        o = ObservationInput(
            edge_ref="edge_abc",
            result="ALLOW",
            strength="DIRECT",
            signal_q=80,
        )
        assert o.probe_type == "REPLAY_SCRIPTED"
        assert o.reason_class == "UNKNOWN"
        assert o.is_counterfactual is False

    def test_signal_q_rejects_float(self):
        """Spec §18.3: Scenario MUST provide signal_q as int."""
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="DIRECT", signal_q=80.0,
            )

    def test_signal_q_rejects_bool(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="DIRECT", signal_q=True,
            )

    def test_signal_q_rejects_out_of_range(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="DIRECT", signal_q=101,
            )

    def test_signal_q_rejects_negative(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="DIRECT", signal_q=-1,
            )

    def test_invalid_result_rejected(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="INVALID",
                strength="DIRECT", signal_q=80,
            )

    def test_invalid_strength_rejected(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="INVALID", signal_q=80,
            )

    def test_invalid_probe_type_rejected(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="ALLOW",
                strength="DIRECT", signal_q=80,
                probe_type="INVALID",
            )

    def test_invalid_reason_class_rejected(self):
        with pytest.raises(ValidationError):
            ObservationInput(
                edge_ref="e", result="DENY",
                strength="DIRECT", signal_q=80,
                reason_class="INVALID",
            )

    def test_all_valid_results(self):
        for result in ["ALLOW", "DENY", "ERROR", "INCONCLUSIVE"]:
            o = ObservationInput(
                edge_ref="e", result=result,
                strength="DIRECT", signal_q=80,
            )
            assert o.result == result

    def test_all_valid_strengths(self):
        for strength in ["DETERMINISTIC", "DIRECT", "INFERRED", "HEURISTIC"]:
            o = ObservationInput(
                edge_ref="e", result="ALLOW",
                strength=strength, signal_q=80,
            )
            assert o.strength == strength

    def test_evidence_hash_optional(self):
        o = ObservationInput(
            edge_ref="e", result="ALLOW",
            strength="DIRECT", signal_q=80,
        )
        assert o.evidence_hash is None


# ===================================================================
# ObjectiveInput
# ===================================================================


class TestObjectiveInput:
    """Tests for ObjectiveInput model."""

    def test_valid_objective(self):
        o = ObjectiveInput(
            objective_type="priv_esc",
            start_nodes=["node_a"],
            target_nodes=["node_c"],
            max_depth=3, k=5,
        )
        assert o.max_depth == 3

    def test_max_depth_rejects_zero(self):
        with pytest.raises(ValidationError):
            ObjectiveInput(
                objective_type="pe",
                start_nodes=["a"], target_nodes=["b"],
                max_depth=0, k=5,
            )

    def test_k_rejects_negative(self):
        with pytest.raises(ValidationError):
            ObjectiveInput(
                objective_type="pe",
                start_nodes=["a"], target_nodes=["b"],
                max_depth=3, k=-1,
            )

    def test_max_depth_rejects_bool(self):
        with pytest.raises(ValidationError):
            ObjectiveInput(
                objective_type="pe",
                start_nodes=["a"], target_nodes=["b"],
                max_depth=True, k=5,
            )


# ===================================================================
# ScenarioInput
# ===================================================================


class TestScenarioInput:
    """Tests for ScenarioInput model."""

    def test_minimal_valid_scenario(self):
        s = ScenarioInput(
            nodes=[
                NodeInput(provider="aws", node_type="identity",
                          provider_id="a"),
            ],
            edges=[
                EdgeInput(edge_type="assume_role", src="a", dst="b"),
            ],
            objectives=[
                ObjectiveInput(
                    objective_type="pe",
                    start_nodes=["a"], target_nodes=["b"],
                    max_depth=3, k=5,
                ),
            ],
        )
        assert len(s.nodes) == 1
        assert s.constraints is None

    def test_empty_objectives_rejected(self):
        with pytest.raises(ValidationError):
            ScenarioInput(
                nodes=[
                    NodeInput(provider="aws", node_type="identity",
                              provider_id="a"),
                ],
                edges=[
                    EdgeInput(edge_type="assume_role", src="a", dst="b"),
                ],
                objectives=[],
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            ScenarioInput(
                nodes=[
                    NodeInput(provider="aws", node_type="identity",
                              provider_id="a"),
                ],
                edges=[
                    EdgeInput(edge_type="assume_role", src="a", dst="b"),
                ],
                objectives=[
                    ObjectiveInput(
                        objective_type="pe",
                        start_nodes=["a"], target_nodes=["b"],
                        max_depth=3, k=5,
                    ),
                ],
                unknown_section=[],
            )

    def test_full_scenario_with_all_sections(self):
        s = ScenarioInput(
            nodes=[
                NodeInput(provider="aws", node_type="identity",
                          provider_id="a"),
            ],
            edges=[
                EdgeInput(edge_type="assume_role", src="a", dst="b"),
            ],
            templates=[
                TemplateInput(
                    provider="aws", edge_type="assume_role",
                    features={"service": "iam"},
                ),
            ],
            constraints=[
                ConstraintInput(
                    provider="aws", constraint_type="SCP",
                    scope_type="ACCOUNT", scope_id="123",
                ),
            ],
            edge_constraints=[
                EdgeConstraintInput(
                    edge_ref="edge1", constraint_ref="constraint1",
                ),
            ],
            objectives=[
                ObjectiveInput(
                    objective_type="pe",
                    start_nodes=["a"], target_nodes=["b"],
                    max_depth=3, k=5,
                ),
            ],
            observations=[
                ObservationInput(
                    edge_ref="edge1", result="ALLOW",
                    strength="DIRECT", signal_q=80,
                ),
            ],
        )
        assert len(s.templates) == 1
        assert len(s.constraints) == 1
        assert len(s.observations) == 1


# ===================================================================
# RunWarningInput
# ===================================================================


class TestRunWarningInput:
    """Tests for RunWarningInput model."""

    def test_valid_warning(self):
        w = RunWarningInput(
            code="DOWNGRADED_DIRECT_NO_EVIDENCE",
            message="Evidence hash missing",
        )
        assert w.severity == "WARN"

    def test_valid_severities(self):
        for sev in ["INFO", "WARN", "ERROR"]:
            w = RunWarningInput(code="TEST", severity=sev)
            assert w.severity == sev

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            RunWarningInput(code="TEST", severity="CRITICAL")


# ===================================================================
# EdgeConstraintInput
# ===================================================================


class TestEdgeConstraintInput:
    """Tests for EdgeConstraintInput model."""

    def test_valid(self):
        ec = EdgeConstraintInput(
            edge_ref="edge1", constraint_ref="constraint1",
        )
        assert ec.relation_type == "APPLIES_TO"

    def test_depends_on(self):
        ec = EdgeConstraintInput(
            edge_ref="edge1", constraint_ref="constraint1",
            relation_type="DEPENDS_ON",
        )
        assert ec.relation_type == "DEPENDS_ON"

    def test_invalid_relation_type_rejected(self):
        with pytest.raises(ValidationError):
            EdgeConstraintInput(
                edge_ref="edge1", constraint_ref="constraint1",
                relation_type="INVALID",
            )
