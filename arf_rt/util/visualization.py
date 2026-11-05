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


def export_to_mermaid(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    graph_name: str = "ARF-RT Attack Path",
) -> str:
    """Generate Mermaid diagram markup for attack path visualization.

    Args:
        nodes: Sequence of node dictionaries.
        edges: Sequence of edge dictionaries.
        graph_name: Title for the diagram.

    Returns:
        Mermaid diagram as string.
    """
    lines = [f"graph LR", f"    title[{graph_name}]", "    style title fill:#f9f,stroke:#333"]

    for n in nodes:
        node_id = n.get("provider_id", "unknown")
        node_type = n.get("node_type", "Node")
        short_label = node_id.split("/")[-1] if "/" in node_id else node_id.split(":")[-1]
        # Sanitize for Mermaid
        safe_id = node_id.replace(":", "_").replace("/", "_").replace("-", "_")
        lines.append(f'    {safe_id}["{node_type}: {short_label}"]')

    for e in edges:
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        action = e.get("action", "")
        safe_src = src.replace(":", "_").replace("/", "_").replace("-", "_")
        safe_tgt = tgt.replace(":", "_").replace("/", "_").replace("-", "_")
        lines.append(f'    {safe_src} -->|{action}| {safe_tgt}')

    return "\n".join(lines)


def export_to_gephi(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
) -> str:
    """Generate GEXF XML for Gephi import.

    Args:
        nodes: Sequence of node dictionaries.
        edges: Sequence of edge dictionaries.

    Returns:
        GEXF XML string.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">',
        '  <meta lastmodifieddate="2026-11-05">',
        '    <creator>ARF-RT</creator>',
        '    <description>Attack path graph</description>',
        '  </meta>',
        '  <graph mode="static" defaultedgetype="directed">',
        '    <nodes>',
    ]

    for n in nodes:
        node_id = n.get("provider_id", "unknown")
        node_type = n.get("node_type", "Node")
        short_label = node_id.split("/")[-1] if "/" in node_id else node_id.split(":")[-1]
        lines.append(f'      <node id="{node_id}" label="{node_type}: {short_label}" />')

    lines.append("    </nodes>")
    lines.append("    <edges>")

    for idx, e in enumerate(edges):
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        action = e.get("action", "")
        lines.append(f'      <edge id="e_{idx}" source="{src}" target="{tgt}" label="{action}" />')

    lines.append("    </edges>")
    lines.append("  </graph>")
    lines.append("</gexf>")

    return "\n".join(lines)


def export_to_graphml(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
) -> str:
    """Generate GraphML XML for graph tools.

    Args:
        nodes: Sequence of node dictionaries.
        edges: Sequence of edge dictionaries.

    Returns:
        GraphML XML string.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
        '  <key id="action" for="edge" attr.name="action" attr.type="string"/>',
        '  <graph id="G" edgedefault="directed">',
    ]

    for n in nodes:
        node_id = n.get("provider_id", "unknown")
        node_type = n.get("node_type", "Node")
        short_label = node_id.split("/")[-1] if "/" in node_id else node_id.split(":")[-1]
        lines.append(f'    <node id="{node_id}">')
        lines.append(f'      <data key="label">{node_type}: {short_label}</data>')
        lines.append(f'      <data key="type">{node_type}</data>')
        lines.append(f'    </node>')

    for idx, e in enumerate(edges):
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        action = e.get("action", "")
        lines.append(f'    <edge id="e_{idx}" source="{src}" target="{tgt}">')
        lines.append(f'      <data key="action">{action}</data>')
        lines.append(f'    </edge>')

    lines.append("  </graph>")
    lines.append("</graphml>")

    return "\n".join(lines)


def style_attack_path_dot(
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    path_edges: Sequence[str],
    graph_name: str = "ARF_RT_AttackPath",
) -> str:
    """Generate DOT with highlighted attack path.

    Args:
        nodes: Sequence of node dictionaries.
        edges: Sequence of edge dictionaries.
        path_edges: Edge IDs that are part of the attack path.
        graph_name: Graph name.

    Returns:
        DOT string with path highlighted.
    """
    path_set = set(path_edges)
    lines = [
        f"digraph {graph_name} {{",
        '  rankdir="LR";',
        '  node [shape=box, style=rounded, fontname="Helvetica"];',
        '  edge [fontname="Helvetica"];',
    ]

    for n in nodes:
        node_id = n.get("provider_id", "unknown")
        node_type = n.get("node_type", "Node")
        short_label = node_id.split("/")[-1] if "/" in node_id else node_id.split(":")[-1]
        lines.append(f'  "{node_id}" [label="{node_type}\\n{short_label}"];')

    for e in edges:
        src = e.get("source_node", "")
        tgt = e.get("target_node", "")
        action = e.get("action", "")
        edge_id = e.get("edge_id", "")
        is_path = edge_id in path_set
        if is_path:
            lines.append(f'  "{src}" -> "{tgt}" [label="{action}", color=red, penwidth=3.0, fontcolor=red];')
        else:
            lines.append(f'  "{src}" -> "{tgt}" [label="{action}", color=gray, penwidth=1.0];')

    lines.append("}")
    return "\n".join(lines)
