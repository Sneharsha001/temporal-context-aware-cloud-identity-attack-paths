"""
tests/unit/test_temporal_dashboard.py - Unit tests for TemporalDashboard.

Validates that the dashboard renders without errors, contains expected section
markers for each provided data source, and handles empty/missing inputs gracefully.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from arf_rt.temporal.credential_alert_engine import Alert, AlertSeverity
from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.coverage_reporter import CoverageReport, FieldCoverage
from arf_rt.temporal.policy_window_validator import PolicyValidationResult
from arf_rt.temporal.temporal_dashboard import TemporalDashboard
from arf_rt.temporal.temporal_drift_detector import DriftReport

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(edge_id: str = "e1", score: float = 0.7) -> CredentialRiskScore:
    return CredentialRiskScore(
        edge_id=edge_id, score=score,
        expiry_factor=0.6, staleness_factor=0.5, short_lived_bonus=0.0,
    )


def _alert() -> Alert:
    return Alert(
        edge_id="e1",
        severity=AlertSeverity.HIGH,
        rule_name="HIGH_SCORE",
        message="test alert",
        score=0.75,
        triggered_at=NOW,
    )


def _policy_result(passed: int = 2, failed: int = 0) -> PolicyValidationResult:
    return PolicyValidationResult(passed_count=passed, failed_count=failed)


def _coverage_report() -> CoverageReport:
    fc = FieldCoverage(field_name="credential_expiry", covered=3, total=5)
    return CoverageReport(
        total_edges=5,
        covered_edges=3,
        uncovered_edge_ids=["x", "y"],
        field_coverage={"credential_expiry": fc},
    )


def _drift_report() -> DriftReport:
    return DriftReport(events=[], detected_at=NOW, baseline_count=3, current_count=3)


# ---------------------------------------------------------------------------
# Basic render
# ---------------------------------------------------------------------------

class TestDashboardRender:
    def test_renders_without_error(self):
        d = TemporalDashboard(generated_at=NOW)
        output = d.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_empty_dashboard_has_title(self):
        d = TemporalDashboard(generated_at=NOW)
        output = d.render()
        assert "ARF-RT Temporal Analysis Dashboard" in output

    def test_generated_at_in_output(self):
        d = TemporalDashboard(generated_at=NOW)
        output = d.render()
        assert "2026-10-25" in output

    def test_print_does_not_raise(self, capsys):
        d = TemporalDashboard(generated_at=NOW)
        d.print()
        captured = capsys.readouterr()
        assert "ARF-RT" in captured.out


# ---------------------------------------------------------------------------
# Score section
# ---------------------------------------------------------------------------

class TestScoreSection:
    def test_score_section_present_when_scores_provided(self):
        d = TemporalDashboard(scores=[_score("edge-alpha", 0.85)], generated_at=NOW)
        output = d.render()
        assert "edge-alpha" in output

    def test_score_section_absent_when_no_scores(self):
        d = TemporalDashboard(scores=[], generated_at=NOW)
        output = d.render()
        assert "Top Credential Risk Scores" not in output

    def test_top_5_capped(self):
        scores = [_score(f"e{i}", 0.9 - i * 0.05) for i in range(10)]
        d = TemporalDashboard(scores=scores, generated_at=NOW)
        output = d.render()
        # Only first 5 should appear
        assert "e0" in output
        assert "e4" in output
        assert "e5" not in output


# ---------------------------------------------------------------------------
# Alert section
# ---------------------------------------------------------------------------

class TestAlertSection:
    def test_alert_section_rendered(self):
        d = TemporalDashboard(alerts=[_alert()], generated_at=NOW)
        output = d.render()
        assert "Alert Summary" in output

    def test_zero_alerts_rendered(self):
        d = TemporalDashboard(alerts=[], generated_at=NOW)
        output = d.render()
        assert "Alert Summary" in output
        assert "Total alerts: 0" in output


# ---------------------------------------------------------------------------
# Policy section
# ---------------------------------------------------------------------------

class TestPolicySection:
    def test_policy_section_rendered(self):
        d = TemporalDashboard(policy_result=_policy_result(), generated_at=NOW)
        output = d.render()
        assert "Policy Validation" in output

    def test_policy_pass_shown(self):
        d = TemporalDashboard(policy_result=_policy_result(2, 0), generated_at=NOW)
        output = d.render()
        assert "PASS" in output

    def test_policy_section_absent_when_none(self):
        d = TemporalDashboard(policy_result=None, generated_at=NOW)
        output = d.render()
        assert "Policy Validation" not in output


# ---------------------------------------------------------------------------
# Coverage section
# ---------------------------------------------------------------------------

class TestCoverageSection:
    def test_coverage_section_rendered(self):
        d = TemporalDashboard(coverage_report=_coverage_report(), generated_at=NOW)
        output = d.render()
        assert "Temporal Coverage" in output

    def test_coverage_section_absent_when_none(self):
        d = TemporalDashboard(coverage_report=None, generated_at=NOW)
        output = d.render()
        assert "Temporal Coverage" not in output


# ---------------------------------------------------------------------------
# Drift section
# ---------------------------------------------------------------------------

class TestDriftSection:
    def test_drift_section_rendered(self):
        d = TemporalDashboard(drift_report=_drift_report(), generated_at=NOW)
        output = d.render()
        assert "Drift Detection" in output

    def test_no_drift_reported(self):
        d = TemporalDashboard(drift_report=_drift_report(), generated_at=NOW)
        output = d.render()
        assert "No" in output  # "Has drift : No"

    def test_drift_section_absent_when_none(self):
        d = TemporalDashboard(drift_report=None, generated_at=NOW)
        output = d.render()
        assert "Drift Detection" not in output
