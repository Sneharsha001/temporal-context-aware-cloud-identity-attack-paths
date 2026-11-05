"""Tests for dag module."""

from __future__ import annotations

import pytest

from arf_rt.util.dag import (
    topological_sort,
    get_ancestors,
    get_descendants,
    has_path,
    find_all_paths,
    find_shortest_path,
    detect_cycles,
    is_dag,
    reverse_graph,
    get_sources,
    get_sinks,
)


class TestTopologicalSort:
    """Tests for topological_sort function."""

    def test_basic(self):
        """Test basic topological sort."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        result = topological_sort(adj)
        assert result is not None
        # a before b and c, b and c before d
        assert result.index("a") < result.index("b")
        assert result.index("a") < result.index("c")
        assert result.index("b") < result.index("d")
        assert result.index("c") < result.index("d")

    def test_linear(self):
        """Test linear chain."""
        adj = {"a": ["b"], "b": ["c"], "c": ["d"]}
        result = topological_sort(adj)
        assert result == ["a", "b", "c", "d"]

    def test_cycle(self):
        """Test cycle detection."""
        adj = {"a": ["b"], "b": ["c"], "c": ["a"]}
        result = topological_sort(adj)
        assert result is None

    def test_disconnected(self):
        """Test disconnected components."""
        adj = {"a": ["b"], "c": ["d"]}
        result = topological_sort(adj)
        assert result is not None
        assert set(result) == {"a", "b", "c", "d"}

    def test_empty(self):
        """Test empty graph."""
        result = topological_sort({})
        assert result == []


class TestGetAncestors:
    """Tests for get_ancestors function."""

    def test_basic(self):
        """Test basic ancestors."""
        adj = {"a": ["b"], "b": ["c"]}
        ancestors = get_ancestors(adj, "c")
        assert ancestors == {"a", "b"}

    def test_direct_parent(self):
        """Test direct parent."""
        adj = {"a": ["b"]}
        ancestors = get_ancestors(adj, "b")
        assert ancestors == {"a"}

    def test_no_ancestors(self):
        """Test node with no ancestors."""
        adj = {"a": ["b"]}
        ancestors = get_ancestors(adj, "a")
        assert ancestors == set()

    def test_multiple_parents(self):
        """Test node with multiple parents."""
        adj = {"a": ["c"], "b": ["c"]}
        ancestors = get_ancestors(adj, "c")
        assert ancestors == {"a", "b"}


class TestGetDescendants:
    """Tests for get_descendants function."""

    def test_basic(self):
        """Test basic descendants."""
        adj = {"a": ["b"], "b": ["c"]}
        descendants = get_descendants(adj, "a")
        assert descendants == {"b", "c"}

    def test_direct_child(self):
        """Test direct child."""
        adj = {"a": ["b"]}
        descendants = get_descendants(adj, "a")
        assert descendants == {"b"}

    def test_no_descendants(self):
        """Test node with no descendants."""
        adj = {"a": ["b"]}
        descendants = get_descendants(adj, "b")
        assert descendants == set()

    def test_multiple_children(self):
        """Test node with multiple children."""
        adj = {"a": ["b", "c"]}
        descendants = get_descendants(adj, "a")
        assert descendants == {"b", "c"}


class TestHasPath:
    """Tests for has_path function."""

    def test_path_exists(self):
        """Test path exists."""
        adj = {"a": ["b"], "b": ["c"]}
        assert has_path(adj, "a", "c") is True

    def test_direct_edge(self):
        """Test direct edge."""
        adj = {"a": ["b"]}
        assert has_path(adj, "a", "b") is True

    def test_no_path(self):
        """Test no path."""
        adj = {"a": ["b"], "c": ["d"]}
        assert has_path(adj, "a", "d") is False

    def test_same_node(self):
        """Test same node (not implemented, returns False)."""
        adj = {"a": ["b"]}
        assert has_path(adj, "a", "a") is False


class TestFindAllPaths:
    """Tests for find_all_paths function."""

    def test_single_path(self):
        """Test single path."""
        adj = {"a": ["b"], "b": ["c"]}
        paths = find_all_paths(adj, "a", "c")
        assert paths == [["a", "b", "c"]]

    def test_multiple_paths(self):
        """Test multiple paths."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        paths = find_all_paths(adj, "a", "d")
        assert len(paths) == 2
        assert ["a", "b", "d"] in paths
        assert ["a", "c", "d"] in paths

    def test_max_paths(self):
        """Test max_paths limit."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        paths = find_all_paths(adj, "a", "d", max_paths=1)
        assert len(paths) == 1

    def test_no_path(self):
        """Test no path."""
        adj = {"a": ["b"], "c": ["d"]}
        paths = find_all_paths(adj, "a", "d")
        assert paths == []

    def test_cycle_handling(self):
        """Test cycle doesn't cause infinite loop."""
        adj = {"a": ["b"], "b": ["a"]}
        paths = find_all_paths(adj, "a", "b")
        assert len(paths) == 1
        assert paths == [["a", "b"]]


class TestFindShortestPath:
    """Tests for find_shortest_path function."""

    def test_basic(self):
        """Test shortest path."""
        adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
        path = find_shortest_path(adj, "a", "d")
        assert path is not None
        assert len(path) == 3  # a -> b -> d or a -> c -> d

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
        # Cycle should contain a, b, c
        cycle = cycles[0]
        assert set(cycle[:-1]) == {"a", "b", "c"}
        assert cycle[0] == cycle[-1]  # Closed cycle

    def test_self_loop(self):
        """Test self-loop."""
        adj = {"a": ["a"]}
        cycles = detect_cycles(adj)
        assert len(cycles) == 1
        assert cycles[0] == ["a", "a"]

    def test_multiple_cycles(self):
        """Test multiple cycles."""
        adj = {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]}
        cycles = detect_cycles(adj)
        assert len(cycles) == 2


class TestIsDAG:
    """Tests for is_dag function."""

    def test_dag(self):
        """Test DAG returns True."""
        adj = {"a": ["b"], "b": ["c"]}
        assert is_dag(adj) is True

    def test_cycle(self):
        """Test graph with cycle returns False."""
        adj = {"a": ["b"], "b": ["a"]}
        assert is_dag(adj) is False


class TestReverseGraph:
    """Tests for reverse_graph function."""

    def test_basic(self):
        """Test basic reverse."""
        adj = {"a": ["b", "c"], "b": ["d"]}
        rev = reverse_graph(adj)
        assert rev == {"a": [], "b": ["a"], "c": ["a"], "d": ["b"]}

    def test_empty(self):
        """Test empty graph."""
        rev = reverse_graph({})
        assert rev == {}


class TestGetSources:
    """Tests for get_sources function."""

    def test_basic(self):
        """Test sources."""
        adj = {"a": ["b"], "c": ["d"]}
        sources = get_sources(adj)
        assert set(sources) == {"a", "c"}

    def test_no_sources_in_cycle(self):
        """Test cycle has no sources."""
        adj = {"a": ["b"], "b": ["a"]}
        sources = get_sources(adj)
        assert sources == []


class TestGetSinks:
    """Tests for get_sinks function."""

    def test_basic(self):
        """Test sinks."""
        adj = {"a": ["b"], "c": ["d"]}
        sinks = get_sinks(adj)
        assert set(sinks) == {"b", "d"}

    def test_no_sinks_in_cycle(self):
        """Test cycle has no sinks."""
        adj = {"a": ["b"], "b": ["a"]}
        sinks = get_sinks(adj)
        assert sinks == []