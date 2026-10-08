#!/usr/bin/env python3
"""Generate and benchmark a large synthetic ARF-RT fixture.

This script is intentionally conservative: it records measured runtime on the
current machine rather than asserting the camera-ready 250k-edge numbers. Use it
as a rebenchmark tool. If the measured values do not match the paper claim, do
not force the claim; report the measured values or omit the 250k number.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_fixture import generate_scenario  # noqa: E402


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def run_cmd(cmd: list[str], cwd: Path, timeout_s: int) -> dict[str, object]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            check=False,
        )
        elapsed = time.perf_counter() - start
        return {
            "command": cmd,
            "returncode": proc.returncode,
            "elapsed_s": elapsed,
            "stdout_head": proc.stdout[:4000],
            "stderr_head": proc.stderr[:4000],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        return {
            "command": cmd,
            "returncode": None,
            "elapsed_s": elapsed,
            "stdout_head": (exc.stdout or "")[:4000] if isinstance(exc.stdout, str) else "",
            "stderr_head": (exc.stderr or "")[:4000] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges", type=int, default=250_000)
    parser.add_argument("--correlation", choices=["none", "medium", "heavy"], default="medium")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", default="artifacts/bench/scenario_250k_medium.json")
    parser.add_argument("--output", default="artifacts/bench/benchmark_250k_runtime.json")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--timeout-s", type=int, default=900)
    args = parser.parse_args()

    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = ROOT / scenario_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    result: dict[str, object] = {
        "note": "Measured benchmark; hardware/CPU/Python dependent. Do not use as proof unless run on the target release environment.",
        "target_edges": args.edges,
        "correlation": args.correlation,
        "seed": args.seed,
        "scenario": str(scenario_path),
    }

    if not args.skip_generate:
        t0 = time.perf_counter()
        scenario = generate_scenario(args.edges, args.correlation, seed=args.seed)
        write_json(scenario_path, scenario)
        result["generation"] = {
            "elapsed_s": time.perf_counter() - t0,
            "actual_nodes": len(scenario.get("nodes", [])),
            "actual_edges": len(scenario.get("edges", [])),
            "constraints": len(scenario.get("constraints", [])),
            "observations": len(scenario.get("observations", [])),
            "file_size_mb": scenario_path.stat().st_size / (1024 * 1024),
        }

    py = sys.executable
    result["analyze"] = run_cmd([py, "-m", "arf_rt.cli", "analyze", str(scenario_path), "--format", "json"], ROOT, args.timeout_s)
    result["plan"] = run_cmd([py, "-m", "arf_rt.cli", "plan", str(scenario_path)], ROOT, args.timeout_s)

    # Convenience paper-comparison fields. These are not assertions.
    analyze_s = float(result["analyze"]["elapsed_s"]) if isinstance(result.get("analyze"), dict) else None
    plan_s = float(result["plan"]["elapsed_s"]) if isinstance(result.get("plan"), dict) else None
    result["paper_claim_comparison"] = {
        "paper_analysis_claim_ms": 40,
        "paper_planner_claim_s": 2,
        "measured_analysis_ms": analyze_s * 1000 if analyze_s is not None else None,
        "measured_planner_s": plan_s,
        "matches_claim": (analyze_s is not None and plan_s is not None and analyze_s <= 0.040 and plan_s <= 2.0),
    }

    write_json(output_path, result)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
