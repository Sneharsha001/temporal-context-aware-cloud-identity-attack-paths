"""
arf_rt/temporal/path_filter.py - High-level temporal path filter.

Wraps TemporalEvaluator + WindowAnalyzer into a single callable that
accepts a list of candidate paths (each a list of edge IDs) and returns
those that pass temporal feasibility checks.

This is the integration point between the CCPF logical layer and the
Bayesian scorer — it is called after CCPF has already removed logically
infeasible paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind
from arf_rt.temporal.window_analyzer import (
    WindowAnalysisResult,
    detect_burst,
    detect_cross_account_reuse,
    detect_impossible_concurrency,
)


@dataclass
class FilterResult:
    """
    Result of filtering a single candidate path through temporal checks.

    Attributes
    ----------
    edge_ids:
        The path (ordered edge ID list) that was evaluated.
    passed:
        True if the path is temporally feasible (or UNKNOWN with passthrough).
    verdict_kind:
        The raw VerdictKind from the temporal evaluator.
    rejected_by:
        Human-readable reason for rejection, or empty string if passed.
    window_anomalies:
        List of window analysis findings (may be non-empty even if path passed).
    """

    edge_ids: list[str]
    passed: bool
    verdict_kind: str
    rejected_by: str = ""
    window_anomalies: list[str] = field(default_factory=list)


class TemporalPathFilter:
    """
    Filters candidate paths using the temporal evaluator and window analyzer.

    Parameters
    ----------
    config:
        Temporal evaluation settings.
    run_window_checks:
        If True (default), also run window analyzer checks and attach
        anomaly notes to FilterResult (but do NOT reject based on them
        unless ``reject_on_window_anomaly`` is True).
    reject_on_window_anomaly:
        If True, paths with window anomalies are also rejected. Default False.
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        run_window_checks: bool = True,
        reject_on_window_anomaly: bool = False,
    ) -> None:
        self._config = config or TemporalConfig()
        self._ev = TemporalEvaluator(config=self._config)
        self._run_window = run_window_checks
        self._reject_window = reject_on_window_anomaly

    def filter(
        self,
        paths: Iterable[list[str]],
        hints: dict[str, TemporalHint],
    ) -> list[FilterResult]:
        """
        Evaluate every candidate path and return FilterResult objects.

        Parameters
        ----------
        paths:
            Iterable of candidate paths, each a list of ordered edge IDs.
        hints:
            Mapping from edge ID to TemporalHint (may be sparse).

        Returns
        -------
        list[FilterResult]
            One result per input path.
        """
        results: list[FilterResult] = []
        for path_ids in paths:
            results.append(self._evaluate_one(path_ids, hints))
        return results

    def passing(
        self,
        paths: Iterable[list[str]],
        hints: dict[str, TemporalHint],
    ) -> list[list[str]]:
        """Convenience method — return only the paths that passed."""
        return [r.edge_ids for r in self.filter(paths, hints) if r.passed]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evaluate_one(
        self, edge_ids: list[str], hints: dict[str, TemporalHint]
    ) -> FilterResult:
        verdict = self._ev.evaluate(edge_ids, hints)

        passed = verdict.kind in (VerdictKind.FEASIBLE, VerdictKind.UNKNOWN)
        rejected_by = "" if passed else verdict.reason

        anomalies: list[str] = []
        if self._run_window:
            path_hints = [hints.get(eid, TemporalHint(edge_id=eid)) for eid in edge_ids]
            for check_fn in (
                detect_impossible_concurrency,
                detect_burst,
                detect_cross_account_reuse,
            ):
                result: WindowAnalysisResult = check_fn(path_hints)  # type: ignore[call-arg]
                if result.suspicious:
                    anomalies.append(result.reason)
                    if self._reject_window and passed:
                        passed = False
                        rejected_by = result.reason

        return FilterResult(
            edge_ids=edge_ids,
            passed=passed,
            verdict_kind=verdict.kind.name,
            rejected_by=rejected_by,
            window_anomalies=anomalies,
        )
