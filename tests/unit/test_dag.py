"""
tests/unit/test_dag.py - Unit tests for topological sorting and DAG helpers.
"""

from arf_rt.util.dag import topological_sort, get_ancestors


def test_topological_sort_acyclic():
    adj = {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    order = topological_sort(adj)
    assert order is not None
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_topological_sort_cyclic():
    adj = {
        "A": ["B"],
        "B": ["C"],
        "C": ["A"],
    }
    order = topological_sort(adj)
    assert order is None


def test_get_ancestors():
    adj = {
        "A": ["B"],
        "B": ["C"],
        "C": ["D"],
    }
    ancestors = get_ancestors(adj, "D")
    assert ancestors == {"A", "B", "C"}
