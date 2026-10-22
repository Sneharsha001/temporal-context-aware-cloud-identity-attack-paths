"""
arf_rt/temporal/export.py - Exporters for temporal evaluation metrics and audit logs.

Provides utilities to export TemporalMetrics and TemporalAuditLog instances
to CSV, JSON, and Markdown summary tables for reporting and downstream analysis.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, TextIO

from arf_rt.temporal.audit_log import TemporalAuditLog
from arf_rt.temporal.metrics import TemporalMetrics


def export_metrics_to_dict(metrics: TemporalMetrics) -> dict[str, Any]:
    """Serialize TemporalMetrics to a Python dictionary."""
    return metrics.to_dict()


def export_metrics_to_csv(
    metrics: TemporalMetrics,
    target: Path | str | TextIO,
) -> None:
    """
    Export key metrics and constraint violation counts to CSV.

    Columns: Category, Metric, Value
    """
    rows: list[tuple[str, str, Any]] = [
        ("summary", "total_paths", metrics.total_paths),
        ("summary", "feasible_paths", metrics.feasible_paths),
        ("summary", "infeasible_paths", metrics.infeasible_paths),
        ("summary", "unknown_paths", metrics.unknown_paths),
        ("summary", "elimination_rate_pct", round(metrics.elimination_rate * 100, 2)),
    ]

    for constraint, count in metrics.constraint_violations.items():
        rows.append(("constraint_violation", constraint, count))

    for length, count in sorted(metrics.path_length_distribution.items()):
        rows.append(("path_length_distribution", f"length_{length}", count))

    if isinstance(target, (str, Path)):
        with open(target, "w", newline="", encoding="utf-8") as f:
            _write_csv_rows(f, ["Category", "Metric", "Value"], rows)
    else:
        _write_csv_rows(target, ["Category", "Metric", "Value"], rows)


def export_audit_log_to_csv(
    log: TemporalAuditLog,
    target: Path | str | TextIO,
) -> None:
    """
    Export audit log records to CSV.

    Columns: EdgeIDs, VerdictKind, Passed, RejectionReason, WindowAnomalies
    """
    headers = ["EdgeIDs", "VerdictKind", "Passed", "RejectionReason", "WindowAnomalies"]
    rows = []
    for r in log.records:
        rows.append((
            " -> ".join(r.edge_ids),
            r.verdict_kind,
            str(r.passed),
            r.rejected_by,
            "; ".join(r.window_anomalies),
        ))

    if isinstance(target, (str, Path)):
        with open(target, "w", newline="", encoding="utf-8") as f:
            _write_csv_rows(f, headers, rows)
    else:
        _write_csv_rows(target, headers, rows)


def generate_summary_table(metrics: TemporalMetrics) -> str:
    """Generate a GitHub-flavored Markdown summary table from TemporalMetrics."""
    lines = [
        "| Metric | Count | Ratio |",
        "|---|---|---|",
        f"| Evaluated Paths | {metrics.total_paths} | 100.0% |",
        f"| Feasible Paths | {metrics.feasible_paths} | {metrics.feasible_paths / max(1, metrics.total_paths):.1%} |",
        f"| Infeasible (Eliminated) | {metrics.infeasible_paths} | {metrics.elimination_rate:.1%} |",
        f"| Unknown (Incomplete Data) | {metrics.unknown_paths} | {metrics.unknown_paths / max(1, metrics.total_paths):.1%} |",
    ]
    return "\n".join(lines)


def _write_csv_rows(f: TextIO, headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    writer = csv.writer(f)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
