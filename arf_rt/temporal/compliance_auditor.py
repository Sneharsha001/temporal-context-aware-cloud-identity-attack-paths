"""
arf_rt/temporal/compliance_auditor.py - Compliance framework mapping for temporal credentials.

Evaluates TemporalHint collections against CIS AWS Foundations Benchmark
and NIST SP 800-53 Rev 5 control objectives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


class Framework(str, Enum):
    CIS_AWS = "CIS_AWS"
    NIST_800_53 = "NIST_800_53"


@dataclass(frozen=True)
class ComplianceFinding:
    """A single compliance evaluation finding for an identity edge."""

    control_id: str
    framework: Framework
    edge_id: str
    status: str              # PASS / FAIL
    severity: str            # CRITICAL / HIGH / MEDIUM / LOW
    title: str
    details: str

    @property
    def is_violation(self) -> bool:
        return self.status == "FAIL"

    def to_dict(self) -> dict:
        return {
            "control_id": self.control_id,
            "framework": self.framework.value,
            "edge_id": self.edge_id,
            "status": self.status,
            "severity": self.severity,
            "title": self.title,
            "details": self.details,
        }


@dataclass
class ComplianceAuditReport:
    """Aggregated compliance report across all evaluated controls and edges."""

    findings: list[ComplianceFinding] = field(default_factory=list)
    evaluated_edges_count: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def violations(self) -> list[ComplianceFinding]:
        return [f for f in self.findings if f.is_violation]

    @property
    def total_checks(self) -> int:
        return len(self.findings)

    @property
    def passed_checks(self) -> int:
        return len(self.findings) - len(self.violations)

    @property
    def compliance_score(self) -> float:
        if not self.findings:
            return 100.0
        return round((self.passed_checks / self.total_checks) * 100.0, 2)

    def findings_by_framework(self, framework: Framework) -> list[ComplianceFinding]:
        return [f for f in self.findings if f.framework == framework]

    def summary(self) -> str:
        lines = [
            "=" * 70,
            f"  TEMPORAL COMPLIANCE AUDIT REPORT: [{self.compliance_score:.1f}% COMPLIANT]",
            "=" * 70,
            f"  Total Checks Evaluated : {self.total_checks}",
            f"  Passed Checks          : {self.passed_checks}",
            f"  Violations             : {len(self.violations)}",
            "-" * 70,
        ]
        if not self.violations:
            lines.append("  All credentials satisfy CIS AWS and NIST 800-53 temporal controls.")
        else:
            lines.append(f"  {'CONTROL':<12} {'FRAMEWORK':<12} {'EDGE ID':<20} {'DETAILS'}")
            lines.append("  " + "-" * 66)
            for v in self.violations:
                lines.append(f"  {v.control_id:<12} {v.framework.value:<12} {v.edge_id:<20} {v.title}")
        lines.append("=" * 70)
        return "\n".join(lines)


class TemporalComplianceAuditor:
    """
    Evaluates temporal credentials against CIS AWS and NIST 800-53 controls.

    Parameters
    ----------
    reference_time:
        Instant used as evaluation time. Defaults to now UTC.
    max_rotation_days:
        Max days since last rotation/usage (CIS 1.3 / 1.4: 90 days default).
    max_session_duration_seconds:
        Max permissible STS session duration (default: 43200s = 12h).
    """

    def __init__(
        self,
        reference_time: datetime | None = None,
        max_rotation_days: float = 90.0,
        max_session_duration_seconds: float = 43200.0,
    ) -> None:
        self.reference_time = reference_time or datetime.now(tz=timezone.utc)
        self.max_rotation_days = max_rotation_days
        self.max_session_duration = max_session_duration_seconds

    def audit(self, hints: Sequence[TemporalHint]) -> ComplianceAuditReport:
        """Run audit across all provided hints and return a ComplianceAuditReport."""
        report = ComplianceAuditReport(evaluated_edges_count=len(hints))
        now = self._utc(self.reference_time)

        for h in hints:
            # 1. CIS-1.3 & NIST-AC-2: Stale credential check (> 90 days unused)
            if h.last_used is not None:
                days = h.days_since_last_use(now)
                if days is not None and days > self.max_rotation_days:
                    report.findings.append(ComplianceFinding(
                        control_id="CIS-1.3",
                        framework=Framework.CIS_AWS,
                        edge_id=h.edge_id,
                        status="FAIL",
                        severity="HIGH",
                        title=f"Credential unused for {days:.0f} days (threshold {self.max_rotation_days:.0f}d)",
                        details=f"Last used at {h.last_used.isoformat()}",
                    ))
                    report.findings.append(ComplianceFinding(
                        control_id="NIST-AC-2",
                        framework=Framework.NIST_800_53,
                        edge_id=h.edge_id,
                        status="FAIL",
                        severity="HIGH",
                        title=f"Stale account identifier exceeding inactive lifetime",
                        details=f"Last used at {h.last_used.isoformat()}",
                    ))
                else:
                    report.findings.append(ComplianceFinding(
                        control_id="CIS-1.3",
                        framework=Framework.CIS_AWS,
                        edge_id=h.edge_id,
                        status="PASS",
                        severity="LOW",
                        title="Credential within active rotation window",
                        details=f"Last used {days:.1f} days ago" if days is not None else "Active",
                    ))

            # 2. CIS-1.16 & NIST-SC-10: Max Session Duration
            if h.credential_issued is not None and h.credential_expiry is not None:
                duration = h.session_duration_seconds()
                if duration is not None and duration > self.max_session_duration:
                    report.findings.append(ComplianceFinding(
                        control_id="CIS-1.16",
                        framework=Framework.CIS_AWS,
                        edge_id=h.edge_id,
                        status="FAIL",
                        severity="MEDIUM",
                        title=f"Session duration {duration:.0f}s exceeds limit {self.max_session_duration:.0f}s",
                        details="Reduce IAM role MaxSessionDuration attribute",
                    ))
                    report.findings.append(ComplianceFinding(
                        control_id="NIST-SC-10",
                        framework=Framework.NIST_800_53,
                        edge_id=h.edge_id,
                        status="FAIL",
                        severity="MEDIUM",
                        title="Session lifetime exceeds network disconnect policy",
                        details=f"Session length {duration:.0f}s",
                    ))
                else:
                    report.findings.append(ComplianceFinding(
                        control_id="CIS-1.16",
                        framework=Framework.CIS_AWS,
                        edge_id=h.edge_id,
                        status="PASS",
                        severity="LOW",
                        title="Session duration conforms to maximum permissible limit",
                        details=f"Duration: {duration:.0f}s" if duration is not None else "Compliant",
                    ))

            # 3. NIST-IA-5: Active expired credential token
            if h.credential_expiry is not None:
                exp = self._utc(h.credential_expiry)
                if exp <= now:
                    report.findings.append(ComplianceFinding(
                        control_id="NIST-IA-5",
                        framework=Framework.NIST_800_53,
                        edge_id=h.edge_id,
                        status="FAIL",
                        severity="CRITICAL",
                        title="Active reference to expired authentication credential",
                        details=f"Expired at {exp.isoformat()}",
                    ))
                else:
                    report.findings.append(ComplianceFinding(
                        control_id="NIST-IA-5",
                        framework=Framework.NIST_800_53,
                        edge_id=h.edge_id,
                        status="PASS",
                        severity="LOW",
                        title="Credential within valid unexpired lifetime",
                        details=f"Expires at {exp.isoformat()}",
                    ))

        return report

    def _utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
