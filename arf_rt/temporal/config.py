"""
arf_rt/temporal/config.py - Configuration dataclass for the temporal evaluator.

Controls which temporal constraints are active, threshold values, and
whether paths with missing data (UNKNOWN) pass through or are blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
    max_path_length:
        Maximum number of hops allowed in a path. Paths exceeding this
        will be marked INFEASIBLE. Default: 10.
    max_concurrent_sessions:
        Maximum number of concurrent sessions allowed per principal.
        Used by TC-5. Default: 5.
    credential_reuse_window_seconds:
        Time window (seconds) within which credential reuse is considered
        suspicious for TC-5. Default: 3600 (1 hour).
    """

    min_hop_delta_seconds: float = 0.5
    stale_credential_days: int = 90
    session_expiry_grace_seconds: float = 30.0
    unknown_passthrough: bool = True
    enabled_constraints: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_CONSTRAINTS
    )
    max_path_length: int = 10
    max_concurrent_sessions: int = 5
    credential_reuse_window_seconds: float = 3600.0

    def is_enabled(self, constraint_id: str) -> bool:
        """Return True if the given constraint ID is active."""
        return constraint_id in self.enabled_constraints

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings.

        Returns:
            List of warning messages (empty if valid).
        """
        warnings = []

        if self.min_hop_delta_seconds < 0:
            warnings.append("min_hop_delta_seconds should be non-negative")

        if self.stale_credential_days < 0:
            warnings.append("stale_credential_days should be non-negative")

        if self.session_expiry_grace_seconds < 0:
            warnings.append("session_expiry_grace_seconds should be non-negative")

        if self.max_path_length < 1:
            warnings.append("max_path_length should be at least 1")

        if self.max_concurrent_sessions < 1:
            warnings.append("max_concurrent_sessions should be at least 1")

        if self.credential_reuse_window_seconds < 0:
            warnings.append("credential_reuse_window_seconds should be non-negative")

        return warnings

    def to_dict(self) -> dict:
        """Serialize config to a plain dict."""
        return {
            "min_hop_delta_seconds": self.min_hop_delta_seconds,
            "stale_credential_days": self.stale_credential_days,
            "session_expiry_grace_seconds": self.session_expiry_grace_seconds,
            "unknown_passthrough": self.unknown_passthrough,
            "enabled_constraints": list(self.enabled_constraints),
            "max_path_length": self.max_path_length,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "credential_reuse_window_seconds": self.credential_reuse_window_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemporalConfig":
        """Create config from a dictionary."""
        enabled = data.get("enabled_constraints")
        if enabled is not None:
            enabled = frozenset(enabled)

        return cls(
            min_hop_delta_seconds=data.get("min_hop_delta_seconds", 0.5),
            stale_credential_days=data.get("stale_credential_days", 90),
            session_expiry_grace_seconds=data.get("session_expiry_grace_seconds", 30.0),
            unknown_passthrough=data.get("unknown_passthrough", True),
            enabled_constraints=enabled or _DEFAULT_CONSTRAINTS,
            max_path_length=data.get("max_path_length", 10),
            max_concurrent_sessions=data.get("max_concurrent_sessions", 5),
            credential_reuse_window_seconds=data.get("credential_reuse_window_seconds", 3600.0),
        )

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
            max_path_length=5,
            max_concurrent_sessions=2,
            credential_reuse_window_seconds=1800.0,
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
            max_path_length=20,
            max_concurrent_sessions=10,
            credential_reuse_window_seconds=7200.0,
        )

    @classmethod
    def balanced(cls) -> "TemporalConfig":
        """
        Return a balanced config with moderate settings.
        """
        return cls(
            min_hop_delta_seconds=0.5,
            stale_credential_days=90,
            session_expiry_grace_seconds=30.0,
            unknown_passthrough=True,
            enabled_constraints=_DEFAULT_CONSTRAINTS,
            max_path_length=10,
            max_concurrent_sessions=5,
            credential_reuse_window_seconds=3600.0,
        )

    def with_overrides(self, **kwargs) -> "TemporalConfig":
        """Create a new config with the given overrides."""
        current = self.to_dict()
        current.update(kwargs)
        return self.from_dict(current)
