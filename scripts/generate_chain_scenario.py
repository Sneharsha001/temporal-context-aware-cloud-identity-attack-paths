#!/usr/bin/env python3
"""
scripts/generate_chain_scenario.py - Generates linear and branching attack chains of length N.
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


def build_chain(length: int = 5) -> dict:
    nodes = []
    edges = []

    for i in range(length):
        role_type = "IAMUser" if i == 0 else "IAMRole"
        arn = f"arn:aws:iam::111111111111:{role_type.lower()}/node_{i}"
        nodes.append({"provider": "aws", "node_type": role_type, "provider_id": arn, "region": "-"})

    for i in range(length - 1):
        edges.append(
            {
                "edge_id": f"edge_{i}_to_{i+1}",
                "source_node": nodes[i]["provider_id"],
                "target_node": nodes[i + 1]["provider_id"],
                "action": "sts:AssumeRole",
            }
        )

    objectives = [
        {
            "objective_type": "REACHABILITY",
            "start_nodes": [nodes[0]],
            "target_nodes": [nodes[-1]],
            "max_depth": length + 2,
            "k": 5,
        }
    ]

    return {
        "scenario_name": f"linear_chain_{length}",
        "nodes": nodes,
        "edges": edges,
        "constraints": [],
        "objectives": objectives,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate linear attack chain scenario")
    parser.add_argument("--length", "-l", type=int, default=6, help="Chain length")
    parser.add_argument("--output", "-o", type=Path, default=Path("artifacts/scenarios/chain_scenario.json"))
    args = parser.parse_args()

    scen = build_chain(args.length)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scen, indent=2), encoding="utf-8")
    print(f"Generated {args.length}-hop linear chain scenario at: {args.output}")


if __name__ == "__main__":
    main()
