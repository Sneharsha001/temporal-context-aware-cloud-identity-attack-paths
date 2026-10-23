"""
arf_rt/temporal/summary.py - Structured summary and audit reporting for temporal evaluations.

Provides formatted executive summaries, constraint violation breakdowns, and
complete diagnostic audit reports from TemporalMetrics and TemporalAuditLog.
"""

from __future__ import annotations

from typing import Any

from arf_rt.temporal.audit_log import TemporalAuditLog
from arf_rt.temporal.metrics import TemporalMetrics


class TemporalSummaryReporter:
    """
    Generates human-readable Markdown summaries and security audit reports
    from temporal feasibility evaluation results.
    """

    def __init__(self, metrics: TemporalMetrics, audit_log: TemporalAuditLog | None = None) -> None:
        self.metrics = metrics
        self.audit_log = audit_log

    def generate_executive_summary(self) -> str:
        """Generate a concise Markdown executive summary for incident commanders."""
        total = self.metrics.total_paths
        elim = self.metrics.infeasible_count
        rate = self.metrics.elimination_rate
        feas = self.metrics.feasible_count
        unk = self.metrics.unknown_count

        status = "CRITICAL_ANOMALIES_DETECTED" if elim > 0 else "NOMINAL_FEASIBILITY"

        lines = [
            "# Temporal Evaluation Executive Summary",
            "",
            f"**Status:** `{status}`  ",
            f"**Total Paths Evaluated:** {total}  ",
            f"**Feasible Paths:** {feas} ({feas / max(1, total):.1%})  ",
            f"**Infeasible Paths (Eliminated):** {elim} ({rate:.1%})  ",
            f"**Unknown Status (Sparse Data):** {unk} ({unk / max(1, total):.1%})  ",
            "",
            "### Risk Impact",
            f"- Temporal post-filtering eliminated **{rate:.1%}** of candidate attack paths.",
        ]

        top_violation = self.metrics.top_violated_constraint
        if top_violation:
            lines.append(
                f"- Primary elimination driver: **{top_violation}** "
                f"({self.metrics.constraint_violations.get(top_violation, 0)} violations)."
            )
        else:
            lines.append("- No temporal constraints were violated across the evaluated paths.")

        return "\n".join(lines)

    def generate_constraint_breakdown(self) -> str:
        """Generate a detailed breakdown table of constraint violations."""
        if not self.metrics.constraint_violations:
            return "No temporal constraint violations recorded."

        lines = [
            "### Constraint Violation Breakdown",
            "",
            "| Constraint ID | Description | Violations | Percentage |",
            "|---|---|---|---|",
        ]

        descriptions = {
            "TC-1": "Causal Order Violation (Event observed before prior step)",
            "TC-2": "Session Lifetime Expiration (Token expired before use)",
            "TC-3": "Minimum Velocity Violation (Hop traversed too fast)",
            "TC-4": "Stale Credential Violation (Inactive beyond freshness threshold)",
            "TC-5": "Concurrent Session Anomaly (Impossible simultaneous assume)",
        }

        total_violations = sum(self.metrics.constraint_violations.values())
        for cid, count in sorted(self.metrics.constraint_violations.items(), key=lambda x: x[1], reverse=True):
            desc = descriptions.get(cid, "Custom Temporal Constraint")
            pct = (count / max(1, total_violations)) * 100
            lines.append(f"| `{cid}` | {desc} | {count} | {pct:.1f}% |")

        return "\n".join(lines)

    def generate_full_audit_report(self, title: str = "Temporal Path Feasibility Audit Report") -> str:
        """Generate a complete Markdown audit report including metrics and recent log entries."""
        sections = [
            f"# {title}",
            "",
            self.generate_executive_summary(),
            "",
            self.generate_constraint_breakdown(),
            "",
            "### Path Length Distribution",
            "",
            "| Hop Count | Number of Paths |",
            "|---|---|",
        ]

        for hops, count in sorted(self.metrics.path_length_histogram.items()):
            sections.append(f"| {hops} hops | {count} |")

        if self.audit_log and len(self.audit_log) > 0:
            sections.extend([
                "",
                "### Detailed Audit Trail (Last 10 Records)",
                "",
                "| Path | Verdict | Violated Constraint | Reason |",
                "|---|---|---|---|",
            ])
            for entry in self.audit_log.entries[-10:]:
                path_str = " -> ".join(entry.path_edge_ids)
                viol = entry.violated_constraint or "-"
                sections.append(f"| `{path_str}` | `{entry.verdict_kind}` | `{viol}` | {entry.reason} |")

        return "\n".join(sections)
