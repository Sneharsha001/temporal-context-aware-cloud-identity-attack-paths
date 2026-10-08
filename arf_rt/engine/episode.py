"""Realized Information Gain (RIG) episode runner.

Measures the actual entropy reduction after applying a probe outcome,
compared to the Expected Information Gain (EIG) predicted by the planner.

Episode protocol:
    1. Freeze baseline: run pipeline, record H_before, top-K, planner output
    2. Apply one probe outcome: insert DIRECT observation
    3. Re-run pipeline: compute H_after
    4. RIG = H_before - H_after
    5. Log episode results tied to call_log via run_hash

Two forced episodes demonstrate the system works:
    - Episode DENY: confirms the block → entropy drops (more certain)
    - Episode ALLOW: surprises the model → entropy rises (more uncertainty)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from arf_rt.engine.constraints import validate_all_constraints
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.planner import (
    _get_entropy,
    _get_topk_paths,
    compute_eig,
    plan_probes,
)
from arf_rt.engine.snapshot import canonical_run_hash
from arf_rt.engine.updater import apply_all_observations, reset_replay_state
from arf_rt.engine.whatif import fork_db


def run_episode(
    baseline_conn: sqlite3.Connection,
    edge_id: str,
    outcome: str,
    signal_q: int = 100,
    as_of: str | None = None,
) -> dict:
    """Run a single realized-gain episode.

    Args:
        baseline_conn: Pipeline DB after full run (not modified).
        edge_id: Edge to probe.
        outcome: "ALLOW" or "DENY".
        signal_q: Signal quality for the probe.
        as_of: Reference timestamp.

    Returns:
        {
            edge_id, outcome,
            h_before, h_after, rig,
            eig, eig_predicted_h (h_allow or h_deny matching outcome),
            prediction_error (|predicted_h - actual_h|),
            paths_before, paths_after,
            rep_before, rep_after, rep_changed,
            baseline_hash, episode_hash,
        }
    """
    assert outcome in ("ALLOW", "DENY"), f"outcome must be ALLOW or DENY, got {outcome}"

    # --- Step 0: Freeze baseline ---
    h_before = _get_entropy(baseline_conn)
    paths_before = _get_topk_paths(baseline_conn)
    baseline_hash = canonical_run_hash(baseline_conn)
    corr_before = compute_correlation(baseline_conn)

    # Get baseline representative for the edge's component
    edge_groups = corr_before.get("edge_groups", {})
    p_worst_reps = corr_before.get("p_worst_reps", {})
    rep_before = None
    if edge_id in edge_groups:
        sig = edge_groups[edge_id].get("p_worst_sig")
        if sig:
            rep_before = p_worst_reps.get(sig)

    # Compute EIG for this edge
    eig_result = compute_eig(baseline_conn, edge_id, h_before, signal_q, as_of)
    eig = eig_result["eig"]
    predicted_h = eig_result["h_allow"] if outcome == "ALLOW" else eig_result["h_deny"]

    # --- Step 2: Apply probe outcome on fork ---
    fork = fork_db(baseline_conn)

    fork.execute(
        """INSERT INTO observations
           (edge_id, probe_type, result, reason_class, strength,
            signal_q, is_counterfactual, constraint_relevant,
            evidence_hash, observed_at)
           VALUES (?, 'REPLAY_SCRIPTED', ?, ?, 'DIRECT', ?, 0, 0, NULL, ?)""",
        (
            edge_id,
            outcome,
            "UNKNOWN" if outcome == "ALLOW" else "CONSTRAINT_DENY",
            signal_q,
            as_of,
        ),
    )

    # Restore mutable replay state to ingested priors and rerun.
    reset_replay_state(fork)

    apply_all_observations(fork, as_of=as_of)
    validate_all_constraints(fork)
    fork.commit()
    corr_after = compute_correlation(fork)
    search_and_store_top_k(fork, corr_after)

    # --- Step 3: Measure ---
    h_after = _get_entropy(fork)
    paths_after = _get_topk_paths(fork)
    episode_hash = canonical_run_hash(fork)

    # Check representative change
    rep_after = None
    if edge_id in corr_after.get("edge_groups", {}):
        sig = corr_after["edge_groups"][edge_id].get("p_worst_sig")
        if sig:
            rep_after = corr_after.get("p_worst_reps", {}).get(sig)

    # --- Step 4: Compute RIG ---
    rig = h_before - h_after
    prediction_error = abs(predicted_h - h_after)

    return {
        "edge_id": edge_id,
        "outcome": outcome,
        "h_before": h_before,
        "h_after": h_after,
        "rig": rig,
        "eig": eig,
        "eig_predicted_h": predicted_h,
        "prediction_error": prediction_error,
        "paths_before": len(paths_before),
        "paths_after": len(paths_after),
        "rep_before": rep_before,
        "rep_after": rep_after,
        "rep_changed": rep_before != rep_after,
        "baseline_hash": baseline_hash,
        "episode_hash": episode_hash,
    }


def format_episode_report(
    episode: dict,
    conn: sqlite3.Connection,
) -> str:
    """Format an episode result as Markdown."""
    from arf_rt.reporting.analysis_report import edge_name

    ename = edge_name(conn, episode["edge_id"])
    outcome = episode["outcome"]

    md = []
    md.append(f"### Episode: {ename} → {outcome}")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| Probe target | {ename} |")
    md.append(f"| Outcome | {outcome} |")
    md.append(f"| H before | {episode['h_before']:.4f} |")
    md.append(f"| H after | {episode['h_after']:.4f} |")
    md.append(f"| **Realized Information Gain (RIG)** | **{episode['rig']:+.4f}** |")
    md.append(f"| Expected Information Gain (EIG) | {episode['eig']:.4f} |")
    md.append(f"| Planner predicted H after | {episode['eig_predicted_h']:.4f} |")
    md.append(f"| Prediction error | {episode['prediction_error']:.4f} |")
    md.append(f"| Paths before | {episode['paths_before']} |")
    md.append(f"| Paths after | {episode['paths_after']} |")

    if episode["rep_before"]:
        rep_b = edge_name(conn, episode["rep_before"])
        rep_a = edge_name(conn, episode["rep_after"]) if episode["rep_after"] else "none"
        md.append(f"| Representative before | {rep_b} |")
        md.append(f"| Representative after | {rep_a} |")
        md.append(f"| Representative changed | {'Yes' if episode['rep_changed'] else 'No'} |")

    md.append(f"| Baseline hash | `{episode['baseline_hash'][:24]}...` |")
    md.append(f"| Episode hash | `{episode['episode_hash'][:24]}...` |")
    md.append("")

    # Interpretation
    if episode["rig"] > 0:
        md.append(f"Entropy decreased by {episode['rig']:.4f} nats — the {outcome} outcome reduced uncertainty about path viability.")
    elif episode["rig"] < 0:
        md.append(f"Entropy increased by {abs(episode['rig']):.4f} nats — the {outcome} outcome shifted probability mass toward viable paths, increasing distributional uncertainty.")
    else:
        md.append("Entropy unchanged — this probe did not affect path uncertainty.")

    if episode["prediction_error"] < 0.01:
        md.append(f"Planner prediction was exact (error = {episode['prediction_error']:.4f}).")
    elif episode["prediction_error"] < 0.1:
        md.append(f"Planner prediction was close (error = {episode['prediction_error']:.4f}).")
    else:
        md.append(f"Planner prediction diverged (error = {episode['prediction_error']:.4f}) — correlation dynamics may have shifted unexpectedly.")

    md.append("")
    return "\n".join(md)
