"""
arf_rt/util/math_stats.py - Information theory and discrete probability calculations.

Provides routines for computing Shannon entropy, Kullback-Leibler divergence,
and probability normalization over candidate path vectors.
"""

from __future__ import annotations

import math
from typing import Sequence


def shannon_entropy(probabilities: Sequence[float]) -> float:
    """Calculate Shannon entropy H(P) in nats for a discrete probability distribution.

    Args:
        probabilities: Sequence of non-negative probabilities summing to ~1.0.

    Returns:
        Entropy value in nats (non-negative float).
    """
    total = sum(probabilities)
    if total <= 0:
        return 0.0

    entropy = 0.0
    for p in probabilities:
        if p > 0:
            norm_p = p / total
            entropy -= norm_p * math.log(norm_p)
    return entropy


def normalize_distribution(weights: Sequence[float]) -> list[float]:
    """Normalize a sequence of non-negative weights into a probability distribution."""
    total = sum(weights)
    if total <= 0:
        n = len(weights)
        return [1.0 / n] * n if n > 0 else []
    return [w / total for w in weights]


def kl_divergence(p_dist: Sequence[float], q_dist: Sequence[float]) -> float:
    """Calculate discrete Kullback-Leibler divergence D_KL(P || Q) in nats."""
    div = 0.0
    for p, q in zip(p_dist, q_dist):
        if p > 0:
            if q <= 0:
                return float("inf")
            div += p * math.log(p / q)
    return div
