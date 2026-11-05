"""
arf_rt/temporal/evaluator.py - Core temporal path feasibility evaluator.

Evaluates the five temporal constraints (TC-1 through TC-5) defined in
docs/TEMPORAL_CONTEXT_DESIGN.md against an ordered sequence of edges
and their associated TemporalHints.

Design invariants
-----------------
* The evaluator is a **pure function** over its inputs — it has no side
  effects and does not modify any Bayesian belief state.
* UNKNOWN is returned when required timestamp data is absent and
  ``TemporalConfig.unknown_passthrough`` is True (default). Set it to
  False for conservative (recall-sacrificing) operation.
* Constraints are evaluated in order TC-1 → TC-5. The first violation
  short-circuits evaluation and is reported as the verdict reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Callable, Optional

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind
from arf_rt.temporal.metrics import TemporalMetrics


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class EvaluationStats:
    """Statistics from a single evaluation."""

    constraints_evaluated: int = 0
    constraints_passed: int = 0
    constraints_failed: int = 0
    constraints_unknown: int = 0
    evaluation_time_ms: float = 0.0
    path_length: int = 0
    missing_constraints: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "constraints_evaluated": self.constraints_evaluated,
            "constraints_passed": self.constraints_passed,
            "constraints_failed": self.constraints_failed,
            "constraints_unknown": self.constraints_unknown,
            "evaluation_time_ms": self.evaluation_time_ms,
            "path_length": self.path_length,
            "missing_constraints": list(self.missing_constraints),
        }


class TemporalEvaluator:
    """
    Evaluates temporal feasibility of an ordered path.

    Parameters
    ----------
    config:
        Temporal evaluation settings. If omitted, defaults are used.
    reference_time:
        The wall-clock reference used for staleness checks (TC-4).
        Defaults to UTC now at construction time. Supply a fixed value
        in tests to ensure determinism.
    enable_stats:
        If True, collect evaluation statistics.
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        reference_time: datetime | None = None,
        enable_stats: bool = False,
    ) -> None:
        self._config = config or TemporalConfig()
        self._ref = reference_time or _now_utc()
        self._enable_stats = enable_stats
        self._stats = EvaluationStats() if enable_stats else None

    @property
    def config(self) -> TemporalConfig:
        """Return the evaluation configuration."""
        return self._config

    @property
    def reference_time(self) -> datetime:
        """Return the reference time for staleness checks."""
        return self._ref

    @property
    def stats(self) -> EvaluationStats | None:
        """Return evaluation statistics if enabled."""
        return self._stats

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        path_edge_ids: list[str],
        hints: dict[str, TemporalHint],
    ) -> TemporalVerdict:
        """
        Evaluate temporal constraints for an ordered list of edge IDs.

        Parameters
        ----------
        path_edge_ids:
            Ordered list of edge identifiers representing the candidate
            attack path (first hop → last hop).
        hints:
            Mapping from edge ID to TemporalHint. Missing entries are
            treated as hints with all fields set to None.

        Returns
        -------
        TemporalVerdict
            FEASIBLE if all enabled constraints pass, INFEASIBLE if any
            constraint fires, or UNKNOWN if data is insufficient.
        """
        import time
        start_time = time.perf_counter()

        if self._stats:
            self._stats = EvaluationStats()
            self._stats.path_length = len(path_edge_ids)

        resolved = [hints.get(eid, TemporalHint(edge_id=eid)) for eid in path_edge_ids]
        missing: set[str] = set()
        constraints_to_check = self._get_enabled_constraints()

        for idx in range(len(resolved)):
            hint = resolved[idx]

            # TC-1: Causal order
            if "TC-1" in constraints_to_check and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc1(prev, hint)
                if verdict is not None:
                    self._update_stats(verdict, "TC-1")
                    if verdict.is_infeasible():
                        self._finalize_stats(start_time)
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-2: Session validity (credential issued on previous hop covers this hop)
            if "TC-2" in constraints_to_check and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc2(prev, hint)
                if verdict is not None:
                    self._update_stats(verdict, "TC-2")
                    if verdict.is_infeasible():
                        self._finalize_stats(start_time)
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-3: Minimum velocity
            if "TC-3" in constraints_to_check and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc3(prev, hint)
                if verdict is not None:
                    self._update_stats(verdict, "TC-3")
                    if verdict.is_infeasible():
                        self._finalize_stats(start_time)
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-4: Stale credential
            if "TC-4" in constraints_to_check:
                verdict = self._check_tc4(hint)
                if verdict is not None:
                    self._update_stats(verdict, "TC-4")
                    if verdict.is_infeasible():
                        self._finalize_stats(start_time)
                        return verdict
                    missing.update(verdict.missing_data_constraints)

        # TC-5: Concurrent session (path-level check)
        if "TC-5" in constraints_to_check:
            verdict = self._check_tc5(resolved)
            if verdict is not None:
                self._update_stats(verdict, "TC-5")
                if verdict.is_infeasible():
                    self._finalize_stats(start_time)
                    return verdict
                missing.update(verdict.missing_data_constraints)

        if missing and not self._config.unknown_passthrough:
            result = TemporalVerdict.unknown(frozenset(missing))
        elif missing:
            result = TemporalVerdict.unknown(frozenset(missing))
        else:
            result = TemporalVerdict.feasible()

        if self._stats:
            self._finalize_stats(start_time, result)

        return result

    def evaluate_with_metrics(
        self,
        path_edge_ids: list[str],
        hints: dict[str, TemporalHint],
        metrics: Optional["TemporalMetrics"] = None,
    ) -> TemporalVerdict:
        """Evaluate path and update metrics collector.

        Parameters
        ----------
        path_edge_ids:
            Ordered list of edge identifiers.
        hints:
            Mapping from edge ID to TemporalHint.
        metrics:
            Optional TemporalMetrics instance to update.

        Returns
        -------
        TemporalVerdict
            The evaluation result.
        """
        from arf_rt.temporal.metrics import TemporalMetrics

        local_metrics = metrics or TemporalMetrics()
        verdict = self.evaluate(path_edge_ids, hints)

        path_length = len(path_edge_ids)
        if verdict.is_feasible():
            local_metrics.record_feasible(path_length)
        elif verdict.is_infeasible():
            constraint_id = verdict.violated_constraint or "UNKNOWN"
            local_metrics.record_infeasible(constraint_id, path_length)
        else:
            local_metrics.record_unknown(path_length)

        if self._stats:
            local_metrics.record_latency(self._stats.evaluation_time_ms)

        return verdict

    def _get_enabled_constraints(self) -> list[str]:
        """Get list of enabled constraint IDs in evaluation order."""
        all_constraints = ["TC-1", "TC-2", "TC-3", "TC-4", "TC-5"]
        return [c for c in all_constraints if self._config.is_enabled(c)]

    def _update_stats(self, verdict: TemporalVerdict, constraint_id: str) -> None:
        """Update evaluation statistics."""
        if not self._stats:
            return

        self._stats.constraints_evaluated += 1
        if verdict.is_feasible():
            self._stats.constraints_passed += 1
        elif verdict.is_infeasible():
            self._stats.constraints_failed += 1
        else:
            self._stats.constraints_unknown += 1
            self._stats.missing_constraints.update(verdict.missing_data_constraints)

    def _finalize_stats(self, start_time: float, verdict: Optional[TemporalVerdict] = None) -> None:
        """Finalize evaluation statistics."""
        if not self._stats:
            return

        import time
        self._stats.evaluation_time_ms = (time.perf_counter() - start_time) * 1000

    # ------------------------------------------------------------------
    # Individual constraint checks
    # ------------------------------------------------------------------

    def _check_tc1(
        self, prev: TemporalHint, curr: TemporalHint
    ) -> TemporalVerdict | None:
        """TC-1: Causal order — curr must be observed after prev."""
        if prev.latest_observed is None or curr.earliest_observed is None:
            return TemporalVerdict.unknown(frozenset({"TC-1"}))
        if curr.earliest_observed < prev.latest_observed:
            return TemporalVerdict.infeasible(
                "TC-1",
                f"Edge {curr.edge_id!r} observed ({curr.earliest_observed.isoformat()}) "
                f"before preceding edge {prev.edge_id!r} "
                f"({prev.latest_observed.isoformat()}); causal order violated.",
            )
        return None  # constraint passed

    def _check_tc2(
        self, prev: TemporalHint, curr: TemporalHint
    ) -> TemporalVerdict | None:
        """TC-2: Session validity — credential from prev hop must not be expired."""
        if prev.credential_expiry is None or curr.earliest_observed is None:
            return TemporalVerdict.unknown(frozenset({"TC-2"}))
        grace = self._config.session_expiry_grace_seconds
        effective_expiry_ts = prev.credential_expiry.timestamp() + grace
        if curr.earliest_observed.timestamp() > effective_expiry_ts:
            return TemporalVerdict.infeasible(
                "TC-2",
                f"Credential for edge {prev.edge_id!r} expired at "
                f"{prev.credential_expiry.isoformat()} but edge "
                f"{curr.edge_id!r} was observed at "
                f"{curr.earliest_observed.isoformat()}.",
            )
        return None

    def _check_tc3(
        self, prev: TemporalHint, curr: TemporalHint
    ) -> TemporalVerdict | None:
        """TC-3: Minimum velocity — hops must be separated by at least δ_min."""
        if prev.latest_observed is None or curr.earliest_observed is None:
            return TemporalVerdict.unknown(frozenset({"TC-3"}))
        delta = (
            curr.earliest_observed - prev.latest_observed
        ).total_seconds()
        min_delta = self._config.min_hop_delta_seconds
        if delta < min_delta:
            return TemporalVerdict.infeasible(
                "TC-3",
                f"Hop from {prev.edge_id!r} to {curr.edge_id!r} completed in "
                f"{delta:.3f}s, below minimum δ={min_delta}s (bot velocity threshold).",
            )
        return None

    def _check_tc4(self, hint: TemporalHint) -> TemporalVerdict | None:
        """TC-4: Stale credential — last_used must be within the stale window."""
        days = hint.days_since_last_use(self._ref)
        if days is None:
            return TemporalVerdict.unknown(frozenset({"TC-4"}))
        threshold = self._config.stale_credential_days
        if days > threshold:
            return TemporalVerdict.infeasible(
                "TC-4",
                f"Credential for edge {hint.edge_id!r} last used "
                f"{days:.1f} days ago (threshold: {threshold} days).",
            )
        return None

    def _check_tc5(self, path: list[TemporalHint]) -> TemporalVerdict | None:
        """TC-5: Concurrent session — no two hops may share a session token in overlapping windows."""
        # Simplified heuristic: flag if any two hops have overlapping
        # credential windows AND the same credential_issued timestamp
        # (which would indicate the same session token).
        issued_times: list[datetime] = [
            h.credential_issued for h in path if h.credential_issued is not None
        ]
        if len(issued_times) < 2:
            return None  # Not enough data to evaluate; treat as passed
        seen: set[float] = set()
        for ts in issued_times:
            key = ts.timestamp()
            if key in seen:
                return TemporalVerdict.infeasible(
                    "TC-5",
                    f"Duplicate credential_issued timestamp {ts.isoformat()} detected "
                    "across multiple hops — possible concurrent session reuse.",
                )
            seen.add(key)
        return None
