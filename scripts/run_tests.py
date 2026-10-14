#!/usr/bin/env python3
"""
run_tests.py - Unified test runner for ARF-RT project.

Runs unit, integration, stress, and research tests with configurable
verbosity and filtering. Produces a structured summary report.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="ARF-RT unified test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_tests.py --suite unit
  python scripts/run_tests.py --suite integration --verbose
  python scripts/run_tests.py --suite all --fail-fast
""",
    )
    parser.add_argument(
        "--suite",
        choices=["unit", "integration", "stress", "research", "all"],
        default="all",
        help="Test suite to run (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Increase output verbosity"
    )
    parser.add_argument(
        "--fail-fast", "-x", action="store_true", help="Stop on first failure"
    )
    parser.add_argument(
        "--coverage", action="store_true", help="Generate coverage report"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/test_reports"),
        help="Directory to write test reports (default: artifacts/test_reports)",
    )
    return parser.parse_args()


SUITE_MAP = {
    "unit": "tests/unit",
    "integration": "tests/integration",
    "stress": "tests/stress",
    "research": "tests/research",
}


def build_pytest_cmd(suite: str, args) -> list[str]:
    cmd = [sys.executable, "-m", "pytest"]
    if suite == "all":
        cmd.append("tests/")
    else:
        cmd.append(SUITE_MAP[suite])

    if args.verbose:
        cmd.append("-v")
    if args.fail_fast:
        cmd.append("-x")
    if args.coverage:
        cmd += ["--cov=arf_rt", "--cov-report=term-missing"]
        args.output_dir.mkdir(parents=True, exist_ok=True)
        cmd += [f"--cov-report=html:{args.output_dir}/coverage_html"]

    cmd += ["--tb=short", "-q" if not args.verbose else ""]
    return [c for c in cmd if c]


def run_suite(suite: str, args) -> dict:
    print(f"\n{'='*60}")
    print(f"  Running suite: {suite.upper()}")
    print(f"{'='*60}")

    cmd = build_pytest_cmd(suite, args)
    start = time.perf_counter()
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    elapsed = time.perf_counter() - start

    return {
        "suite": suite,
        "returncode": result.returncode,
        "elapsed": elapsed,
        "passed": result.returncode == 0,
    }


def print_summary(results: list[dict]):
    print(f"\n{'='*60}")
    print("  TEST SUMMARY")
    print(f"{'='*60}")
    total_time = sum(r["elapsed"] for r in results)
    passed = sum(1 for r in results if r["passed"])
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"  {status}  {r['suite']:<20} {r['elapsed']:.2f}s")
    print(f"{'='*60}")
    print(f"  Suites: {passed}/{len(results)} passed  |  Total time: {total_time:.2f}s")
    print(f"{'='*60}\n")
    return passed == len(results)


def main():
    args = parse_args()
    suites = list(SUITE_MAP.keys()) if args.suite == "all" else [args.suite]

    results = []
    for suite in suites:
        res = run_suite(suite, args)
        results.append(res)
        if args.fail_fast and not res["passed"]:
            print(f"\n[fail-fast] Stopping after failure in suite: {suite}")
            break

    success = print_summary(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
