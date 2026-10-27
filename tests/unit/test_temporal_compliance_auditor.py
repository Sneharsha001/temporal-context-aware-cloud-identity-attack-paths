"""
tests/unit/test_temporal_compliance_auditor.py - Tests for TemporalComplianceAuditor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from arf_rt.temporal.compliance_auditor import (
    ComplianceFinding,
    Framework,
    TemporalComplianceAuditor,
)
from arf_rt.temporal.hints import TemporalHint


UTC = timezone.utc


class TestTemporalComplianceAuditor:
    def test_compliant_hints(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        hint = TemporalHint(
            edge_id="edge_compliant",
            credential_issued=now - timedelta(hours=1),
            credential_expiry=now + timedelta(hours=3),
            last_used=now - timedelta(days=10),
        )
        auditor = TemporalComplianceAuditor(reference_time=now)
        report = auditor.audit([hint])

        assert report.compliance_score == 100.0
        assert len(report.violations) == 0
        assert report.passed_checks == len(report.findings)
        assert "All credentials satisfy CIS AWS and NIST 800-53" in report.summary()

    def test_stale_credential_triggers_cis_and_nist_violation(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        hint = TemporalHint(
            edge_id="edge_stale",
            last_used=now - timedelta(days=120),  # > 90d
        )
        auditor = TemporalComplianceAuditor(reference_time=now, max_rotation_days=90.0)
        report = auditor.audit([hint])

        violations = report.violations
        assert len(violations) == 2
        control_ids = {v.control_id for v in violations}
        assert "CIS-1.3" in control_ids
        assert "NIST-AC-2" in control_ids
        assert report.compliance_score < 100.0

    def test_excessive_session_duration_violation(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        hint = TemporalHint(
            edge_id="edge_long_session",
            credential_issued=now,
            credential_expiry=now + timedelta(hours=24),  # 24h > 12h
        )
        auditor = TemporalComplianceAuditor(reference_time=now, max_session_duration_seconds=43200.0)
        report = auditor.audit([hint])

        cis_findings = report.findings_by_framework(Framework.CIS_AWS)
        assert any(f.control_id == "CIS-1.16" and f.is_violation for f in cis_findings)

        nist_findings = report.findings_by_framework(Framework.NIST_800_53)
        assert any(f.control_id == "NIST-SC-10" and f.is_violation for f in nist_findings)

    def test_expired_credential_violation(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        hint = TemporalHint(
            edge_id="edge_expired",
            credential_expiry=now - timedelta(minutes=15),
        )
        auditor = TemporalComplianceAuditor(reference_time=now)
        report = auditor.audit([hint])

        assert any(f.control_id == "NIST-IA-5" and f.is_violation for f in report.findings)

    def test_empty_audit(self) -> None:
        auditor = TemporalComplianceAuditor()
        report = auditor.audit([])
        assert report.compliance_score == 100.0
        assert report.total_checks == 0
        assert report.evaluated_edges_count == 0

    def test_finding_to_dict(self) -> None:
        f = ComplianceFinding(
            control_id="CIS-1.3",
            framework=Framework.CIS_AWS,
            edge_id="e1",
            status="FAIL",
            severity="HIGH",
            title="Stale",
            details="100d",
        )
        d = f.to_dict()
        assert d["control_id"] == "CIS-1.3"
        assert d["framework"] == "CIS_AWS"
        assert d["status"] == "FAIL"
        assert d["severity"] == "HIGH"
