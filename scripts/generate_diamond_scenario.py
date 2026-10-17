#!/usr/bin/env python3
"""
scripts/generate_diamond_scenario.py - Generates synthetic diamond topology scenarios.

Produces canonical multi-account scenario fixtures exhibiting diamond collapse
characteristics for testing correlation algorithms and EIG probe selection.
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


def build_diamond_scenario(accounts: int = 4) -> dict:
    nodes = [
        {"provider": "aws", "node_type": "IAMUser", "provider_id": "arn:aws:iam::111111111111:user/attacker", "region": "-"},
        {"provider": "aws", "node_type": "IAMRole", "provider_id": "arn:aws:iam::222222222222:role/intermediate_b", "region": "-"},
        {"provider": "aws", "node_type": "IAMRole", "provider_id": "arn:aws:iam::333333333333:role/intermediate_c", "region": "-"},
        {"provider": "aws", "node_type": "IAMRole", "provider_id": "arn:aws:iam::444444444444:role/target_admin", "region": "-"},
    ]

    edges = [
        {"edge_id": "edge_e1", "source_node": nodes[0]["provider_id"], "target_node": nodes[1]["provider_id"], "action": "sts:AssumeRole"},
        {"edge_id": "edge_e2", "source_node": nodes[0]["provider_id"], "target_node": nodes[2]["provider_id"], "action": "sts:AssumeRole"},
        {"edge_id": "edge_e3", "source_node": nodes[1]["provider_id"], "target_node": nodes[3]["provider_id"], "action": "sts:AssumeRole"},
        {"edge_id": "edge_e4", "source_node": nodes[2]["provider_id"], "target_node": nodes[3]["provider_id"], "action": "sts:AssumeRole"},
    ]

    constraints = [
        {
            "constraint_id": "scp_shared_deny",
            "constraint_type": "SCP",
            "target_edges": ["edge_e1", "edge_e2", "edge_e3", "edge_e4"],
            "parameters": {"effect": "Deny", "condition": "aws:SourceIp"},
        }
    ]

    objectives = [
        {
            "objective_type": "REACHABILITY",
            "start_nodes": [nodes[0]],
            "target_nodes": [nodes[3]],
            "max_depth": 4,
            "k": 5,
        }
    ]

    return {
        "scenario_name": f"synthetic_diamond_{accounts}acc",
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "objectives": objectives,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic diamond scenario")
    parser.add_argument("--output", type=Path, default=Path("artifacts/scenarios/synthetic_diamond.json"))
    args = parser.parse_args()

    scenario = build_diamond_scenario()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    print(f"Generated diamond scenario at: {args.output}")


if __name__ == "__main__":
    main()
