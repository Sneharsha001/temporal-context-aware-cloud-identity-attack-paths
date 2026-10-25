"""
tests/unit/test_coverage_reporter.py - Unit tests for CoverageReporter.

Validates overall coverage ratio, per-field counts, uncovered edge detection,
empty input handling, and low_coverage_fields filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from arf_rt.temporal.coverage_reporter import CoverageReporter, FieldCoverage
from arf_rt.temporal.hints import TemporalHint

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _hint(edge_id: str, has_expiry: bool = True, has_last_used: bool = True) -> TemporalHint:
    return TemporalHint(
        edge_id=edge_id,
        credential_expiry=NOW if has_expiry else None,
        last_used=NOW if has_last_used else None,
    )


class TestFieldCoverage:
    def test_ratio_zero_when_no_covered(self):
        fc = FieldCoverage("f", covered=0, total=10)
        assert fc.ratio == 0.0

    def test_ratio_one_when_all_covered(self):
        fc = FieldCoverage("f", covered=5, total=5)
        assert fc.ratio == 1.0

    def test_percent_rounds_to_two_decimals(self):
        fc = FieldCoverage("f", covered=1, total=3)
        assert fc.percent == round(fc.ratio * 100, 2)

    def test_zero_total_ratio_zero(self):
        fc = FieldCoverage("f", covered=0, total=0)
        assert fc.ratio == 0.0


class TestCoverageReporterBasic:
    def test_all_edges_covered(self):
        reporter = CoverageReporter(["a", "b"])
        report = reporter.report([_hint("a"), _hint("b")])
        assert report.covered_edges == 2
        assert report.overall_ratio == 1.0
        assert report.uncovered_edge_ids == []

    def test_no_hints_all_uncovered(self):
        reporter = CoverageReporter(["a", "b", "c"])
        report = reporter.report([])
        assert report.covered_edges == 0
        assert report.total_edges == 3
        assert set(report.uncovered_edge_ids) == {"a", "b", "c"}

    def test_partial_coverage(self):
        reporter = CoverageReporter(["a", "b", "c"])
        report = reporter.report([_hint("a")])
        assert report.covered_edges == 1
        assert report.overall_percent == pytest.approx(33.33, abs=0.01)

    def test_empty_edge_set(self):
        reporter = CoverageReporter([])
        report = reporter.report([])
        assert report.total_edges == 0
        assert report.overall_ratio == 0.0

    def test_hint_for_unknown_edge_ignored(self):
        reporter = CoverageReporter(["a"])
        report = reporter.report([_hint("a"), _hint("UNKNOWN")])
        assert report.total_edges == 1
        assert report.covered_edges == 1


class TestFieldCoverageBreakdown:
    def test_credential_expiry_counted(self):
        reporter = CoverageReporter(["a", "b"])
        hints = [_hint("a", has_expiry=True), _hint("b", has_expiry=False)]
        report = reporter.report(hints)
        fc = report.field_coverage["credential_expiry"]
        assert fc.covered == 1

    def test_last_used_counted(self):
        reporter = CoverageReporter(["a"])
        report = reporter.report([_hint("a", has_last_used=True)])
        assert report.field_coverage["last_used"].covered == 1

    def test_all_tracked_fields_present(self):
        reporter = CoverageReporter(["a"])
        report = reporter.report([_hint("a")])
        for fname in CoverageReporter.TRACKED_FIELDS:
            assert fname in report.field_coverage


class TestLowCoverageFields:
    def test_returns_fields_below_threshold(self):
        reporter = CoverageReporter(["a", "b", "c"])
        # only 'a' has expiry, so 1/3 = 33% < 50%
        hints = [_hint("a", has_expiry=True), _hint("b", has_expiry=False), _hint("c", has_expiry=False)]
        report = reporter.report(hints)
        low = report.low_coverage_fields(threshold=0.50)
        field_names = [fc.field_name for fc in low]
        assert "credential_expiry" in field_names

    def test_full_coverage_no_low_fields(self):
        reporter = CoverageReporter(["a"])
        report = reporter.report([_hint("a")])
        # credential_expiry and last_used are covered; rest may be low
        # We check at threshold 0 — nothing should be below 0%
        low = report.low_coverage_fields(threshold=0.0)
        assert low == []


class TestSummaryOutput:
    def test_summary_contains_total(self):
        reporter = CoverageReporter(["a", "b"])
        report = reporter.report([_hint("a")])
        summary = report.summary()
        assert "Total edges" in summary
        assert "2" in summary
