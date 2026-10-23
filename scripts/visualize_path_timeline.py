#!/usr/bin/env python3
"""
scripts/visualize_path_timeline.py - CLI tool to visualize credential lifecycle on an attack path.

Outputs ASCII Gantt charts and chronological event tables for incident response.

Usage::

    python scripts/visualize_path_timeline.py --path edge1,edge2,edge3 --hints hints.json
    python scripts/visualize_path_timeline.py --path edge1,edge2 --hints hints.json --chart --table
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.timeline import CredentialTimelineBuilder


def _load_hints(hints_path: Path) -> dict[str, TemporalHint]:
    with open(hints_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {eid: TemporalHint.from_dict(h) for eid, h in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visualize credential lifecycle timeline for a cloud identity attack path."
    )
    parser.add_argument(
        "--path",
        type=str,
        required=True,
        help="Comma-separated list of edge IDs representing the attack path.",
    )
    parser.add_argument(
        "--hints",
        type=Path,
        required=True,
        help="Path to JSON file containing TemporalHints mapping.",
    )
    parser.add_argument(
        "--chart",
        action="store_true",
        default=True,
        help="Display ASCII Gantt chart of credential validity windows.",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="Display chronological Markdown milestone table.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Save output to a Markdown file.",
    )

    args = parser.parse_args()

    if not args.hints.exists():
        print(f"Error: Hints file '{args.hints}' does not exist.", file=sys.stderr)
        return 1

    edge_ids = [e.strip() for e in args.path.split(",") if e.strip()]
    if not edge_ids:
        print("Error: Path must contain at least one valid edge ID.", file=sys.stderr)
        return 1

    hints = _load_hints(args.hints)
    builder = CredentialTimelineBuilder(edge_ids, hints)

    output_lines: list[str] = [
        f"# Attack Path Timeline: {' -> '.join(edge_ids)}",
        "",
    ]

    if args.chart:
        output_lines.extend([
            "### Credential Validity Gantt Chart",
            "```text",
            builder.generate_ascii_gantt(width=50),
            "```",
            "",
        ])

    if args.table:
        output_lines.extend([
            "### Chronological Event Log",
            builder.to_markdown_table(),
            "",
        ])

    rendered = "\n".join(output_lines)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"Saved timeline visualization to {args.out}")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    sys.exit(main())
