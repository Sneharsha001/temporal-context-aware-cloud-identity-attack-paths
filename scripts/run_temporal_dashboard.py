#!/usr/bin/env python3
"""
scripts/run_temporal_dashboard.py - CLI tool for running the integrated temporal security dashboard.

Aggregates multiple temporal analysis engines into a single unified terminal dashboard:
  - Credential risk scoring (CredentialScorer)
  - Security alerts & SIEM thresholds (CredentialAlertEngine)
  - Policy window compliance (PolicyWindowValidator)
  - Temporal hint coverage (CoverageReporter)
  - Cross-snapshot drift detection (TemporalDriftDetector) [optional]

Usage:
  python scripts/run_temporal_dashboard.py --input scenario.json
  python scripts/run_temporal_dashboard.py --input current_hints.json --baseline base_hints.json
  python scripts/run_temporal_dashboard.py --input scenario.json --out dashboard.txt
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.coverage_reporter import CoverageReporter
from arf_rt.temporal.credential_alert_engine import CredentialAlertEngine
from arf_rt.temporal.credential_scorer import CredentialScorer
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.policy_window_validator import PolicyConfig, PolicyWindowValidator
from arf_rt.temporal.temporal_dashboard import TemporalDashboard
from arf_rt.temporal.temporal_drift_detector import TemporalDriftDetector
from scripts.report_temporal_coverage import extract_edges_and_hints
from scripts.validate_policy_windows import load_hints


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_temporal_dashboard",
        description="Run unified temporal analysis dashboard across hints, scoring, policy, and drift.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to hints JSON, scenario JSON, or CloudTrail log file.",
    )
    parser.add_argument(
        "--baseline", "-b",
        type=Path,
        default=None,
        help="Optional baseline hints/scenario file for drift detection.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top risk credentials to display (default: 5).",
    )
    parser.add_argument(
        "--reference-time",
        type=str,
        default=None,
        help="ISO timestamp for evaluation reference time (defaults to now UTC).",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help="Optional file path to write dashboard output.",
    )

    args = parser.parse_args()

    if not args.input.exists():
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        return 2

    if args.baseline and not args.baseline.exists():
        sys.stderr.write(f"Error: baseline file '{args.baseline}' not found.\n")
        return 2

    ref_time = None
    if args.reference_time:
        try:
            ref_time = datetime.fromisoformat(args.reference_time.replace("Z", "+00:00"))
        except ValueError as err:
            sys.stderr.write(f"Invalid reference-time ISO format: {err}\n")
            return 2

    now = ref_time or datetime.now(tz=timezone.utc)

    try:
        all_edges, hints = extract_edges_and_hints(args.input)
    except Exception as exc:
        sys.stderr.write(f"Error extracting hints from input: {exc}\n")
        return 2

    # 1. Credential Risk Scoring
    scorer = CredentialScorer(reference_time=now)
    scores = scorer.score_all(hints)

    # 2. Alert Engine
    engine = CredentialAlertEngine()
    alerts = engine.evaluate(scores)

    # 3. Policy Window Validator
    validator = PolicyWindowValidator(reference_time=now)
    policy_result = validator.validate(hints)

    # 4. Coverage Reporter
    reporter = CoverageReporter(all_edge_ids=all_edges)
    coverage_report = reporter.report(hints)

    # 5. Drift Report (optional)
    drift_report = None
    if args.baseline:
        try:
            baseline_hints = load_hints(args.baseline)
            detector = TemporalDriftDetector(reference_time=now)
            drift_report = detector.compare(baseline_hints, hints)
        except Exception as exc:
            sys.stderr.write(f"Warning: failed to compute drift: {exc}\n")

    # Assemble Dashboard
    dashboard = TemporalDashboard(
        scores=scores,
        alerts=alerts,
        policy_result=policy_result,
        coverage_report=coverage_report,
        drift_report=drift_report,
        generated_at=now,
    )

    rendered = dashboard.render()

    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
        print(f"Dashboard written to {args.out}")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    sys.exit(main())
