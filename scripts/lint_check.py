#!/usr/bin/env python3
"""
lint_check.py - Static analysis and code quality gate for ARF-RT.

Runs ruff (linting), mypy (type checking), and bandit (security scan)
in sequence and exits non-zero if any check fails.
"""

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "arf_rt"
TESTS_DIR = ROOT / "tests"


@dataclass
class CheckResult:
    name: str
    passed: bool
    output: str = ""
    returncode: int = 0


@dataclass
class QualityReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, result: CheckResult):
        self.checks.append(result)

    def print_summary(self):
        print(f"\n{'='*60}")
        print("  CODE QUALITY GATE — SUMMARY")
        print(f"{'='*60}")
        for c in self.checks:
            icon = "✅" if c.passed else "❌"
            print(f"  {icon}  {c.name}")
        verdict = "PASSED" if self.all_passed else "FAILED"
        color = "\033[92m" if self.all_passed else "\033[91m"
        reset = "\033[0m"
        print(f"\n  Gate verdict: {color}{verdict}{reset}")
        print(f"{'='*60}\n")


def _run(cmd: list[str], label: str) -> CheckResult:
    print(f"\n→ {label}")
    print(f"  cmd: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=ROOT
    )
    combined = (result.stdout + result.stderr).strip()
    passed = result.returncode == 0
    if combined:
        # Indent output for readability
        indented = "\n".join("    " + line for line in combined.splitlines())
        print(indented)
    if passed:
        print(f"  ✅ {label} passed")
    else:
        print(f"  ❌ {label} failed (exit {result.returncode})")
    return CheckResult(
        name=label,
        passed=passed,
        output=combined,
        returncode=result.returncode,
    )


def check_ruff() -> CheckResult:
    return _run(
        [sys.executable, "-m", "ruff", "check", str(SOURCE_DIR), str(TESTS_DIR)],
        "ruff (lint)",
    )


def check_ruff_format() -> CheckResult:
    return _run(
        [sys.executable, "-m", "ruff", "format", "--check",
         str(SOURCE_DIR), str(TESTS_DIR)],
        "ruff (format)",
    )


def check_mypy() -> CheckResult:
    return _run(
        [sys.executable, "-m", "mypy", str(SOURCE_DIR),
         "--ignore-missing-imports", "--no-error-summary"],
        "mypy (type check)",
    )


def check_bandit() -> CheckResult:
    return _run(
        [sys.executable, "-m", "bandit", "-r", str(SOURCE_DIR),
         "-ll", "-q"],
        "bandit (security)",
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ARF-RT code quality gate")
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=["ruff", "ruff-format", "mypy", "bandit", "all"],
        default=["all"],
        help="Which checks to run (default: all)",
    )
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="Stop after first failing check"
    )
    args = parser.parse_args()

    selected = args.checks
    if "all" in selected:
        selected = ["ruff", "ruff-format", "mypy", "bandit"]

    check_map = {
        "ruff": check_ruff,
        "ruff-format": check_ruff_format,
        "mypy": check_mypy,
        "bandit": check_bandit,
    }

    report = QualityReport()
    print(f"\n{'='*60}")
    print("  ARF-RT Code Quality Gate")
    print(f"{'='*60}")

    for name in selected:
        result = check_map[name]()
        report.add(result)
        if args.fail_fast and not result.passed:
            print(f"\n[fail-fast] Stopping after: {name}")
            break

    report.print_summary()
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
