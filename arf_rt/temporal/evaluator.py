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

from datetime import datetime, timezone

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


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
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        self._config = config or TemporalConfig()
        self._ref = reference_time or _now_utc()

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
        resolved = [hints.get(eid, TemporalHint(edge_id=eid)) for eid in path_edge_ids]
        missing: set[str] = set()

        for idx in range(len(resolved)):
            hint = resolved[idx]

            # TC-1: Causal order
            if self._config.is_enabled("TC-1") and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc1(prev, hint)
                if verdict is not None:
                    if verdict.is_infeasible():
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-2: Session validity (credential issued on previous hop covers this hop)
            if self._config.is_enabled("TC-2") and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc2(prev, hint)
                if verdict is not None:
                    if verdict.is_infeasible():
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-3: Minimum velocity
            if self._config.is_enabled("TC-3") and idx > 0:
                prev = resolved[idx - 1]
                verdict = self._check_tc3(prev, hint)
                if verdict is not None:
                    if verdict.is_infeasible():
                        return verdict
                    missing.update(verdict.missing_data_constraints)

            # TC-4: Stale credential
            if self._config.is_enabled("TC-4"):
                verdict = self._check_tc4(hint)
                if verdict is not None:
                    if verdict.is_infeasible():
                        return verdict
                    missing.update(verdict.missing_data_constraints)

        # TC-5: Concurrent session (path-level check)
        if self._config.is_enabled("TC-5"):
            verdict = self._check_tc5(resolved)
            if verdict is not None:
                if verdict.is_infeasible():
                    return verdict
                missing.update(verdict.missing_data_constraints)

        if missing and not self._config.unknown_passthrough:
            return TemporalVerdict.unknown(frozenset(missing))

        if missing:
            return TemporalVerdict.unknown(frozenset(missing))

        return TemporalVerdict.feasible()

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
