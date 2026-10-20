#!/usr/bin/env python3
"""
scripts/profile_scenario.py - Computes graph topological complexity and degree metrics.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def profile(scenario_path: Path):
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    in_degree = defaultdict(int)
    out_degree = defaultdict(int)

    for e in edges:
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        out_degree[src] += 1
        in_degree[tgt] += 1

    print("=" * 60)
    print(f"Scenario Topology Profile: {scenario_path.name}")
    print("=" * 60)
    print(f"Total Principals: {len(nodes)}")
    print(f"Total Privilege Transitions: {len(edges)}")
    max_out = max(out_degree.values()) if out_degree else 0
    max_in = max(in_degree.values()) if in_degree else 0
    print(f"Max Out-Degree (Branching Factor): {max_out}")
    print(f"Max In-Degree (Asset Convergence): {max_in}")
    density = (len(edges) / (len(nodes) * (len(nodes) - 1))) if len(nodes) > 1 else 0
    print(f"Graph Density: {density:.4f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Profile scenario complexity")
    parser.add_argument("scenario", type=Path)
    args = parser.parse_args()

    if not args.scenario.is_file():
        print(f"File not found: {args.scenario}")
        sys.exit(1)

    profile(args.scenario)


if __name__ == "__main__":
    main()
