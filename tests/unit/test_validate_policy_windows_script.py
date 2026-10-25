"""
tests/unit/test_validate_policy_windows_script.py - Unit and functional tests for validate_policy_windows.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.validate_policy_windows import load_hints, main, render_table
from arf_rt.temporal.policy_window_validator import PolicyValidationResult, PolicyViolation


UTC = timezone.utc


@pytest.fixture
def sample_hints_file(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    data = {
        "edge_valid": {
            "edge_id": "edge_valid",
            "credential_issued": (now - timedelta(hours=1)).isoformat(),
            "credential_expiry": (now + timedelta(hours=3)).isoformat(),
            "last_used": (now - timedelta(days=5)).isoformat(),
        },
        "edge_expired": {
            "edge_id": "edge_expired",
            "credential_issued": (now - timedelta(hours=4)).isoformat(),
            "credential_expiry": (now - timedelta(minutes=10)).isoformat(),
            "last_used": (now - timedelta(days=100)).isoformat(),
        },
    }
    p = tmp_path / "test_hints.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def sample_list_hints_file(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    data = [
        {
            "edge_id": "edge_1",
            "credential_issued": (now - timedelta(minutes=30)).isoformat(),
            "credential_expiry": (now + timedelta(hours=2)).isoformat(),
        }
    ]
    p = tmp_path / "hints_list.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestLoadHints:
    def test_load_dict_format(self, sample_hints_file: Path) -> None:
        hints = load_hints(sample_hints_file)
        assert len(hints) == 2
        edge_ids = {h.edge_id for h in hints}
        assert "edge_valid" in edge_ids
        assert "edge_expired" in edge_ids

    def test_load_list_format(self, sample_list_hints_file: Path) -> None:
        hints = load_hints(sample_list_hints_file)
        assert len(hints) == 1
        assert hints[0].edge_id == "edge_1"

    def test_load_scenario_with_temporal_hints(self, tmp_path: Path) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        scenario_data = {
            "scenario_name": "test_scenario",
            "temporal_hints": {
                "e_scen_1": {
                    "credential_issued": now.isoformat(),
                    "credential_expiry": (now + timedelta(hours=1)).isoformat(),
                }
            },
        }
        p = tmp_path / "scenario.json"
        p.write_text(json.dumps(scenario_data), encoding="utf-8")
        hints = load_hints(p)
        assert len(hints) == 1
        assert hints[0].edge_id == "e_scen_1"


class TestRenderTable:
    def test_render_table_passed(self) -> None:
        res = PolicyValidationResult(passed_count=3, failed_count=0)
        table = render_table(res)
        assert "[PASS]" in table
        assert "All evaluated credential windows satisfy policy rules" in table

    def test_render_table_with_violations(self) -> None:
        res = PolicyValidationResult(
            violations=[
                PolicyViolation(edge_id="e1", rule="CREDENTIAL_EXPIRED", detail="Expired 10s ago")
            ],
            passed_count=1,
            failed_count=1,
        )
        table = render_table(res)
        assert "[FAIL]" in table
        assert "CREDENTIAL_EXPIRED" in table
        assert "e1" in table


class TestScriptMainCLI:
    def test_main_strict_failure_on_violations(
        self, sample_hints_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "validate_policy_windows.py",
                "--input",
                str(sample_hints_file),
                "--reference-time",
                ref_time,
                "--strict",
            ],
        )
        exit_code = main()
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "CREDENTIAL_EXPIRED" in captured.out

    def test_main_json_format_output(
        self, sample_hints_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_file = tmp_path / "results.json"
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "validate_policy_windows.py",
                "--input",
                str(sample_hints_file),
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
        parsed = json.loads(out_file.read_text(encoding="utf-8"))
        assert parsed["is_valid"] is False
        assert parsed["failed_count"] >= 1
        assert len(parsed["violations"]) >= 1

    def test_main_file_not_found(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["validate_policy_windows.py", "--input", "non_existent_file_path.json"],
        )
        exit_code = main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: input file" in captured.err
