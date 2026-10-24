#!/usr/bin/env python3
"""
scripts/simulate_revocation.py - CLI tool for evaluating credential revocation impact.

Evaluates how many candidate attack paths are neutralized by invalidating
specific IAM roles or session credentials at a given timestamp.

Usage::

    python scripts/simulate_revocation.py --paths paths.json --hints hints.json --revoke-role DevRole
    python scripts/simulate_revocation.py --paths paths.json --hints hints.json --revoke-role ProdRole --time 2026-10-24T12:00:00Z
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.revocation_simulator import SessionRevocationSimulator


def _load_paths(path: Path) -> list[list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and all(isinstance(p, list) for p in data):
        return data
    raise ValueError("Paths file must contain an array of string arrays.")


def _load_hints(path: Path) -> dict[str, TemporalHint]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {eid: TemporalHint.from_dict(h) for eid, h in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate the blast radius and risk reduction of credential revocation."
    )
    parser.add_argument(
        "--paths",
        type=Path,
        required=True,
        help="Path to JSON file containing candidate attack paths.",
    )
    parser.add_argument(
        "--hints",
        type=Path,
        required=True,
        help="Path to JSON file containing TemporalHints mapping.",
    )
    parser.add_argument(
        "--revoke-role",
        type=str,
        required=True,
        help="Role name, ARN, or substring identifier to revoke.",
    )
    parser.add_argument(
        "--time",
        type=str,
        default=None,
        help="ISO-8601 revocation timestamp (defaults to current UTC time).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write Markdown impact report.",
    )

    args = parser.parse_args()

    if not args.paths.exists():
        print(f"Error: Paths file '{args.paths}' does not exist.", file=sys.stderr)
        return 1

    if not args.hints.exists():
        print(f"Error: Hints file '{args.hints}' does not exist.", file=sys.stderr)
        return 1

    if args.time:
        rev_time = datetime.fromisoformat(args.time.replace("Z", "+00:00"))
    else:
        rev_time = datetime.now(timezone.utc)

    paths = _load_paths(args.paths)
    hints = _load_hints(args.hints)

    impact = SessionRevocationSimulator.simulate_revocation(
        paths=paths,
        hints=hints,
        revocation_time=rev_time,
        revoked_edge_or_role_identifiers={args.revoke_role},
    )

    lines = [
        "# Credential Revocation Simulation Report",
        "",
        f"**Target Role / Identifier:** `{args.revoke_role}`  ",
        f"**Revocation Timestamp:** `{rev_time.isoformat()}`  ",
        "",
        "### Blast Radius Impact",
        f"- **Total Attack Paths:** {impact.total_paths}",
        f"- **Neutralized (Severed) Paths:** {impact.eliminated_paths_count} ({impact.elimination_ratio:.1%})",
        f"- **Remaining Active Paths:** {impact.active_paths_count}",
        "",
    ]

    if impact.severed_paths:
        lines.append("### Neutralized Attack Paths")
        for p in impact.severed_paths[:10]:
            lines.append(f"- `{' -> '.join(p)}`")
        if len(impact.severed_paths) > 10:
            lines.append(f"- *(and {len(impact.severed_paths) - 10} more paths...)*")

    report = "\n".join(lines)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Report saved to {args.out}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
