"""Template aggregation for ARF-RT (spec §11).

Templates aggregate beliefs across edges with the same
(provider, edge_type, features_fp, feature_schema_version).

Spec §11.2: Same increment + polarity as the edge update.
Spec §11.3: Order is edge update → template aggregation → mass caps.
"""

from __future__ import annotations

import sqlite3

from arf_rt.config import MAX_TEMPLATE_MASS
from arf_rt.engine.belief import apply_mass_cap
from arf_rt.models.enums import ObsPolarity
from arf_rt.util.canon import ARFValidationError


def aggregate_to_template(
    conn: sqlite3.Connection,
    template_id: str,
    polarity: str,
    increment: int,
) -> None:
    """Apply an observation's contribution to a template (spec §11.2).

    Caller is responsible for eligibility check (spec §11.1).
    This function only handles the actual aggregation math.

    Args:
        conn: DB connection (within a transaction).
        template_id: Template to update.
        polarity: SUPPORT or AGAINST (NEUTRAL should not be passed).
        increment: The inc value (same as edge update).
    """
    if polarity == ObsPolarity.NEUTRAL:
        return  # No-op for NEUTRAL (should not reach here if eligibility checked)

    if increment == 0:
        return  # No-op for zero increment

    row = conn.execute(
        "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates "
        "WHERE template_id = ?",
        (template_id,),
    ).fetchone()

    if row is None:
        raise ARFValidationError(f"Template {template_id} not found")

    alpha = row["alpha_agg_i"]
    beta = row["beta_agg_i"]
    count = row["sample_count"]

    # Apply same polarity routing as edge (spec §11.2)
    if polarity == ObsPolarity.SUPPORT:
        alpha += increment
    elif polarity == ObsPolarity.AGAINST:
        beta += increment

    # Apply template mass cap (spec §11.3)
    alpha, beta = apply_mass_cap(alpha, beta, MAX_TEMPLATE_MASS)

    conn.execute(
        """UPDATE templates
           SET alpha_agg_i = ?, beta_agg_i = ?, sample_count = ?
           WHERE template_id = ?""",
        (alpha, beta, count + 1, template_id),
    )
