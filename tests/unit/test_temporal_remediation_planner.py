"""
tests/unit/test_temporal_remediation_planner.py - Tests for TemporalRemediationPlanner.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.compliance_auditor import ComplianceFinding, Framework
from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.policy_window_validator import PolicyViolation
from arf_rt.temporal.remediation_planner import (
    RemediationActionType,
    TemporalRemediationPlanner,
)


class TestTemporalRemediationPlanner:
    def test_plan_with_empty_inputs(self) -> None:
        planner = TemporalRemediationPlanner()
        plan = planner.generate_plan()
        assert plan == []

    def test_plan_from_policy_violations(self) -> None:
        planner = TemporalRemediationPlanner()
        violations = [
            PolicyViolation(edge_id="role_expired", rule="CREDENTIAL_EXPIRED", detail="Expired 1h ago"),
            PolicyViolation(edge_id="role_long", rule="SESSION_DURATION_EXCEEDED", detail="43200s"),
        ]
        plan = planner.generate_plan(policy_violations=violations)

        assert len(plan) == 2
        # Priority 1 comes before Priority 2
        assert plan[0].edge_id == "role_expired"
        assert plan[0].priority == 1
        assert plan[0].action_type == RemediationActionType.REVOKE_SESSION
        assert "RevokeOldSessions" in plan[0].cli_command_template

        assert plan[1].edge_id == "role_long"
        assert plan[1].priority == 2
        assert plan[1].action_type == RemediationActionType.REDUCE_SESSION_DURATION

    def test_plan_from_compliance_findings(self) -> None:
        planner = TemporalRemediationPlanner()
        findings = [
            ComplianceFinding(
                control_id="CIS-1.3",
                framework=Framework.CIS_AWS,
                edge_id="stale_user",
                status="FAIL",
                severity="HIGH",
                title="Stale",
                details="Unused 120d",
            )
        ]
        plan = planner.generate_plan(compliance_findings=findings)

        assert len(plan) == 1
        assert plan[0].edge_id == "stale_user"
        assert plan[0].action_type == RemediationActionType.ROTATE_ACCESS_KEY
        assert "update-access-key" in plan[0].cli_command_template

    def test_plan_from_critical_risk_scores(self) -> None:
        planner = TemporalRemediationPlanner()
        scores = [
            CredentialRiskScore(
                edge_id="high_risk_role",
                score=0.91,
                expiry_factor=0.9,
                staleness_factor=0.9,
                short_lived_bonus=0.1,
            )
        ]
        plan = planner.generate_plan(scores=scores)

        assert len(plan) == 1
        assert plan[0].edge_id == "high_risk_role"
        assert plan[0].priority == 1

    def test_to_dict_serialization(self) -> None:
        planner = TemporalRemediationPlanner()
        violations = [
            PolicyViolation(edge_id="r1", rule="CREDENTIAL_EXPIRED", detail="Expired"),
        ]
        plan = planner.generate_plan(policy_violations=violations)
        d = plan[0].to_dict()
        assert d["edge_id"] == "r1"
        assert d["priority"] == 1
        assert d["action_type"] == "REVOKE_SESSION"
