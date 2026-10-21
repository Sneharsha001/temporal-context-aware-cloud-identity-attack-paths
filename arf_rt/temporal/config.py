"""
arf_rt/temporal/config.py - Configuration dataclass for the temporal evaluator.

Controls which temporal constraints are active, threshold values, and
whether paths with missing data (UNKNOWN) pass through or are blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Default enabled constraint IDs (see TEMPORAL_CONTEXT_DESIGN.md §2.2)
_DEFAULT_CONSTRAINTS: frozenset[str] = frozenset(
    {"TC-1", "TC-2", "TC-3", "TC-4", "TC-5"}
)


@dataclass
class TemporalConfig:
    """
    Configuration for the TemporalEvaluator.

    Attributes
    ----------
    min_hop_delta_seconds:
        Minimum time (seconds) that must elapse between consecutive hops.
        Paths where two hops are separated by less than this threshold
        trigger TC-3 (WINDOW_TOO_NARROW).  Default: 0.5 s.
    stale_credential_days:
        Number of days after last use at which a credential is considered
        stale.  Triggers TC-4 (STALE_CREDENTIAL).  Default: 90 days.
    session_expiry_grace_seconds:
        Allow a small grace window (seconds) when checking TC-2 to
        accommodate clock skew between AWS services.  Default: 30 s.
    unknown_passthrough:
        If True (default), a path with insufficient timestamp data
        evaluates as UNKNOWN and passes through to the Bayesian layer.
        If False, UNKNOWN paths are treated as INFEASIBLE (conservative).
    enabled_constraints:
        Set of constraint IDs to evaluate.  Use a subset to disable
        specific checks without changing thresholds.
    """

    min_hop_delta_seconds: float = 0.5
    stale_credential_days: int = 90
    session_expiry_grace_seconds: float = 30.0
    unknown_passthrough: bool = True
    enabled_constraints: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_CONSTRAINTS
    )

    def is_enabled(self, constraint_id: str) -> bool:
        """Return True if the given constraint ID is active."""
        return constraint_id in self.enabled_constraints

    @classmethod
    def strict(cls) -> "TemporalConfig":
        """
        Return a conservative config that fails UNKNOWN paths and enables
        all constraints with tighter velocity bounds.
        """
        return cls(
            min_hop_delta_seconds=1.0,
            stale_credential_days=30,
            session_expiry_grace_seconds=0.0,
            unknown_passthrough=False,
            enabled_constraints=_DEFAULT_CONSTRAINTS,
        )

    @classmethod
    def permissive(cls) -> "TemporalConfig":
        """
        Return a recall-favoring config that passes UNKNOWN paths and
        disables velocity and staleness checks.
        """
        return cls(
            min_hop_delta_seconds=0.0,
            stale_credential_days=365,
            session_expiry_grace_seconds=120.0,
            unknown_passthrough=True,
            enabled_constraints=frozenset({"TC-1", "TC-2"}),
        )
