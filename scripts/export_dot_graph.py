#!/usr/bin/env python3
"""
scripts/export_dot_graph.py - Exports scenario graph topology into Graphviz DOT format.
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

from arf_rt.util.visualization import export_to_dot


def main():
    parser = argparse.ArgumentParser(description="Export scenario to DOT graph")
    parser.add_argument("scenario", type=Path, help="Input scenario JSON")
    parser.add_argument("--output", "-o", type=Path, help="Output DOT file path")
    args = parser.parse_args()

    if not args.scenario.is_file():
        print(f"Error: Scenario file '{args.scenario}' not found.")
        sys.exit(1)

    data = json.loads(args.scenario.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    dot_str = export_to_dot(nodes, edges)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(dot_str, encoding="utf-8")
        print(f"DOT graph exported to: {args.output}")
    else:
        print(dot_str)


if __name__ == "__main__":
    main()
