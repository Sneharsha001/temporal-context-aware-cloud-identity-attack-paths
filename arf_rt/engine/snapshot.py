"""Snapshot: obs_digest, canonical_run_hash, and full state export (spec §2.2, §2.3.3).

obs_digest per edge:
  1. Collect observations for the edge
  2. Build tuple: [probe_type, result, reason_class, strength, signal_q,
                    is_counterfactual, constraint_relevant, evidence_hash_or_null]
  3. canonical_json(tuple) for each → list of strings
  4. Sort strings lexicographically (UTF-8 bytes)
  5. canonical_json(sorted_list) → JSON array of strings
  6. sha256(UTF-8 bytes of that JSON array)

canonical_run_hash:
  Hash all determinism-sensitive DB state into a single sha256.
  Excludes:
    - Timestamps (created_at, applied_at)
    - Display-only keys (template_key, constraint_key — derived, never parsed)
    - Raw observations table (replaced by obs_digest)
    - run_warnings table (informational, not semantic state)
    - edge_updates table (audit trail, not semantic state)
  Includes:
    - Edges, templates, nodes, constraints, objectives (structural + belief state)
    - Obs digests (computed from observations)
    - derived_topk (computed paths — included when populated)
  Uses COLLATE BINARY ordering for all queries.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from arf_rt.util.canon import canonical_json


def compute_obs_digest(conn: sqlite3.Connection, edge_id: str) -> str:
    """Compute the observation digest for a single edge (spec §2.3.3).

    Returns:
        Hex sha256 digest string, or empty string if no observations.
    """
    rows = conn.execute(
        """SELECT probe_type, result, reason_class, strength, signal_q,
                  is_counterfactual, constraint_relevant, evidence_hash
           FROM observations
           WHERE edge_id = ?
           ORDER BY observation_id""",
        (edge_id,),
    ).fetchall()

    if not rows:
        return ""

    tuple_jsons = []
    for row in rows:
        obs_tuple = [
            row["probe_type"],
            row["result"],
            row["reason_class"],
            row["strength"],
            row["signal_q"],
            row["is_counterfactual"],
            row["constraint_relevant"],
            row["evidence_hash"],  # None → null in canonical_json
        ]
        tuple_jsons.append(canonical_json(obs_tuple))

    tuple_jsons.sort()
    digest_input = canonical_json(tuple_jsons)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def compute_all_obs_digests(conn: sqlite3.Connection) -> dict[str, str]:
    """Compute obs_digest for all edges that have observations.

    Single ordered SQL stream per spec — no per-edge queries.

    Returns:
        Dict mapping edge_id → obs_digest hex string.
    """
    rows = conn.execute(
        """SELECT edge_id, probe_type, result, reason_class, strength,
                  signal_q, is_counterfactual, constraint_relevant, evidence_hash
           FROM observations
           ORDER BY edge_id COLLATE BINARY, observation_id"""
    ).fetchall()

    edge_obs: dict[str, list] = {}
    for row in rows:
        eid = row["edge_id"]
        obs_tuple = [
            row["probe_type"],
            row["result"],
            row["reason_class"],
            row["strength"],
            row["signal_q"],
            row["is_counterfactual"],
            row["constraint_relevant"],
            row["evidence_hash"],
        ]
        if eid not in edge_obs:
            edge_obs[eid] = []
        edge_obs[eid].append(canonical_json(obs_tuple))

    result = {}
    for eid in sorted(edge_obs.keys()):
        tuple_jsons = edge_obs[eid]
        tuple_jsons.sort()
        digest_input = canonical_json(tuple_jsons)
        result[eid] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    return result


# ===================================================================
# Canonical run hash (spec §2.2)
# ===================================================================


def _hash_edges(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash edge belief state (excludes timestamps)."""
    edges = conn.execute(
        """SELECT edge_id, edge_type, src_node_id, dst_node_id, region,
                  template_id, alpha_i, beta_i, status, frozen, flags_json,
                  features_json, features_fp
           FROM edges ORDER BY edge_id COLLATE BINARY"""
    ).fetchall()

    rows = []
    for e in edges:
        rows.append([
            e["edge_id"], e["edge_type"], e["src_node_id"], e["dst_node_id"],
            e["region"], e["template_id"], e["alpha_i"], e["beta_i"],
            e["status"], e["frozen"], e["flags_json"],
            e["features_json"], e["features_fp"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def _hash_obs_digests(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash obs_digests (replaces raw observations in hash)."""
    obs_digests = compute_all_obs_digests(conn)
    digest_pairs = [[k, v] for k, v in sorted(obs_digests.items())]
    h.update(canonical_json(digest_pairs).encode("utf-8"))


def _hash_templates(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash template state (excludes template_key — display only)."""
    templates = conn.execute(
        """SELECT template_id, provider, edge_type,
                  features_json, features_fp, feature_schema_version,
                  alpha_agg_i, beta_agg_i, sample_count
           FROM templates ORDER BY template_id COLLATE BINARY"""
    ).fetchall()

    rows = []
    for t in templates:
        rows.append([
            t["template_id"], t["provider"], t["edge_type"],
            t["features_json"], t["features_fp"],
            t["feature_schema_version"], t["alpha_agg_i"],
            t["beta_agg_i"], t["sample_count"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def _hash_nodes(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash node structural data."""
    nodes = conn.execute(
        """SELECT node_id, provider, node_type, provider_id, region,
                  display_name, properties_json
           FROM nodes ORDER BY node_id COLLATE BINARY"""
    ).fetchall()

    rows = []
    for n in nodes:
        rows.append([
            n["node_id"], n["provider"], n["node_type"], n["provider_id"],
            n["region"], n["display_name"], n["properties_json"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def _hash_constraints(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash constraint state (excludes constraint_key — display only)."""
    constraints = conn.execute(
        """SELECT constraint_id, provider, constraint_type,
                  scope_type, scope_id, region, properties_json, properties_fp,
                  status, validation_status, confidence_q
           FROM constraints ORDER BY constraint_id COLLATE BINARY"""
    ).fetchall()

    rows = []
    for c in constraints:
        rows.append([
            c["constraint_id"], c["provider"], c["constraint_type"],
            c["scope_type"], c["scope_id"], c["region"],
            c["properties_json"], c["properties_fp"],
            c["status"], c["validation_status"], c["confidence_q"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def _hash_objectives(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash objective structural data."""
    objectives = conn.execute(
        """SELECT objective_id, objective_type, start_nodes_json,
                  target_nodes_json, max_depth, k
           FROM objectives ORDER BY objective_id COLLATE BINARY"""
    ).fetchall()

    rows = []
    for o in objectives:
        rows.append([
            o["objective_id"], o["objective_type"],
            o["start_nodes_json"], o["target_nodes_json"],
            o["max_depth"], o["k"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def _hash_derived_topk(h: "hashlib._Hash", conn: sqlite3.Connection) -> None:
    """Hash derived Top-K paths (includes bands and flags)."""
    topk = conn.execute(
        """SELECT objective_id, rank, edge_id_sequence, p_best_q8,
                  p_worst_q8, confidence_band, path_length, flags_json
           FROM derived_topk
           ORDER BY objective_id COLLATE BINARY, rank"""
    ).fetchall()

    rows = []
    for t in topk:
        rows.append([
            t["objective_id"], t["rank"], t["edge_id_sequence"],
            t["p_best_q8"], t["p_worst_q8"], t["confidence_band"],
            t["path_length"], t["flags_json"],
        ])
    h.update(canonical_json(rows).encode("utf-8"))


def canonical_run_hash(conn: sqlite3.Connection) -> str:
    """Compute the canonical run hash over all determinism-sensitive state (spec §2.2).

    Includes: edges, obs_digests, templates, nodes, constraints, objectives, derived_topk.
    Excludes: timestamps, display-only keys, raw observations, warnings, edge_updates.

    Returns:
        Hex sha256 digest (64 chars).
    """
    h = hashlib.sha256()

    _hash_edges(h, conn)
    _hash_obs_digests(h, conn)
    _hash_templates(h, conn)
    _hash_nodes(h, conn)
    _hash_constraints(h, conn)
    _hash_objectives(h, conn)
    _hash_derived_topk(h, conn)

    return h.hexdigest()


# ===================================================================
# Full state export (spec §2.2 — machine-readable)
# ===================================================================


def full_state_export(conn: sqlite3.Connection) -> dict[str, Any]:
    """Export all determinism-sensitive state as a dict for JSON serialization.

    This is the machine-readable equivalent of canonical_run_hash.
    Useful for debugging, diff reports, and what-if comparison.

    Returns:
        Dict with keys: edges, obs_digests, templates, nodes, constraints,
        objectives, derived_topk, warnings, canonical_run_hash.
    """
    edges = conn.execute(
        """SELECT edge_id, edge_type, src_node_id, dst_node_id, region,
                  template_id, alpha_i, beta_i, status, frozen, flags_json,
                  features_json, features_fp
           FROM edges ORDER BY edge_id COLLATE BINARY"""
    ).fetchall()

    obs_digests = compute_all_obs_digests(conn)

    templates = conn.execute(
        """SELECT template_id, template_key, provider, edge_type,
                  features_json, features_fp, feature_schema_version,
                  alpha_agg_i, beta_agg_i, sample_count
           FROM templates ORDER BY template_id COLLATE BINARY"""
    ).fetchall()

    nodes = conn.execute(
        """SELECT node_id, provider, node_type, provider_id, region,
                  display_name, properties_json
           FROM nodes ORDER BY node_id COLLATE BINARY"""
    ).fetchall()

    constraints = conn.execute(
        """SELECT constraint_id, constraint_key, provider, constraint_type,
                  scope_type, scope_id, region, properties_json, properties_fp,
                  status, validation_status, confidence_q
           FROM constraints ORDER BY constraint_id COLLATE BINARY"""
    ).fetchall()

    objectives = conn.execute(
        """SELECT objective_id, objective_type, start_nodes_json,
                  target_nodes_json, max_depth, k
           FROM objectives ORDER BY objective_id COLLATE BINARY"""
    ).fetchall()

    topk = conn.execute(
        """SELECT objective_id, rank, edge_id_sequence, p_best_q8,
                  p_worst_q8, confidence_band, path_length, flags_json
           FROM derived_topk
           ORDER BY objective_id COLLATE BINARY, rank"""
    ).fetchall()

    warnings = conn.execute(
        """SELECT code, severity, message, context_json
           FROM run_warnings
           ORDER BY code COLLATE BINARY, message COLLATE BINARY"""
    ).fetchall()

    run_hash = canonical_run_hash(conn)

    return {
        "edges": [dict(e) for e in edges],
        "obs_digests": obs_digests,
        "templates": [dict(t) for t in templates],
        "nodes": [dict(n) for n in nodes],
        "constraints": [dict(c) for c in constraints],
        "objectives": [dict(o) for o in objectives],
        "derived_topk": [dict(t) for t in topk],
        "warnings": [dict(w) for w in warnings],
        "canonical_run_hash": run_hash,
    }
