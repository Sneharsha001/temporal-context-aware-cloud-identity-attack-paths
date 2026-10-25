"""
tests/unit/test_detect_temporal_drift_script.py - Unit and functional tests for detect_temporal_drift.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.detect_temporal_drift import main, render_table
from arf_rt.temporal.temporal_drift_detector import (
    DriftEvent,
    DriftKind,
    DriftReport,
)


UTC = timezone.utc


@pytest.fixture
def baseline_file(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    data = {
        "edge_stay": {
            "edge_id": "edge_stay",
            "credential_issued": (now - timedelta(hours=1)).isoformat(),
            "credential_expiry": (now + timedelta(hours=2)).isoformat(),
        },
        "edge_removed": {
            "edge_id": "edge_removed",
            "credential_issued": (now - timedelta(hours=2)).isoformat(),
            "credential_expiry": (now + timedelta(hours=1)).isoformat(),
        },
    }
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def current_file(tmp_path: Path) -> Path:
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    data = {
        "edge_stay": {
            "edge_id": "edge_stay",
            "credential_issued": (now - timedelta(hours=1)).isoformat(),
            "credential_expiry": (now + timedelta(hours=5)).isoformat(),  # extended
        },
        "edge_new": {
            "edge_id": "edge_new",
            "credential_issued": now.isoformat(),
            "credential_expiry": (now + timedelta(hours=1)).isoformat(),
        },
    }
    p = tmp_path / "current.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestRenderTable:
    def test_render_table_no_drift(self) -> None:
        rep = DriftReport(
            baseline_count=2,
            current_count=2,
            events=[],
            detected_at=datetime.now(tz=UTC),
        )
        table = render_table(rep)
        assert "[STABLE (NO DRIFT)]" in table
        assert "All credential validity windows match baseline" in table

    def test_render_table_with_drift(self) -> None:
        ev = DriftEvent(
            edge_id="e_new",
            kind=DriftKind.NEW_CREDENTIAL,
            baseline_value=None,
            current_value="present",
            delta_seconds=None,
            detected_at=datetime.now(tz=UTC),
        )
        rep = DriftReport(
            baseline_count=1,
            current_count=2,
            events=[ev],
            detected_at=datetime.now(tz=UTC),
        )
        table = render_table(rep)
        assert "[DRIFT DETECTED]" in table
        assert "NEW_CREDENTIAL" in table
        assert "e_new" in table


class TestScriptMainCLI:
    def test_main_detects_drift_and_strict_exit(
        self, baseline_file: Path, current_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            [
                "detect_temporal_drift.py",
                "-b",
                str(baseline_file),
                "-c",
                str(current_file),
                "--strict",
            ],
        )
        exit_code = main()
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "NEW_CREDENTIAL" in captured.out
        assert "REMOVED_CREDENTIAL" in captured.out
        assert "EXPIRY_EXTENDED" in captured.out

    def test_main_json_output(
        self, baseline_file: Path, current_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out_file = tmp_path / "drift_out.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "detect_temporal_drift.py",
                "-b",
                str(baseline_file),
                "-c",
                str(current_file),
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
        assert parsed["has_drift"] is True
        assert parsed["new_credentials_count"] == 1
        assert parsed["removed_credentials_count"] == 1
        assert parsed["expiry_shifts_count"] == 1

    def test_main_missing_baseline(self, current_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["detect_temporal_drift.py", "-b", "nonexistent.json", "-c", str(current_file)],
        )
        exit_code = main()
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error: baseline file" in captured.err
