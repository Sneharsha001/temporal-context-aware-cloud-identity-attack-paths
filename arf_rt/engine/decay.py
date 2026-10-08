"""Belief decay: stale observations lose weight over time.

Decay is opt-in. When --as-of is provided, each observation's effective
increment is scaled by:

    decay_factor = max(2^(-age_days / half_life_days), DECAY_MIN_WEIGHT)

where age_days = (as_of - observed_at).days.

If an observation has no observed_at timestamp, it is not decayed
(treated as current).  If --as-of is not provided, no decay occurs
and all existing behavior is preserved.

Timestamp semantics:
    - observed_at: when the observation occurred in the external world
      (e.g., CloudTrail event timestamp, PMapper scan timestamp).
      Set by the adapter that produced the observation.
    - created_at: when ARF-RT ingested/wrote the row to the database.
      Internal bookkeeping only; NEVER used for decay.
    Adapters MUST set observed_at from the source event timestamp.
    Using created_at for decay would mean "time since import," not
    "time since observation," which is not what decay models.

Future observation policy:
    If observed_at > as_of (observation is "in the future" relative to
    the reference point), age is treated as 0 and no decay is applied.
    This supports scenarios where as_of is set to an arbitrary past
    date for historical analysis.

Bounds:
    - Factor floored at DECAY_MIN_WEIGHT (default 0.01): very old
      evidence never fully disappears, preserving structural signal.
    - Increment floored at 1: an observation always contributes at
      least 1 unit of evidence.
    - Half-life is currently global (90 days). Future work may support
      per-strength or per-template half-lives for ephemeral vs.
      structural signals.

Properties:
    - Deterministic: same as_of → same output
    - Replay-friendly: full recompute from observations, no mutable state
    - Monotonic: older observations always have equal or lower weight
    - Bounded: weight never drops below DECAY_MIN_WEIGHT (default 1%)
    - Half-life default: 90 days (quarterly reassessment cycle)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from arf_rt.config import DECAY_HALF_LIFE_DAYS, DECAY_MIN_WEIGHT


def compute_decay_factor(
    observed_at: str | None,
    as_of: str | None,
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
    min_weight: float = DECAY_MIN_WEIGHT,
) -> float:
    """Compute the decay multiplier for an observation.

    Args:
        observed_at: ISO 8601 timestamp of the observation (may be None).
        as_of: ISO 8601 reference timestamp (may be None → no decay).
        half_life_days: Half-life in days (default 90).
        min_weight: Floor for the decay factor (default 0.01).

    Returns:
        Decay factor in [min_weight, 1.0].
        Returns 1.0 (no decay) if either timestamp is None.
    """
    if observed_at is None or as_of is None:
        return 1.0

    try:
        t_obs = _parse_iso(observed_at)
        t_ref = _parse_iso(as_of)
    except (ValueError, TypeError):
        return 1.0

    age_days = (t_ref - t_obs).total_seconds() / 86400.0

    if age_days <= 0:
        return 1.0

    # Exponential decay: 2^(-age / half_life)
    factor = math.pow(2.0, -age_days / half_life_days)

    return max(factor, min_weight)


def apply_decay_to_increment(
    increment: int,
    observed_at: str | None,
    as_of: str | None,
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
    min_weight: float = DECAY_MIN_WEIGHT,
) -> int:
    """Apply decay to an observation's increment.

    Args:
        increment: The raw increment (from compute_increment).
        observed_at: ISO 8601 timestamp of the observation.
        as_of: ISO 8601 reference timestamp.
        half_life_days: Half-life in days.
        min_weight: Floor for the decay factor.

    Returns:
        Decayed increment, at least 1 if original increment was ≥ 1.
    """
    if increment <= 0:
        return increment

    factor = compute_decay_factor(observed_at, as_of, half_life_days, min_weight)

    if factor >= 1.0:
        return increment

    decayed = int(round(increment * factor))
    return max(decayed, 1)  # never reduce to 0


def _parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 string to a timezone-aware datetime."""
    # Handle common formats
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
