"""
arf_rt/temporal/anomaly_classifier.py - Security anomaly classification and risk tiering.

Categorizes temporal violations and window anomalies into standardized severity tiers
(CRITICAL, HIGH, MEDIUM, LOW) with actionable remediation recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


class SeverityTier(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass(frozen=True)
class ClassifiedAnomaly:
    """A classified temporal security anomaly."""
    anomaly_id: str
    severity: SeverityTier
    title: str
    description: str
    remediation: str


class AnomalyClassifier:
    """Classifies temporal feasibility failures and suspicious window events."""

    @classmethod
    def classify_constraint_violation(cls, constraint_id: str, reason: str = "") -> ClassifiedAnomaly:
        """Classify an infeasibility verdict constraint into a severity tier."""
        if constraint_id == "TC-1":
            return ClassifiedAnomaly(
                anomaly_id="TC-1",
                severity=SeverityTier.HIGH,
                title="Causal Order Inversion",
                description=reason or "Hop was observed before the prerequisite credential was issued.",
                remediation="Investigate host clock drift or inspect for compromised replay activity.",
            )
        elif constraint_id == "TC-2":
            return ClassifiedAnomaly(
                anomaly_id="TC-2",
                severity=SeverityTier.CRITICAL,
                title="Expired Credential Usage",
                description=reason or "Path relies on an assumed role session after its STS expiry.",
                remediation="Revoke active sessions and audit CloudTrail for unauthorized API execution post-expiry.",
            )
        elif constraint_id == "TC-3":
            return ClassifiedAnomaly(
                anomaly_id="TC-3",
                severity=SeverityTier.HIGH,
                title="Super-Velocity Hopping",
                description=reason or "Hop traversed faster than physically or causally plausible.",
                remediation="Check for automated scripted credential harvesting and deploy rate limiting.",
            )
        elif constraint_id == "TC-4":
            return ClassifiedAnomaly(
                anomaly_id="TC-4",
                severity=SeverityTier.MEDIUM,
                title="Dormant Credential Resuscitation",
                description=reason or "Credential was inactive beyond the freshness threshold.",
                remediation="Rotate dormant IAM access keys and enforce 90-day maximum key age.",
            )
        elif constraint_id == "TC-5":
            return ClassifiedAnomaly(
                anomaly_id="TC-5",
                severity=SeverityTier.CRITICAL,
                title="Impossible Concurrent Session",
                description=reason or "Single session token simultaneously active from incompatible regions/contexts.",
                remediation="Trigger immediate credential revocation and isolate involved IAM roles.",
            )
        else:
            return ClassifiedAnomaly(
                anomaly_id=constraint_id,
                severity=SeverityTier.MEDIUM,
                title="Unclassified Temporal Violation",
                description=reason or f"Violation of constraint {constraint_id}.",
                remediation="Review custom temporal policies and audit log evidence.",
            )

    @classmethod
    def classify_window_finding(cls, finding: str) -> ClassifiedAnomaly:
        """Classify a window analyzer finding string into a structured anomaly."""
        lower = finding.lower()
        if "burst" in lower:
            return ClassifiedAnomaly(
                anomaly_id="WIN-BURST",
                severity=SeverityTier.HIGH,
                title="Credential Burst Activity",
                description=finding,
                remediation="Inspect for automated exploitation tools or enumeration scripts.",
            )
        elif "concurren" in lower or "overlap" in lower:
            return ClassifiedAnomaly(
                anomaly_id="WIN-CONCURRENCY",
                severity=SeverityTier.CRITICAL,
                title="Suspicious Session Concurrency",
                description=finding,
                remediation="Terminate active STS sessions and verify multi-factor authentication enforcement.",
            )
        elif "reuse" in lower or "cross-account" in lower:
            return ClassifiedAnomaly(
                anomaly_id="WIN-REUSE",
                severity=SeverityTier.HIGH,
                title="Cross-Account Credential Reuse",
                description=finding,
                remediation="Enforce ExternalId checks and restrict STS trust policies by condition keys.",
            )
        else:
            return ClassifiedAnomaly(
                anomaly_id="WIN-GENERIC",
                severity=SeverityTier.LOW,
                title="Temporal Window Anomaly",
                description=finding,
                remediation="Log event for threat modeling baseline refinement.",
            )

    @classmethod
    def classify_path(
        cls, verdict: TemporalVerdict, window_findings: list[str] | None = None
    ) -> list[ClassifiedAnomaly]:
        """Classify all issues on a path, sorted by severity (highest first)."""
        anomalies: list[ClassifiedAnomaly] = []

        if verdict.kind == VerdictKind.INFEASIBLE and verdict.violated_constraint:
            anomalies.append(
                cls.classify_constraint_violation(
                    verdict.violated_constraint, verdict.reason
                )
            )

        if window_findings:
            for finding in window_findings:
                anomalies.append(cls.classify_window_finding(finding))

        # Sort order: CRITICAL (0), HIGH (1), MEDIUM (2), LOW (3), INFO (4)
        order = {
            SeverityTier.CRITICAL: 0,
            SeverityTier.HIGH: 1,
            SeverityTier.MEDIUM: 2,
            SeverityTier.LOW: 3,
            SeverityTier.INFO: 4,
        }
        anomalies.sort(key=lambda a: order.get(a.severity, 99))
        return anomalies
