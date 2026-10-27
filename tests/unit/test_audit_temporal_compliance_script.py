"""
tests/unit/test_audit_temporal_compliance_script.py - Tests for audit_temporal_compliance CLI.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from scripts.audit_temporal_compliance import main, report_to_dict
from arf_rt.temporal.compliance_auditor import ComplianceFinding, Framework, ComplianceAuditReport


UTC = timezone.utc


@pytest.fixture
def sample_hints_json(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    payload = {
        "user_clean": {
            "credential_issued": (now - timedelta(hours=1)).isoformat(),
            "credential_expiry": (now + timedelta(hours=2)).isoformat(),
            "last_used": (now - timedelta(days=5)).isoformat(),
        },
        "user_stale": {
            "credential_issued": (now - timedelta(hours=2)).isoformat(),
            "credential_expiry": (now + timedelta(hours=1)).isoformat(),
            "last_used": (now - timedelta(days=120)).isoformat(),  # Stale > 90d
        },
    }
    p = tmp_path / "hints.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestAuditTemporalComplianceCLI:
    def test_main_table_output(
        self, sample_hints_json: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "audit_temporal_compliance.py",
                "--input",
                str(sample_hints_json),
                "--reference-time",
                ref_time,
            ],
        )
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "TEMPORAL COMPLIANCE AUDIT REPORT" in captured.out
        assert "CIS-1.3" in captured.out

    def test_main_strict_exit_on_violations(
        self, sample_hints_json: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "audit_temporal_compliance.py",
                "--input",
                str(sample_hints_json),
                "--reference-time",
                ref_time,
                "--strict",
            ],
        )
        exit_code = main()
        assert exit_code == 1

    def test_main_json_output_and_file(
        self, sample_hints_json: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_file = tmp_path / "compliance_out.json"
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "audit_temporal_compliance.py",
                "--input",
                str(sample_hints_json),
                "--reference-time",
                ref_time,
                "--format",
                "json",
                "--out",
                str(out_file),
            ],
        )
        exit_code = main()
        assert exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "compliance_score" in data
        assert data["violation_count"] >= 1

    def test_missing_input_file(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["audit_temporal_compliance.py", "--input", "non_existent.json"],
        )
        exit_code = main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: input file" in captured.err
