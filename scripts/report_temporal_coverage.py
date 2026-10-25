#!/usr/bin/env python3
"""
scripts/report_temporal_coverage.py - CLI tool for temporal metadata coverage analysis.

Measures the proportion of graph edges carrying temporal hints, identifies
uncovered edges, and produces per-field breakdown statistics (observation windows,
STS session lifetimes, and IAM last-used timestamps).

Usage:
  python scripts/report_temporal_coverage.py --input scenario.json
  python scripts/report_temporal_coverage.py --hints hints.json --edges e1,e2,e3
  python scripts/report_temporal_coverage.py --input scenario.json --threshold 80 --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.coverage_reporter import CoverageReport, CoverageReporter
from arf_rt.temporal.hints import TemporalHint
from scripts.validate_policy_windows import load_hints


def extract_edges_and_hints(file_path: Path) -> tuple[list[str], list[TemporalHint]]:
    """Extract all edge IDs and available TemporalHint objects from input."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    hints = load_hints(file_path)
    hint_edge_ids = [h.edge_id for h in hints if h.edge_id]

    all_edge_ids: list[str] = []
    if isinstance(data, dict):
        # Scenario with 'edges' list
        if "edges" in data and isinstance(data["edges"], list):
            for e in data["edges"]:
                if isinstance(e, dict):
                    eid = e.get("edge_id") or e.get("id")
                    if not eid and "src" in e and "dst" in e:
                        src = e["src"] if isinstance(e["src"], str) else e["src"].get("provider_id", "")
                        dst = e["dst"] if isinstance(e["dst"], str) else e["dst"].get("provider_id", "")
                        eid = f"{src}->{dst}"
                    if eid:
                        all_edge_ids.append(str(eid))
                elif isinstance(e, str):
                    all_edge_ids.append(e)

    # Fallback to hint edge IDs if no edges list was explicitly found
    if not all_edge_ids:
        all_edge_ids = list(dict.fromkeys(hint_edge_ids))

    return all_edge_ids, hints


def coverage_to_dict(report: CoverageReport) -> dict:
    """Serialize CoverageReport to a JSON-compatible dictionary."""
    return {
        "total_edges": report.total_edges,
        "covered_edges": report.covered_edges,
        "overall_percent": report.overall_percent,
        "uncovered_count": len(report.uncovered_edge_ids),
        "uncovered_edge_ids": report.uncovered_edge_ids,
        "fields": {
            k: {
                "covered": fc.covered,
                "total": fc.total,
                "percent": fc.percent,
            }
            for k, fc in report.field_coverage.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="report_temporal_coverage",
        description="Analyze temporal hint coverage and identify gaps across graph edges.",
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Path to scenario JSON or hints JSON.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="Minimum required overall coverage percentage (default: 50.0%%).",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit with non-zero exit code (1) if overall coverage is below threshold.",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help="Optional destination path to write output report.",
    )

    args = parser.parse_args()

    if not args.input.exists():
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        return 2

    try:
        all_edges, hints = extract_edges_and_hints(args.input)
    except Exception as exc:
        sys.stderr.write(f"Error parsing scenario or hints: {exc}\n")
        return 2

    reporter = CoverageReporter(all_edge_ids=all_edges)
    report = reporter.report(hints)

    if args.format == "json":
        output_str = json.dumps(coverage_to_dict(report), indent=2)
    else:
        output_str = report.summary()

    if args.out:
        args.out.write_text(output_str, encoding="utf-8")
        print(f"Coverage report written to {args.out}")
    else:
        print(output_str)

    if args.strict and report.overall_percent < args.threshold:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
