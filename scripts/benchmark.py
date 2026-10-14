#!/usr/bin/env python3
"""
benchmark.py - Performance benchmarking utility for ARF-RT core operations.

Measures throughput and latency of key pipeline stages so regressions
can be caught before they reach production.
"""

import time
import statistics
import argparse
import json
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Benchmark harness
# ---------------------------------------------------------------------------

def _timeit(fn: Callable, iterations: int = 100) -> dict:
    """Run *fn* *iterations* times and return timing statistics (seconds)."""
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)

    return {
        "min": min(samples),
        "max": max(samples),
        "mean": statistics.mean(samples),
        "median": statistics.median(samples),
        "stdev": statistics.stdev(samples) if len(samples) > 1 else 0.0,
        "p95": sorted(samples)[int(len(samples) * 0.95)],
        "p99": sorted(samples)[int(len(samples) * 0.99)],
        "iterations": iterations,
    }


# ---------------------------------------------------------------------------
# Micro-benchmarks
# ---------------------------------------------------------------------------

def bench_import():
    """Measure cold-import time of the arf_rt package."""
    import importlib
    import sys

    def _do():
        sys.modules.pop("arf_rt", None)
        importlib.import_module("arf_rt")

    return _timeit(_do, iterations=10)


def bench_config_load():
    """Measure config loading from disk."""
    from arf_rt.config import ARFConfig

    def _do():
        ARFConfig()

    return _timeit(_do, iterations=200)


def bench_path_resolution():
    """Measure engine path resolution latency."""
    try:
        from arf_rt.engine.paths import PathResolver
        resolver = PathResolver()

        def _do():
            resolver.resolve("test.node", "test.resource")

        return _timeit(_do, iterations=500)
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Registry & runner
# ---------------------------------------------------------------------------

BENCHMARKS = {
    "import": bench_import,
    "config_load": bench_config_load,
    "path_resolution": bench_path_resolution,
}


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.3f} ms"


def run_benchmarks(selected: list[str], output: Path | None = None):
    results = {}
    for name in selected:
        fn = BENCHMARKS.get(name)
        if fn is None:
            print(f"[WARN] Unknown benchmark: {name}")
            continue
        print(f"  Running: {name} ...", end=" ", flush=True)
        stats = fn()
        results[name] = stats
        if "error" in stats:
            print(f"ERROR — {stats['error']}")
        else:
            print(f"median={_fmt_ms(stats['median'])}  p99={_fmt_ms(stats['p99'])}")

    print()
    # Tabular summary
    print(f"{'Benchmark':<25} {'min':>10} {'median':>10} {'p95':>10} {'p99':>10}")
    print("-" * 65)
    for name, s in results.items():
        if "error" in s:
            print(f"{name:<25} {'ERROR':>10}")
        else:
            print(
                f"{name:<25} {_fmt_ms(s['min']):>10} {_fmt_ms(s['median']):>10}"
                f" {_fmt_ms(s['p95']):>10} {_fmt_ms(s['p99']):>10}"
            )

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2))
        print(f"\nResults written to {output}")

    return results


def main():
    parser = argparse.ArgumentParser(description="ARF-RT performance benchmarks")
    parser.add_argument(
        "benchmarks",
        nargs="*",
        default=list(BENCHMARKS.keys()),
        help=f"Benchmarks to run (default: all). Choices: {list(BENCHMARKS.keys())}",
    )
    parser.add_argument("--output", type=Path, help="Write JSON results to this file")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print("  ARF-RT Performance Benchmarks")
    print(f"{'='*65}\n")

    run_benchmarks(args.benchmarks, args.output)


if __name__ == "__main__":
    main()
