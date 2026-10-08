"""Belief system primitives for ARF-RT (spec §§8-11).

Provides:
  - base_w_q lookup by ObservationStrength
  - Increment calculation: floor(base_w_q * signal_q / 100)
  - Polarity classification (SUPPORT/AGAINST/NEUTRAL)
  - Saturation values for DETERMINISTIC observations
  - Mass cap renormalization
  - Template aggregation eligibility check
"""

from __future__ import annotations

from arf_rt.config import (
    BASE_W_Q,
    MAX_EDGE_MASS,
    MAX_TEMPLATE_MASS,
    SATURATION_ALPHA_ALLOW,
    SATURATION_ALPHA_DENY,
    SATURATION_BETA_ALLOW,
    SATURATION_BETA_DENY,
)
from arf_rt.models.enums import (
    ObservationResult,
    ObservationStrength,
    ObsPolarity,
    ReasonClass,
)
from arf_rt.util.canon import ARFValidationError


def get_base_w_q(strength: str) -> int:
    """Look up base_w_q for an ObservationStrength (spec §9.2).

    Returns:
        Weight integer: DETERMINISTIC=100, DIRECT=95, INFERRED=60, HEURISTIC=30
    """
    val = BASE_W_Q.get(strength)
    if val is None:
        raise ARFValidationError(
            f"Unknown strength for base_w_q: {strength!r}. "
            f"Valid: {list(BASE_W_Q.keys())}"
        )
    return val


def compute_increment(base_w_q: int, signal_q: int) -> int:
    """Compute belief increment: floor(base_w_q * signal_q / 100) (spec §9.2)."""
    return (base_w_q * signal_q) // 100


def classify_polarity(result: str, reason_class: str) -> str:
    """Classify an observation into SUPPORT/AGAINST/NEUTRAL (spec §10).

    Rules:
      ALLOW → SUPPORT
      DENY + CONSTRAINT_DENY → AGAINST
      DENY + MISSING_PERMISSION → AGAINST
      DENY + CONDITION_MISMATCH → NEUTRAL
      DENY + UNKNOWN → NEUTRAL
      ERROR/INCONCLUSIVE → NEUTRAL
      TRANSIENT/THROTTLED → NEUTRAL
    """
    if result == ObservationResult.ALLOW:
        return ObsPolarity.SUPPORT

    if result == ObservationResult.DENY:
        if reason_class in (
            ReasonClass.CONSTRAINT_DENY,
            ReasonClass.MISSING_PERMISSION,
        ):
            return ObsPolarity.AGAINST
        # CONDITION_MISMATCH, UNKNOWN, TRANSIENT, THROTTLED → NEUTRAL
        return ObsPolarity.NEUTRAL

    # ERROR, INCONCLUSIVE → NEUTRAL
    return ObsPolarity.NEUTRAL


def get_saturation_values(result: str) -> tuple[int, int, str, int]:
    """Get saturation alpha, beta, status, frozen for DETERMINISTIC obs (spec §9.3).

    Returns:
        (alpha_i, beta_i, status, frozen)
    """
    if result == ObservationResult.ALLOW:
        return (SATURATION_ALPHA_ALLOW, SATURATION_BETA_ALLOW, "CONFIRMED", 1)
    elif result == ObservationResult.DENY:
        return (SATURATION_ALPHA_DENY, SATURATION_BETA_DENY, "REFUTED", 1)
    else:
        raise ARFValidationError(
            f"DETERMINISTIC saturation requires ALLOW or DENY result, got {result!r}"
        )


def apply_mass_cap(alpha: int, beta: int, cap: int) -> tuple[int, int]:
    """Renormalize alpha/beta if total mass exceeds cap (spec §9.5).

    Formula:
      mass = alpha + beta
      if mass > cap:
        alpha = max(1, floor(alpha * cap / mass))
        beta = max(1, cap - alpha)

    Returns:
        (capped_alpha, capped_beta)
    """
    mass = alpha + beta
    if mass <= cap:
        return (alpha, beta)

    new_alpha = max(1, (alpha * cap) // mass)
    new_beta = max(1, cap - new_alpha)
    return (new_alpha, new_beta)


def is_template_eligible(
    is_counterfactual: int,
    strength: str,
    result: str,
) -> bool:
    """Check if an observation is eligible for template aggregation (spec §11.1).

    Eligible iff:
      - is_counterfactual == 0
      - strength in {DIRECT, DETERMINISTIC, INFERRED}
      - result in {ALLOW, DENY}

    HEURISTIC does NOT update templates.
    """
    if is_counterfactual != 0:
        return False

    if strength not in (
        ObservationStrength.DIRECT,
        ObservationStrength.DETERMINISTIC,
        ObservationStrength.INFERRED,
    ):
        return False

    if result not in (
        ObservationResult.ALLOW,
        ObservationResult.DENY,
    ):
        return False

    return True
