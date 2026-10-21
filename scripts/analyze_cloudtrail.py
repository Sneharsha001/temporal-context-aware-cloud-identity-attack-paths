#!/usr/bin/env python3
"""
scripts/analyze_cloudtrail.py - CLI tool to analyze CloudTrail logs for temporal anomalies.

Reads a CloudTrail JSON export, extracts TemporalHints for AssumeRole events,
and reports suspicious timing patterns using the window analyzer.

Usage
-----
    python scripts/analyze_cloudtrail.py cloudtrail_events.json [--strict] [--json]

Options
-------
--strict    Use TemporalConfig.strict() (fails UNKNOWN, tight thresholds).
--json      Output results as JSON instead of human-readable text.
--path      Comma-separated ordered list of edge IDs to evaluate specifically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure arf_rt is importable when run from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.window_analyzer import (
    detect_burst,
    detect_cross_account_reuse,
    detect_impossible_concurrency,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Analyze CloudTrail logs for temporal attack path anomalies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("log_file", type=Path, help="Path to CloudTrail JSON export.")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Use strict temporal config (UNKNOWN paths are blocked).",
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output results as JSON.",
    )
    p.add_argument(
        "--path",
        dest="edge_path",
        default="",
        help="Comma-separated ordered edge IDs to evaluate (optional).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.log_file.exists():
        print(f"ERROR: File not found: {args.log_file}", file=sys.stderr)
        return 1

    with open(args.log_file, encoding="utf-8") as f:
        raw = json.load(f)

    # CloudTrail exports may wrap events in a "Records" key
    if isinstance(raw, dict):
        events = raw.get("Records", raw.get("events", [raw]))
    else:
        events = raw

    print(f"Loaded {len(events)} CloudTrail events from {args.log_file}")

    hints = extract_hints_from_log(events)
    print(f"Extracted {len(hints)} unique privilege edges.\n")

    cfg = TemporalConfig.strict() if args.strict else TemporalConfig()
    ev = TemporalEvaluator(config=cfg)

    results: dict[str, object] = {}

    # --- Window analysis on the full path (all observed edges in temporal order) ---
    all_hints = sorted(
        hints.values(),
        key=lambda h: h.earliest_observed or __import__("datetime").datetime.min,
    )

    concurrency_result = detect_impossible_concurrency(all_hints)
    burst_result = detect_burst(all_hints)
    reuse_result = detect_cross_account_reuse(all_hints)

    results["impossible_concurrency"] = {
        "suspicious": concurrency_result.suspicious,
        "reason": concurrency_result.reason,
        "affected": list(concurrency_result.affected_edge_ids),
    }
    results["burst_detection"] = {
        "suspicious": burst_result.suspicious,
        "reason": burst_result.reason,
        "affected": list(burst_result.affected_edge_ids),
    }
    results["cross_account_reuse"] = {
        "suspicious": reuse_result.suspicious,
        "reason": reuse_result.reason,
        "affected": list(reuse_result.affected_edge_ids),
    }

    # --- Optional specific path evaluation ---
    if args.edge_path:
        edge_ids = [e.strip() for e in args.edge_path.split(",") if e.strip()]
        verdict = ev.evaluate(edge_ids, hints)
        results["path_evaluation"] = {
            "edge_ids": edge_ids,
            "verdict": verdict.kind.name,
            "violated_constraint": verdict.violated_constraint,
            "reason": verdict.reason,
        }

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        _print_human(results)

    any_suspicious = any(
        v.get("suspicious", False)
        for v in results.values()
        if isinstance(v, dict) and "suspicious" in v
    )
    return 1 if any_suspicious else 0


def _print_human(results: dict) -> None:
    icons = {True: "⚠️ SUSPICIOUS", False: "✅ CLEAN"}
    for check, data in results.items():
        if "suspicious" in data:
            print(f"{icons[data['suspicious']]}  [{check}]")
            print(f"  {data['reason']}")
            if data.get("affected"):
                print(f"  Affected edges: {', '.join(data['affected'])}")
        else:
            print(f"\n[{check}]")
            for k, v in data.items():
                print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    sys.exit(main())
