"""
arf_rt/temporal/coverage_reporter.py - Temporal hint coverage analysis and reporting.

Measures what fraction of privilege-graph edges have temporal metadata attached,
identifies uncovered edges, and produces per-field coverage breakdowns to guide
data collection priorities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


@dataclass
class FieldCoverage:
    """Coverage statistics for a single TemporalHint field."""

    field_name: str
    covered: int    # edges with non-None value
    total: int

    @property
    def ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.covered / self.total

    @property
    def percent(self) -> float:
        return round(self.ratio * 100, 2)


@dataclass
class CoverageReport:
    """Full temporal hint coverage report for a graph edge set."""

    total_edges: int
    covered_edges: int          # edges with at least one non-None temporal field
    uncovered_edge_ids: list[str] = field(default_factory=list)
    field_coverage: dict[str, FieldCoverage] = field(default_factory=dict)

    TRACKED_FIELDS: tuple[str, ...] = field(
        default=(
            "earliest_observed",
            "latest_observed",
            "credential_issued",
            "credential_expiry",
            "last_used",
        ),
        repr=False,
    )

    @property
    def overall_ratio(self) -> float:
        if self.total_edges == 0:
            return 0.0
        return self.covered_edges / self.total_edges

    @property
    def overall_percent(self) -> float:
        return round(self.overall_ratio * 100, 2)

    def summary(self) -> str:
        lines = [
            f"Temporal Coverage Report",
            f"  Total edges    : {self.total_edges}",
            f"  Covered edges  : {self.covered_edges} ({self.overall_percent:.1f}%)",
            f"  Uncovered      : {len(self.uncovered_edge_ids)}",
            "",
            "  Per-field coverage:",
        ]
        for fc in self.field_coverage.values():
            lines.append(
                f"    {fc.field_name:<25} {fc.covered:>4}/{fc.total:<4}  ({fc.percent:.1f}%)"
            )
        return "\n".join(lines)

    def low_coverage_fields(self, threshold: float = 0.50) -> list[FieldCoverage]:
        """Return fields with coverage below *threshold* (0–1)."""
        return [fc for fc in self.field_coverage.values() if fc.ratio < threshold]


class CoverageReporter:
    """
    Computes temporal hint coverage for a collection of edge IDs vs. available hints.

    Parameters
    ----------
    all_edge_ids:
        The complete set of privilege-graph edge identifiers.
    """

    def __init__(self, all_edge_ids: Sequence[str]) -> None:
        self.all_edge_ids = list(all_edge_ids)

    TRACKED_FIELDS = (
        "earliest_observed",
        "latest_observed",
        "credential_issued",
        "credential_expiry",
        "last_used",
    )

    def report(self, hints: Sequence[TemporalHint]) -> CoverageReport:
        """Generate a :class:`CoverageReport` for the provided hints."""
        hint_map = {h.edge_id: h for h in hints}
        total = len(self.all_edge_ids)

        covered_edge_ids: set[str] = set()
        uncovered: list[str] = []
        field_counts: dict[str, int] = {f: 0 for f in self.TRACKED_FIELDS}

        for edge_id in self.all_edge_ids:
            hint = hint_map.get(edge_id)
            if hint is None:
                uncovered.append(edge_id)
                continue

            has_any = False
            for fname in self.TRACKED_FIELDS:
                val = getattr(hint, fname, None)
                if val is not None:
                    field_counts[fname] += 1
                    has_any = True

            if has_any:
                covered_edge_ids.add(edge_id)
            else:
                uncovered.append(edge_id)

        field_coverage = {
            fname: FieldCoverage(
                field_name=fname,
                covered=field_counts[fname],
                total=total,
            )
            for fname in self.TRACKED_FIELDS
        }

        return CoverageReport(
            total_edges=total,
            covered_edges=len(covered_edge_ids),
            uncovered_edge_ids=uncovered,
            field_coverage=field_coverage,
        )
