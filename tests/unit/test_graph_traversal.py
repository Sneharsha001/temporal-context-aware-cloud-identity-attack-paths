"""
tests/unit/test_graph_traversal.py - Unit tests for graph traversal and cycle detection.
"""

from arf_rt.util.graph_traversal import find_all_simple_paths, detect_cycles


def test_find_all_simple_paths():
    adj = {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    paths = find_all_simple_paths(adj, "A", "D")
    assert ["A", "B", "D"] in paths
    assert ["A", "C", "D"] in paths
    assert len(paths) == 2


def test_detect_cycles():
    adj = {
        "A": ["B"],
        "B": ["C"],
        "C": ["A"],
    }
    cycles = detect_cycles(adj)
    assert len(cycles) > 0


def test_no_cycles():
    adj = {
        "A": ["B"],
        "B": ["C"],
        "C": [],
    }
    cycles = detect_cycles(adj)
    assert len(cycles) == 0
