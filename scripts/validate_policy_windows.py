#!/usr/bin/env python3
"""
scripts/validate_policy_windows.py - CLI tool for credential window policy enforcement.

Validates TemporalHint credential windows against organizational security constraints:
  - Expired credential detection
  - Minimum remaining validity window (TTL)
  - Maximum STS session duration
  - Maximum credential rotation age / staleness

Usage:
  python scripts/validate_policy_windows.py --input hints.json
  python scripts/validate_policy_windows.py --input cloudtrail.json --format json
  python scripts/validate_policy_windows.py --input hints.json --max-session-duration 3600 --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.policy_window_validator import (
    PolicyConfig,
    PolicyValidationResult,
    PolicyWindowValidator,
)


def load_hints(file_path: Path) -> list[TemporalHint]:
    """Load TemporalHint instances from a JSON file (hints dict, list, or CloudTrail log)."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # CloudTrail format (Records key or list of event records)
    if isinstance(data, dict) and "Records" in data:
        extracted = extract_hints_from_log(data["Records"])
        return list(extracted.values())
    if isinstance(data, list) and data and isinstance(data[0], dict) and "eventName" in data[0]:
        extracted = extract_hints_from_log(data)
        return list(extracted.values())

    # Direct list of hint dicts
    if isinstance(data, list):
        return [TemporalHint.from_dict(item) for item in data if isinstance(item, dict)]

    # Dictionary format
    if isinstance(data, dict):
        # Scenario with 'temporal_hints' key
        if "temporal_hints" in data and isinstance(data["temporal_hints"], dict):
            return [
                TemporalHint.from_dict({**h, "edge_id": eid} if "edge_id" not in h else h)
                for eid, h in data["temporal_hints"].items()
            ]
        # Map of edge_id -> hint dict
        hints = []
        for eid, item in data.items():
            if isinstance(item, dict):
                hint_dict = dict(item)
                if "edge_id" not in hint_dict:
                    hint_dict["edge_id"] = eid
                hints.append(TemporalHint.from_dict(hint_dict))
        return hints

    raise ValueError(f"Unrecognized file format in {file_path}")


def render_table(result: PolicyValidationResult) -> str:
    """Format PolicyValidationResult into an ASCII report table."""
    status_str = "PASS" if result.is_valid else "FAIL"
    lines = [
        "=" * 68,
        f"  CREDENTIAL POLICY WINDOW VALIDATION REPORT: [{status_str}]",
        "=" * 68,
        f"  Total Hints Evaluated : {result.passed_count + result.failed_count}",
        f"  Passed Policy Checks  : {result.passed_count}",
        f"  Violations Detected   : {len(result.violations)} (across {result.failed_count} credentials)",
        "-" * 68,
    ]
    if not result.violations:
        lines.append("  All evaluated credential windows satisfy policy rules.")
    else:
        lines.append(f"  {'RULE':<26} {'EDGE ID':<20} {'DETAIL'}")
        lines.append("  " + "-" * 64)
        for v in result.violations:
            lines.append(f"  {v.rule:<26} {v.edge_id:<20} {v.detail}")
    lines.append("=" * 68)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="validate_policy_windows",
        description="Validate credential lifetimes against organizational policy rules.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to hints JSON or CloudTrail JSON file.",
    )
    parser.add_argument(
        "--max-session-duration",
        type=float,
        default=43200.0,
        help="Maximum permissible session duration in seconds (default: 43200s = 12h).",
    )
    parser.add_argument(
        "--max-rotation-age",
        type=float,
        default=7776000.0,
        help="Maximum permissible credential age without rotation in seconds (default: 90d).",
    )
    parser.add_argument(
        "--min-validity-window",
        type=float,
        default=300.0,
        help="Minimum remaining credential validity window in seconds (default: 300s).",
    )
    parser.add_argument(
        "--allow-expired",
        action="store_true",
        default=False,
        help="Do not flag expired credentials as violations.",
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
        help="Return non-zero exit code (1) if any policy violations exist.",
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

    try:
        hints = load_hints(args.input)
    except Exception as exc:
        sys.stderr.write(f"Error loading hints: {exc}\n")
        return 2

    ref_time = None
    if args.reference_time:
        try:
            ref_time = datetime.fromisoformat(args.reference_time.replace("Z", "+00:00"))
        except ValueError as err:
            sys.stderr.write(f"Invalid reference-time ISO format: {err}\n")
            return 2

    policy = PolicyConfig(
        max_session_duration_seconds=args.max_session_duration,
        max_rotation_age_seconds=args.max_rotation_age,
        min_validity_window_seconds=args.min_validity_window,
        allow_expired=args.allow_expired,
    )

    validator = PolicyWindowValidator(policy=policy, reference_time=ref_time)
    result = validator.validate(hints)

    if args.format == "json":
        output_str = json.dumps(
            {
                "is_valid": result.is_valid,
                "passed_count": result.passed_count,
                "failed_count": result.failed_count,
                "violation_count": len(result.violations),
                "violations": [
                    {"edge_id": v.edge_id, "rule": v.rule, "detail": v.detail}
                    for v in result.violations
                ],
            },
            indent=2,
        )
    else:
        output_str = render_table(result)

    if args.out:
        args.out.write_text(output_str, encoding="utf-8")
        print(f"Results written to {args.out}")
    else:
        print(output_str)

    if args.strict and not result.is_valid:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
