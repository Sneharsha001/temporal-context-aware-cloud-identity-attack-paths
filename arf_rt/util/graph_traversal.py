"""
arf_rt/util/graph_traversal.py - Topological traversal and loop detection routines.

Detects cycles in identity assume-role chains and computes all acyclic paths
between attacker entry nodes and target high-value assets.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple


def find_all_simple_paths(
    adjacency: Dict[str, List[str]],
    start: str,
    target: str,
    max_depth: int = 6,
) -> List[List[str]]:
    """Enumerate all elementary acyclic paths from start to target within max_depth."""
    results: List[List[str]] = []
    stack: List[Tuple[str, List[str], Set[str]]] = [(start, [start], {start})]

    while stack:
        curr, path, visited = stack.pop()
        if curr == target:
            results.append(path)
            continue
        if len(path) >= max_depth:
            continue

        for neighbor in adjacency.get(curr, []):
            if neighbor not in visited:
                stack.append((neighbor, path + [neighbor], visited | {neighbor}))

    return results


def detect_cycles(adjacency: Dict[str, List[str]]) -> List[List[str]]:
    """Detect cycles within an adjacency graph representation."""
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles: List[List[str]] = []

    def dfs(node: str, current_path: List[str]):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, current_path + [neighbor])
            elif neighbor in rec_stack:
                cycle_start = current_path.index(neighbor) if neighbor in current_path else 0
                cycles.append(current_path[cycle_start:] + [neighbor])

        rec_stack.remove(node)

    for n in list(adjacency.keys()):
        if n not in visited:
            dfs(n, [n])

    return cycles
