"""
arf_rt/util/objective_helpers.py - Objective schema validation and conversion utilities.

Helpers for formatting start/target nodes, computing path constraints, and validating
reachability objectives against scenario specifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def validate_node_ref(node: Dict[str, Any]) -> bool:
    """Validate that a node dictionary contains required identification keys."""
    required = {"provider", "node_type", "provider_id"}
    return required.issubset(node.keys()) and bool(node["provider_id"])


def build_reachability_objective(
    start_arn: str,
    target_arn: str,
    max_depth: int = 6,
    k: int = 5,
    provider: str = "aws",
    start_type: str = "IAMUser",
    target_type: str = "IAMRole",
) -> Dict[str, Any]:
    """Construct a canonical REACHABILITY objective dictionary."""
    return {
        "objective_type": "REACHABILITY",
        "start_nodes": [
            {
                "provider": provider,
                "node_type": start_type,
                "provider_id": start_arn,
                "region": "-",
            }
        ],
        "target_nodes": [
            {
                "provider": provider,
                "node_type": target_type,
                "provider_id": target_arn,
                "region": "-",
            }
        ],
        "max_depth": max_depth,
        "k": k,
    }
