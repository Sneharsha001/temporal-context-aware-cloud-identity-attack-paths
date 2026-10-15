#!/usr/bin/env python3
"""
compare_benchmarks.py - Benchmark comparison and regression detection utility.

Compares two benchmark JSON runs (baseline vs current) and flags any regression
exceeding a user-defined threshold percentage.
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_runs(baseline: dict, candidate: dict, threshold_pct: float) -> tuple[bool, list[str]]:
    regressions: list[str] = []
    lines: list[str] = []

    lines.append(f"{'Benchmark':<25} {'Baseline (ms)':>15} {'Candidate (ms)':>15} {'Diff (%)':>10}")
    lines.append("-" * 70)

    for bench_name, base_stat in baseline.items():
        if bench_name not in candidate:
            lines.append(f"{bench_name:<25} {base_stat.get('median', 0)*1000:>15.2f} {'MISSING':>15}")
            continue

        cand_stat = candidate[bench_name]
        b_med = base_stat.get("median", 0) * 1000
        c_med = cand_stat.get("median", 0) * 1000

        if b_med == 0:
            diff_pct = 0.0
        else:
            diff_pct = ((c_med - b_med) / b_med) * 100.0

        flag = ""
        if diff_pct > threshold_pct:
            flag = " ⚠️ REGRESSION"
            regressions.append(bench_name)

        lines.append(f"{bench_name:<25} {b_med:>15.2f} {c_med:>15.2f} {diff_pct:>9.1f}%{flag}")

    return len(regressions) == 0, lines


def main():
    parser = argparse.ArgumentParser(description="Compare ARF-RT benchmark results")
    parser.add_argument("baseline", type=Path, help="Path to baseline benchmark JSON")
    parser.add_argument("candidate", type=Path, help="Path to candidate benchmark JSON")
    parser.add_argument(
        "--threshold",
        type=float,
        default=15.0,
        help="Allowed regression percentage threshold (default: 15.0%%)",
    )
    args = parser.parse_args()

    base_data = load_json(args.baseline)
    cand_data = load_json(args.candidate)

    passed, report_lines = compare_runs(base_data, cand_data, args.threshold)
    print("\n".join(report_lines))

    if not passed:
        print(f"\n❌ Benchmark regression exceeded {args.threshold}% threshold.")
        sys.exit(1)
    else:
        print(f"\n✅ All benchmarks within acceptable {args.threshold}% range.")
        sys.exit(0)


if __name__ == "__main__":
    main()
