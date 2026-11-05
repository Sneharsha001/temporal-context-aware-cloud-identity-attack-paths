"""Tests for math_stats module."""

from __future__ import annotations

import pytest

from arf_rt.util.math_stats import (
    shannon_entropy,
    normalize_distribution,
    kl_divergence,
    js_divergence,
    cosine_similarity,
    euclidean_distance,
    mean,
    variance,
    standard_deviation,
)


class TestShannonEntropy:
    """Tests for shannon_entropy function."""

    def test_uniform_distribution(self):
        """Test entropy of uniform distribution."""
        probs = [0.25, 0.25, 0.25, 0.25]
        entropy = shannon_entropy(probs)
        assert abs(entropy - 1.38629436112) < 1e-6  # ln(4)

    def test_skewed_distribution(self):
        """Test entropy of skewed distribution."""
        probs = [0.9, 0.1]
        entropy = shannon_entropy(probs)
        assert entropy < 0.5  # Low entropy for skewed

    def test_zero_probabilities(self):
        """Test handling of zero probabilities."""
        probs = [0.5, 0.5, 0.0, 0.0]
        entropy = shannon_entropy(probs)
        assert abs(entropy - 0.69314718056) < 1e-6  # ln(2)

    def test_all_zero(self):
        """Test all zero probabilities."""
        probs = [0.0, 0.0, 0.0]
        entropy = shannon_entropy(probs)
        assert entropy == 0.0

    def test_single_element(self):
        """Test single element distribution."""
        probs = [1.0]
        entropy = shannon_entropy(probs)
        assert entropy == 0.0


class TestNormalizeDistribution:
    """Tests for normalize_distribution function."""

    def test_normalize_weights(self):
        """Test normalizing weights to probabilities."""
        weights = [1.0, 2.0, 3.0]
        probs = normalize_distribution(weights)
        assert abs(sum(probs) - 1.0) < 1e-10
        assert probs == [1/6, 2/6, 3/6]

    def test_already_normalized(self):
        """Test already normalized distribution."""
        probs = [0.2, 0.3, 0.5]
        result = normalize_distribution(probs)
        assert result == probs

    def test_all_zero(self):
        """Test all zero weights."""
        weights = [0.0, 0.0, 0.0]
        probs = normalize_distribution(weights)
        assert probs == [1/3, 1/3, 1/3]

    def test_empty(self):
        """Test empty sequence."""
        probs = normalize_distribution([])
        assert probs == []


class TestKLDivergence:
    """Tests for kl_divergence function."""

    def test_identical_distributions(self):
        """Test KL divergence of identical distributions."""
        p = [0.5, 0.5]
        q = [0.5, 0.5]
        assert kl_divergence(p, q) == 0.0

    def test_different_distributions(self):
        """Test KL divergence of different distributions."""
        p = [1.0, 0.0]
        q = [0.5, 0.5]
        div = kl_divergence(p, q)
        assert div > 0

    def test_zero_in_q(self):
        """Test KL divergence when q has zero where p is non-zero."""
        p = [0.5, 0.5]
        q = [1.0, 0.0]
        assert kl_divergence(p, q) == float("inf")


class TestJSDivergence:
    """Tests for js_divergence function."""

    def test_identical_distributions(self):
        """Test JSD of identical distributions."""
        p = [0.5, 0.5]
        q = [0.5, 0.5]
        assert js_divergence(p, q) == 0.0

    def test_orthogonal_distributions(self):
        """Test JSD of orthogonal distributions."""
        p = [1.0, 0.0]
        q = [0.0, 1.0]
        jsd = js_divergence(p, q)
        assert abs(jsd - 0.69314718056) < 1e-6  # ln(2)

    def test_symmetric(self):
        """Test JSD is symmetric."""
        p = [0.7, 0.3]
        q = [0.4, 0.6]
        assert abs(js_divergence(p, q) - js_divergence(q, p)) < 1e-10

    def test_bounded(self):
        """Test JSD is bounded by ln(2)."""
        import math
        p = [1.0, 0.0, 0.0]
        q = [0.0, 1.0, 0.0]
        jsd = js_divergence(p, q)
        assert jsd <= math.log(2)


class TestCosineSimilarity:
    """Tests for cosine_similarity function."""

    def test_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 1.0

    def test_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == 0.0

    def test_opposite_vectors(self):
        """Test cosine similarity of opposite vectors."""
        a = [1.0, 1.0]
        b = [-1.0, -1.0]
        assert cosine_similarity(a, b) == -1.0

    def test_zero_vector(self):
        """Test cosine similarity with zero vector."""
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        assert cosine_similarity(a, b) == 0.0

    def test_different_lengths(self):
        """Test error on different length vectors."""
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0])


class TestEuclideanDistance:
    """Tests for euclidean_distance function."""

    def test_same_point(self):
        """Test distance between same points."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        assert euclidean_distance(a, b) == 0.0

    def test_known_distance(self):
        """Test known distance."""
        a = [0.0, 0.0]
        b = [3.0, 4.0]
        assert euclidean_distance(a, b) == 5.0

    def test_different_lengths(self):
        """Test error on different length vectors."""
        with pytest.raises(ValueError):
            euclidean_distance([1.0, 2.0], [1.0])


class TestMean:
    """Tests for mean function."""

    def test_mean_positive(self):
        """Test mean of positive numbers."""
        assert mean([1.0, 2.0, 3.0]) == 2.0

    def test_mean_negative(self):
        """Test mean of negative numbers."""
        assert mean([-1.0, -2.0, -3.0]) == -2.0

    def test_mean_mixed(self):
        """Test mean of mixed numbers."""
        assert mean([-1.0, 0.0, 1.0]) == 0.0

    def test_empty(self):
        """Test empty sequence."""
        assert mean([]) == 0.0


class TestVariance:
    """Tests for variance function."""

    def test_variance_population(self):
        """Test population variance."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        var = variance(values, ddof=0)
        assert abs(var - 2.0) < 1e-6

    def test_variance_sample(self):
        """Test sample variance."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        var = variance(values, ddof=1)
        assert abs(var - 2.5) < 1e-6

    def test_single_value(self):
        """Test variance of single value."""
        assert variance([5.0], ddof=0) == 0.0
        assert variance([5.0], ddof=1) == 0.0

    def test_empty(self):
        """Test empty sequence."""
        assert variance([]) == 0.0


class TestStandardDeviation:
    """Tests for standard_deviation function."""

    def test_std_population(self):
        """Test population standard deviation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        std = standard_deviation(values, ddof=0)
        assert abs(std - 1.41421356237) < 1e-6

    def test_std_sample(self):
        """Test sample standard deviation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        std = standard_deviation(values, ddof=1)
        assert abs(std - 1.58113883008) < 1e-6

    def test_zero_variance(self):
        """Test standard deviation of constant values."""
        assert standard_deviation([5.0, 5.0, 5.0]) == 0.0