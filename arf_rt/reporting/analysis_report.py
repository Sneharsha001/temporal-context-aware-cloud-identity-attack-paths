"""Report generation for ARF-RT analysis results.

Produces human-readable Markdown reports from pipeline + planner + executor
results. All label formatting is centralized here so fixes apply everywhere.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def edge_name(conn: sqlite3.Connection, edge_id: str) -> str:
    """Get 'SrcName→DstName' label for an edge."""
    row = conn.execute("""
        SELECT n1.provider_id, n2.provider_id FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
        WHERE e.edge_id = ?
    """, (edge_id,)).fetchone()
    if row:
        return f"{row[0].split('/')[-1]}→{row[1].split('/')[-1]}"
    return edge_id[:16] + "..."


def _pluralize(n: int, singular: str, plural: str | None = None) -> str:
    """'1 edge' vs '6 edges'."""
    if plural is None:
        plural = singular + "s"
    return f"{n} {singular}" if n == 1 else f"{n} {plural}"


def constraint_label(constraint_row: dict) -> str:
    """Human-readable label for a constraint."""
    props = json.loads(constraint_row["properties_json"])
    ctype = constraint_row["constraint_type"]
    if ctype == "SCP":
        return f"SCP: {props['policy_name']}"
    elif ctype == "TRUST_CONDITION":
        target = constraint_row["scope_id"].split("/")[-1]
        cond_key = props.get("condition_key", "unknown").split(":")[-1]
        return f"Trust: {target} {cond_key}"
    return f"{ctype}: {constraint_row['constraint_id'][:16]}..."


def component_label(
    sig_str: str,
    conn: sqlite3.Connection,
) -> str:
    """Human-readable label for a correlation component signature."""
    sig = json.loads(sig_str)
    ctype = sig[0][0]
    if ctype == "NONE":
        return f"Uncorrelated: {edge_name(conn, sig[0][1])}"
    comp_id = sig[0][1]
    row = conn.execute(
        "SELECT * FROM constraints WHERE constraint_id = ?", (comp_id,)
    ).fetchone()
    if row:
        return constraint_label(dict(row))
    return f"{ctype}: {comp_id[:16]}..."


def mechanism_text(ctype: str) -> str:
    """Explanation of how correlation works for this constraint type."""
    if ctype == "SCP":
        return (
            "Shared SCP governance — edges in this component share the same "
            "Service Control Policy; p_worst uses the component representative."
        )
    elif ctype == "TRUST_CONDITION":
        return (
            "Shared trust condition — edges in this component share the same "
            "trust policy constraint; p_worst uses the component representative."
        )
    return "Uncorrelated — no shared constraints."


def generate_analysis_report(
    conn: sqlite3.Connection,
    correlation: dict[str, Any],
    plan: dict,
    run_hash: str,
    exec_summary: dict | None = None,
    top_n: int = 5,
) -> str:
    """Generate a full Markdown analysis report.

    Args:
        conn: Pipeline database connection.
        correlation: Output of compute_correlation().
        plan: Output of plan_probes().
        run_hash: canonical_run_hash of the pipeline.
        exec_summary: Output of executor.get_call_log_summary() (optional).
        top_n: Number of top probe recommendations to show.

    Returns:
        Markdown string.
    """
    md: list[str] = []

    # --- Header ---
    md.append("# ARF-RT Analysis Report")
    md.append("")

    # --- Objective ---
    objectives = conn.execute("SELECT * FROM objectives").fetchall()
    if objectives:
        obj = dict(objectives[0])
        start_nodes = json.loads(obj.get("start_nodes_json", "[]"))
        target_nodes = json.loads(obj.get("target_nodes_json", "[]"))
        if start_nodes and target_nodes:
            start = conn.execute(
                "SELECT provider_id FROM nodes WHERE node_id = ?",
                (start_nodes[0],),
            ).fetchone()
            target = conn.execute(
                "SELECT provider_id FROM nodes WHERE node_id = ?",
                (target_nodes[0],),
            ).fetchone()
            if start and target:
                s = start[0].split("/")[-1]
                t = target[0].split("/")[-1]
                md.append(f"**Objective**: Can `{s}` reach `{t}`?")
                md.append("")

    # --- Environment ---
    n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    n_obs = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    constraints_rows = [dict(r) for r in conn.execute("SELECT * FROM constraints").fetchall()]
    n_scp = len([c for c in constraints_rows if c["constraint_type"] == "SCP"])
    n_trust = len([c for c in constraints_rows if c["constraint_type"] == "TRUST_CONDITION"])

    md.append("## Environment")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| Principals | {n_nodes} |")
    md.append(f"| Edges | {n_edges} |")
    md.append(f"| SCP Constraints | {n_scp} |")
    md.append(f"| Trust Conditions | {n_trust} |")
    md.append(f"| Observations | {n_obs} |")
    md.append("")

    # --- Constraints ---
    md.append("## Constraints")
    md.append("")
    for c in constraints_rows:
        props = json.loads(c["properties_json"])
        ctype = c["constraint_type"]
        n_links = conn.execute(
            "SELECT COUNT(*) FROM edge_constraints WHERE constraint_id = ?",
            (c["constraint_id"],),
        ).fetchone()[0]
        link_text = _pluralize(n_links, "edge linkage")

        if ctype == "SCP":
            md.append(f"**{props['policy_name']}** (SCP, attached to {c['scope_id']}, {link_text})")
            md.append(f"- Denied actions: {', '.join(props.get('denied_actions', []))}")
        elif ctype == "TRUST_CONDITION":
            target = c["scope_id"].split("/")[-1]
            md.append(f"**{target}** (Trust condition, {link_text})")
            md.append(f"- Requires: {props.get('condition_key', '')} = {props.get('required_values', '')}")
        md.append("")

    # --- Edge Beliefs ---
    md.append("## Edge Beliefs")
    md.append("")
    md.append("| Source | Target | α | β | P(allow) | Status |")
    md.append("|--------|--------|---|---|----------|--------|")
    edges = conn.execute("""
        SELECT n1.provider_id as src, n2.provider_id as dst,
               e.alpha_i, e.beta_i, e.status
        FROM edges e
        JOIN nodes n1 ON n1.node_id = e.src_node_id
        JOIN nodes n2 ON n2.node_id = e.dst_node_id
        ORDER BY n1.provider_id, n2.provider_id
    """).fetchall()
    for e in edges:
        src = e["src"].split("/")[-1]
        dst = e["dst"].split("/")[-1]
        p = e["alpha_i"] * 100.0 / (e["alpha_i"] + e["beta_i"])
        md.append(f"| {src} | {dst} | {e['alpha_i']} | {e['beta_i']} | {p:.1f}% | {e['status']} |")
    md.append("")

    # --- Correlation Groups ---
    md.append("## Correlation Groups")
    md.append("")
    edge_groups = correlation["edge_groups"]
    p_worst_reps = correlation["p_worst_reps"]
    sig_map: dict[str, list[str]] = {}
    for eid, grp in edge_groups.items():
        sig = grp.get("p_worst_sig", "NONE")
        sig_parsed = json.loads(sig)
        if sig_parsed[0][0] != "NONE":
            sig_map.setdefault(sig, []).append(eid)

    for sig, eids in sig_map.items():
        sig_parsed = json.loads(sig)
        ctype = sig_parsed[0][0]
        rep = p_worst_reps.get(sig, "")
        label = component_label(sig, conn)
        md.append(f"**{label}** ({_pluralize(len(eids), 'edge')})")
        md.append(f"- Representative: {edge_name(conn, rep)}")
        md.append(f"- Members: {', '.join(edge_name(conn, eid) for eid in eids)}")
        md.append(f"- {mechanism_text(ctype)}")
        md.append("")

    # --- Paths ---
    md.append("## Paths Found")
    md.append("")
    paths = [dict(r) for r in conn.execute(
        "SELECT rank, p_worst_q8, edge_id_sequence FROM derived_topk ORDER BY rank"
    ).fetchall()]
    for p in paths:
        eids = json.loads(p["edge_id_sequence"])
        chain = " → ".join(edge_name(conn, eid) for eid in eids)
        pw = p["p_worst_q8"] * 100.0 / 100_000_000
        md.append(f"**Rank {p['rank']}**: p_worst = {pw:.2f}%")
        md.append(f"- {chain}")
        md.append("")

    # --- Planner ---
    md.append("## Probe Recommendations")
    md.append("")
    stats = plan.get("stats", {})
    h_base = plan.get("baseline_entropy", 0)
    md.append(
        f"Baseline entropy: {h_base:.4f} nats | "
        f"{stats.get('candidate_edges', '?')} candidates | "
        f"{stats.get('forks_executed', '?')} pipeline forks | "
        f"{stats.get('runtime_ms', '?')}ms"
    )
    md.append("")

    candidates = plan.get("candidates", [])
    for i, c in enumerate(candidates[:top_n]):
        name = edge_name(conn, c["edge_id"])
        reasons = ", ".join(c["reasons"])
        md.append(f"**#{i+1}: {name}** (EIG = {c['eig']:.4f})")
        md.append(
            f"- P(allow) = {c['p_edge']:.2f} | "
            f"H if ALLOW = {c['h_allow']:.4f} | "
            f"H if DENY = {c['h_deny']:.4f}"
        )
        md.append(f"- Why: {reasons}")
        md.append("")

    # Component summary table
    comp_summary = plan.get("component_summary", [])
    if comp_summary:
        md.append("### Component Summary")
        md.append("")
        md.append("| Component | Edges | Best Probe | EIG |")
        md.append("|-----------|-------|------------|-----|")
        for cs in comp_summary:
            best = edge_name(conn, cs["best_probe_edge"])
            label = component_label(cs["component_sig"], conn)
            md.append(f"| {label} | {cs['edge_count']} | {best} | {cs['best_eig']:.4f} |")
        md.append("")

    # --- Executor ---
    if exec_summary:
        md.append("## Executor Audit Log")
        md.append("")
        total = sum(exec_summary.values())
        md.append(f"Mode: DRY_RUN | Run hash: `{run_hash[:24]}...` | {total} probes logged")
        md.append("")

    # --- Reproducibility ---
    md.append("## Reproducibility")
    md.append("")
    md.append(f"Pipeline hash: `{run_hash}`. Deterministic. Decay not active (no `--as-of`).")

    return "\n".join(md)
