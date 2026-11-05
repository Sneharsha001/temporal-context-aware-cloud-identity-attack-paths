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


def median(values: Sequence[float]) -> float:
    """Calculate median of values.

    Args:
        values: Sequence of numbers.

    Returns:
        Median value, or 0 if empty.
    """
    if not values:
        return 0.0

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2

    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]


def quantile(values: Sequence[float], q: float) -> float:
    """Calculate quantile of values.

    Args:
        values: Sequence of numbers.
        q: Quantile (0 to 1).

    Returns:
        Quantile value.
    """
    if not values:
        return 0.0

    if q < 0 or q > 1:
        raise ValueError("Quantile must be between 0 and 1")

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    if q == 0:
        return sorted_vals[0]
    if q == 1:
        return sorted_vals[-1]

    # Linear interpolation
    idx = q * (n - 1)
    lower = int(math.floor(idx))
    upper = int(math.ceil(idx))

    if lower == upper:
        return sorted_vals[lower]

    weight = idx - lower
    return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight


def percentile(values: Sequence[float], p: float) -> float:
    """Calculate percentile of values.

    Args:
        values: Sequence of numbers.
        p: Percentile (0 to 100).

    Returns:
        Percentile value.
    """
    return quantile(values, p / 100.0)


def iqr(values: Sequence[float]) -> float:
    """Calculate interquartile range (IQR).

    Args:
        values: Sequence of numbers.

    Returns:
        IQR value (Q3 - Q1).
    """
    q1 = quantile(values, 0.25)
    q3 = quantile(values, 0.75)
    return q3 - q1


def skewness(values: Sequence[float]) -> float:
    """Calculate sample skewness (measure of asymmetry).

    Args:
        values: Sequence of numbers.

    Returns:
        Skewness value.
    """
    n = len(values)
    if n < 3:
        return 0.0

    m = mean(values)
    std = standard_deviation(values, ddof=1)

    if std == 0:
        return 0.0

    return (sum((x - m) ** 3 for x in values) / n) / (std ** 3)


def kurtosis(values: Sequence[float]) -> float:
    """Calculate sample kurtosis (measure of tail heaviness).

    Args:
        values: Sequence of numbers.

    Returns:
        Excess kurtosis (normal distribution = 0).
    """
    n = len(values)
    if n < 4:
        return 0.0

    m = mean(values)
    std = standard_deviation(values, ddof=1)

    if std == 0:
        return 0.0

    return (sum((x - m) ** 4 for x in values) / n) / (std ** 4) - 3


def covariance(x: Sequence[float], y: Sequence[float]) -> float:
    """Calculate covariance between two sequences.

    Args:
        x: First sequence.
        y: Second sequence.

    Returns:
        Covariance value.
    """
    if len(x) != len(y):
        raise ValueError("Sequences must have same length")

    n = len(x)
    if n < 2:
        return 0.0

    mx = mean(x)
    my = mean(y)

    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)


def correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Calculate Pearson correlation coefficient.

    Args:
        x: First sequence.
        y: Second sequence.

    Returns:
        Correlation coefficient in [-1, 1].
    """
    if len(x) != len(y):
        raise ValueError("Sequences must have same length")

    n = len(x)
    if n < 2:
        return 0.0

    std_x = standard_deviation(x, ddof=1)
    std_y = standard_deviation(y, ddof=1)

    if std_x == 0 or std_y == 0:
        return 0.0

    return covariance(x, y) / (std_x * std_y)


def cross_entropy(p: Sequence[float], q: Sequence[float]) -> float:
    """Calculate cross-entropy H(P, Q) = -sum(P * log(Q)).

    Args:
        p: True distribution.
        q: Predicted distribution.

    Returns:
        Cross-entropy in nats.
    """
    # Normalize both
    p_norm = normalize_distribution(p)
    q_norm = normalize_distribution(q)

    ce = 0.0
    for pi, qi in zip(p_norm, q_norm):
        if pi > 0:
            if qi <= 0:
                return float("inf")
            ce -= pi * math.log(qi)
    return ce


def mutual_information(p_xy: Sequence[float], p_x: Sequence[float], p_y: Sequence[float]) -> float:
    """Calculate mutual information I(X;Y) from joint and marginal distributions.

    Args:
        p_xy: Joint distribution P(X,Y) as flattened array.
        p_x: Marginal distribution P(X).
        p_y: Marginal distribution P(Y).

    Returns:
        Mutual information in nats.
    """
    # I(X;Y) = sum(P(x,y) * log(P(x,y) / (P(x) * P(y))))
    mi = 0.0
    for i, pxy in enumerate(p_xy):
        if pxy > 0:
            px = p_x[i // len(p_y)] if p_x else 1.0
            py = p_y[i % len(p_y)] if p_y else 1.0
            if px > 0 and py > 0:
                mi += pxy * math.log(pxy / (px * py))
    return mi


def softmax(logits: Sequence[float], temperature: float = 1.0) -> list[float]:
    """Compute softmax with temperature scaling.

    Args:
        logits: Input logits.
        temperature: Temperature parameter (higher = softer).

    Returns:
        Probability distribution.
    """
    if temperature <= 0:
        raise ValueError("Temperature must be positive")

    scaled = [x / temperature for x in logits]
    max_logit = max(scaled)
    exps = [math.exp(x - max_logit) for x in scaled]
    sum_exps = sum(exps)
    return [e / sum_exps for e in exps]


def logsumexp(values: Sequence[float]) -> float:
    """Compute log(sum(exp(values))) in numerically stable way.

    Args:
        values: Input values.

    Returns:
        Log-sum-exp value.
    """
    if not values:
        return float("-inf")

    max_val = max(values)
    return max_val + math.log(sum(math.exp(x - max_val) for x in values))
