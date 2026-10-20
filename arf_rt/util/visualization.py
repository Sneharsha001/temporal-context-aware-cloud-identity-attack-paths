"""
arf_rt/util/visualization.py - Graph serialization for Graphviz DOT and Cytoscape.js.

Formats ARF-RT scenarios, attack paths, and belief states into visual graph representations.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence


def export_to_dot(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    graph_name: str = "ARF_RT_AttackPath",
) -> str:
    """Generate Graphviz DOT markup string representing an identity privilege graph."""
    lines = [f"digraph {graph_name} {{", '  rankdir="LR";', "  node [shape=box, style=rounded];"]

    for n in nodes:
        node_id = n.get("provider_id", "unknown")
        node_type = n.get("node_type", "Node")
        short_label = node_id.split("/")[-1] if "/" in node_id else node_id.split(":")[-1]
        lines.append(f'  "{node_id}" [label="{node_type}\\n{short_label}"];')

    for e in edges:
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        action = e.get("action", "")
        lines.append(f'  "{src}" -> "{tgt}" [label="{action}"];')

    lines.append("}")
    return "\n".join(lines)


def export_to_cytoscape(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Format nodes and edges into a standard Cytoscape.js elements dictionary."""
    cy_nodes = []
    for n in nodes:
        nid = n.get("provider_id", "")
        cy_nodes.append({"data": {"id": nid, "label": n.get("node_type", "Node")}})

    cy_edges = []
    for idx, e in enumerate(edges):
        cy_edges.append(
            {
                "data": {
                    "id": e.get("edge_id", f"e_{idx}"),
                    "source": e.get("source_node", ""),
                    "target": e.get("target_node", ""),
                    "action": e.get("action", ""),
                }
            }
        )

    return {"nodes": cy_nodes, "edges": cy_edges}
