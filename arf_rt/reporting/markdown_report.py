"""Markdown report generator for ARF-RT (spec §16).

Rules:
  - No decimals — use confidence bands (from p_worst)
  - Evidence coverage: observed_edges / total_edges as percentage
  - Conflict surfacing: if any top-K path edge has conflict=true
  - Read-only: MUST NOT modify DB state
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def generate_markdown_report(conn: sqlite3.Connection) -> str:
    """Generate a human-readable Markdown report from computed state.

    This function is READ-ONLY — it does not modify any DB state.

    Returns:
        Markdown string.
    """
    sections = []

    # Header
    sections.append(_header_section(conn))

    # Per-objective results
    objectives = conn.execute(
        "SELECT objective_id, objective_type, start_nodes_json, target_nodes_json, max_depth, k "
        "FROM objectives ORDER BY objective_id COLLATE BINARY"
    ).fetchall()

    for obj in objectives:
        sections.append(_objective_section(conn, obj))

    # Evidence coverage
    sections.append(_evidence_coverage_section(conn))

    # Constraint validation summary
    sections.append(_constraint_summary_section(conn))

    # Conflicts
    conflict_section = _conflict_section(conn)
    if conflict_section:
        sections.append(conflict_section)

    # Warnings
    warn_section = _warnings_section(conn)
    if warn_section:
        sections.append(warn_section)

    return "\n\n".join(sections) + "\n"


# ===================================================================
# Section generators
# ===================================================================


def _header_section(conn: sqlite3.Connection) -> str:
    """Report header with summary stats."""
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    constraint_count = conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
    objective_count = conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0]
    obs_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    lines = [
        "# ARF-RT Analysis Report",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Nodes | {node_count} |",
        f"| Edges | {edge_count} |",
        f"| Constraints | {constraint_count} |",
        f"| Objectives | {objective_count} |",
        f"| Observations | {obs_count} |",
    ]
    return "\n".join(lines)


def _objective_section(conn: sqlite3.Connection, obj: sqlite3.Row) -> str:
    """Section for one objective's Top-K results."""
    oid = obj["objective_id"]
    otype = obj["objective_type"]

    # Resolve node display names
    start_nodes = json.loads(obj["start_nodes_json"])
    target_nodes = json.loads(obj["target_nodes_json"])
    start_names = _resolve_node_names(conn, start_nodes)
    target_names = _resolve_node_names(conn, target_nodes)

    lines = [
        f"## Objective: {otype}",
        "",
        f"**From:** {', '.join(start_names)}",
        f"**To:** {', '.join(target_names)}",
        f"**Max depth:** {obj['max_depth']}, **K:** {obj['k']}",
        "",
    ]

    # Top-K paths
    paths = conn.execute(
        "SELECT rank, edge_id_sequence, p_worst_q8, p_best_q8, "
        "confidence_band, path_length, flags_json "
        "FROM derived_topk WHERE objective_id = ? ORDER BY rank",
        (oid,),
    ).fetchall()

    if not paths:
        lines.append("*No paths found.*")
        return "\n".join(lines)

    lines.append("### Top-K Attack Paths")
    lines.append("")
    lines.append("| Rank | Confidence | Length | Flags |")
    lines.append("|------|------------|--------|-------|")

    for p in paths:
        flags = _format_flags(p["flags_json"])
        lines.append(
            f"| {p['rank']} | {p['confidence_band']} | {p['path_length']} | {flags} |"
        )

    # Path details
    lines.append("")
    for p in paths:
        edge_ids = json.loads(p["edge_id_sequence"])
        path_desc = _describe_path(conn, edge_ids)
        lines.append(f"**Path {p['rank']}** ({p['confidence_band']}):")
        lines.append(path_desc)
        lines.append("")

    return "\n".join(lines)


def _evidence_coverage_section(conn: sqlite3.Connection) -> str:
    """Evidence coverage: observed_edges / total_edges (spec §16)."""
    total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # observed_edges: edges with ≥1 observation where strength in
    # {DIRECT, DETERMINISTIC} and is_counterfactual==0
    observed = conn.execute(
        """SELECT COUNT(DISTINCT edge_id) FROM observations
           WHERE strength IN ('DIRECT', 'DETERMINISTIC')
             AND is_counterfactual = 0"""
    ).fetchone()[0]

    denominator = max(1, total_edges)
    coverage_pct = round(100 * observed / denominator)

    lines = [
        "## Evidence Coverage",
        "",
        f"**{observed}** of **{total_edges}** edges observed "
        f"with DIRECT/DETERMINISTIC non-counterfactual evidence "
        f"(**{coverage_pct}%**).",
    ]
    return "\n".join(lines)


def _constraint_summary_section(conn: sqlite3.Connection) -> str:
    """Constraint validation status summary."""
    rows = conn.execute(
        """SELECT validation_status, COUNT(*) as cnt
           FROM constraints
           WHERE status = 'ACTIVE'
           GROUP BY validation_status
           ORDER BY validation_status"""
    ).fetchall()

    if not rows:
        return "## Constraint Validation\n\n*No active constraints.*"

    lines = [
        "## Constraint Validation",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for r in rows:
        lines.append(f"| {r['validation_status']} | {r['cnt']} |")

    return "\n".join(lines)


def _conflict_section(conn: sqlite3.Connection) -> str | None:
    """Conflict section — only rendered if any edge has conflict=true."""
    conflict_edges = []
    edges = conn.execute(
        "SELECT edge_id, src_node_id, dst_node_id, flags_json FROM edges"
    ).fetchall()

    for e in edges:
        flags = json.loads(e["flags_json"])
        if flags.get("conflict"):
            src_name = _node_name(conn, e["src_node_id"])
            dst_name = _node_name(conn, e["dst_node_id"])
            conflict_edges.append(f"- {src_name} → {dst_name} (`{e['edge_id'][:16]}...`)")

    if not conflict_edges:
        return None

    lines = [
        "## ⚠️ Conflicts Detected",
        "",
        "The following edges have conflicting observations "
        "(frozen belief contradicted by new evidence):",
        "",
    ] + conflict_edges

    return "\n".join(lines)


def _warnings_section(conn: sqlite3.Connection) -> str | None:
    """Warnings section."""
    warnings = conn.execute(
        "SELECT code, severity, message FROM run_warnings "
        "ORDER BY severity DESC, code"
    ).fetchall()

    if not warnings:
        return None

    lines = [
        "## Warnings",
        "",
        "| Code | Severity | Message |",
        "|------|----------|---------|",
    ]
    for w in warnings:
        lines.append(f"| {w['code']} | {w['severity']} | {w['message']} |")

    return "\n".join(lines)


# ===================================================================
# Helpers
# ===================================================================


def _resolve_node_names(conn: sqlite3.Connection, node_ids: list[str]) -> list[str]:
    """Resolve node_ids to display names."""
    names = []
    for nid in node_ids:
        names.append(_node_name(conn, nid))
    return names


def _node_name(conn: sqlite3.Connection, node_id: str) -> str:
    """Get display name for a node: short_name (full ARN).

    Priority: display_name > provider_id > truncated hash.
    """
    row = conn.execute(
        "SELECT display_name, provider_id FROM nodes WHERE node_id = ?", (node_id,)
    ).fetchone()
    if row:
        if row["display_name"]:
            return row["display_name"]
        if row["provider_id"]:
            arn = row["provider_id"]
            # Extract short name: last segment(s) after account id
            # e.g. "arn:aws:iam::516525145310:role/DevRole" → "role/DevRole"
            parts = arn.split(":")
            if len(parts) >= 6:
                short = parts[-1]  # "role/DevRole" or "user/attacker"
                return f"{short} ({arn})"
            return arn
    return node_id[:16] + "..."


def _describe_path(conn: sqlite3.Connection, edge_ids: list[str]) -> str:
    """Describe a path as a chain of node names."""
    if not edge_ids:
        return "(empty path)"

    parts = []
    for i, eid in enumerate(edge_ids):
        e = conn.execute(
            "SELECT src_node_id, dst_node_id, edge_type, status FROM edges WHERE edge_id = ?",
            (eid,),
        ).fetchone()
        if e is None:
            parts.append(f"  {i+1}. (unknown edge)")
            continue

        src = _node_name(conn, e["src_node_id"])
        dst = _node_name(conn, e["dst_node_id"])
        parts.append(f"  {i+1}. {src} →[{e['edge_type']}]→ {dst} ({e['status']})")

    return "\n".join(parts)


def _format_flags(flags_json: str) -> str:
    """Format flags for table display."""
    flags = json.loads(flags_json)
    active = []
    if flags.get("conflict"):
        active.append("CONFLICT")
    if flags.get("prior_only"):
        active.append("PRIOR_ONLY")
    if flags.get("counterfactual_override"):
        active.append("COUNTERFACTUAL")
    if flags.get("stale"):
        active.append("STALE")
    return ", ".join(active) if active else "—"
