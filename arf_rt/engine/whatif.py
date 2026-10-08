"""What-If analysis for ARF-RT (spec §17).

Fork: SQLite backup API → new in-memory DB.
Baseline opened read-only. Immutability verified via snapshot hash.

Forced refute: Insert WHATIF_FORCED observation with is_counterfactual=1,
strength=DETERMINISTIC, result=DENY, reason_class=CONSTRAINT_DENY.
Override frozen: alpha/beta to deterministic deny, status=REFUTED,
frozen=1, flags_json.counterfactual_override=true. Do NOT set conflict.

Counterfactual exclusions: template aggregation, constraint validation,
evidence coverage, EIG scoring.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from arf_rt.config import MAX_EDGE_MASS
from arf_rt.engine.belief import get_saturation_values
from arf_rt.engine.constraints import validate_all_constraints
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.snapshot import canonical_run_hash, full_state_export
from arf_rt.engine.updater import apply_all_observations
from arf_rt.reporting.diff_report import generate_diff_report
from arf_rt.util.canon import ARFValidationError, make_flags_json


def fork_db(baseline_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Create a fork of the baseline DB using SQLite backup API (spec §17).

    The fork is an independent in-memory copy. The baseline is not modified.

    Returns:
        New connection to the forked in-memory DB.
    """
    fork_conn = sqlite3.connect(":memory:")
    fork_conn.row_factory = sqlite3.Row
    baseline_conn.backup(fork_conn)
    fork_conn.execute("PRAGMA journal_mode=WAL")
    fork_conn.execute("PRAGMA foreign_keys=ON")
    return fork_conn


def forced_refute(
    conn: sqlite3.Connection,
    edge_id: str,
    signal_q: int = 100,
) -> dict:
    """Force-refute an edge in a what-if fork (spec §17).

    Inserts a WHATIF_FORCED observation and overrides edge state to
    deterministic deny, regardless of current frozen state.

    Args:
        conn: Fork DB connection (NOT baseline).
        edge_id: Edge to refute.
        signal_q: Signal quality (default 100).

    Returns:
        Dict with observation details and before/after state.
    """
    # Verify edge exists
    edge = conn.execute(
        "SELECT alpha_i, beta_i, status, frozen, flags_json FROM edges WHERE edge_id = ?",
        (edge_id,),
    ).fetchone()
    if edge is None:
        raise ARFValidationError(f"Edge {edge_id} not found")

    alpha_before = edge["alpha_i"]
    beta_before = edge["beta_i"]
    status_before = edge["status"]
    frozen_before = edge["frozen"]
    flags_before = json.loads(edge["flags_json"])

    # 1. Insert WHATIF_FORCED observation
    conn.execute(
        """INSERT INTO observations
           (edge_id, probe_type, result, reason_class, strength,
            signal_q, is_counterfactual, constraint_relevant, evidence_hash)
           VALUES (?, 'WHATIF_FORCED', 'DENY', 'CONSTRAINT_DENY',
                   'DETERMINISTIC', ?, 1, 0, NULL)""",
        (edge_id, signal_q),
    )

    # 2. Override edge to deterministic deny
    sat_alpha, sat_beta, sat_status, sat_frozen = get_saturation_values("DENY")

    # Set counterfactual_override flag, do NOT set conflict
    flags_after = dict(flags_before)
    flags_after["counterfactual_override"] = True
    flags_after["prior_only"] = False
    # Explicitly do NOT set conflict — spec §17 requirement
    flags_json_after = make_flags_json(**flags_after)

    conn.execute(
        """UPDATE edges
           SET alpha_i = ?, beta_i = ?, status = ?, frozen = ?, flags_json = ?
           WHERE edge_id = ?""",
        (sat_alpha, sat_beta, sat_status, sat_frozen, flags_json_after, edge_id),
    )

    # 3. Write audit trail
    obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]
    conn.execute(
        """INSERT INTO edge_updates
           (edge_id, observation_id, alpha_before, beta_before,
            alpha_after, beta_after, status_before, status_after,
            frozen_before, frozen_after, flags_json_before, flags_json_after,
            polarity, increment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AGAINST', 0)""",
        (
            edge_id, obs_id,
            alpha_before, beta_before, sat_alpha, sat_beta,
            status_before, sat_status,
            frozen_before, sat_frozen,
            json.dumps(flags_before, sort_keys=True, separators=(",", ":")),
            flags_json_after,
        ),
    )

    conn.commit()

    return {
        "edge_id": edge_id,
        "observation_id": obs_id,
        "alpha_before": alpha_before,
        "beta_before": beta_before,
        "alpha_after": sat_alpha,
        "beta_after": sat_beta,
        "status_before": status_before,
        "status_after": sat_status,
        "frozen_before": frozen_before,
        "frozen_after": sat_frozen,
        "counterfactual_override": True,
    }


def run_whatif(
    baseline_conn: sqlite3.Connection,
    refute_edge_ids: list[str],
    signal_q: int = 100,
) -> dict[str, Any]:
    """Run a complete what-if analysis (spec §17).

    1. Record baseline hash
    2. Fork baseline
    3. Force-refute specified edges
    4. Re-run correlation + path search on fork
    5. Generate diff report
    6. Verify baseline immutability

    Args:
        baseline_conn: Baseline DB (will NOT be modified).
        refute_edge_ids: Edges to force-refute in the fork.
        signal_q: Signal quality for forced observations.

    Returns:
        {
            baseline_hash: str,
            fork_hash: str,
            baseline_verified: bool,
            refute_results: list[dict],
            diff_report: dict,
            fork_export: dict,
        }
    """
    # 1. Record baseline hash
    baseline_hash = canonical_run_hash(baseline_conn)
    baseline_export = full_state_export(baseline_conn)

    # 2. Fork
    fork_conn = fork_db(baseline_conn)

    # 3. Force-refute
    refute_results = []
    for eid in refute_edge_ids:
        r = forced_refute(fork_conn, eid, signal_q)
        refute_results.append(r)

    # 4. Re-run pipeline on fork
    # Note: observations already applied during ingest+update on baseline.
    # The forced_refute already set the edge state directly.
    # We need to re-run correlation + paths on the fork.
    validate_all_constraints(fork_conn)
    fork_conn.commit()

    # Clear old derived_topk before re-computing
    fork_conn.execute("DELETE FROM derived_topk")
    fork_conn.commit()

    corr = compute_correlation(fork_conn)
    search_and_store_top_k(fork_conn, corr)

    fork_export = full_state_export(fork_conn)
    fork_hash = fork_export["canonical_run_hash"]

    # 5. Generate diff
    diff = generate_diff_report(baseline_export, fork_export)

    # 6. Verify baseline immutability
    baseline_hash_after = canonical_run_hash(baseline_conn)
    baseline_verified = (baseline_hash == baseline_hash_after)

    fork_conn.close()

    return {
        "baseline_hash": baseline_hash,
        "fork_hash": fork_hash,
        "baseline_verified": baseline_verified,
        "refute_results": refute_results,
        "diff_report": diff,
        "fork_export": fork_export,
    }
