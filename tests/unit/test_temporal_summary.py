"""
tests/unit/test_temporal_summary.py - Unit tests for TemporalSummaryReporter.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.audit_log import TemporalAuditLog
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.summary import TemporalSummaryReporter
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


@pytest.fixture
def populated_metrics() -> TemporalMetrics:
    m = TemporalMetrics()
    m.record_feasible(path_length=2)
    m.record_feasible(path_length=3)
    m.record_infeasible(constraint_id="TC-1", path_length=3)
    m.record_infeasible(constraint_id="TC-2", path_length=4)
    m.record_infeasible(constraint_id="TC-1", path_length=5)
    m.record_unknown(path_length=1)
    return m


@pytest.fixture
def populated_audit_log() -> TemporalAuditLog:
    log = TemporalAuditLog()
    v1 = TemporalVerdict(kind=VerdictKind.FEASIBLE, reason="Path is temporally valid.")
    v2 = TemporalVerdict(kind=VerdictKind.INFEASIBLE, violated_constraint="TC-1", reason="Causal order violated.")
    log.record(["e1", "e2"], v1)
    log.record(["e2", "e3"], v2)
    return log


class TestTemporalSummaryReporter:
    def test_executive_summary_content(self, populated_metrics: TemporalMetrics) -> None:
        reporter = TemporalSummaryReporter(populated_metrics)
        summary = reporter.generate_executive_summary()
        assert "CRITICAL_ANOMALIES_DETECTED" in summary
        assert "Total Paths Evaluated:** 6" in summary
        assert "Feasible Paths:** 2" in summary
        assert "Infeasible Paths (Eliminated):** 3" in summary
        assert "TC-1" in summary

    def test_constraint_breakdown_table(self, populated_metrics: TemporalMetrics) -> None:
        reporter = TemporalSummaryReporter(populated_metrics)
        breakdown = reporter.generate_constraint_breakdown()
        assert "| `TC-1` |" in breakdown
        assert "| `TC-2` |" in breakdown
        assert "Causal Order Violation" in breakdown
        assert "Session Lifetime Expiration" in breakdown

    def test_empty_violations_breakdown(self) -> None:
        m = TemporalMetrics()
        m.record_feasible(path_length=2)
        reporter = TemporalSummaryReporter(m)
        breakdown = reporter.generate_constraint_breakdown()
        assert "No temporal constraint violations recorded" in breakdown

    def test_full_audit_report(
        self, populated_metrics: TemporalMetrics, populated_audit_log: TemporalAuditLog
    ) -> None:
        reporter = TemporalSummaryReporter(populated_metrics, populated_audit_log)
        report = reporter.generate_full_audit_report("Weekly Attack Path Feasibility")
        assert "Weekly Attack Path Feasibility" in report
        assert "Path Length Distribution" in report
        assert "e1 -> e2" in report
        assert "e2 -> e3" in report
        assert "`TC-1`" in report
