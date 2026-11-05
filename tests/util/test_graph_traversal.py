"""Tests for graph_traversal module."""

from __future__ import annotations

import pytest

from arf_rt.util.graph_traversal import (
    find_all_simple_paths,
    detect_cycles,
    find_shortest_path,
    find_all_paths,
    bfs_layers,
    dfs_preorder,
    dfs_postorder,
    get_reachable,
    get_reachable_reverse,
    path_length_distribution,
    count_paths,
)


class TestFindAllSimplePaths:
    """Tests for find_all_simple_paths function."""

    def test_basic(self):
        """Test basic path finding."""
        adj = {"a": ["b"], "b": ["c"]}
        paths = find_all_simple_paths(adj, "a", "c")
        assert paths == [["a", "b", "c"]]

    def test_multiple_paths(self):
        """Test multiple paths."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        paths = find_all_simple_paths(adj, "a", "d")
        assert len(paths) == 2
        assert ["a", "b", "d"] in paths
        assert ["a", "c", "d"] in paths

    def test_max_depth(self):
        """Test max_depth limit."""
        adj = {"a": ["b"], "b": ["c"], "c": ["d"]}
        paths = find_all_simple_paths(adj, "a", "d", max_depth=2)
        assert paths == []

        paths = find_all_simple_paths(adj, "a", "d", max_depth=3)
        assert paths == [["a", "b", "c", "d"]]

    def test_cycle_handling(self):
        """Test cycle doesn't cause infinite loop."""
        adj = {"a": ["b"], "b": ["a"]}
        paths = find_all_simple_paths(adj, "a", "b")
        assert paths == [["a", "b"]]

    def test_no_path(self):
        """Test no path."""
        adj = {"a": ["b"], "c": ["d"]}
        paths = find_all_simple_paths(adj, "a", "d")
        assert paths == []

    def test_start_equals_target(self):
        """Test start equals target."""
        adj = {"a": ["b"]}
        paths = find_all_simple_paths(adj, "a", "a")
        assert paths == [["a"]]


class TestDetectCycles:
    """Tests for detect_cycles function."""

    def test_no_cycles(self):
        """Test DAG has no cycles."""
        adj = {"a": ["b"], "b": ["c"]}
        cycles = detect_cycles(adj)
        assert cycles == []

    def test_simple_cycle(self):
        """Test simple cycle."""
        adj = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detect_cycles(adj)
        assert len(cycles) >= 1
        cycle = cycles[0]
        assert set(cycle[:-1]) == {"a", "b", "c"}

    def test_self_loop(self):
        """Test self-loop."""
        adj = {"a": ["a"]}
        cycles = detect_cycles(adj)
        assert len(cycles) == 1
        assert cycles[0] == ["a", "a"]

    def test_disconnected_cycle(self):
        """Test cycle in disconnected component."""
        adj = {"a": ["b"], "c": ["d"], "d": ["c"]}
        cycles = detect_cycles(adj)
        assert len(cycles) == 1


class TestFindShortestPath:
    """Tests for find_shortest_path function."""

    def test_basic(self):
        """Test shortest path."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        path = find_shortest_path(adj, "a", "d")
        assert path is not None
        assert len(path) == 3

    def test_direct_edge(self):
        """Test direct edge."""
        adj = {"a": ["b"]}
        path = find_shortest_path(adj, "a", "b")
        assert path == ["a", "b"]

    def test_no_path(self):
        """Test no path."""
        adj = {"a": ["b"], "c": ["d"]}
        path = find_shortest_path(adj, "a", "d")
        assert path is None

    def test_same_node(self):
        """Test same node."""
        adj = {"a": ["b"]}
        path = find_shortest_path(adj, "a", "a")
        assert path == ["a"]


class TestFindAllPaths:
    """Tests for find_all_paths function."""

    def test_basic(self):
        """Test find all paths."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        paths = find_all_paths(adj, "a", "d")
        assert len(paths) == 2

    def test_max_paths(self):
        """Test max_paths limit."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        paths = find_all_paths(adj, "a", "d", max_paths=1)
        assert len(paths) == 1


class TestBFSLayers:
    """Tests for bfs_layers function."""

    def test_basic(self):
        """Test BFS layers."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["e"]}
        layers = bfs_layers(adj, "a")
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert set(layers[2]) == {"d", "e"}

    def test_max_depth(self):
        """Test max_depth limit."""
        adj = {"a": ["b"], "b": ["c"]}
        layers = bfs_layers(adj, "a", max_depth=1)
        assert layers == [["a"], ["b"]]

    def test_cycle(self):
        """Test cycle handling."""
        adj = {"a": ["b"], "b": ["a"]}
        layers = bfs_layers(adj, "a")
        assert layers == [["a"], ["b"]]


class TestDFSOrders:
    """Tests for DFS preorder and postorder."""

    def test_preorder(self):
        """Test preorder traversal."""
        adj = {"a": ["b", "c"], "b": ["d"]}
        order = dfs_preorder(adj, "a")
        assert order[0] == "a"
        assert "b" in order and "c" in order and "d" in order

    def test_postorder(self):
        """Test postorder traversal."""
        adj = {"a": ["b", "c"], "b": ["d"]}
        order = dfs_postorder(adj, "a")
        assert order[-1] == "a"
        assert "b" in order and "c" in order and "d" in order

    def test_preorder_before_children(self):
        """Test parent before children in preorder."""
        adj = {"a": ["b"]}
        order = dfs_preorder(adj, "a")
        assert order.index("a") < order.index("b")

    def test_postorder_after_children(self):
        """Test parent after children in postorder."""
        adj = {"a": ["b"]}
        order = dfs_postorder(adj, "a")
        assert order.index("a") > order.index("b")


class TestGetReachable:
    """Tests for get_reachable function."""

    def test_basic(self):
        """Test reachable nodes."""
        adj = {"a": ["b"], "b": ["c"]}
        reachable = get_reachable(adj, "a")
        assert reachable == {"a", "b", "c"}

    def test_no_outgoing(self):
        """Test node with no outgoing edges."""
        adj = {"a": ["b"]}
        reachable = get_reachable(adj, "b")
        assert reachable == {"b"}


class TestGetReachableReverse:
    """Tests for get_reachable_reverse function."""

    def test_basic(self):
        """Test reverse reachable."""
        adj = {"a": ["b"], "b": ["c"]}
        reachable = get_reachable_reverse(adj, "c")
        assert reachable == {"a", "b", "c"}

    def test_no_incoming(self):
        """Test node with no incoming edges."""
        adj = {"a": ["b"]}
        reachable = get_reachable_reverse(adj, "a")
        assert reachable == {"a"}


class TestPathLengthDistribution:
    """Tests for path_length_distribution function."""

    def test_basic(self):
        """Test path length distribution."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        dist = path_length_distribution(adj, "a", "d")
        assert dist == {2: 2}  # Two paths of length 2

    def test_different_lengths(self):
        """Test paths of different lengths."""
        adj = {"a": ["b"], "b": ["c"], "a": ["d"], "d": ["c"]}
        # Need to fix: duplicate key "a"
        adj = {"a": ["b", "d"], "b": ["c"], "d": ["c"]}
        dist = path_length_distribution(adj, "a", "c")
        assert dist == {2: 2}


class TestCountPaths:
    """Tests for count_paths function."""

    def test_basic(self):
        """Test path counting."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        count = count_paths(adj, "a", "d")
        assert count == 2

    def test_no_path(self):
        """Test no path."""
        adj = {"a": ["b"], "c": ["d"]}
        count = count_paths(adj, "a", "d")
        assert count == 0