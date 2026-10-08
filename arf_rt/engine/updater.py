"""Belief updater for ARF-RT (spec §§9-11).

Core function: apply_observation()
  1. Classify polarity (SUPPORT/AGAINST/NEUTRAL)
  2. Compute increment
  3. Handle DETERMINISTIC saturation
  4. Handle frozen collision rule
  5. Update edge alpha/beta/status/frozen/flags
  6. Write edge_updates audit row
  7. Trigger template aggregation (same inc + polarity)
  8. Apply mass caps

Order is fixed per spec §11.3:
  edge update → template aggregation → mass caps
"""

from __future__ import annotations

import json
import sqlite3

from arf_rt.config import MAX_EDGE_MASS
from arf_rt.engine.belief import (
    apply_mass_cap,
    classify_polarity,
    compute_increment,
    get_base_w_q,
    get_saturation_values,
    is_template_eligible,
)
from arf_rt.engine.decay import apply_decay_to_increment
from arf_rt.engine.templates import aggregate_to_template
from arf_rt.models.enums import ObservationStrength, ObsPolarity
from arf_rt.util.canon import ARFValidationError, make_flags_json


def apply_observation(
    conn: sqlite3.Connection,
    observation_id: int,
    edge_id: str,
    probe_type: str,
    result: str,
    reason_class: str,
    strength: str,
    signal_q: int,
    is_counterfactual: int,
    constraint_relevant: int,
    evidence_hash: str | None,
    observed_at: str | None = None,
    as_of: str | None = None,
) -> dict:
    """Apply a single observation to its edge and template.

    Returns a dict summarizing what happened:
      {polarity, increment, frozen_before, frozen_after,
       alpha_before, beta_before, alpha_after, beta_after,
       status_before, status_after, conflict_set, template_updated}
    """
    # 1. Classify polarity
    polarity = classify_polarity(result, reason_class)

    # 2. Compute increment (with optional decay)
    base_w = get_base_w_q(strength)
    inc = compute_increment(base_w, signal_q)

    if as_of is not None:
        inc = apply_decay_to_increment(inc, observed_at, as_of)

    # 3. Read current edge state
    row = conn.execute(
        "SELECT alpha_i, beta_i, status, frozen, flags_json, template_id "
        "FROM edges WHERE edge_id = ?",
        (edge_id,),
    ).fetchone()
    if row is None:
        raise ARFValidationError(f"Edge {edge_id} not found")

    alpha_before = row["alpha_i"]
    beta_before = row["beta_i"]
    status_before = row["status"]
    frozen_before = row["frozen"]
    flags_before = row["flags_json"]
    template_id = row["template_id"]

    flags = json.loads(flags_before)

    # Start with current values
    alpha_after = alpha_before
    beta_after = beta_before
    status_after = status_before
    frozen_after = frozen_before
    conflict_set = False
    template_updated = False

    # 4. Handle DETERMINISTIC saturation (spec §9.3)
    if strength == ObservationStrength.DETERMINISTIC and result in ("ALLOW", "DENY"):
        if frozen_before == 1:
            # Frozen collision rule (spec §9.4)
            # Never modify alpha/beta/status
            # Check for conflict: contradictory DIRECT/DETERMINISTIC non-counterfactual
            if is_counterfactual == 0:
                # Is this contradictory to current state?
                current_is_allow = (status_before == "CONFIRMED")
                obs_is_allow = (result == "ALLOW")
                if current_is_allow != obs_is_allow:
                    flags["conflict"] = True
                    conflict_set = True
        else:
            # Not frozen: saturate
            sat_alpha, sat_beta, sat_status, sat_frozen = get_saturation_values(result)
            alpha_after = sat_alpha
            beta_after = sat_beta
            status_after = sat_status
            frozen_after = sat_frozen
    elif frozen_before == 1:
        # Frozen but not DETERMINISTIC — frozen collision rule
        # Always record obs, never modify alpha/beta/status
        if is_counterfactual == 0 and strength in (
            ObservationStrength.DIRECT,
            ObservationStrength.DETERMINISTIC,
        ):
            # Check for contradiction
            current_is_allow = (status_before == "CONFIRMED")
            obs_is_allow = (result == "ALLOW")
            if current_is_allow != obs_is_allow:
                flags["conflict"] = True
                conflict_set = True
    else:
        # Normal update (not frozen, not DETERMINISTIC saturation)
        if polarity == ObsPolarity.SUPPORT:
            alpha_after = alpha_before + inc
        elif polarity == ObsPolarity.AGAINST:
            beta_after = beta_before + inc
        # NEUTRAL: no change

        # Update status based on evidence (clear prior_only)
        if polarity != ObsPolarity.NEUTRAL:
            if polarity == ObsPolarity.SUPPORT:
                status_after = "CONFIRMED"
            else:
                status_after = "REFUTED"

    # 5. Apply edge mass cap (spec §9.5)
    if frozen_after == 0:
        alpha_after, beta_after = apply_mass_cap(alpha_after, beta_after, MAX_EDGE_MASS)

    # Clear prior_only if we have observations
    flags["prior_only"] = False

    flags_after = make_flags_json(**flags)

    # 6. Write edge update
    conn.execute(
        """UPDATE edges
           SET alpha_i = ?, beta_i = ?, status = ?, frozen = ?, flags_json = ?
           WHERE edge_id = ?""",
        (alpha_after, beta_after, status_after, frozen_after, flags_after, edge_id),
    )

    # 7. Write audit trail (spec §7.8)
    conn.execute(
        """INSERT INTO edge_updates
           (edge_id, observation_id, alpha_before, beta_before,
            alpha_after, beta_after, status_before, status_after,
            frozen_before, frozen_after, flags_json_before, flags_json_after,
            polarity, increment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            edge_id, observation_id,
            alpha_before, beta_before, alpha_after, beta_after,
            status_before, status_after,
            frozen_before, frozen_after,
            flags_before, flags_after,
            polarity, inc,
        ),
    )

    # 8. Template aggregation (spec §11)
    if is_template_eligible(is_counterfactual, strength, result):
        aggregate_to_template(conn, template_id, polarity, inc)
        template_updated = True

    return {
        "polarity": polarity,
        "increment": inc,
        "frozen_before": frozen_before,
        "frozen_after": frozen_after,
        "alpha_before": alpha_before,
        "beta_before": beta_before,
        "alpha_after": alpha_after,
        "beta_after": beta_after,
        "status_before": status_before,
        "status_after": status_after,
        "conflict_set": conflict_set,
        "template_updated": template_updated,
    }


def apply_all_observations(
    conn: sqlite3.Connection,
    as_of: str | None = None,
) -> list[dict]:
    """Apply all observations in the DB to their edges, in insertion order.

    Args:
        conn: Database connection.
        as_of: ISO 8601 reference timestamp for decay. If None, no decay.

    Returns list of result dicts from apply_observation().
    """
    rows = conn.execute(
        """SELECT observation_id, edge_id, probe_type, result, reason_class,
                  strength, signal_q, is_counterfactual, constraint_relevant,
                  evidence_hash, observed_at
           FROM observations ORDER BY observation_id"""
    ).fetchall()

    results = []
    for row in rows:
        r = apply_observation(
            conn,
            observation_id=row["observation_id"],
            edge_id=row["edge_id"],
            probe_type=row["probe_type"],
            result=row["result"],
            reason_class=row["reason_class"],
            strength=row["strength"],
            signal_q=row["signal_q"],
            is_counterfactual=row["is_counterfactual"],
            constraint_relevant=row["constraint_relevant"],
            evidence_hash=row["evidence_hash"],
            observed_at=row["observed_at"],
            as_of=as_of,
        )
        results.append(r)

    return results


def reset_replay_state(conn: sqlite3.Connection) -> None:
    """Restore mutable replay state to immutable ingested base values.

    Planner, episode, and evaluation forks append observations and then replay
    the full observation log. Before replay, edge beliefs and template
    aggregates must return to the scenario state captured at ingest, not to
    hard-coded uniform priors or already-aggregated template values.
    """
    conn.execute(
        """UPDATE edges
           SET alpha_i = base_alpha_i,
               beta_i = base_beta_i,
               status = base_status,
               frozen = base_frozen,
               flags_json = base_flags_json"""
    )
    conn.execute(
        """UPDATE templates
           SET alpha_agg_i = base_alpha_agg_i,
               beta_agg_i = base_beta_agg_i,
               sample_count = base_sample_count"""
    )
    conn.execute("DELETE FROM edge_updates")
    conn.execute("DELETE FROM derived_topk")
