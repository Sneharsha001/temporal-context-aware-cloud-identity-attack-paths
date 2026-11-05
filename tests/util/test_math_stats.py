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
    median,
    quantile,
    percentile,
    iqr,
    skewness,
    kurtosis,
    covariance,
    correlation,
    cross_entropy,
    mutual_information,
    softmax,
    logsumexp,
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


class TestMedian:
    """Tests for median function."""

    def test_odd_length(self):
        """Test median of odd-length sequence."""
        assert median([1, 2, 3, 4, 5]) == 3
        assert median([3, 1, 2]) == 2

    def test_even_length(self):
        """Test median of even-length sequence."""
        assert median([1, 2, 3, 4]) == 2.5
        assert median([1, 3]) == 2.0

    def test_single_element(self):
        """Test median of single element."""
        assert median([5.0]) == 5.0

    def test_empty(self):
        """Test empty sequence."""
        assert median([]) == 0.0


class TestQuantile:
    """Tests for quantile function."""

    def test_quartiles(self):
        """Test quartile calculation."""
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        assert abs(quantile(values, 0.25) - 2.75) < 1e-6
        assert quantile(values, 0.5) == 4.5
        assert abs(quantile(values, 0.75) - 6.25) < 1e-6

    def test_min_max(self):
        """Test min and max quantiles."""
        values = [1, 2, 3, 4, 5]
        assert quantile(values, 0.0) == 1
        assert quantile(values, 1.0) == 5

    def test_invalid_quantile(self):
        """Test invalid quantile raises error."""
        with pytest.raises(ValueError):
            quantile([1, 2, 3], -0.1)
        with pytest.raises(ValueError):
            quantile([1, 2, 3], 1.1)

    def test_empty(self):
        """Test empty sequence."""
        assert quantile([], 0.5) == 0.0


class TestPercentile:
    """Tests for percentile function."""

    def test_percentiles(self):
        """Test percentile calculation."""
        values = list(range(1, 101))
        assert abs(percentile(values, 50) - 50.5) < 1
        assert abs(percentile(values, 95) - 95.5) < 1
        assert abs(percentile(values, 99) - 99.5) < 1

    def test_percentile_0_100(self):
        """Test 0th and 100th percentiles."""
        values = [1, 2, 3, 4, 5]
        assert percentile(values, 0) == 1
        assert percentile(values, 100) == 5


class TestIQR:
    """Tests for iqr function."""

    def test_iqr(self):
        """Test IQR calculation."""
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        assert abs(iqr(values) - 3.5) < 1e-6

    def test_empty(self):
        """Test empty sequence."""
        assert iqr([]) == 0.0


class TestSkewness:
    """Tests for skewness function."""

    def test_symmetric(self):
        """Test symmetric distribution has zero skewness."""
        # Symmetric distribution
        values = [1, 2, 3, 4, 5, 6, 7]
        assert abs(skewness(values)) < 1e-10

    def test_positive_skew(self):
        """Test positive skew."""
        # Right-skewed
        values = [1, 1, 1, 2, 2, 3, 10]
        assert skewness(values) > 0

    def test_negative_skew(self):
        """Test negative skew."""
        # Left-skewed
        values = [1, 7, 7, 7, 8, 8, 9]
        assert skewness(values) < 0

    def test_constant(self):
        """Test constant values."""
        assert skewness([5, 5, 5]) == 0.0

    def test_too_few(self):
        """Test too few values."""
        assert skewness([1, 2]) == 0.0


class TestKurtosis:
    """Tests for kurtosis function."""

    def test_normal(self):
        """Test normal-like distribution."""
        # Approximately normal
        values = [1, 2, 2, 3, 3, 3, 4, 4, 5]
        # Should be close to 0 (mesokurtic)
        assert kurtosis(values) < 2

    def test_constant(self):
        """Test constant values."""
        assert kurtosis([5, 5, 5, 5]) == 0.0

    def test_too_few(self):
        """Test too few values."""
        assert kurtosis([1, 2, 3]) == 0.0


class TestCovariance:
    """Tests for covariance function."""

    def test_positive_covariance(self):
        """Test positive covariance."""
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        cov = covariance(x, y)
        assert cov > 0
        assert abs(cov - 5.0) < 1e-6

    def test_negative_covariance(self):
        """Test negative covariance."""
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        cov = covariance(x, y)
        assert cov < 0

    def test_zero_covariance(self):
        """Test zero covariance (independent)."""
        x = [1, 2, 3]
        y = [1, 1, 1]
        assert covariance(x, y) == 0.0

    def test_different_lengths(self):
        """Test error on different lengths."""
        with pytest.raises(ValueError):
            covariance([1, 2], [1, 2, 3])


class TestCorrelation:
    """Tests for correlation function."""

    def test_perfect_positive(self):
        """Test perfect positive correlation."""
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        corr = correlation(x, y)
        assert abs(corr - 1.0) < 1e-10

    def test_perfect_negative(self):
        """Test perfect negative correlation."""
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        corr = correlation(x, y)
        assert abs(corr + 1.0) < 1e-10

    def test_no_correlation(self):
        """Test no correlation."""
        x = [1, 2, 3]
        y = [1, 1, 1]
        corr = correlation(x, y)
        assert corr == 0.0

    def test_different_lengths(self):
        """Test error on different lengths."""
        with pytest.raises(ValueError):
            correlation([1, 2], [1, 2, 3])


class TestCrossEntropy:
    """Tests for cross_entropy function."""

    def test_identical_distributions(self):
        """Test cross entropy of identical distributions."""
        p = [0.5, 0.5]
        q = [0.5, 0.5]
        ce = cross_entropy(p, q)
        # Cross entropy of identical = entropy
        import math
        assert abs(ce - math.log(2)) < 1e-6

    def test_different_distributions(self):
        """Test cross entropy of different distributions."""
        p = [1.0, 0.0]
        q = [0.5, 0.5]
        ce = cross_entropy(p, q)
        import math
        assert abs(ce - math.log(2)) < 1e-6

    def test_zero_in_q(self):
        """Test cross entropy when q has zero where p is non-zero."""
        p = [0.5, 0.5]
        q = [1.0, 0.0]
        assert cross_entropy(p, q) == float("inf")


class TestMutualInformation:
    """Tests for mutual_information function."""

    def test_independent(self):
        """Test independent variables have zero MI."""
        # P(X,Y) = P(X)*P(Y) for independent
        p_x = [0.5, 0.5]
        p_y = [0.5, 0.5]
        p_xy = [0.25, 0.25, 0.25, 0.25]  # P(X)*P(Y)
        mi = mutual_information(p_xy, p_x, p_y)
        assert abs(mi) < 1e-10

    def test_dependent(self):
        """Test dependent variables have positive MI."""
        # Perfect correlation: X=Y
        p_x = [0.5, 0.5]
        p_y = [0.5, 0.5]
        p_xy = [0.5, 0.0, 0.0, 0.5]  # P(X=0,Y=0)=0.5, P(X=1,Y=1)=0.5
        mi = mutual_information(p_xy, p_x, p_y)
        import math
        assert abs(mi - math.log(2)) < 1e-6


class TestSoftmax:
    """Tests for softmax function."""

    def test_basic(self):
        """Test basic softmax."""
        logits = [1.0, 2.0, 3.0]
        probs = softmax(logits)
        assert abs(sum(probs) - 1.0) < 1e-10
        assert all(p > 0 for p in probs)
        assert probs[2] > probs[1] > probs[0]

    def test_temperature(self):
        """Test temperature scaling."""
        logits = [1.0, 2.0, 3.0]
        probs_high = softmax(logits, temperature=10.0)
        probs_low = softmax(logits, temperature=0.1)
        # High temp = more uniform
        assert max(probs_high) - min(probs_high) < max(probs_low) - min(probs_low)

    def test_invalid_temperature(self):
        """Test invalid temperature."""
        with pytest.raises(ValueError):
            softmax([1.0], temperature=0)
        with pytest.raises(ValueError):
            softmax([1.0], temperature=-1.0)


class TestLogSumExp:
    """Tests for logsumexp function."""

    def test_basic(self):
        """Test basic logsumexp."""
        values = [1.0, 2.0, 3.0]
        result = logsumexp(values)
        # log(exp(1) + exp(2) + exp(3)) = log(e + e^2 + e^3)
        import math
        expected = math.log(math.e + math.e**2 + math.e**3)
        assert abs(result - expected) < 1e-10

    def test_large_values(self):
        """Test with large values (numerical stability)."""
        values = [1000.0, 1001.0, 1002.0]
        result = logsumexp(values)
        import math
        expected = 1002.0 + math.log(math.exp(-2) + math.exp(-1) + 1)
        assert abs(result - expected) < 1e-6

    def test_empty(self):
        """Test empty sequence."""
        assert logsumexp([]) == float("-inf")