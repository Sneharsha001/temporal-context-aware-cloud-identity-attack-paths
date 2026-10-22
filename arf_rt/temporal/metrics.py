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
