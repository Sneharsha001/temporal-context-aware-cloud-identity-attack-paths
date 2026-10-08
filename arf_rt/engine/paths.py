"""Top-K path search for ARF-RT (spec §15).

Best-first search using p_worst_partial_q8 as the admissible bound.
Global components ensure extending a path cannot increase the bound.

Frontier priority (§15.2):
  1. Higher p_worst_partial_q8 (best probability first)
  2. Shorter path length
  3. Lexicographic edge_id_sequence COLLATE BINARY

Cycle safety: visited_nodes set per path, max_depth from objective.
"""

from __future__ import annotations

import heapq
import json
import sqlite3
from typing import Any

from arf_rt.config import Q8
from arf_rt.engine.correlation import compute_correlation
from arf_rt.util.canon import canonical_json, edge_p_q8, grouped_product_q8


def search_top_k(
    conn: sqlite3.Connection,
    objective_id: str,
    correlation: dict[str, Any] | None = None,
) -> list[dict]:
    """Find Top-K paths for an objective.

    Args:
        conn: DB connection with fully updated beliefs.
        objective_id: The objective to search.
        correlation: Pre-computed correlation result. If None, computes it.

    Returns:
        List of path dicts sorted by rank:
          [{rank, edge_id_sequence, p_best_q8, p_worst_q8,
            confidence_band, path_length, flags_json}]
    """
    # Load objective
    obj = conn.execute(
        "SELECT objective_type, start_nodes_json, target_nodes_json, max_depth, k "
        "FROM objectives WHERE objective_id = ?",
        (objective_id,),
    ).fetchone()

    if obj is None:
        return []

    start_nodes = set(json.loads(obj["start_nodes_json"]))
    target_nodes = set(json.loads(obj["target_nodes_json"]))
    max_depth = obj["max_depth"]
    k = obj["k"]

    if correlation is None:
        correlation = compute_correlation(conn)

    edge_groups = correlation["edge_groups"]
    p_worst_reps = correlation["p_worst_reps"]
    p_best_reps = correlation["p_best_reps"]

    # Build adjacency: src_node_id → [(edge_id, dst_node_id)]
    edges = conn.execute(
        "SELECT edge_id, src_node_id, dst_node_id, alpha_i, beta_i, flags_json "
        "FROM edges ORDER BY edge_id COLLATE BINARY"
    ).fetchall()

    adj: dict[str, list[tuple[str, str]]] = {}
    edge_data: dict[str, dict] = {}
    for e in edges:
        eid = e["edge_id"]
        src = e["src_node_id"]
        dst = e["dst_node_id"]
        if src not in adj:
            adj[src] = []
        adj[src].append((eid, dst))
        edge_data[eid] = {
            "alpha_i": e["alpha_i"],
            "beta_i": e["beta_i"],
            "flags_json": e["flags_json"],
            "src": src,
            "dst": dst,
        }

    # Compute edge probabilities
    edge_probs: dict[str, int] = {}
    for eid, data in edge_data.items():
        edge_probs[eid] = edge_p_q8(data["alpha_i"], data["beta_i"])

    # For p_worst: use representative probability for grouped edges
    def _get_p_worst_q8(eid: str) -> int:
        """Get p_worst probability for an edge (uses group representative)."""
        info = edge_groups.get(eid)
        if info is None:
            return edge_probs.get(eid, 0)
        sig = info["p_worst_sig"]
        rep = p_worst_reps.get(sig, eid)
        return edge_probs.get(rep, edge_probs.get(eid, 0))

    def _get_p_best_q8(eid: str) -> int:
        """Get p_best probability for an edge (uses group representative)."""
        info = edge_groups.get(eid)
        if info is None:
            return edge_probs.get(eid, 0)
        sig = info["p_best_sig"]
        rep = p_best_reps.get(sig, eid)
        return edge_probs.get(rep, edge_probs.get(eid, 0))

    # Best-first search
    # State: (current_node, visited_nodes, edge_sequence, p_worst_partial_q8, p_best_partial_q8)
    # Heap item: (-p_worst_partial_q8, path_length, edge_id_seq_str, state)
    # Negate p_worst because heapq is min-heap and we want highest first

    results: list[dict] = []
    # Track which p_worst group sigs we've already used per partial path
    # to avoid multiplying the same group representative twice

    # Initial frontier: one entry per start node
    # heap items: (-p_worst_q8, length, edge_seq_str, current_node, visited, edge_list,
    #              p_worst_q8, p_best_q8, worst_seen_sigs, best_seen_sigs)
    heap: list[tuple] = []

    for sn in sorted(start_nodes):
        heapq.heappush(heap, (
            -Q8,  # p_worst starts at 1.0 (Q8)
            0,    # path length
            "",   # edge_id_sequence string for tie-break
            sn,   # current node
            frozenset({sn}),  # visited nodes
            [],   # edge_id list
            Q8,   # p_worst_q8
            Q8,   # p_best_q8
            frozenset(),  # worst group sigs already multiplied
            frozenset(),  # best group sigs already multiplied
        ))

    while heap and len(results) < k:
        (neg_pw, plen, seq_str, cur_node, visited, edge_list,
         pw_q8, pb_q8, worst_sigs, best_sigs) = heapq.heappop(heap)

        # Check if we reached a target
        if cur_node in target_nodes and plen > 0:
            # Compute final path values
            edge_seq = canonical_json(edge_list)

            # Aggregate flags
            path_flags = _aggregate_path_flags(edge_list, edge_data)

            results.append({
                "rank": len(results) + 1,
                "edge_id_sequence": edge_seq,
                "p_best_q8": pb_q8,
                "p_worst_q8": pw_q8,
                "confidence_band": _confidence_band(pw_q8),
                "path_length": plen,
                "flags_json": path_flags,
            })
            continue

        # Expand neighbors
        if plen >= max_depth:
            continue

        for eid, dst in adj.get(cur_node, []):
            if dst in visited:
                continue  # Cycle safety

            # Compute new p_worst
            info = edge_groups.get(eid, {})
            w_sig = info.get("p_worst_sig", canonical_json([["NONE", eid]]))
            b_sig = info.get("p_best_sig", canonical_json([["NONE", eid]]))

            new_pw_q8 = pw_q8
            new_worst_sigs = worst_sigs
            if w_sig not in worst_sigs:
                # First time seeing this group in this path → multiply
                ep = _get_p_worst_q8(eid)
                new_pw_q8 = grouped_product_q8(pw_q8, ep)
                new_worst_sigs = worst_sigs | {w_sig}
            # else: group already counted, probability = 1.0 for this edge

            new_pb_q8 = pb_q8
            new_best_sigs = best_sigs
            if b_sig not in best_sigs:
                ep = _get_p_best_q8(eid)
                new_pb_q8 = grouped_product_q8(pb_q8, ep)
                new_best_sigs = best_sigs | {b_sig}

            new_edges = edge_list + [eid]
            new_seq_str = canonical_json(new_edges)

            heapq.heappush(heap, (
                -new_pw_q8,
                plen + 1,
                new_seq_str,
                dst,
                visited | {dst},
                new_edges,
                new_pw_q8,
                new_pb_q8,
                new_worst_sigs,
                new_best_sigs,
            ))

    return results


def search_and_store_top_k(
    conn: sqlite3.Connection,
    correlation: dict[str, Any] | None = None,
) -> dict[str, list[dict]]:
    """Search Top-K for all objectives and store in derived_topk.

    Returns:
        Dict mapping objective_id → list of path results.
    """
    if correlation is None:
        correlation = compute_correlation(conn)

    objectives = conn.execute(
        "SELECT objective_id FROM objectives ORDER BY objective_id COLLATE BINARY"
    ).fetchall()

    all_results: dict[str, list[dict]] = {}

    for obj in objectives:
        oid = obj["objective_id"]
        paths = search_top_k(conn, oid, correlation)
        all_results[oid] = paths

        # Store in derived_topk
        for p in paths:
            conn.execute(
                """INSERT OR REPLACE INTO derived_topk
                   (objective_id, rank, edge_id_sequence, p_best_q8,
                    p_worst_q8, confidence_band, path_length, flags_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    oid, p["rank"], p["edge_id_sequence"],
                    p["p_best_q8"], p["p_worst_q8"],
                    p["confidence_band"], p["path_length"],
                    p["flags_json"],
                ),
            )

    conn.commit()
    return all_results


def _aggregate_path_flags(
    edge_list: list[str],
    edge_data: dict[str, dict],
) -> str:
    """Aggregate flags across path edges.

    Any edge with conflict=true → path has conflict=true, etc.
    """
    import json as _json
    flags = {
        "conflict": False,
        "counterfactual_override": False,
        "prior_only": False,
        "stale": False,
    }

    all_prior_only = True
    for eid in edge_list:
        ef = _json.loads(edge_data[eid]["flags_json"])
        if ef.get("conflict"):
            flags["conflict"] = True
        if ef.get("counterfactual_override"):
            flags["counterfactual_override"] = True
        if ef.get("stale"):
            flags["stale"] = True
        if not ef.get("prior_only", False):
            all_prior_only = False

    if all_prior_only and edge_list:
        flags["prior_only"] = True

    from arf_rt.util.canon import make_flags_json
    return make_flags_json(**flags)


def _confidence_band(p_worst_q8: int) -> str:
    """Map p_worst_q8 to confidence band (spec §16)."""
    # p_worst is in Q8 scale (0 to 100_000_000)
    # Convert to percentage-like for band mapping
    pct = p_worst_q8 * 100 // Q8  # 0-100 range

    if pct >= 90:
        return "VERY_HIGH"
    elif pct >= 70:
        return "HIGH"
    elif pct >= 40:
        return "MEDIUM"
    elif pct >= 15:
        return "LOW"
    elif pct >= 1:
        return "VERY_LOW"
    else:
        return "INSUFFICIENT"
