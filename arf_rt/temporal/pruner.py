"""
arf_rt/temporal/pruner.py - Search expansion pruner using prefix feasibility.

Provides early pruning of candidate attack paths during search expansion:
if a prefix path violates temporal constraints (e.g. causality or session expiration),
all sub-trees branching from that prefix are pruned immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind


@dataclass
class PruningMetrics:
    """Metrics tracking search expansion pruning effectiveness."""
    evaluated_extensions: int = 0
    pruned_extensions: int = 0

    @property
    def prune_rate(self) -> float:
        if self.evaluated_extensions == 0:
            return 0.0
        return self.pruned_extensions / self.evaluated_extensions


class PathFeasibilityPruner:
    """
    Evaluates incremental path extensions against temporal constraints to prune
    combinatorially unviable search branches early.
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        self.config = config or TemporalConfig()
        self.reference_time = reference_time
        self.evaluator = TemporalEvaluator(
            config=self.config, reference_time=self.reference_time
        )
        self.metrics = PruningMetrics()

    def can_extend(
        self,
        prefix_edge_ids: list[str],
        next_edge_id: str,
        hints: dict[str, TemporalHint],
    ) -> bool:
        """
        Check whether extending prefix_edge_ids with next_edge_id preserves feasibility.
        Returns False if the combined path is INFEASIBLE.
        """
        self.metrics.evaluated_extensions += 1
        candidate_path = [*prefix_edge_ids, next_edge_id]

        verdict = self.evaluator.evaluate(candidate_path, hints)
        if verdict.kind == VerdictKind.INFEASIBLE:
            self.metrics.pruned_extensions += 1
            return False

        return True

    def prune_candidate_extensions(
        self,
        prefix_edge_ids: list[str],
        candidate_next_edge_ids: list[str],
        hints: dict[str, TemporalHint],
    ) -> list[str]:
        """
        Given a prefix path and a list of possible next hop edges, return only
        those edges that yield a temporally viable continuation.
        """
        viable: list[str] = []
        for next_edge in candidate_next_edge_ids:
            if self.can_extend(prefix_edge_ids, next_edge, hints):
                viable.append(next_edge)
        return viable
