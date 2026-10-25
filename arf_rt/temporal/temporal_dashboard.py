"""
arf_rt/temporal/temporal_dashboard.py - ASCII text dashboard for temporal analysis results.

Aggregates outputs from CredentialScorer, CredentialAlertEngine, PolicyWindowValidator,
CoverageReporter, and TemporalDriftDetector into a single formatted terminal report
suitable for CI log output, operator consoles, and Markdown embedding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from arf_rt.temporal.credential_alert_engine import Alert, AlertSeverity
from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.coverage_reporter import CoverageReport
from arf_rt.temporal.policy_window_validator import PolicyValidationResult
from arf_rt.temporal.temporal_drift_detector import DriftReport


# ---------------------------------------------------------------------------
# Box drawing helpers
# ---------------------------------------------------------------------------

_BOX_WIDTH = 72


def _header(title: str) -> str:
    pad = max(0, _BOX_WIDTH - len(title) - 4)
    return f"+- {title} {'-' * pad}+"


def _footer() -> str:
    return "+" + "-" * (_BOX_WIDTH - 2) + "+"


def _row(content: str) -> str:
    pad = max(0, _BOX_WIDTH - len(content) - 4)
    return f"|  {content}{' ' * pad} |"


def _separator() -> str:
    return "+" + "-" * (_BOX_WIDTH - 2) + "+"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_scores(scores: Sequence[CredentialRiskScore], top_n: int = 5) -> list[str]:
    lines: list[str] = [_header("Top Credential Risk Scores"), _row("")]
    for s in list(scores)[:top_n]:
        bar_len = int(s.score * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        label = f"{s.label:<8}"
        lines.append(_row(f"{s.edge_id[:28]:<28}  [{bar}] {s.score:.3f}  {label}"))
    if not scores:
        lines.append(_row("  (no scored edges)"))
    lines += [_row(""), _footer()]
    return lines


def _render_alerts(alerts: Sequence[Alert]) -> list[str]:
    by_sev: dict[AlertSeverity, int] = {s: 0 for s in AlertSeverity}
    for a in alerts:
        by_sev[a.severity] += 1
    lines = [_header("Alert Summary"), _row("")]
    for sev in AlertSeverity:
        count = by_sev[sev]
        indicator = "⚠" if count > 0 else "·"
        lines.append(_row(f"  {indicator}  {sev.value:<10}  {count} alert(s)"))
    lines += [_row(""), _row(f"  Total alerts: {len(alerts)}"), _row(""), _footer()]
    return lines


def _render_policy(result: PolicyValidationResult) -> list[str]:
    status = "✓ PASS" if result.is_valid else "✗ FAIL"
    lines = [
        _header("Policy Validation"),
        _row(""),
        _row(f"  Status  : {status}"),
        _row(f"  Passed  : {result.passed_count}"),
        _row(f"  Failed  : {result.failed_count}"),
        _row(f"  Violations: {len(result.violations)}"),
    ]
    for v in result.violations[:3]:
        lines.append(_row(f"    [{v.rule}] {v.edge_id[:35]}"))
    if len(result.violations) > 3:
        lines.append(_row(f"    ... and {len(result.violations) - 3} more"))
    lines += [_row(""), _footer()]
    return lines


def _render_coverage(report: CoverageReport) -> list[str]:
    pct = report.overall_percent
    bar_len = int(pct / 5)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    lines = [
        _header("Temporal Coverage"),
        _row(""),
        _row(f"  Overall  [{bar}] {pct:.1f}%"),
        _row(f"  Covered  : {report.covered_edges} / {report.total_edges} edges"),
        _row(f"  Uncovered: {len(report.uncovered_edge_ids)} edge(s)"),
        _row(""),
        _row("  Per-field coverage:"),
    ]
    for fc in report.field_coverage.values():
        bar_len2 = int(fc.ratio * 20)
        fbar = "█" * bar_len2 + "░" * (20 - bar_len2)
        lines.append(_row(f"    {fc.field_name:<25} [{fbar}] {fc.percent:.1f}%"))
    lines += [_row(""), _footer()]
    return lines


def _render_drift(report: DriftReport) -> list[str]:
    lines = [
        _header("Drift Detection"),
        _row(""),
        _row(f"  Has drift : {'Yes' if report.has_drift else 'No'}"),
        _row(f"  Events    : {len(report.events)}"),
    ]
    by_kind = report.by_kind
    for kind, evts in by_kind.items():
        if evts:
            lines.append(_row(f"  {kind.value}: {len(evts)}"))
    lines += [_row(""), _footer()]
    return lines


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TemporalDashboard:
    """
    Assembles a multi-section ASCII dashboard from temporal analysis results.

    All parameters are optional — omit sections you don't have data for.
    """

    def __init__(
        self,
        scores: Sequence[CredentialRiskScore] | None = None,
        alerts: Sequence[Alert] | None = None,
        policy_result: PolicyValidationResult | None = None,
        coverage_report: CoverageReport | None = None,
        drift_report: DriftReport | None = None,
        generated_at: datetime | None = None,
    ) -> None:
        self.scores = scores or []
        self.alerts = alerts or []
        self.policy_result = policy_result
        self.coverage_report = coverage_report
        self.drift_report = drift_report
        self.generated_at = generated_at or datetime.now(tz=timezone.utc)

    def render(self) -> str:
        """Return the full dashboard as a string."""
        sections: list[str] = []

        # Title
        ts = self.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        title = f"ARF-RT Temporal Analysis Dashboard  --  {ts}"
        sections.append("=" * _BOX_WIDTH)
        sections.append(title.center(_BOX_WIDTH))
        sections.append("=" * _BOX_WIDTH)
        sections.append("")

        if self.scores:
            sections += _render_scores(self.scores)
            sections.append("")

        if self.alerts is not None:
            sections += _render_alerts(self.alerts)
            sections.append("")

        if self.policy_result is not None:
            sections += _render_policy(self.policy_result)
            sections.append("")

        if self.coverage_report is not None:
            sections += _render_coverage(self.coverage_report)
            sections.append("")

        if self.drift_report is not None:
            sections += _render_drift(self.drift_report)
            sections.append("")

        sections.append("═" * _BOX_WIDTH)
        return "\n".join(sections)

    def print(self) -> None:
        """Print the dashboard to stdout."""
        print(self.render())
