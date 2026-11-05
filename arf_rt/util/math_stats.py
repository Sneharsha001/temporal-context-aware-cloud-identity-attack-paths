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


def js_divergence(p_dist: Sequence[float], q_dist: Sequence[float]) -> float:
    """Calculate Jensen-Shannon divergence (symmetric, bounded).

    JSD(P || Q) = 0.5 * D_KL(P || M) + 0.5 * D_KL(Q || M)
    where M = 0.5 * (P + Q)

    Args:
        p_dist: First probability distribution.
        q_dist: Second probability distribution.

    Returns:
        JSD value in nats (0 to ln(2)).
    """
    # Normalize both distributions
    p = normalize_distribution(p_dist)
    q = normalize_distribution(q_dist)

    # Compute mixture distribution
    m = [(p[i] + q[i]) / 2 for i in range(len(p))]

    # JSD = 0.5 * KL(P || M) + 0.5 * KL(Q || M)
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity in range [-1, 1], or 0 if either vector is zero.
    """
    if len(a) != len(b):
        raise ValueError("Vectors must have same length")

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def euclidean_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Calculate Euclidean distance between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Euclidean distance (non-negative).
    """
    if len(a) != len(b):
        raise ValueError("Vectors must have same length")

    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def mean(values: Sequence[float]) -> float:
    """Calculate arithmetic mean of values.

    Args:
        values: Sequence of numbers.

    Returns:
        Mean value, or 0 if empty.
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values: Sequence[float], ddof: int = 0) -> float:
    """Calculate variance of values.

    Args:
        values: Sequence of numbers.
        ddof: Delta degrees of freedom (0 for population, 1 for sample).

    Returns:
        Variance, or 0 if insufficient data.
    """
    n = len(values)
    if n <= ddof:
        return 0.0

    m = mean(values)
    return sum((x - m) ** 2 for x in values) / (n - ddof)


def standard_deviation(values: Sequence[float], ddof: int = 0) -> float:
    """Calculate standard deviation of values.

    Args:
        values: Sequence of numbers.
        ddof: Delta degrees of freedom (0 for population, 1 for sample).

    Returns:
        Standard deviation.
    """
    return math.sqrt(variance(values, ddof))
