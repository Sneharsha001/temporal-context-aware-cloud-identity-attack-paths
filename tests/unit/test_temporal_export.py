"""
tests/unit/test_temporal_export.py - Unit tests for arf_rt.temporal.export.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from arf_rt.temporal.audit_log import AuditEntry, TemporalAuditLog
from arf_rt.temporal.export import (
    export_audit_log_to_csv,
    export_metrics_to_csv,
    export_metrics_to_dict,
    generate_summary_table,
)
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


@pytest.fixture
def sample_metrics() -> TemporalMetrics:
    m = TemporalMetrics()
    m.record_feasible(path_length=3)
    m.record_infeasible(constraint_id="TC-1", path_length=4)
    m.record_unknown(path_length=2)
    return m


@pytest.fixture
def sample_audit_log() -> TemporalAuditLog:
    log = TemporalAuditLog()
    v1 = TemporalVerdict(kind=VerdictKind.FEASIBLE, reason="All constraints satisfied.")
    v2 = TemporalVerdict(
        kind=VerdictKind.INFEASIBLE,
        violated_constraint="TC-2",
        reason="Expired token",
    )
    log.record(["e1", "e2"], v1)
    log.record(["e3", "e4"], v2)
    return log


class TestExportMetrics:
    def test_export_metrics_to_dict(self, sample_metrics: TemporalMetrics) -> None:
        d = export_metrics_to_dict(sample_metrics)
        assert d["total_paths"] == 3
        assert d["feasible_count"] == 1
        assert d["infeasible_count"] == 1
        assert d["unknown_count"] == 1
        assert d["constraint_violations"]["TC-1"] == 1

    def test_export_metrics_to_csv_stream(self, sample_metrics: TemporalMetrics) -> None:
        buf = io.StringIO()
        export_metrics_to_csv(sample_metrics, buf)
        buf.seek(0)
        reader = list(csv.reader(buf))
        assert reader[0] == ["Category", "Metric", "Value"]
        categories = {row[0] for row in reader[1:]}
        assert "summary" in categories
        assert "constraint_violation" in categories

    def test_export_metrics_to_csv_file(
        self, sample_metrics: TemporalMetrics, tmp_path: Path
    ) -> None:
        out = tmp_path / "metrics.csv"
        export_metrics_to_csv(sample_metrics, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "elimination_rate_pct" in content
        assert "TC-1" in content

    def test_generate_summary_table(self, sample_metrics: TemporalMetrics) -> None:
        md = generate_summary_table(sample_metrics)
        assert "| Evaluated Paths | 3 |" in md
        assert "| Feasible Paths | 1 |" in md
        assert "| Infeasible (Eliminated) | 1 |" in md
        assert "| Unknown (Incomplete Data) | 1 |" in md


class TestExportAuditLog:
    def test_export_audit_log_to_csv_stream(
        self, sample_audit_log: TemporalAuditLog
    ) -> None:
        buf = io.StringIO()
        export_audit_log_to_csv(sample_audit_log, buf)
        buf.seek(0)
        reader = list(csv.reader(buf))
        assert reader[0] == [
            "LoggedAt",
            "Path",
            "VerdictKind",
            "ViolatedConstraint",
            "Reason",
        ]
        assert len(reader) == 3
        assert reader[1][1] == "e1 -> e2"
        assert reader[2][1] == "e3 -> e4"
        assert reader[2][3] == "TC-2"
        assert reader[2][4] == "Expired token"

    def test_export_audit_log_to_csv_file(
        self, sample_audit_log: TemporalAuditLog, tmp_path: Path
    ) -> None:
        out = tmp_path / "audit.csv"
        export_audit_log_to_csv(sample_audit_log, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "e3 -> e4" in content
        assert "Expired token" in content
