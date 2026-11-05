"""
arf_rt/temporal/metrics.py - Temporal evaluation metrics collector.

Tracks aggregate statistics across multiple temporal evaluations:
- Verdict distribution (FEASIBLE / INFEASIBLE / UNKNOWN)
- Per-constraint violation counts
- Path length distribution
- Reduction rate (fraction of paths eliminated)

Designed to be attached to a TemporalPathFilter and inspected after
a batch run to quantify the temporal layer's contribution.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class TemporalMetrics:
    """
    Aggregate metrics from a batch of temporal path evaluations.

    All attributes are mutable counters updated by ``record()``.
    Call ``reset()`` between distinct evaluation batches.
    """

    # Verdict counts
    feasible_count: int = 0
    infeasible_count: int = 0
    unknown_count: int = 0

    # Per-constraint violation tallies
    constraint_violations: Counter = field(default_factory=Counter)

    # Path length histogram: length → count
    path_length_histogram: Counter = field(default_factory=Counter)

    # Total evaluated paths
    total_paths: int = 0

    def record_feasible(self, path_length: int) -> None:
        self.feasible_count += 1
        self.total_paths += 1
        self.path_length_histogram[path_length] += 1

    def record_infeasible(self, constraint_id: str, path_length: int) -> None:
        self.infeasible_count += 1
        self.total_paths += 1
        self.constraint_violations[constraint_id] += 1
        self.path_length_histogram[path_length] += 1

    def record_unknown(self, path_length: int) -> None:
        self.unknown_count += 1
        self.total_paths += 1
        self.path_length_histogram[path_length] += 1

    # ------------------------------------------------------------------
    # Derived statistics
    # ------------------------------------------------------------------

    @property
    def elimination_rate(self) -> float:
        """Fraction of paths eliminated (INFEASIBLE / total)."""
        if self.total_paths == 0:
            return 0.0
        return self.infeasible_count / self.total_paths

    @property
    def unknown_rate(self) -> float:
        """Fraction of paths with insufficient data (UNKNOWN / total)."""
        if self.total_paths == 0:
            return 0.0
        return self.unknown_count / self.total_paths

    @property
    def top_violated_constraint(self) -> str | None:
        """Return the constraint ID with the most violations, or None."""
        if not self.constraint_violations:
            return None
        return self.constraint_violations.most_common(1)[0][0]

    def mean_path_length(self) -> float:
        """Return the mean path length across all evaluated paths."""
        if self.total_paths == 0:
            return 0.0
        total_hops = sum(
            length * count for length, count in self.path_length_histogram.items()
        )
        return total_hops / self.total_paths

    def to_dict(self) -> dict:
        """Serialize metrics to a plain dict (JSON-safe)."""
        return {
            "total_paths": self.total_paths,
            "feasible_count": self.feasible_count,
            "infeasible_count": self.infeasible_count,
            "unknown_count": self.unknown_count,
            "elimination_rate": round(self.elimination_rate, 4),
            "unknown_rate": round(self.unknown_rate, 4),
            "top_violated_constraint": self.top_violated_constraint,
            "mean_path_length": round(self.mean_path_length(), 2),
            "constraint_violations": dict(self.constraint_violations),
            "path_length_histogram": dict(self.path_length_histogram),
        }

    def reset(self) -> None:
        """Clear all counters to zero."""
        self.feasible_count = 0
        self.infeasible_count = 0
        self.unknown_count = 0
        self.constraint_violations.clear()
        self.path_length_histogram.clear()
        self.total_paths = 0

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TemporalMetrics(total={self.total_paths}, "
            f"feasible={self.feasible_count}, "
            f"infeasible={self.infeasible_count}, "
            f"unknown={self.unknown_count}, "
            f"elim_rate={self.elimination_rate:.1%})"
        )


def percentile(data: dict[int, int], p: float) -> float:
    """Calculate percentile from histogram data.

    Args:
        data: Histogram mapping value -> count.
        p: Percentile (0-100).

    Returns:
        Value at the given percentile.
    """
    if not data:
        return 0.0

    items = sorted(data.items())
    total = sum(count for _, count in items)
    target = total * p / 100.0

    cumulative = 0
    for value, count in items:
        cumulative += count
        if cumulative >= target:
            return float(value)

    return float(items[-1][0])


@dataclass
class TemporalMetricsExtended(TemporalMetrics):
    """Extended temporal metrics with additional statistical measures."""

    # Latency tracking (milliseconds)
    evaluation_latencies: list[float] = field(default_factory=list)

    def record_latency(self, latency_ms: float) -> None:
        """Record evaluation latency in milliseconds."""
        self.evaluation_latencies.append(latency_ms)

    @property
    def median_path_length(self) -> float:
        """Return the median path length."""
        return percentile(self.path_length_histogram, 50)

    @property
    def p95_path_length(self) -> float:
        """Return the 95th percentile path length."""
        return percentile(self.path_length_histogram, 95)

    @property
    def p99_path_length(self) -> float:
        """Return the 99th percentile path length."""
        return percentile(self.path_length_histogram, 99)

    @property
    def std_path_length(self) -> float:
        """Return the standard deviation of path lengths."""
        if self.total_paths <= 1:
            return 0.0

        mean_len = self.mean_path_length()
        variance = sum(
            count * (length - mean_len) ** 2
            for length, count in self.path_length_histogram.items()
        ) / self.total_paths

        import math
        return math.sqrt(variance)

    @property
    def mean_latency_ms(self) -> float:
        """Return mean evaluation latency in milliseconds."""
        if not self.evaluation_latencies:
            return 0.0
        return sum(self.evaluation_latencies) / len(self.evaluation_latencies)

    @property
    def median_latency_ms(self) -> float:
        """Return median evaluation latency in milliseconds."""
        if not self.evaluation_latencies:
            return 0.0
        sorted_lat = sorted(self.evaluation_latencies)
        n = len(sorted_lat)
        if n % 2 == 0:
            return (sorted_lat[n // 2 - 1] + sorted_lat[n // 2]) / 2
        return sorted_lat[n // 2]

    @property
    def p95_latency_ms(self) -> float:
        """Return 95th percentile evaluation latency in milliseconds."""
        if not self.evaluation_latencies:
            return 0.0
        sorted_lat = sorted(self.evaluation_latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def to_dict(self) -> dict:
        """Serialize extended metrics to a plain dict (JSON-safe)."""
        base = super().to_dict()
        base.update({
            "median_path_length": round(self.median_path_length, 2),
            "p95_path_length": round(self.p95_path_length, 2),
            "p99_path_length": round(self.p99_path_length, 2),
            "std_path_length": round(self.std_path_length, 2),
            "mean_latency_ms": round(self.mean_latency_ms, 2),
            "median_latency_ms": round(self.median_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "evaluation_count": len(self.evaluation_latencies),
        })
        return base

    def reset(self) -> None:
        """Clear all counters to zero."""
        super().reset()
        self.evaluation_latencies.clear()
