"""Constraint validation for ARF-RT (spec §13).

Validates constraints based on observation evidence:
  - Relevance rule (§13.1): SCP/PERMISSION_BOUNDARY count only observations
    where reason_class == CONSTRAINT_DENY OR constraint_relevant == 1
  - Thresholds (§13.2):
    * SCP/PERMISSION_BOUNDARY: ≥N distinct edges with qualifying observations
      spanning ≥M distinct src_node_id values
    * TRUST_CONDITION/RESOURCE_POLICY/AZURE_CA/AZURE_PIM: ≥1 qualifying observation
  - ASSUMED counts as unvalidated (§13.3)
  - INVALIDATED constraints excluded from everything (§13.4)

Qualifying observations:
  - non-counterfactual (is_counterfactual == 0)
  - strength in {DIRECT, DETERMINISTIC}
  - passes relevance rule for constraint type
"""

from __future__ import annotations

import sqlite3

from arf_rt.config import DEFAULT_CONSTRAINT_M, DEFAULT_CONSTRAINT_N

# Constraint types requiring strict N/M validation
_STRICT_TYPES = frozenset({"SCP", "PERMISSION_BOUNDARY"})

# Constraint types requiring only ≥1 observation
_SIMPLE_TYPES = frozenset({
    "TRUST_CONDITION", "RESOURCE_POLICY", "AZURE_CA", "AZURE_PIM",
})


def validate_all_constraints(
    conn: sqlite3.Connection,
    n: int = DEFAULT_CONSTRAINT_N,
    m: int = DEFAULT_CONSTRAINT_M,
) -> list[dict]:
    """Validate all ACTIVE constraints and update their validation_status.

    Args:
        conn: DB connection.
        n: Minimum distinct edges for SCP/PERMISSION_BOUNDARY (default 2).
        m: Minimum distinct src_node_id values (default 2).

    Returns:
        List of validation result dicts:
          [{constraint_id, constraint_type, old_status, new_status,
            distinct_edges, distinct_sources}]
    """
    constraints = conn.execute(
        """SELECT constraint_id, constraint_type, validation_status
           FROM constraints
           WHERE status = 'ACTIVE'
           ORDER BY constraint_id COLLATE BINARY"""
    ).fetchall()

    results = []
    for cst in constraints:
        cid = cst["constraint_id"]
        ctype = cst["constraint_type"]
        old_status = cst["validation_status"]

        # Get qualifying observation evidence for this constraint
        distinct_edges, distinct_sources = _count_evidence(conn, cid, ctype)

        # Determine new validation status
        new_status = _compute_validation_status(
            ctype, distinct_edges, distinct_sources, n, m,
        )

        # Update if changed (but don't downgrade VALIDATED → UNVALIDATED)
        if new_status != old_status:
            conn.execute(
                "UPDATE constraints SET validation_status = ? WHERE constraint_id = ?",
                (new_status, cid),
            )

        results.append({
            "constraint_id": cid,
            "constraint_type": ctype,
            "old_status": old_status,
            "new_status": new_status,
            "distinct_edges": distinct_edges,
            "distinct_sources": distinct_sources,
        })

    return results


def _count_evidence(
    conn: sqlite3.Connection,
    constraint_id: str,
    constraint_type: str,
) -> tuple[int, int]:
    """Count qualifying evidence for a constraint.

    Returns:
        (distinct_edge_count, distinct_src_node_count)
    """
    # Get all edges linked to this constraint
    edge_rows = conn.execute(
        """SELECT ec.edge_id, e.src_node_id
           FROM edge_constraints ec
           JOIN edges e ON e.edge_id = ec.edge_id
           WHERE ec.constraint_id = ?""",
        (constraint_id,),
    ).fetchall()

    if not edge_rows:
        return 0, 0

    # Build edge_id → src_node_id map
    edge_src_map = {r["edge_id"]: r["src_node_id"] for r in edge_rows}
    edge_ids = list(edge_src_map.keys())

    if not edge_ids:
        return 0, 0

    # Get qualifying observations for these edges
    placeholders = ",".join("?" * len(edge_ids))

    if constraint_type in _STRICT_TYPES:
        # Relevance rule (§13.1): only reason_class=CONSTRAINT_DENY or constraint_relevant=1
        query = f"""
            SELECT DISTINCT o.edge_id
            FROM observations o
            WHERE o.edge_id IN ({placeholders})
              AND o.is_counterfactual = 0
              AND o.strength IN ('DIRECT', 'DETERMINISTIC')
              AND (o.reason_class = 'CONSTRAINT_DENY' OR o.constraint_relevant = 1)
        """
    else:
        # Simple types: any qualifying observation
        query = f"""
            SELECT DISTINCT o.edge_id
            FROM observations o
            WHERE o.edge_id IN ({placeholders})
              AND o.is_counterfactual = 0
              AND o.strength IN ('DIRECT', 'DETERMINISTIC')
        """

    qualifying_edges = conn.execute(query, edge_ids).fetchall()
    qualifying_edge_ids = {r["edge_id"] for r in qualifying_edges}

    # Count distinct src_node_ids from qualifying edges
    distinct_sources = {
        edge_src_map[eid] for eid in qualifying_edge_ids if eid in edge_src_map
    }

    return len(qualifying_edge_ids), len(distinct_sources)


def _compute_validation_status(
    constraint_type: str,
    distinct_edges: int,
    distinct_sources: int,
    n: int,
    m: int,
) -> str:
    """Determine validation status based on evidence counts.

    Spec §13.2:
      SCP/PERMISSION_BOUNDARY: VALIDATED if ≥N edges AND ≥M sources
      TRUST_CONDITION/RESOURCE_POLICY/AZURE_CA/AZURE_PIM: VALIDATED if ≥1 edge
    """
    if constraint_type in _STRICT_TYPES:
        if distinct_edges >= n and distinct_sources >= m:
            return "VALIDATED"
        return "UNVALIDATED"
    elif constraint_type in _SIMPLE_TYPES:
        if distinct_edges >= 1:
            return "VALIDATED"
        return "UNVALIDATED"
    else:
        # Unknown constraint type — leave unvalidated
        return "UNVALIDATED"


def get_active_validated_constraints(
    conn: sqlite3.Connection,
) -> list[dict]:
    """Get all ACTIVE + VALIDATED constraints for use in correlation.

    Spec §13.4: INVALIDATED constraints excluded.
    Spec §13.3: ASSUMED counts as unvalidated.

    Returns:
        List of constraint dicts with constraint_id, constraint_type, etc.
    """
    rows = conn.execute(
        """SELECT constraint_id, constraint_type, confidence_q
           FROM constraints
           WHERE status = 'ACTIVE'
             AND validation_status = 'VALIDATED'
           ORDER BY constraint_id COLLATE BINARY"""
    ).fetchall()
    return [dict(r) for r in rows]


def invalidate_constraint(
    conn: sqlite3.Connection,
    constraint_id: str,
) -> None:
    """Mark a constraint as INVALIDATED (spec §13.4).

    INVALIDATED constraints are excluded from:
      - Correlation union-find
      - Correlation signatures
      - Constraint validation counts
    """
    conn.execute(
        "UPDATE constraints SET status = 'INVALIDATED' WHERE constraint_id = ?",
        (constraint_id,),
    )
