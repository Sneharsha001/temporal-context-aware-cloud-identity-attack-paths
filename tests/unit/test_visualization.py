"""
tests/unit/test_visualization.py - Unit tests for graph export utilities.
"""

from arf_rt.util.visualization import export_to_dot, export_to_cytoscape


def test_export_to_dot():
    nodes = [
        {"provider_id": "arn:aws:iam::1:user/attacker", "node_type": "IAMUser"},
        {"provider_id": "arn:aws:iam::2:role/admin", "node_type": "IAMRole"},
    ]
    edges = [
        {
            "source_node": "arn:aws:iam::1:user/attacker",
            "target_node": "arn:aws:iam::2:role/admin",
            "action": "sts:AssumeRole",
        }
    ]
    dot = export_to_dot(nodes, edges)
    assert "digraph ARF_RT_AttackPath" in dot
    assert "attacker" in dot
    assert "sts:AssumeRole" in dot


def test_export_to_cytoscape():
    nodes = [{"provider_id": "user1", "node_type": "IAMUser"}]
    edges = [{"edge_id": "e1", "source_node": "user1", "target_node": "role1", "action": "assume"}]
    cy = export_to_cytoscape(nodes, edges)
    assert len(cy["nodes"]) == 1
    assert len(cy["edges"]) == 1
    assert cy["nodes"][0]["data"]["id"] == "user1"
    assert cy["edges"][0]["data"]["action"] == "assume"
