#!/usr/bin/env python3
"""
scripts/audit_temporal_compliance.py - CLI tool for CIS AWS and NIST 800-53 temporal compliance auditing.

Audits cloud identity credentials against industry compliance standards:
  - CIS AWS Foundations Benchmark 1.3 / 1.4 / 1.16
  - NIST SP 800-53 Rev 5 (AC-2, IA-5, SC-10)

Usage:
  python scripts/audit_temporal_compliance.py --input scenario.json
  python scripts/audit_temporal_compliance.py --input hints.json --framework cis --strict
  python scripts/audit_temporal_compliance.py --input cloudtrail.json --format json --out compliance.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.compliance_auditor import (
    ComplianceAuditReport,
    Framework,
    TemporalComplianceAuditor,
)
from scripts.validate_policy_windows import load_hints


def report_to_dict(report: ComplianceAuditReport, framework_filter: Framework | None = None) -> dict:
    """Serialize compliance report to JSON dict with optional framework filtering."""
    findings = report.findings if framework_filter is None else report.findings_by_framework(framework_filter)
    violations = [f for f in findings if f.is_violation]
    score = (
        round(((len(findings) - len(violations)) / len(findings)) * 100.0, 2)
        if findings else 100.0
    )
    return {
        "compliance_score": score,
        "total_checks": len(findings),
        "passed_checks": len(findings) - len(violations),
        "violation_count": len(violations),
        "evaluated_edges_count": report.evaluated_edges_count,
        "findings": [f.to_dict() for f in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="audit_temporal_compliance",
        description="Audit credential temporal metadata against CIS AWS and NIST 800-53 compliance controls.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to hints JSON, scenario JSON, or CloudTrail log file.",
    )
    parser.add_argument(
        "--framework",
        choices=["all", "cis", "nist"],
        default="all",
        help="Target compliance framework (default: all).",
    )
    parser.add_argument(
        "--max-rotation-days",
        type=float,
        default=90.0,
        help="Maximum allowable credential age without rotation in days (default: 90.0d).",
    )
    parser.add_argument(
        "--max-session-duration",
        type=float,
        default=43200.0,
        help="Maximum permissible STS session duration in seconds (default: 43200s = 12h).",
    )
    parser.add_argument(
        "--reference-time",
        type=str,
        default=None,
        help="ISO timestamp for evaluation reference time (defaults to now UTC).",
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
        help="Exit with non-zero exit code (1) if any compliance violations exist.",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help="Optional destination path to write output file.",
    )

    args = parser.parse_args()

    if not args.input.exists():
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        return 2

    ref_time = None
    if args.reference_time:
        try:
            ref_time = datetime.fromisoformat(args.reference_time.replace("Z", "+00:00"))
        except ValueError as err:
            sys.stderr.write(f"Invalid reference-time ISO format: {err}\n")
            return 2

    try:
        hints = load_hints(args.input)
    except Exception as exc:
        sys.stderr.write(f"Error loading hints: {exc}\n")
        return 2

    auditor = TemporalComplianceAuditor(
        reference_time=ref_time,
        max_rotation_days=args.max_rotation_days,
        max_session_duration_seconds=args.max_session_duration,
    )
    report = auditor.audit(hints)

    fw_filter = None
    if args.framework == "cis":
        fw_filter = Framework.CIS_AWS
    elif args.framework == "nist":
        fw_filter = Framework.NIST_800_53

    if args.format == "json":
        output_str = json.dumps(report_to_dict(report, fw_filter), indent=2)
    else:
        output_str = report.summary()

    if args.out:
        args.out.write_text(output_str, encoding="utf-8")
        print(f"Compliance report written to {args.out}")
    else:
        print(output_str)

    has_violations = (
        any(f.is_violation for f in report.findings_by_framework(fw_filter))
        if fw_filter else len(report.violations) > 0
    )

    if args.strict and has_violations:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
