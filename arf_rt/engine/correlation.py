"""Correlation system for ARF-RT (spec §14).

Builds global constraint components via union-find, assigns edges to
correlation groups, and selects group representatives for p_worst/p_best.

Key concepts:
  - Global components (§14.2): Union-find per constraint_type across all
    edge_constraints where constraint is ACTIVE and confidence_q >= threshold.
  - Component ID (§14.3): min(constraint_id) in component, lexicographic.
  - Group signatures (§14.4):
    * p_worst: sorted list of (constraint_type, component_id)
    * p_best: sorted list of (constraint_type, constraint_id)
    * No constraints: ("NONE", edge_id)
  - Representative (§14.5): Min by cross-multiply rational compare,
    tie-break by edge_id COLLATE BINARY.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from arf_rt.config import CORRELATION_LINK_MIN_CONFIDENCE_Q
from arf_rt.util.canon import canonical_json


# ===================================================================
# Union-Find
# ===================================================================


class UnionFind:
    """Simple union-find with path compression and union by rank."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def components(self) -> dict[str, set[str]]:
        """Return root → set of members."""
        groups: dict[str, set[str]] = {}
        for x in self._parent:
            root = self.find(x)
            if root not in groups:
                groups[root] = set()
            groups[root].add(x)
        return groups


# ===================================================================
# Build global components (§14.2)
# ===================================================================


def build_global_components(
    conn: sqlite3.Connection,
    min_confidence_q: int = CORRELATION_LINK_MIN_CONFIDENCE_Q,
) -> dict[str, dict]:
    """Build union-find components per constraint_type.

    Spec §14.2: Iterate edges by edge_id COLLATE BINARY,
    within each edge iterate constraint_ids COLLATE BINARY.
    Only ACTIVE constraints with confidence_q >= threshold.

    Returns:
        Dict mapping constraint_id → {component_id, constraint_type}
        where component_id = min(constraint_id) in the component.
    """
    # Get eligible constraints
    eligible = conn.execute(
        """SELECT constraint_id, constraint_type
           FROM constraints
           WHERE status = 'ACTIVE'
             AND confidence_q >= ?
           ORDER BY constraint_id COLLATE BINARY""",
        (min_confidence_q,),
    ).fetchall()

    eligible_ids = {r["constraint_id"] for r in eligible}
    cst_type_map = {r["constraint_id"]: r["constraint_type"] for r in eligible}

    if not eligible_ids:
        return {}

    # Build union-find per constraint_type
    uf_by_type: dict[str, UnionFind] = {}

    # Get all edge_constraints, ordered deterministically
    ec_rows = conn.execute(
        """SELECT ec.edge_id, ec.constraint_id
           FROM edge_constraints ec
           WHERE ec.constraint_id IN ({placeholders})
           ORDER BY ec.edge_id COLLATE BINARY, ec.constraint_id COLLATE BINARY""".format(
            placeholders=",".join("?" * len(eligible_ids))
        ),
        list(eligible_ids),
    ).fetchall()

    # Group by edge_id (maintaining order)
    edge_constraints: dict[str, list[str]] = {}
    for row in ec_rows:
        eid = row["edge_id"]
        cid = row["constraint_id"]
        if eid not in edge_constraints:
            edge_constraints[eid] = []
        edge_constraints[eid].append(cid)

    # For each edge, union all constraints of the same type
    for eid in sorted(edge_constraints.keys()):  # COLLATE BINARY order
        cids = edge_constraints[eid]  # Already sorted from SQL

        # Group by constraint_type
        by_type: dict[str, list[str]] = {}
        for cid in cids:
            ct = cst_type_map[cid]
            if ct not in by_type:
                by_type[ct] = []
            by_type[ct].append(cid)

        # Union within each type
        for ct, type_cids in by_type.items():
            if ct not in uf_by_type:
                uf_by_type[ct] = UnionFind()
            uf = uf_by_type[ct]
            for i in range(1, len(type_cids)):
                uf.union(type_cids[0], type_cids[i])

    # Build component_id = min(constraint_id) in each component
    result: dict[str, dict] = {}

    for ct, uf in uf_by_type.items():
        comps = uf.components()
        for root, members in comps.items():
            comp_id = min(members)  # Lexicographic min = COLLATE BINARY min
            for cid in members:
                result[cid] = {
                    "component_id": comp_id,
                    "constraint_type": ct,
                }

    # Include eligible constraints not in any edge_constraint
    for cid in eligible_ids:
        if cid not in result:
            result[cid] = {
                "component_id": cid,
                "constraint_type": cst_type_map[cid],
            }

    return result


# ===================================================================
# Edge correlation groups (§14.4)
# ===================================================================


def compute_edge_groups(
    conn: sqlite3.Connection,
    components: dict[str, dict],
) -> dict[str, dict]:
    """Assign each edge to p_worst and p_best groups.

    Returns:
        Dict mapping edge_id → {
            p_worst_sig: canonical JSON string of sorted [(ctype, component_id), ...]
            p_best_sig: canonical JSON string of sorted [(ctype, constraint_id), ...]
            constraint_ids: list of constraint_ids linked to this edge
        }
    """
    # Get all edges
    edges = conn.execute(
        "SELECT edge_id FROM edges ORDER BY edge_id COLLATE BINARY"
    ).fetchall()

    # Get edge_constraints for eligible constraints
    eligible_cids = set(components.keys())

    ec_rows = conn.execute(
        "SELECT edge_id, constraint_id FROM edge_constraints "
        "ORDER BY edge_id COLLATE BINARY, constraint_id COLLATE BINARY"
    ).fetchall()

    edge_cids: dict[str, list[str]] = {}
    for row in ec_rows:
        cid = row["constraint_id"]
        if cid in eligible_cids:
            eid = row["edge_id"]
            if eid not in edge_cids:
                edge_cids[eid] = []
            edge_cids[eid].append(cid)

    result: dict[str, dict] = {}

    for erow in edges:
        eid = erow["edge_id"]
        cids = edge_cids.get(eid, [])

        if not cids:
            # No constraints → signature uses edge_id
            sig = canonical_json([["NONE", eid]])
            result[eid] = {
                "p_worst_sig": sig,
                "p_best_sig": sig,
                "constraint_ids": [],
            }
        else:
            # p_worst: sorted (constraint_type, component_id)
            worst_pairs = sorted(set(
                (components[c]["constraint_type"], components[c]["component_id"])
                for c in cids
            ))
            p_worst_sig = canonical_json([list(p) for p in worst_pairs])

            # p_best: sorted (constraint_type, constraint_id)
            best_pairs = sorted(set(
                (components[c]["constraint_type"], c)
                for c in cids
            ))
            p_best_sig = canonical_json([list(p) for p in best_pairs])

            result[eid] = {
                "p_worst_sig": p_worst_sig,
                "p_best_sig": p_best_sig,
                "constraint_ids": cids,
            }

    return result


# ===================================================================
# Group representative selection (§14.5)
# ===================================================================


def _rational_less(a_alpha: int, a_beta: int, b_alpha: int, b_beta: int) -> bool:
    """Compare a/(a+b) < c/(c+d) via cross-multiply.

    A < B iff alphaA*(alphaB+betaB) < alphaB*(alphaA+betaA)
    """
    lhs = a_alpha * (b_alpha + b_beta)
    rhs = b_alpha * (a_alpha + a_beta)
    return lhs < rhs


def select_group_representatives(
    conn: sqlite3.Connection,
    edge_groups: dict[str, dict],
    mode: str = "p_worst",
) -> dict[str, str]:
    """Select representative edge for each correlation group.

    Spec §14.5: Min by cross-multiply rational compare.
    Tie-break by edge_id COLLATE BINARY.

    Args:
        mode: "p_worst" or "p_best" — determines which signature to group by.

    Returns:
        Dict mapping group_signature → representative edge_id.
    """
    sig_key = f"{mode}_sig"

    # Group edges by signature
    groups: dict[str, list[str]] = {}
    for eid, info in edge_groups.items():
        sig = info[sig_key]
        if sig not in groups:
            groups[sig] = []
        groups[sig].append(eid)

    # Get edge beliefs
    edge_beliefs: dict[str, tuple[int, int]] = {}
    rows = conn.execute(
        "SELECT edge_id, alpha_i, beta_i FROM edges"
    ).fetchall()
    for r in rows:
        edge_beliefs[r["edge_id"]] = (r["alpha_i"], r["beta_i"])

    # Select representative per group
    reps: dict[str, str] = {}
    for sig, eids in groups.items():
        best_eid = eids[0]
        best_a, best_b = edge_beliefs.get(best_eid, (1, 1))

        for eid in eids[1:]:
            a, b = edge_beliefs.get(eid, (1, 1))
            if _rational_less(a, b, best_a, best_b):
                best_eid, best_a, best_b = eid, a, b
            elif not _rational_less(best_a, best_b, a, b):
                # Equal ratio → tie-break by edge_id
                if eid < best_eid:
                    best_eid, best_a, best_b = eid, a, b

        reps[sig] = best_eid

    return reps


def _select_representatives_from_beliefs(
    groups: dict[str, list[str]],
    edge_beliefs: dict[str, tuple[int, int]],
) -> dict[str, str]:
    """Select representatives for already-grouped edges."""
    reps: dict[str, str] = {}
    for sig, eids in groups.items():
        best_eid = eids[0]
        best_a, best_b = edge_beliefs.get(best_eid, (1, 1))

        for eid in eids[1:]:
            a, b = edge_beliefs.get(eid, (1, 1))
            if _rational_less(a, b, best_a, best_b):
                best_eid, best_a, best_b = eid, a, b
            elif not _rational_less(best_a, best_b, a, b):
                if eid < best_eid:
                    best_eid, best_a, best_b = eid, a, b

        reps[sig] = best_eid
    return reps


def select_all_group_representatives(
    conn: sqlite3.Connection,
    edge_groups: dict[str, dict],
) -> tuple[dict[str, str], dict[str, str]]:
    """Select p_worst and p_best representatives from current edge beliefs.

    This preserves the same representative rule as select_group_representatives,
    but fetches beliefs once and groups both signature modes in one pass.
    """
    worst_groups: dict[str, list[str]] = {}
    best_groups: dict[str, list[str]] = {}
    for eid, info in edge_groups.items():
        worst_groups.setdefault(info["p_worst_sig"], []).append(eid)
        best_groups.setdefault(info["p_best_sig"], []).append(eid)

    rows = conn.execute(
        "SELECT edge_id, alpha_i, beta_i FROM edges"
    ).fetchall()
    edge_beliefs = {r["edge_id"]: (r["alpha_i"], r["beta_i"]) for r in rows}

    return (
        _select_representatives_from_beliefs(worst_groups, edge_beliefs),
        _select_representatives_from_beliefs(best_groups, edge_beliefs),
    )


def refresh_correlation_representatives(
    conn: sqlite3.Connection,
    static_correlation: dict[str, Any],
) -> dict[str, Any]:
    """Reuse static correlation membership and refresh dynamic representatives.

    Safe use requires unchanged nodes, edges, constraints.status/confidence_q,
    and edge_constraints. Planner forks meet that contract: they replay
    observations and update edge beliefs, while constraint validation only
    writes validation_status, which compute_correlation does not use.
    """
    edge_groups = static_correlation["edge_groups"]
    p_worst_reps, p_best_reps = select_all_group_representatives(conn, edge_groups)
    return {
        "components": static_correlation["components"],
        "edge_groups": edge_groups,
        "p_worst_reps": p_worst_reps,
        "p_best_reps": p_best_reps,
    }


def compute_correlation(
    conn: sqlite3.Connection,
    min_confidence_q: int = CORRELATION_LINK_MIN_CONFIDENCE_Q,
) -> dict[str, Any]:
    """Full correlation pipeline.

    Returns:
        {
            components: {constraint_id → {component_id, constraint_type}},
            edge_groups: {edge_id → {p_worst_sig, p_best_sig, constraint_ids}},
            p_worst_reps: {sig → edge_id},
            p_best_reps: {sig → edge_id},
        }
    """
    components = build_global_components(conn, min_confidence_q)
    edge_groups = compute_edge_groups(conn, components)
    p_worst_reps, p_best_reps = select_all_group_representatives(conn, edge_groups)

    return {
        "components": components,
        "edge_groups": edge_groups,
        "p_worst_reps": p_worst_reps,
        "p_best_reps": p_best_reps,
    }
