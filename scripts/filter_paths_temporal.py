#!/usr/bin/env python3
"""
scripts/filter_paths_temporal.py - Batch temporal path filtering CLI tool.

Filters candidate attack paths using temporal feasibility constraints (causality,
validity, expiration, staleness, and concurrency).

Usage::

    python scripts/filter_paths_temporal.py --paths paths.json --hints hints.json
    python scripts/filter_paths_temporal.py --paths paths.json --cloudtrail events.json --summary
    python scripts/filter_paths_temporal.py --paths paths.json --hints hints.json --out-csv results.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.export import (
    export_metrics_to_csv,
    generate_summary_table,
)
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.path_filter import TemporalPathFilter


def _load_paths(path: Path) -> list[list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and all(isinstance(p, list) for p in data):
        return data
    raise ValueError("Paths file must contain a JSON array of string arrays (paths).")


def _load_hints(hints_path: Path | None, ct_path: Path | None) -> dict[str, TemporalHint]:
    hints: dict[str, TemporalHint] = {}
    if hints_path and hints_path.exists():
        with open(hints_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for eid, h_dict in raw.items():
            hints[eid] = TemporalHint.from_dict(h_dict)
    elif ct_path and ct_path.exists():
        with open(ct_path, "r", encoding="utf-8") as f:
            ct_data = json.load(f)
        events = ct_data.get("Records", ct_data if isinstance(ct_data, list) else [])
        hints = extract_hints_from_log(events)
    return hints


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter candidate attack paths using temporal feasibility constraints."
    )
    parser.add_argument(
        "--paths",
        type=Path,
        required=True,
        help="Path to JSON file containing list of candidate paths (array of edge ID arrays).",
    )
    parser.add_argument(
        "--hints",
        type=Path,
        default=None,
        help="Path to JSON file with pre-computed TemporalHints dictionary.",
    )
    parser.add_argument(
        "--cloudtrail",
        type=Path,
        default=None,
        help="Path to CloudTrail export JSON containing Records.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict configuration (fail closed on missing timestamps).",
    )
    parser.add_argument(
        "--permissive",
        action="store_true",
        help="Use permissive configuration (fail open on missing timestamps).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print Markdown summary table of filtering metrics to stdout.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Save filtered passing paths to this JSON file.",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Export filtering metrics summary to this CSV file.",
    )

    args = parser.parse_args()

    if not args.paths.exists():
        print(f"Error: Paths file '{args.paths}' does not exist.", file=sys.stderr)
        return 1

    if args.strict:
        config = TemporalConfig.strict()
    elif args.permissive:
        config = TemporalConfig.permissive()
    else:
        config = TemporalConfig()

    paths = _load_paths(args.paths)
    hints = _load_hints(args.hints, args.cloudtrail)

    flt = TemporalPathFilter(config=config, run_window_checks=True)
    results = flt.filter(paths, hints)

    metrics = TemporalMetrics()
    for r in results:
        plen = len(r.edge_ids)
        if r.verdict_kind == "FEASIBLE":
            metrics.record_feasible(plen)
        elif r.verdict_kind == "INFEASIBLE":
            metrics.record_infeasible("temporal_filter", plen)
        else:
            metrics.record_unknown(plen)

    passing_paths = [r.edge_ids for r in results if r.passed]

    if args.summary:
        print("\n### Temporal Path Feasibility Summary\n")
        print(generate_summary_table(metrics))
        print(f"\nPassing paths: {len(passing_paths)} / {len(paths)}\n")

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(passing_paths, f, indent=2)
        print(f"Saved {len(passing_paths)} passing paths to {args.out_json}")

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        export_metrics_to_csv(metrics, args.out_csv)
        print(f"Saved filtering metrics to {args.out_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
