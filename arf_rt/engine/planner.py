"""Probe planner: Expected Information Gain (EIG) scoring.

Recommends which edge to probe next to maximally reduce uncertainty
about attack path viability.

Entropy is computed on normalized Top-K path weights per objective:
    w_i = p_worst_q8(path_i)
    q_i = w_i / sum(w_j)
    H = -sum(q_i * log(q_i))

For each candidate edge, we simulate ALLOW and DENY outcomes on
forked databases and measure the resulting entropy reduction:
    EIG(e) = H_baseline - [p(e) * H_allow + (1-p(e)) * H_deny]

Candidate set is pruned to edges that could affect Top-K paths:
    - Edges appearing on any Top-K path
    - Edges in a correlation component whose representative appears
      on any Top-K path (the collapse mechanism)
    - Edges that could change a representative if probed

Probe simulation uses the full pipeline fork:
    1. Fork baseline DB (SQLite backup API)
    2. Insert one DIRECT observation (ALLOW or DENY)
    3. Reset edge beliefs to priors
    4. Rerun apply_all_observations + correlation + paths
    5. Measure entropy on fork's Top-K

This ensures the planner respects all engine semantics: correlation,
mass caps, template aggregation, constraint validation.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from arf_rt.config import Q8
from arf_rt.engine.constraints import validate_all_constraints
from arf_rt.engine.correlation import compute_correlation, refresh_correlation_representatives
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.updater import apply_all_observations, reset_replay_state
from arf_rt.engine.whatif import fork_db


# ===================================================================
# Entropy
# ===================================================================


def entropy_from_weights(weights: list[int], include_null: bool = True) -> float:
    """Compute Shannon entropy on normalized weights.

    When include_null=True, adds a complement weight representing
    "no viable path exists." This ensures entropy correctly decreases
    when all path probabilities drop (rather than increasing because
    their relative distribution becomes more uniform).

    Args:
        weights: Non-negative integers (e.g., p_worst_q8 values).
        include_null: If True, add Q8-sum(weights) as null weight.

    Returns:
        Entropy in nats (natural log). Returns 0.0 for empty/zero input.
    """
    if len(weights) == 0:
        return 0.0

    if include_null:
        path_sum = sum(weights)
        null_weight = max(Q8 - path_sum, 0)
        all_weights = list(weights) + [null_weight]
    else:
        all_weights = list(weights)

    total = sum(all_weights)
    if total <= 0:
        return 0.0

    h = 0.0
    for w in all_weights:
        if w > 0:
            q = w / total
            h -= q * math.log(q)
    return h


# ===================================================================
# Candidate pruning
# ===================================================================


def _get_topk_paths(conn: sqlite3.Connection) -> list[dict]:
    """Get Top-K paths from the database."""
    return [dict(r) for r in conn.execute(
        "SELECT rank, p_worst_q8, edge_id_sequence FROM derived_topk ORDER BY rank"
    ).fetchall()]


def _edges_on_topk(paths: list[dict]) -> set[str]:
    """Extract all edge_ids appearing on any Top-K path."""
    result = set()
    for p in paths:
        for eid in json.loads(p["edge_id_sequence"]):
            result.add(eid)
    return result


def _edges_in_correlated_components(
    topk_edges: set[str],
    correlation: dict[str, Any],
    conn: sqlite3.Connection,
) -> set[str]:
    """Find edges in correlation components that share a component with Top-K edges.

    If a Top-K path goes through edge A, and edge B is in the same SCP
    correlation component, probing B affects A's representative. So B
    is a candidate even though it's not on any Top-K path.
    """
    edge_groups = correlation["edge_groups"]

    # Find component signatures for Top-K edges
    topk_sigs = set()
    for eid in topk_edges:
        if eid in edge_groups:
            sig = edge_groups[eid].get("p_worst_sig")
            if sig:
                topk_sigs.add(sig)

    # Find all edges sharing those component signatures
    result = set()
    for eid, group in edge_groups.items():
        sig = group.get("p_worst_sig")
        if sig and sig in topk_sigs:
            result.add(eid)

    return result


def compute_candidates(
    conn: sqlite3.Connection,
    correlation: dict[str, Any],
) -> set[str]:
    """Compute the set of candidate edges worth evaluating for probing.

    Includes:
        - All edges on any Top-K path
        - All edges in correlation components that share a component
          with any Top-K edge
    """
    paths = _get_topk_paths(conn)
    topk_edges = _edges_on_topk(paths)
    corr_edges = _edges_in_correlated_components(topk_edges, correlation, conn)
    return topk_edges | corr_edges


# ===================================================================
# Probe simulation
# ===================================================================


def _simulate_probe(
    baseline_conn: sqlite3.Connection,
    edge_id: str,
    result: str,
    signal_q: int = 95,
    as_of: str | None = None,
    static_correlation: dict[str, Any] | None = None,
) -> sqlite3.Connection:
    """Fork the baseline, inject a probe observation, and rerun the pipeline.

    Args:
        baseline_conn: The baseline DB (not modified).
        edge_id: Edge to probe.
        result: "ALLOW" or "DENY".
        signal_q: Signal quality for the probe (default 95).
        as_of: Reference timestamp for decay (may be None).

    Returns:
        Fork connection with updated beliefs, correlation, and paths.
    """
    fork = fork_db(baseline_conn)

    # Insert observation
    fork.execute(
        """INSERT INTO observations
           (edge_id, probe_type, result, reason_class, strength,
            signal_q, is_counterfactual, constraint_relevant,
            evidence_hash, observed_at)
           VALUES (?, 'REPLAY_SCRIPTED', ?, ?, 'DIRECT', ?, 0, 0, NULL, ?)""",
        (
            edge_id,
            result,
            "UNKNOWN" if result == "ALLOW" else "CONSTRAINT_DENY",
            signal_q,
            as_of,  # probe is "fresh" if as_of provided
        ),
    )

    # Restore mutable replay state to ingested priors before full recompute.
    reset_replay_state(fork)

    # Rerun full pipeline
    apply_all_observations(fork, as_of=as_of)
    validate_all_constraints(fork)
    fork.commit()
    if static_correlation is None:
        corr = compute_correlation(fork)
    else:
        corr = refresh_correlation_representatives(fork, static_correlation)
    search_and_store_top_k(fork, corr)

    return fork


def _get_entropy(conn: sqlite3.Connection) -> float:
    """Compute entropy from the Top-K paths in the database."""
    paths = _get_topk_paths(conn)
    weights = [p["p_worst_q8"] for p in paths]
    return entropy_from_weights(weights)


def _get_edge_p(conn: sqlite3.Connection, edge_id: str) -> float:
    """Get the current posterior probability of an edge."""
    row = conn.execute(
        "SELECT alpha_i, beta_i FROM edges WHERE edge_id = ?", (edge_id,)
    ).fetchone()
    if row is None:
        return 0.5
    return row["alpha_i"] / (row["alpha_i"] + row["beta_i"])


# ===================================================================
# EIG computation
# ===================================================================


def compute_eig(
    baseline_conn: sqlite3.Connection,
    edge_id: str,
    baseline_entropy: float,
    signal_q: int = 95,
    as_of: str | None = None,
    static_correlation: dict[str, Any] | None = None,
) -> dict:
    """Compute Expected Information Gain for probing one edge.

    EIG(e) = H_baseline - [p(e) * H_allow + (1-p(e)) * H_deny]

    Returns:
        {edge_id, eig, h_baseline, h_allow, h_deny, p_edge,
         paths_allow, paths_deny}
    """
    p_e = _get_edge_p(baseline_conn, edge_id)

    # Simulate ALLOW outcome
    fork_allow = _simulate_probe(
        baseline_conn, edge_id, "ALLOW", signal_q, as_of, static_correlation
    )
    h_allow = _get_entropy(fork_allow)
    paths_allow = len(_get_topk_paths(fork_allow))

    # Simulate DENY outcome
    fork_deny = _simulate_probe(
        baseline_conn, edge_id, "DENY", signal_q, as_of, static_correlation
    )
    h_deny = _get_entropy(fork_deny)
    paths_deny = len(_get_topk_paths(fork_deny))

    # Expected entropy after probe
    h_expected = p_e * h_allow + (1 - p_e) * h_deny

    # EIG = reduction in entropy
    eig = baseline_entropy - h_expected

    return {
        "edge_id": edge_id,
        "eig": eig,
        "h_baseline": baseline_entropy,
        "h_allow": h_allow,
        "h_deny": h_deny,
        "p_edge": p_e,
        "paths_allow": paths_allow,
        "paths_deny": paths_deny,
    }


# ===================================================================
# Explanations
# ===================================================================


def _explain_candidate(
    conn: sqlite3.Connection,
    edge_id: str,
    eig_result: dict,
    correlation: dict[str, Any],
    topk_edges: set[str],
) -> list[str]:
    """Generate human-readable explanations for why this edge matters."""
    reasons = []

    # On Top-K path?
    if edge_id in topk_edges:
        reasons.append("appears on a Top-K path")

    # In a correlation component?
    edge_groups = correlation.get("edge_groups", {})
    if edge_id in edge_groups:
        sig = json.loads(edge_groups[edge_id].get("p_worst_sig", "[[]]"))
        if sig and sig[0][0] != "NONE":
            ctype = sig[0][0]
            reasons.append(f"in {ctype} correlation component")

    # Is it the current representative?
    reps = set(correlation.get("p_worst_reps", {}).values())
    if edge_id in reps:
        reasons.append("current correlation group representative")

    # Could become representative?
    p_e = eig_result["p_edge"]
    if p_e > 0.3 and p_e < 0.7:
        reasons.append(f"high uncertainty (p={p_e:.2f}, α≈β)")

    # Stale?
    row = conn.execute(
        "SELECT observed_at FROM observations WHERE edge_id = ? ORDER BY observation_id DESC LIMIT 1",
        (edge_id,),
    ).fetchone()
    if row is None:
        reasons.append("never directly probed")
    elif row["observed_at"] is None:
        reasons.append("no timestamp on last observation")

    # Path impact
    h_b = eig_result["h_baseline"]
    h_a = eig_result["h_allow"]
    h_d = eig_result["h_deny"]
    if h_b > 0:
        if h_d < h_b * 0.1:
            reasons.append("DENY outcome would near-eliminate path uncertainty")
        if h_a < h_b * 0.1:
            reasons.append("ALLOW outcome would near-eliminate path uncertainty")

    return reasons if reasons else ["on candidate path"]


# ===================================================================
# Main planner entry point
# ===================================================================


def plan_probes(
    conn: sqlite3.Connection,
    correlation: dict[str, Any],
    max_candidates: int = 50,
    signal_q: int = 95,
    as_of: str | None = None,
    reuse_static_correlation: bool = True,
) -> dict:
    """Plan which edges to probe next based on Expected Information Gain.

    Args:
        conn: Baseline DB connection (not modified).
        correlation: Output of compute_correlation().
        max_candidates: Maximum number of candidate edges to evaluate.
        signal_q: Signal quality for simulated probes.
        as_of: Reference timestamp for decay.
        reuse_static_correlation: Reuse baseline correlation membership in
            forks and refresh only representatives from fork edge beliefs.

    Returns:
        {
            baseline_entropy: float,
            candidates: [{edge_id, eig, h_allow, h_deny, p_edge,
                         reasons: [str], on_topk: bool, in_component: bool}],
            top_recommendation: {edge_id, eig, reasons},
            component_summary: [{component_sig, edges, best_probe, eig}],
            stats: {total_edges, candidate_edges, forks_executed, runtime_ms},
        }
    """
    import time
    t0 = time.monotonic()

    baseline_entropy = _get_entropy(conn)

    # Get candidates
    total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    candidates = compute_candidates(conn, correlation)
    topk_edges = _edges_on_topk(_get_topk_paths(conn))

    # Limit candidates
    candidate_list = sorted(candidates)[:max_candidates]

    # Score each candidate (2 forks per candidate: ALLOW + DENY)
    results = []
    forks_executed = 0
    static_correlation = correlation if reuse_static_correlation else None
    for eid in candidate_list:
        eig_result = compute_eig(
            conn,
            eid,
            baseline_entropy,
            signal_q,
            as_of,
            static_correlation,
        )
        forks_executed += 2  # ALLOW + DENY
        reasons = _explain_candidate(conn, eid, eig_result, correlation, topk_edges)

        results.append({
            "edge_id": eid,
            "eig": eig_result["eig"],
            "h_allow": eig_result["h_allow"],
            "h_deny": eig_result["h_deny"],
            "p_edge": eig_result["p_edge"],
            "paths_allow": eig_result["paths_allow"],
            "paths_deny": eig_result["paths_deny"],
            "reasons": reasons,
            "on_topk": eid in topk_edges,
            "in_component": eid in (candidates - topk_edges),
        })

    # Sort by EIG descending
    results.sort(key=lambda r: r["eig"], reverse=True)

    # Component-level summary
    component_summary = _build_component_summary(results, correlation)

    # Top recommendation
    top_rec = None
    if results:
        top = results[0]
        top_rec = {
            "edge_id": top["edge_id"],
            "eig": top["eig"],
            "reasons": top["reasons"],
        }

    elapsed_ms = (time.monotonic() - t0) * 1000

    return {
        "baseline_entropy": baseline_entropy,
        "candidates": results,
        "top_recommendation": top_rec,
        "component_summary": component_summary,
        "stats": {
            "total_edges": total_edges,
            "candidate_edges": len(candidate_list),
            "forks_executed": forks_executed,
            "runtime_ms": round(elapsed_ms, 1),
        },
    }


def _build_component_summary(
    results: list[dict],
    correlation: dict[str, Any],
) -> list[dict]:
    """Group probe results by correlation component."""
    edge_groups = correlation.get("edge_groups", {})
    components = correlation.get("components", {})

    # Group by component signature
    comp_map: dict[str, list[dict]] = {}
    for r in results:
        eid = r["edge_id"]
        if eid in edge_groups:
            sig = edge_groups[eid].get("p_worst_sig", "NONE")
        else:
            sig = "NONE"
        comp_map.setdefault(sig, []).append(r)

    summary = []
    for sig, edges in comp_map.items():
        best = max(edges, key=lambda e: e["eig"])
        # Human-readable label
        label = _component_label(sig, components)
        summary.append({
            "component_sig": sig,
            "component_label": label,
            "edge_count": len(edges),
            "best_probe_edge": best["edge_id"],
            "best_eig": best["eig"],
        })

    summary.sort(key=lambda s: s["best_eig"], reverse=True)
    return summary


def _component_label(sig: str, components: dict) -> str:
    """Convert a component signature to a human-readable label."""
    if sig == "NONE":
        return "Uncorrelated"

    comp = components.get(sig, {})
    ctype = comp.get("constraint_type", "")

    if ctype == "SCP":
        # Try to extract a meaningful name from the signature
        return f"SCP group ({len(comp)} edges)" if isinstance(comp, dict) and "constraint_type" in comp else f"SCP: {sig[:12]}..."
    elif ctype == "TRUST_CONDITION":
        return f"Trust group ({len(comp)} edges)" if isinstance(comp, dict) and "constraint_type" in comp else f"Trust: {sig[:12]}..."
    else:
        # Check if sig looks like JSON (old format)
        if sig.startswith("[["):
            try:
                import json as _json
                parsed = _json.loads(sig)
                types = {item[0] for item in parsed if isinstance(item, list) and len(item) >= 1}
                if types == {"NONE"}:
                    return "Uncorrelated"
                return f"Correlated ({', '.join(t for t in types if t != 'NONE')})"
            except Exception:
                pass
        return f"Group: {sig[:16]}..."
