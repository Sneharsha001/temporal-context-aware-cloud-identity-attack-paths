"""Tests for visualization module."""

from __future__ import annotations

import pytest

from arf_rt.util.visualization import (
    export_to_dot,
    export_to_cytoscape,
    export_to_mermaid,
    export_to_gephi,
    export_to_graphml,
    style_attack_path_dot,
)


class TestExportToDOT:
    """Tests for export_to_dot function."""

    def test_basic(self):
        """Test basic DOT export."""
        nodes = [{"provider_id": "arn:aws:iam::123456789012:user/Alice", "node_type": "User"}]
        edges = [{"source_node": "arn:aws:iam::123456789012:user/Alice", "target_node": "arn:aws:iam::123456789012:role/Admin", "action": "sts:AssumeRole"}]
        dot = export_to_dot(nodes, edges)
        assert "digraph" in dot
        assert "Alice" in dot
        assert "Admin" in dot
        assert "sts:AssumeRole" in dot

    def test_multiple_nodes_edges(self):
        """Test multiple nodes and edges."""
        nodes = [
            {"provider_id": "A", "node_type": "User"},
            {"provider_id": "B", "node_type": "Role"},
            {"provider_id": "C", "node_type": "Role"},
        ]
        edges = [
            {"source_node": "A", "target_node": "B", "action": "assume"},
            {"source_node": "B", "target_node": "C", "action": "assume"},
        ]
        dot = export_to_dot(nodes, edges)
        assert dot.count("->") == 2

    def test_custom_graph_name(self):
        """Test custom graph name."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = []
        dot = export_to_dot(nodes, edges, graph_name="TestGraph")
        assert "digraph TestGraph" in dot


class TestExportToCytoscape:
    """Tests for export_to_cytoscape function."""

    def test_basic(self):
        """Test basic Cytoscape export."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = [{"source_node": "A", "target_node": "B", "action": "assume"}]
        result = export_to_cytoscape(nodes, edges)
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 1
        assert result["nodes"][0]["data"]["id"] == "A"
        assert result["edges"][0]["data"]["source"] == "A"
        assert result["edges"][0]["data"]["target"] == "B"

    def test_edge_id_generation(self):
        """Test edge ID auto-generation."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = [{"source_node": "A", "target_node": "B", "action": "assume"}]
        result = export_to_cytoscape(nodes, edges)
        assert result["edges"][0]["data"]["id"] == "e_0"


class TestExportToMermaid:
    """Tests for export_to_mermaid function."""

    def test_basic(self):
        """Test basic Mermaid export."""
        nodes = [{"provider_id": "arn:aws:iam::123456789012:user/Alice", "node_type": "User"}]
        edges = [{"source_node": "arn:aws:iam::123456789012:user/Alice", "target_node": "arn:aws:iam::123456789012:role/Admin", "action": "sts:AssumeRole"}]
        mermaid = export_to_mermaid(nodes, edges)
        assert "graph LR" in mermaid
        assert "Alice" in mermaid
        assert "Admin" in mermaid
        assert "sts:AssumeRole" in mermaid

    def test_custom_title(self):
        """Test custom title."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = []
        mermaid = export_to_mermaid(nodes, edges, graph_name="Test")
        assert "title[Test]" in mermaid


class TestExportToGephi:
    """Tests for export_to_gephi function."""

    def test_basic(self):
        """Test basic GEXF export."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = [{"source_node": "A", "target_node": "B", "action": "assume"}]
        gexf = export_to_gephi(nodes, edges)
        assert "<?xml" in gexf
        assert "<gexf" in gexf
        assert "A" in gexf
        assert "B" in gexf
        assert "assume" in gexf

    def test_xml_structure(self):
        """Test XML structure."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = []
        gexf = export_to_gephi(nodes, edges)
        assert "<nodes>" in gexf
        assert "<edges>" in gexf
        assert "</gexf>" in gexf


class TestExportToGraphML:
    """Tests for export_to_graphml function."""

    def test_basic(self):
        """Test basic GraphML export."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = [{"source_node": "A", "target_node": "B", "action": "assume"}]
        graphml = export_to_graphml(nodes, edges)
        assert "<?xml" in graphml
        assert "<graphml" in graphml
        assert "A" in graphml
        assert "B" in graphml
        assert "assume" in graphml

    def test_xml_structure(self):
        """Test XML structure."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = []
        graphml = export_to_graphml(nodes, edges)
        assert "<graph" in graphml
        assert "<node" in graphml
        assert "</graphml>" in graphml


class TestStyleAttackPathDOT:
    """Tests for style_attack_path_dot function."""

    def test_highlight_path(self):
        """Test path highlighting."""
        nodes = [
            {"provider_id": "A", "node_type": "User"},
            {"provider_id": "B", "node_type": "Role"},
            {"provider_id": "C", "node_type": "Role"},
        ]
        edges = [
            {"source_node": "A", "target_node": "B", "action": "assume", "edge_id": "e1"},
            {"source_node": "B", "target_node": "C", "action": "assume", "edge_id": "e2"},
        ]
        dot = style_attack_path_dot(nodes, edges, path_edges=["e1"])
        # e1 should be red, e2 should be gray
        assert "color=red" in dot
        assert "penwidth=3.0" in dot
        assert "color=gray" in dot
        assert "penwidth=1.0" in dot

    def test_no_path_edges(self):
        """Test no path edges highlighted."""
        nodes = [{"provider_id": "A", "node_type": "User"}]
        edges = [{"source_node": "A", "target_node": "B", "action": "assume", "edge_id": "e1"}]
        dot = style_attack_path_dot(nodes, edges, path_edges=[])
        assert "color=gray" in dot