#!/usr/bin/env python3
"""
scripts/temporal_report.py - Generate a temporal evaluation summary report.

Reads a JSONL audit log produced by TemporalAuditLog and outputs a
Markdown summary with verdict distribution, top violated constraints,
and suspicious path listings.

Usage
-----
    python scripts/temporal_report.py audit.jsonl [--output report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_jsonl(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _build_report(entries: list[dict]) -> str:
    total = len(entries)
    if total == 0:
        return "# Temporal Audit Report\n\n_No entries found._\n"

    kind_counter: Counter = Counter(e["verdict_kind"] for e in entries)
    constraint_counter: Counter = Counter(
        e["violated_constraint"]
        for e in entries
        if e.get("violated_constraint")
    )
    path_lengths = [len(e["path_edge_ids"]) for e in entries]
    mean_len = sum(path_lengths) / total if path_lengths else 0

    feasible = kind_counter.get("FEASIBLE", 0)
    infeasible = kind_counter.get("INFEASIBLE", 0)
    unknown = kind_counter.get("UNKNOWN", 0)
    elim_rate = infeasible / total if total else 0

    lines = [
        "# Temporal Evaluation Audit Report",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total paths evaluated | {total} |",
        f"| FEASIBLE | {feasible} ({feasible/total:.1%}) |",
        f"| INFEASIBLE | {infeasible} ({infeasible/total:.1%}) |",
        f"| UNKNOWN | {unknown} ({unknown/total:.1%}) |",
        f"| Elimination rate | {elim_rate:.1%} |",
        f"| Mean path length | {mean_len:.1f} hops |",
        "",
        "## Top Violated Constraints",
        "",
    ]

    if constraint_counter:
        lines.append("| Constraint | Violations |")
        lines.append("|---|---|")
        for cid, count in constraint_counter.most_common():
            lines.append(f"| `{cid}` | {count} |")
    else:
        lines.append("_No constraint violations recorded._")

    lines += [
        "",
        "## Infeasible Paths",
        "",
    ]
    infeasible_entries = [e for e in entries if e["verdict_kind"] == "INFEASIBLE"]
    if infeasible_entries:
        for entry in infeasible_entries[:20]:  # cap at 20 for readability
            path_str = " → ".join(entry["path_edge_ids"])
            cid = entry.get("violated_constraint", "?")
            lines.append(f"- **[{cid}]** `{path_str}`")
            lines.append(f"  - _{entry.get('reason', '')}_")
    else:
        lines.append("_None._")

    lines += ["", f"_Report generated from {total} audit entries._", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate temporal audit report from JSONL.")
    p.add_argument("log_file", type=Path, help="Path to temporal audit JSONL file.")
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Output Markdown file (default: stdout).")
    args = p.parse_args(argv)

    if not args.log_file.exists():
        print(f"ERROR: {args.log_file} not found.", file=sys.stderr)
        return 1

    entries = _load_jsonl(args.log_file)
    report = _build_report(entries)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
