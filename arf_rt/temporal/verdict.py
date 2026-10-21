"""
arf_rt/temporal/verdict.py - Verdict types returned by the temporal evaluator.

A TemporalVerdict wraps the outcome of evaluating one or more temporal
constraints against a candidate path.  It is intentionally separate from
the CCPF verdict hierarchy so the two layers remain independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class VerdictKind(Enum):
    """High-level outcome of a temporal feasibility check."""

    FEASIBLE = auto()
    """All evaluated constraints passed — path is temporally consistent."""

    INFEASIBLE = auto()
    """At least one constraint was violated — path is temporally impossible."""

    UNKNOWN = auto()
    """
    Insufficient timestamp data to evaluate one or more constraints.
    Whether an UNKNOWN path passes through is controlled by
    ``TemporalConfig.unknown_passthrough``.
    """


@dataclass(frozen=True)
class TemporalVerdict:
    """
    Immutable result of a temporal feasibility evaluation for a path.

    Attributes
    ----------
    kind:
        The overall outcome (FEASIBLE, INFEASIBLE, or UNKNOWN).
    violated_constraint:
        The ID of the first constraint that caused INFEASIBLE, or None.
    reason:
        Human-readable explanation of the verdict.
    missing_data_constraints:
        Set of constraint IDs that could not be evaluated due to missing
        timestamp data (relevant when kind == UNKNOWN).
    """

    kind: VerdictKind
    violated_constraint: str | None = None
    reason: str = ""
    missing_data_constraints: frozenset[str] = field(default_factory=frozenset)

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def feasible(cls) -> "TemporalVerdict":
        """Return a FEASIBLE verdict with no violations."""
        return cls(kind=VerdictKind.FEASIBLE, reason="All temporal constraints passed.")

    @classmethod
    def infeasible(cls, constraint_id: str, reason: str) -> "TemporalVerdict":
        """Return an INFEASIBLE verdict identifying the triggering constraint."""
        return cls(
            kind=VerdictKind.INFEASIBLE,
            violated_constraint=constraint_id,
            reason=reason,
        )

    @classmethod
    def unknown(cls, missing: frozenset[str]) -> "TemporalVerdict":
        """Return an UNKNOWN verdict listing the constraints that lacked data."""
        ids = ", ".join(sorted(missing))
        return cls(
            kind=VerdictKind.UNKNOWN,
            missing_data_constraints=missing,
            reason=f"Insufficient timestamp data for constraints: {ids}.",
        )

    # ------------------------------------------------------------------
    # Predicates
    # ------------------------------------------------------------------

    def is_feasible(self) -> bool:
        return self.kind == VerdictKind.FEASIBLE

    def is_infeasible(self) -> bool:
        return self.kind == VerdictKind.INFEASIBLE

    def is_unknown(self) -> bool:
        return self.kind == VerdictKind.UNKNOWN

    def __str__(self) -> str:  # pragma: no cover
        return f"TemporalVerdict({self.kind.name}: {self.reason})"
