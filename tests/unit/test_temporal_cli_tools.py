"""
tests/unit/test_temporal_cli_tools.py - Tests for report_temporal_coverage and run_temporal_dashboard scripts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.report_temporal_coverage import (
    coverage_to_dict,
    extract_edges_and_hints,
    main as coverage_main,
)
from scripts.run_temporal_dashboard import main as dashboard_main


UTC = timezone.utc


@pytest.fixture
def scenario_json(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    payload = {
        "scenario_name": "multihop_identity_chain",
        "edges": [
            {"edge_id": "role_jump_1", "src": "UserA", "dst": "Role1"},
            {"edge_id": "role_jump_2", "src": "Role1", "dst": "Role2"},
            {"edge_id": "data_access", "src": "Role2", "dst": "S3Bucket"},
        ],
        "temporal_hints": {
            "role_jump_1": {
                "credential_issued": (now - timedelta(minutes=30)).isoformat(),
                "credential_expiry": (now + timedelta(minutes=30)).isoformat(),
                "last_used": (now - timedelta(days=2)).isoformat(),
            },
            "role_jump_2": {
                "credential_issued": (now - timedelta(hours=2)).isoformat(),
                "credential_expiry": (now - timedelta(minutes=5)).isoformat(),  # expired
            },
        },
    }
    p = tmp_path / "scenario_sample.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestReportTemporalCoverageCLI:
    def test_extract_edges_and_hints(self, scenario_json: Path) -> None:
        edges, hints = extract_edges_and_hints(scenario_json)
        assert len(edges) == 3
        assert len(hints) == 2
        hint_ids = {h.edge_id for h in hints}
        assert "role_jump_1" in hint_ids
        assert "role_jump_2" in hint_ids

    def test_coverage_main_table_output(
        self, scenario_json: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["report_temporal_coverage.py", "--input", str(scenario_json)],
        )
        exit_code = coverage_main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Temporal Coverage Report" in captured.out
        assert "Covered edges" in captured.out

    def test_coverage_main_json_and_out(
        self, scenario_json: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_file = tmp_path / "coverage_out.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "report_temporal_coverage.py",
                "--input",
                str(scenario_json),
                "--format",
                "json",
                "--out",
                str(out_file),
            ],
        )
        exit_code = coverage_main()
        assert exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["total_edges"] == 3
        assert data["covered_edges"] == 2
        assert "data_access" in data["uncovered_edge_ids"]

    def test_coverage_strict_threshold_failure(
        self, scenario_json: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            [
                "report_temporal_coverage.py",
                "--input",
                str(scenario_json),
                "--threshold",
                "90.0",
                "--strict",
            ],
        )
        exit_code = coverage_main()
        assert exit_code == 1

    def test_coverage_missing_input(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["report_temporal_coverage.py", "--input", "missing_file.json"],
        )
        exit_code = coverage_main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: input file" in captured.err


class TestRunTemporalDashboardCLI:
    def test_dashboard_main_renders_successfully(
        self, scenario_json: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ref_time = "2025-06-15T12:00:00Z"
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_temporal_dashboard.py",
                "--input",
                str(scenario_json),
                "--reference-time",
                ref_time,
                "--top",
                "3",
            ],
        )
        exit_code = dashboard_main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "ARF-RT Temporal Analysis Dashboard" in captured.out
        assert "Top Credential Risk Scores" in captured.out
        assert "Policy Validation" in captured.out
        assert "Temporal Coverage" in captured.out

    def test_dashboard_main_writes_to_file(
        self, scenario_json: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_file = tmp_path / "dashboard.txt"
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_temporal_dashboard.py",
                "--input",
                str(scenario_json),
                "--out",
                str(out_file),
            ],
        )
        exit_code = dashboard_main()
        assert exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "ARF-RT Temporal Analysis Dashboard" in content

    def test_dashboard_missing_input(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["run_temporal_dashboard.py", "--input", "missing.json"],
        )
        exit_code = dashboard_main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: input file" in captured.err
