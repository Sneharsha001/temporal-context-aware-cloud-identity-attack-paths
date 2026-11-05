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


def get_descendants(adjacency: Dict[str, List[str]], target: str) -> Set[str]:
    """Compute the set of all descendant nodes reachable from target."""
    visited: Set[str] = set()
    stack = [target]
    while stack:
        curr = stack.pop()
        for child in adjacency.get(curr, []):
            if child not in visited:
                visited.add(child)
                stack.append(child)
    return visited


def has_path(adjacency: Dict[str, List[str]], source: str, target: str) -> bool:
    """Check if there is a path from source to target."""
    return target in get_descendants(adjacency, source)


def find_all_paths(
    adjacency: Dict[str, List[str]],
    source: str,
    target: str,
    max_paths: int | None = None,
) -> List[List[str]]:
    """Find all paths from source to target using DFS.

    Args:
        adjacency: Adjacency list of the graph.
        source: Starting node.
        target: Target node.
        max_paths: Maximum number of paths to return (None for unlimited).

    Returns:
        List of paths, each path is a list of nodes.
    """
    paths: List[List[str]] = []

    def dfs(current: str, path: List[str], visited: Set[str]) -> None:
        if max_paths is not None and len(paths) >= max_paths:
            return

        if current == target:
            paths.append(path.copy())
            return

        if current in visited:
            return

        visited.add(current)
        path.append(current)

        for neighbor in adjacency.get(current, []):
            dfs(neighbor, path, visited)

        path.pop()
        visited.remove(current)

    dfs(source, [], set())
    return paths


def find_shortest_path(
    adjacency: Dict[str, List[str]],
    source: str,
    target: str,
) -> List[str] | None:
    """Find the shortest path from source to target using BFS.

    Args:
        adjacency: Adjacency list of the graph.
        source: Starting node.
        target: Target node.

    Returns:
        List of nodes in the shortest path, or None if no path exists.
    """
    if source == target:
        return [source]

    queue: deque[tuple[str, List[str]]] = deque([(source, [source])])
    visited: Set[str] = {source}

    while queue:
        current, path = queue.popleft()

        for neighbor in adjacency.get(current, []):
            if neighbor == target:
                return path + [neighbor]

            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None


def detect_cycles(adjacency: Dict[str, List[str]]) -> List[List[str]]:
    """Detect all cycles in the graph using DFS.

    Args:
        adjacency: Adjacency list of the graph.

    Returns:
        List of cycles, each cycle is a list of nodes forming a cycle.
    """
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles: List[List[str]] = []

    def dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])

        path.pop()
        rec_stack.remove(node)

    for node in adjacency:
        if node not in visited:
            dfs(node, [])

    return cycles


def is_dag(adjacency: Dict[str, List[str]]) -> bool:
    """Check if the graph is a DAG (no cycles)."""
    return len(detect_cycles(adjacency)) == 0


def reverse_graph(adjacency: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Create reversed graph (edges inverted)."""
    reverse_adj: Dict[str, List[str]] = defaultdict(list)
    all_nodes: Set[str] = set()

    for u, neighbors in adjacency.items():
        all_nodes.add(u)
        for v in neighbors:
            all_nodes.add(v)
            reverse_adj[v].append(u)

    # Ensure all nodes present
    for node in all_nodes:
        if node not in reverse_adj:
            reverse_adj[node] = []

    return dict(reverse_adj)


def get_sources(adjacency: Dict[str, List[str]]) -> List[str]:
    """Get all source nodes (no incoming edges)."""
    in_degree: Dict[str, int] = defaultdict(int)
    all_nodes: Set[str] = set(adjacency.keys())

    for u, neighbors in adjacency.items():
        for v in neighbors:
            all_nodes.add(v)
            in_degree[v] += 1

    return [node for node in all_nodes if in_degree[node] == 0]


def get_sinks(adjacency: Dict[str, List[str]]) -> List[str]:
    """Get all sink nodes (no outgoing edges)."""
    all_nodes: Set[str] = set(adjacency.keys())

    for neighbors in adjacency.values():
        for v in neighbors:
            all_nodes.add(v)

    return [node for node in all_nodes if not adjacency.get(node)]
