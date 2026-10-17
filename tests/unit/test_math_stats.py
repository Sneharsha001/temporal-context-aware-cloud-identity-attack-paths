"""
tests/unit/test_math_stats.py - Unit tests for information theory calculations.
"""

import math
from arf_rt.util.math_stats import (
    shannon_entropy,
    normalize_distribution,
    kl_divergence,
)


def test_shannon_entropy_uniform():
    # For a uniform distribution of 2 elements, entropy = ln(2) nats
    p = [0.5, 0.5]
    assert math.isclose(shannon_entropy(p), math.log(2), rel_tol=1e-5)


def test_shannon_entropy_deterministic():
    # Single certain outcome has zero entropy
    p = [1.0, 0.0]
    assert math.isclose(shannon_entropy(p), 0.0, abs_tol=1e-7)


def test_normalize_distribution():
    weights = [2.0, 3.0, 5.0]
    norm = normalize_distribution(weights)
    assert sum(norm) == 1.0
    assert norm[0] == 0.2
    assert norm[1] == 0.3
    assert norm[2] == 0.5


def test_kl_divergence_identical():
    p = [0.25, 0.75]
    assert math.isclose(kl_divergence(p, p), 0.0, abs_tol=1e-7)
