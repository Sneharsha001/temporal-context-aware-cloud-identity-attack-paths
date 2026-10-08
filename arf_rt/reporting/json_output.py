"""JSON output for ARF-RT (spec §16).

Machine-readable report format including:
  - Semantics version
  - All objectives with Top-K paths
  - Evidence coverage
  - Constraint validation summary
  - Conflicts
  - Canonical run hash

Read-only: MUST NOT modify DB state.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from arf_rt.engine.snapshot import canonical_run_hash, compute_all_obs_digests

# Bump when output schema changes
SEMANTICS_VERSION = "1.0.0"


def generate_json_output(conn: sqlite3.Connection) -> dict[str, Any]:
    """Generate machine-readable JSON output from computed state.

    This function is READ-ONLY — it does not modify any DB state.

    Returns:
        Dict ready for json.dumps().
    """
    return {
        "semantics_version": SEMANTICS_VERSION,
        "canonical_run_hash": canonical_run_hash(conn),
        "summary": _summary(conn),
        "objectives": _objectives(conn),
        "evidence_coverage": _evidence_coverage(conn),
        "constraint_validation": _constraint_validation(conn),
        "conflicts": _conflicts(conn),
        "warnings": _warnings(conn),
        "obs_digests": compute_all_obs_digests(conn),
    }


def _summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "node_count": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
        "edge_count": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "constraint_count": conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0],
        "objective_count": conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0],
        "observation_count": conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
    }


def _objectives(conn: sqlite3.Connection) -> list[dict]:
    objs = conn.execute(
        "SELECT objective_id, objective_type, start_nodes_json, "
        "target_nodes_json, max_depth, k "
        "FROM objectives ORDER BY objective_id COLLATE BINARY"
    ).fetchall()

    results = []
    for obj in objs:
        oid = obj["objective_id"]
        paths = conn.execute(
            "SELECT rank, edge_id_sequence, p_best_q8, p_worst_q8, "
            "confidence_band, path_length, flags_json "
            "FROM derived_topk WHERE objective_id = ? ORDER BY rank",
            (oid,),
        ).fetchall()

        results.append({
            "objective_id": oid,
            "objective_type": obj["objective_type"],
            "start_nodes": json.loads(obj["start_nodes_json"]),
            "target_nodes": json.loads(obj["target_nodes_json"]),
            "max_depth": obj["max_depth"],
            "k": obj["k"],
            "paths": [
                {
                    "rank": p["rank"],
                    "edge_id_sequence": json.loads(p["edge_id_sequence"]),
                    "p_best_q8": p["p_best_q8"],
                    "p_worst_q8": p["p_worst_q8"],
                    "confidence_band": p["confidence_band"],
                    "path_length": p["path_length"],
                    "flags": json.loads(p["flags_json"]),
                }
                for p in paths
            ],
        })

    return results


def _evidence_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    observed = conn.execute(
        """SELECT COUNT(DISTINCT edge_id) FROM observations
           WHERE strength IN ('DIRECT', 'DETERMINISTIC')
             AND is_counterfactual = 0"""
    ).fetchone()[0]
    denominator = max(1, total)
    return {
        "total_edges": total,
        "observed_edges": observed,
        "coverage_percent": round(100 * observed / denominator),
    }


def _constraint_validation(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT constraint_id, constraint_type, status, validation_status, confidence_q
           FROM constraints
           ORDER BY constraint_id COLLATE BINARY"""
    ).fetchall()
    return [dict(r) for r in rows]


def _conflicts(conn: sqlite3.Connection) -> list[dict]:
    conflicts = []
    edges = conn.execute(
        "SELECT edge_id, src_node_id, dst_node_id, edge_type, flags_json FROM edges"
    ).fetchall()

    for e in edges:
        flags = json.loads(e["flags_json"])
        if flags.get("conflict"):
            conflicts.append({
                "edge_id": e["edge_id"],
                "src_node_id": e["src_node_id"],
                "dst_node_id": e["dst_node_id"],
                "edge_type": e["edge_type"],
            })

    return conflicts


def _warnings(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT code, severity, message, context_json "
        "FROM run_warnings ORDER BY code COLLATE BINARY"
    ).fetchall()
    return [
        {
            "code": r["code"],
            "severity": r["severity"],
            "message": r["message"],
            "context": json.loads(r["context_json"]) if r["context_json"] else {},
        }
        for r in rows
    ]
