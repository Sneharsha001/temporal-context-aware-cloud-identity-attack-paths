"""
arf_rt/util/dag.py - Directed Acyclic Graph (DAG) topological sorting and ordering.

Computes valid traversal orders and dependency resolutions for multi-step
attack path sequences and constraint dependency graphs.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set


def topological_sort(adjacency: Dict[str, List[str]]) -> Optional[List[str]]:
    """Compute topological ordering of nodes using Kahn's algorithm.

    Args:
        adjacency: Mapping from source node to list of target nodes.

    Returns:
        List of nodes in valid topological order, or None if a cycle is present.
    """
    in_degree: Dict[str, int] = defaultdict(int)
    all_nodes: Set[str] = set(adjacency.keys())

    for u, neighbors in adjacency.items():
        for v in neighbors:
            all_nodes.add(v)
            in_degree[v] += 1

    queue: deque[str] = deque([node for node in all_nodes if in_degree[node] == 0])
    ordered: List[str] = []

    while queue:
        curr = queue.popleft()
        ordered.append(curr)

        for neighbor in adjacency.get(curr, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) == len(all_nodes):
        return ordered
    return None  # Cycle detected


def get_ancestors(adjacency: Dict[str, List[str]], target: str) -> Set[str]:
    """Compute the set of all ancestor nodes that can reach target."""
    reverse_adj: Dict[str, List[str]] = defaultdict(list)
    for u, neighbors in adjacency.items():
        for v in neighbors:
            reverse_adj[v].append(u)

    visited: Set[str] = set()
    stack = [target]
    while stack:
        curr = stack.pop()
        for parent in reverse_adj.get(curr, []):
            if parent not in visited:
                visited.add(parent)
                stack.append(parent)

    return visited
