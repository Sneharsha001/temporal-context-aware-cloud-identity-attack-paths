#!/usr/bin/env python3
"""
validate_fixtures.py - Validates all JSON/YAML fixture files in tests/golden.

Ensures every fixture:
  1. Is valid JSON or YAML
  2. Contains required top-level keys
  3. Has non-empty 'expected' values
  4. Passes a schema sanity check

Usage:
  python scripts/validate_fixtures.py
  python scripts/validate_fixtures.py --strict
  python scripts/validate_fixtures.py --dir tests/golden
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Required keys every fixture must contain
REQUIRED_KEYS = {"id", "description", "input", "expected"}


def _load_file(path: Path) -> Any:
    """Load JSON or YAML fixture file."""
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix == ".json":
        return json.loads(text)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except ImportError:
            raise RuntimeError(
                f"PyYAML not installed; cannot parse {path}. "
                "Run: pip install pyyaml"
            )
    else:
        raise ValueError(f"Unsupported fixture format: {suffix}")


def _validate_fixture(data: Any, path: Path, strict: bool) -> list[str]:
    """Return list of validation errors for one fixture."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"Root must be a dict, got {type(data).__name__}"]

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")

    if "expected" in data:
        if data["expected"] is None:
            errors.append("'expected' must not be None")
        if isinstance(data["expected"], (list, dict, str)) and not data["expected"]:
            errors.append("'expected' must not be empty")

    if "id" in data and not isinstance(data["id"], str):
        errors.append(f"'id' must be a string, got {type(data['id']).__name__}")

    if strict:
        if "tags" not in data:
            errors.append("[strict] Missing 'tags' field")
        if "version" not in data:
            errors.append("[strict] Missing 'version' field")

    return errors


def validate_directory(fixture_dir: Path, strict: bool) -> dict:
    """Validate all fixture files in *fixture_dir*."""
    fixture_files = sorted(
        list(fixture_dir.rglob("*.json"))
        + list(fixture_dir.rglob("*.yaml"))
        + list(fixture_dir.rglob("*.yml"))
    )

    if not fixture_files:
        print(f"  [WARN] No fixture files found in {fixture_dir}")
        return {"total": 0, "passed": 0, "failed": 0, "errors": {}}

    results = {"total": len(fixture_files), "passed": 0, "failed": 0, "errors": {}}

    for fp in fixture_files:
        rel = fp.relative_to(ROOT)
        try:
            data = _load_file(fp)
            errors = _validate_fixture(data, fp, strict)
        except Exception as exc:
            errors = [f"Parse error: {exc}"]

        if errors:
            results["failed"] += 1
            results["errors"][str(rel)] = errors
            print(f"  ❌  {rel}")
            for e in errors:
                print(f"       • {e}")
        else:
            results["passed"] += 1
            print(f"  ✅  {rel}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate ARF-RT fixture files")
    parser.add_argument(
        "--dir",
        type=Path,
        default=ROOT / "tests" / "golden",
        help="Directory containing fixture files (default: tests/golden)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict schema (requires 'tags' and 'version' fields)",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Fixture Validator  {'[STRICT]' if args.strict else ''}")
    print(f"  Directory: {args.dir.relative_to(ROOT)}")
    print(f"{'='*60}\n")

    results = validate_directory(args.dir, args.strict)

    print(f"\n{'='*60}")
    print(
        f"  Total: {results['total']}  "
        f"Passed: {results['passed']}  "
        f"Failed: {results['failed']}"
    )
    print(f"{'='*60}\n")

    if results["failed"] > 0:
        print(f"  ❌ {results['failed']} fixture(s) failed validation.\n")
        sys.exit(1)
    else:
        print("  ✅ All fixtures valid.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
