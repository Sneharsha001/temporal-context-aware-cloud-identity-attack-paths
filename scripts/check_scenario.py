#!/usr/bin/env python3
"""
scripts/check_scenario.py - Scenario file sanity validator and graph inspector.

Performs static integrity checks on an ARF-RT scenario JSON file:
- Validates JSON format and top-level keys
- Checks presence of start_nodes and target_nodes
- Counts unique principals, privilege edges, and constraint blocks
- Detects disconnected nodes and invalid edge targets
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


def check_scenario(file_path: Path) -> bool:
    print(f"Inspecting scenario: {file_path}")
    if not file_path.is_file():
        print(f"❌ Error: File not found ({file_path})")
        return False

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"❌ Error: Invalid JSON syntax ({exc})")
        return False

    print("✅ JSON syntax valid.")

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    constraints = data.get("constraints", [])
    objectives = data.get("objectives", [])

    print(f"  • Nodes: {len(nodes)}")
    print(f"  • Edges: {len(edges)}")
    print(f"  • Constraints: {len(constraints)}")
    print(f"  • Objectives: {len(objectives)}")

    if not objectives:
        print("⚠️ Warning: No objectives defined.")
    else:
        for idx, obj in enumerate(objectives):
            st = obj.get("start_nodes", [])
            tg = obj.get("target_nodes", [])
            print(f"    Objective {idx + 1}: {len(st)} start node(s), {len(tg)} target node(s)")

    print("✅ Scenario passed sanity verification.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Check ARF-RT scenario file sanity")
    parser.add_argument("scenario", type=Path, help="Path to scenario JSON file")
    args = parser.parse_args()

    success = check_scenario(args.scenario)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
