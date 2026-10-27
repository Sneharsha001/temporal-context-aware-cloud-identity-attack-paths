#!/usr/bin/env python3
"""
scripts/generate_remediation_plan.py - CLI tool for generating prioritized cloud remediation playbooks.

Synthesizes policy violations, compliance findings, and credential risk scores
into prioritized, ready-to-run AWS CLI remediation playbooks.

Usage:
  python scripts/generate_remediation_plan.py --input scenario.json
  python scripts/generate_remediation_plan.py --input hints.json --format shell --out remediate.sh
  python scripts/generate_remediation_plan.py --input hints.json --top 5 --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.compliance_auditor import TemporalComplianceAuditor
from arf_rt.temporal.credential_scorer import CredentialScorer
from arf_rt.temporal.policy_window_validator import PolicyWindowValidator
from arf_rt.temporal.remediation_planner import (
    RemediationAction,
    TemporalRemediationPlanner,
)
from scripts.validate_policy_windows import load_hints


def render_table(actions: list[RemediationAction]) -> str:
    """Format remediation actions into an ASCII plan table."""
    lines = [
        "=" * 76,
        "  PRIORITIZED TEMPORAL REMEDIATION PLAYBOOK",
        "=" * 76,
        f"  Total Recommended Actions: {len(actions)}",
        "-" * 76,
    ]
    if not actions:
        lines.append("  No remediation actions required — all credentials satisfy security policies.")
    else:
        lines.append(f"  {'ID':<9} {'PRIORITY':<10} {'TYPE':<25} {'EDGE ID':<20} {'EST. REDUCTION'}")
        lines.append("  " + "-" * 72)
        for a in actions:
            prio_label = {1: "1 (CRITICAL)", 2: "2 (HIGH)", 3: "3 (MEDIUM)", 4: "4 (LOW)"}.get(a.priority, str(a.priority))
            lines.append(
                f"  {a.action_id:<9} {prio_label:<10} {a.action_type.value:<25} {a.edge_id:<20} {a.estimated_risk_reduction*100:>5.1f}%"
            )
            lines.append(f"    Rationale : {a.rationale}")
            lines.append(f"    AWS CLI   : {a.cli_command_template}")
            lines.append("")
    lines.append("=" * 76)
    return "\n".join(lines)


def render_shell(actions: list[RemediationAction]) -> str:
    """Format remediation actions as an executable bash / AWS CLI script."""
    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated ARF-RT Temporal Remediation Playbook",
        "set -euo pipefail",
        "",
        "echo 'Starting ARF-RT security remediation execution...'",
        "",
    ]
    for a in actions:
        lines.append(f"# [{a.action_id}] Priority {a.priority}: {a.rationale}")
        lines.append(f"# Target Edge: {a.edge_id}")
        lines.append(f"{a.cli_command_template}")
        lines.append("")
    lines.append("echo 'Remediation completed successfully.'")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="generate_remediation_plan",
        description="Generate prioritized cloud security remediation playbooks from temporal findings.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to hints JSON, scenario JSON, or CloudTrail log file.",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=None,
        help="Limit output to top N highest priority actions.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json", "shell"],
        default="table",
        help="Output format (default: table).",
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

    now = ref_time or datetime.now(tz=timezone.utc)

    try:
        hints = load_hints(args.input)
    except Exception as exc:
        sys.stderr.write(f"Error loading hints: {exc}\n")
        return 2

    # Run analysis engines
    policy_validator = PolicyWindowValidator(reference_time=now)
    policy_res = policy_validator.validate(hints)

    compliance_auditor = TemporalComplianceAuditor(reference_time=now)
    compliance_res = compliance_auditor.audit(hints)

    scorer = CredentialScorer(reference_time=now)
    scores = scorer.score_all(hints)

    # Synthesize remediation plan
    planner = TemporalRemediationPlanner()
    actions = planner.generate_plan(
        scores=scores,
        policy_violations=policy_res.violations,
        compliance_findings=compliance_res.findings,
    )

    if args.top is not None:
        actions = actions[: args.top]

    if args.format == "json":
        output_str = json.dumps([a.to_dict() for a in actions], indent=2)
    elif args.format == "shell":
        output_str = render_shell(actions)
    else:
        output_str = render_table(actions)

    if args.out:
        args.out.write_text(output_str, encoding="utf-8")
        print(f"Remediation playbook written to {args.out}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
