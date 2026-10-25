#!/usr/bin/env python3
"""
scripts/detect_temporal_drift.py - CLI tool for credential window drift analysis.

Compares two snapshots of TemporalHints (baseline vs. current) and identifies:
  - New credentials added
  - Deprecated or removed credentials
  - Expiry window contractions or expansions (delta seconds)
  - Staleness regressions (increased days without usage)

Usage:
  python scripts/detect_temporal_drift.py --baseline base_hints.json --current curr_hints.json
  python scripts/detect_temporal_drift.py -b base.json -c curr.json --format json --out drift.json
  python scripts/detect_temporal_drift.py -b base.json -c curr.json --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.temporal_drift_detector import (
    DriftKind,
    DriftReport,
    TemporalDriftDetector,
)
from scripts.validate_policy_windows import load_hints


def render_table(report: DriftReport) -> str:
    """Format DriftReport into an ASCII report table."""
    status_str = "DRIFT DETECTED" if report.has_drift else "STABLE (NO DRIFT)"
    by_k = report.by_kind
    lines = [
        "=" * 72,
        f"  TEMPORAL CREDENTIAL DRIFT REPORT: [{status_str}]",
        "=" * 72,
        f"  Baseline Count : {report.baseline_count}",
        f"  Current Count  : {report.current_count}",
        f"  Total Events   : {len(report.events)}",
        f"    • New Credentials      : {len(by_k[DriftKind.NEW_CREDENTIAL])}",
        f"    • Removed Credentials  : {len(by_k[DriftKind.REMOVED_CREDENTIAL])}",
        f"    • Expiry Extended      : {len(by_k[DriftKind.EXPIRY_EXTENDED])}",
        f"    • Expiry Advanced      : {len(by_k[DriftKind.EXPIRY_ADVANCED])}",
        f"    • Staleness Regressed  : {len(by_k[DriftKind.STALENESS_INCREASED])}",
        "-" * 72,
    ]
    if not report.has_drift:
        lines.append("  All credential validity windows match baseline without drift.")
    else:
        lines.append(f"  {'KIND':<22} {'EDGE ID':<20} {'DETAILS'}")
        lines.append("  " + "-" * 68)
        for ev in report.events:
            detail_str = f"base={ev.baseline_value} -> curr={ev.current_value}"
            if ev.delta_seconds is not None:
                detail_str += f" (Δ={ev.delta_seconds:+.0f}s)"
            lines.append(f"  {ev.kind.value:<22} {ev.edge_id:<20} {detail_str}")
    lines.append("=" * 72)
    return "\n".join(lines)


def report_to_dict(report: DriftReport) -> dict:
    """Serialize DriftReport into a JSON-friendly dict."""
    by_k = report.by_kind
    return {
        "has_drift": report.has_drift,
        "baseline_count": report.baseline_count,
        "current_count": report.current_count,
        "total_events": len(report.events),
        "new_credentials_count": len(by_k[DriftKind.NEW_CREDENTIAL]),
        "removed_credentials_count": len(by_k[DriftKind.REMOVED_CREDENTIAL]),
        "expiry_shifts_count": len(by_k[DriftKind.EXPIRY_EXTENDED]) + len(by_k[DriftKind.EXPIRY_ADVANCED]),
        "staleness_changes_count": len(by_k[DriftKind.STALENESS_INCREASED]) + len(by_k[DriftKind.STALENESS_DECREASED]),
        "events": [
            {
                "edge_id": ev.edge_id,
                "kind": ev.kind.value,
                "baseline_value": ev.baseline_value,
                "current_value": ev.current_value,
                "delta_seconds": ev.delta_seconds,
            }
            for ev in report.events
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="detect_temporal_drift",
        description="Detect temporal credential drift between baseline and current state snapshots.",
    )
    parser.add_argument(
        "--baseline", "-b",
        required=True,
        type=Path,
        help="Path to baseline hints or scenario JSON.",
    )
    parser.add_argument(
        "--current", "-c",
        required=True,
        type=Path,
        help="Path to current hints or scenario JSON.",
    )
    parser.add_argument(
        "--drift-threshold",
        type=float,
        default=0.0,
        help="Minimum expiry shift delta in seconds to trigger a drift event (default: 0.0s).",
    )
    parser.add_argument(
        "--staleness-threshold",
        type=float,
        default=86400.0,
        help="Minimum staleness delta in seconds to trigger a drift event (default: 86400s = 1d).",
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
        help="Exit with non-zero exit code (1) if any drift is detected.",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help="Optional destination path to write output report.",
    )

    args = parser.parse_args()

    if not args.baseline.exists():
        sys.stderr.write(f"Error: baseline file '{args.baseline}' not found.\n")
        return 2

    if not args.current.exists():
        sys.stderr.write(f"Error: current file '{args.current}' not found.\n")
        return 2

    try:
        baseline_hints = load_hints(args.baseline)
        current_hints = load_hints(args.current)
    except Exception as exc:
        sys.stderr.write(f"Error loading hint snapshots: {exc}\n")
        return 2

    detector = TemporalDriftDetector(
        expiry_threshold_seconds=args.drift_threshold,
        staleness_threshold_seconds=args.staleness_threshold,
    )
    report = detector.compare(baseline_hints, current_hints)

    if args.format == "json":
        output_str = json.dumps(report_to_dict(report), indent=2)
    else:
        output_str = render_table(report)

    if args.out:
        args.out.write_text(output_str, encoding="utf-8")
        print(f"Drift report written to {args.out}")
    else:
        print(output_str)

    if args.strict and report.has_drift:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
