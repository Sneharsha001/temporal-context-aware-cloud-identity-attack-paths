"""
tests/unit/test_generate_remediation_plan_script.py - Tests for generate_remediation_plan CLI script.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from scripts.generate_remediation_plan import main, render_shell, render_table
from arf_rt.temporal.remediation_planner import RemediationAction, RemediationActionType


UTC = timezone.utc


@pytest.fixture
def sample_scenario_json(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    payload = {
        "scenario_name": "remediation_test",
        "temporal_hints": {
            "role_expired_token": {
                "credential_issued": (now - timedelta(hours=3)).isoformat(),
                "credential_expiry": (now - timedelta(minutes=10)).isoformat(),  # expired
                "last_used": (now - timedelta(days=2)).isoformat(),
            },
            "user_stale_key": {
                "last_used": (now - timedelta(days=150)).isoformat(),  # stale
            },
        },
    }
    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestGenerateRemediationPlanCLI:
    def test_main_table_output(
        self, sample_scenario_json: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "generate_remediation_plan.py",
                "--input",
                str(sample_scenario_json),
                "--reference-time",
                ref_time,
            ],
        )
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PRIORITIZED TEMPORAL REMEDIATION PLAYBOOK" in captured.out
        assert "role_expired_token" in captured.out
        assert "aws iam" in captured.out

    def test_main_shell_format_and_out_file(
        self, sample_scenario_json: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_script = tmp_path / "remediate.sh"
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "generate_remediation_plan.py",
                "--input",
                str(sample_scenario_json),
                "--reference-time",
                ref_time,
                "--format",
                "shell",
                "--out",
                str(out_script),
            ],
        )
        exit_code = main()
        assert exit_code == 0
        assert out_script.exists()
        content = out_script.read_text(encoding="utf-8")
        assert "#!/usr/bin/env bash" in content
        assert "aws iam" in content

    def test_main_json_format_and_top_limit(
        self, sample_scenario_json: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_json = tmp_path / "remediate.json"
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "generate_remediation_plan.py",
                "--input",
                str(sample_scenario_json),
                "--reference-time",
                ref_time,
                "--top",
                "1",
                "--format",
                "json",
                "--out",
                str(out_json),
            ],
        )
        exit_code = main()
        assert exit_code == 0
        assert out_json.exists()
        actions = json.loads(out_json.read_text(encoding="utf-8"))
        assert len(actions) == 1
        assert "action_id" in actions[0]
        assert "cli_command_template" in actions[0]

    def test_missing_input_file(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["generate_remediation_plan.py", "--input", "non_existent_file.json"],
        )
        exit_code = main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: input file" in captured.err
