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


def find_shortest_path(
    adjacency: Dict[str, List[str]],
    start: str,
    target: str,
) -> List[str] | None:
    """Find shortest path using BFS.

    Args:
        adjacency: Adjacency list.
        start: Start node.
        target: Target node.

    Returns:
        Shortest path as list of nodes, or None if no path exists.
    """
    from collections import deque

    if start == target:
        return [start]

    queue = deque([(start, [start])])
    visited = {start}

    while queue:
        curr, path = queue.popleft()
        for neighbor in adjacency.get(curr, []):
            if neighbor == target:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None


def find_all_paths(
    adjacency: Dict[str, List[str]],
    start: str,
    target: str,
    max_paths: int | None = None,
) -> List[List[str]]:
    """Find all paths from start to target using DFS.

    Args:
        adjacency: Adjacency list.
        start: Start node.
        target: Target node.
        max_paths: Maximum paths to return.

    Returns:
        List of paths.
    """
    results: List[List[str]] = []

    def dfs(node: str, path: List[str], visited: Set[str]):
        if max_paths is not None and len(results) >= max_paths:
            return

        if node == target:
            results.append(path.copy())
            return

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                dfs(neighbor, path, visited)
                path.pop()
                visited.remove(neighbor)

    dfs(start, [start], {start})
    return results


def bfs_layers(
    adjacency: Dict[str, List[str]],
    start: str,
    max_depth: int | None = None,
) -> List[List[str]]:
    """Return BFS layers from start node.

    Args:
        adjacency: Adjacency list.
        start: Start node.
        max_depth: Maximum depth (None for unlimited).

    Returns:
        List of layers, each layer is list of nodes at that distance.
    """
    from collections import deque

    visited = {start}
    layers = [[start]]
    queue = deque([(start, 0)])

    while queue:
        curr, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue

        next_depth = depth + 1
        if next_depth > len(layers):
            layers.append([])

        for neighbor in adjacency.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                layers[next_depth].append(neighbor)
                queue.append((neighbor, next_depth))

    return layers


def dfs_preorder(
    adjacency: Dict[str, List[str]],
    start: str,
) -> List[str]:
    """Return DFS preorder traversal.

    Args:
        adjacency: Adjacency list.
        start: Start node.

    Returns:
        Nodes in preorder.
    """
    visited = set()
    result = []

    def dfs(node: str):
        visited.add(node)
        result.append(node)
        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)

    dfs(start)
    return result


def dfs_postorder(
    adjacency: Dict[str, List[str]],
    start: str,
) -> List[str]:
    """Return DFS postorder traversal.

    Args:
        adjacency: Adjacency list.
        start: Start node.

    Returns:
        Nodes in postorder.
    """
    visited = set()
    result = []

    def dfs(node: str):
        visited.add(node)
        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
        result.append(node)

    dfs(start)
    return result


def get_reachable(
    adjacency: Dict[str, List[str]],
    start: str,
) -> Set[str]:
    """Get all nodes reachable from start.

    Args:
        adjacency: Adjacency list.
        start: Start node.

    Returns:
        Set of reachable nodes.
    """
    visited = set()
    stack = [start]

    while stack:
        curr = stack.pop()
        if curr in visited:
            continue
        visited.add(curr)
        for neighbor in adjacency.get(curr, []):
            if neighbor not in visited:
                stack.append(neighbor)

    return visited


def get_reachable_reverse(
    adjacency: Dict[str, List[str]],
    target: str,
) -> Set[str]:
    """Get all nodes that can reach target.

    Args:
        adjacency: Adjacency list.
        target: Target node.

    Returns:
        Set of nodes that can reach target.
    """
    reverse_adj: Dict[str, List[str]] = {}
    for u, neighbors in adjacency.items():
        for v in neighbors:
            reverse_adj.setdefault(v, []).append(u)

    visited = set()
    stack = [target]

    while stack:
        curr = stack.pop()
        if curr in visited:
            continue
        visited.add(curr)
        for neighbor in reverse_adj.get(curr, []):
            if neighbor not in visited:
                stack.append(neighbor)

    return visited


def path_length_distribution(
    adjacency: Dict[str, List[str]],
    start: str,
    target: str,
    max_depth: int = 10,
) -> Dict[int, int]:
    """Get distribution of path lengths from start to target.

    Args:
        adjacency: Adjacency list.
        start: Start node.
        target: Target node.
        max_depth: Maximum path depth.

    Returns:
        Dict mapping path length to count.
    """
    paths = find_all_simple_paths(adjacency, start, target, max_depth)
    dist: Dict[int, int] = {}
    for path in paths:
        length = len(path) - 1  # edges = nodes - 1
        dist[length] = dist.get(length, 0) + 1
    return dist


def count_paths(
    adjacency: Dict[str, List[str]],
    start: str,
    target: str,
    max_depth: int = 10,
) -> int:
    """Count paths from start to target.

    Args:
        adjacency: Adjacency list.
        start: Start node.
        target: Target node.
        max_depth: Maximum path depth.

    Returns:
        Number of paths.
    """
    return len(find_all_simple_paths(adjacency, start, target, max_depth))
