#!/usr/bin/env python3
"""
scripts/policy_diff.py - Compares constraints and policy rules between two scenario files.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def diff_scenarios(path_a: Path, path_b: Path):
    a_data = json.loads(path_a.read_text(encoding="utf-8"))
    b_data = json.loads(path_b.read_text(encoding="utf-8"))

    a_edges = {e.get("edge_id") for e in a_data.get("edges", [])}
    b_edges = {e.get("edge_id") for e in b_data.get("edges", [])}

    a_constraints = {c.get("constraint_id") for c in a_data.get("constraints", [])}
    b_constraints = {c.get("constraint_id") for c in b_data.get("constraints", [])}

    print("=" * 60)
    print(f"Scenario Diff: {path_a.name} vs {path_b.name}")
    print("=" * 60)
    print(f"Edges in A: {len(a_edges)} | Edges in B: {len(b_edges)}")
    print(f"  Added Edges in B:   {len(b_edges - a_edges)}")
    print(f"  Removed Edges in B: {len(a_edges - b_edges)}")
    print(f"Constraints in A: {len(a_constraints)} | Constraints in B: {len(b_constraints)}")
    print(f"  Added Constraints in B:   {len(b_constraints - a_constraints)}")
    print(f"  Removed Constraints in B: {len(a_constraints - b_constraints)}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Diff policies between two scenario files")
    parser.add_argument("scenario_a", type=Path)
    parser.add_argument("scenario_b", type=Path)
    args = parser.parse_args()

    diff_scenarios(args.scenario_a, args.scenario_b)


if __name__ == "__main__":
    main()
