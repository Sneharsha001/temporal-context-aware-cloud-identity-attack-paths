"""
arf_rt/temporal/remediation_planner.py - Prioritized remediation planning for temporal risk.

Synthesizes policy violations, compliance findings, and credential risk scores
into prioritized, actionable remediation plans with AWS CLI command templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from arf_rt.temporal.compliance_auditor import ComplianceFinding
from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.policy_window_validator import PolicyViolation


class RemediationActionType(str, Enum):
    REVOKE_SESSION = "REVOKE_SESSION"
    ROTATE_ACCESS_KEY = "ROTATE_ACCESS_KEY"
    REDUCE_SESSION_DURATION = "REDUCE_SESSION_DURATION"
    ATTACH_BOUNDARY = "ATTACH_BOUNDARY"


@dataclass(frozen=True)
class RemediationAction:
    """A concrete remediation recommendation with execution templates."""

    action_id: str
    edge_id: str
    priority: int                   # 1 (Critical) .. 4 (Low)
    action_type: RemediationActionType
    estimated_risk_reduction: float # 0.0 - 1.0
    cli_command_template: str
    rationale: str

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "edge_id": self.edge_id,
            "priority": self.priority,
            "action_type": self.action_type.value,
            "estimated_risk_reduction": round(self.estimated_risk_reduction, 4),
            "cli_command_template": self.cli_command_template,
            "rationale": self.rationale,
        }


class TemporalRemediationPlanner:
    """
    Generates ordered, prioritized remediation plans to eliminate path feasibility.
    """

    def generate_plan(
        self,
        scores: Sequence[CredentialRiskScore] | None = None,
        policy_violations: Sequence[PolicyViolation] | None = None,
        compliance_findings: Sequence[ComplianceFinding] | None = None,
    ) -> list[RemediationAction]:
        """Synthesize all inputs into prioritized remediation recommendations."""
        actions: list[RemediationAction] = []
        action_counter = 1

        # 1. Remediations from policy violations
        for v in (policy_violations or []):
            if v.rule in ("CREDENTIAL_EXPIRED", "VALIDITY_WINDOW_TOO_SHORT"):
                actions.append(RemediationAction(
                    action_id=f"REM-{action_counter:03d}",
                    edge_id=v.edge_id,
                    priority=1,
                    action_type=RemediationActionType.REVOKE_SESSION,
                    estimated_risk_reduction=0.85,
                    cli_command_template=f"aws iam put-role-policy --role-name {v.edge_id} --policy-name RevokeOldSessions --policy-document '{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Deny\",\"Action\":\"*\",\"Resource\":\"*\"}}]}}'",
                    rationale=f"Policy violation: {v.detail}",
                ))
                action_counter += 1

            elif v.rule == "SESSION_DURATION_EXCEEDED":
                actions.append(RemediationAction(
                    action_id=f"REM-{action_counter:03d}",
                    edge_id=v.edge_id,
                    priority=2,
                    action_type=RemediationActionType.REDUCE_SESSION_DURATION,
                    estimated_risk_reduction=0.60,
                    cli_command_template=f"aws iam update-role --role-name {v.edge_id} --max-session-duration 3600",
                    rationale=f"Clamp session duration to AWS 1-hour standard. {v.detail}",
                ))
                action_counter += 1

        # 2. Remediations from compliance findings
        for f in (compliance_findings or []):
            if f.is_violation and f.control_id in ("CIS-1.3", "NIST-AC-2"):
                actions.append(RemediationAction(
                    action_id=f"REM-{action_counter:03d}",
                    edge_id=f.edge_id,
                    priority=2,
                    action_type=RemediationActionType.ROTATE_ACCESS_KEY,
                    estimated_risk_reduction=0.75,
                    cli_command_template=f"aws iam update-access-key --user-name {f.edge_id} --access-key-id KEY_ID --status Inactive",
                    rationale=f"Compliance failure {f.control_id}: {f.title}",
                ))
                action_counter += 1

        # 3. Remediations from high risk scores
        for s in (scores or []):
            if s.score >= 0.80 and not any(a.edge_id == s.edge_id for a in actions):
                actions.append(RemediationAction(
                    action_id=f"REM-{action_counter:03d}",
                    edge_id=s.edge_id,
                    priority=1,
                    action_type=RemediationActionType.REVOKE_SESSION,
                    estimated_risk_reduction=s.score,
                    cli_command_template=f"aws sts get-caller-identity && aws iam put-role-permissions-boundary --role-name {s.edge_id} --permissions-boundary arn:aws:iam::aws:policy/AdministratorAccess",
                    rationale=f"Critical temporal risk score: {s.score:.3f} ({s.label})",
                ))
                action_counter += 1

        # Deduplicate and sort by priority (1 asc) then estimated_risk_reduction desc
        seen_keys: set[tuple[str, RemediationActionType]] = set()
        deduped: list[RemediationAction] = []
        for act in sorted(actions, key=lambda a: (a.priority, -a.estimated_risk_reduction)):
            k = (act.edge_id, act.action_type)
            if k not in seen_keys:
                seen_keys.add(k)
                deduped.append(act)

        return deduped
