"""
arf_rt/temporal/sts_metadata.py - STS credential metadata helpers.

Provides utilities for computing and validating STS session lifetimes
from AssumeRole API parameters and IAM role configuration, without
requiring a live AWS connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


# AWS STS AssumeRole: absolute session duration bounds
_STS_MIN_DURATION_SECONDS = 900       # 15 minutes
_STS_MAX_DURATION_SECONDS = 43_200    # 12 hours


@dataclass(frozen=True)
class SessionSpec:
    """
    Describes the desired session lifetime for an AssumeRole call.

    Attributes
    ----------
    duration_seconds:
        Requested session duration (must be between 900 and 43200).
    issued_at:
        UTC datetime when the session token was issued.
    """

    duration_seconds: int
    issued_at: datetime

    def __post_init__(self) -> None:
        if not (_STS_MIN_DURATION_SECONDS <= self.duration_seconds <= _STS_MAX_DURATION_SECONDS):
            raise ValueError(
                f"duration_seconds must be between {_STS_MIN_DURATION_SECONDS} "
                f"and {_STS_MAX_DURATION_SECONDS}, got {self.duration_seconds}."
            )

    @property
    def expiry(self) -> datetime:
        """Compute the UTC expiry time of this session."""
        return self.issued_at + timedelta(seconds=self.duration_seconds)

    def is_valid_at(self, reference: datetime) -> bool:
        """Return True if the session is still valid at ``reference``."""
        return self.issued_at <= reference < self.expiry

    def remaining_seconds(self, reference: datetime) -> float:
        """
        Return seconds remaining until expiry at ``reference``.
        Negative values indicate an expired session.
        """
        return (self.expiry - reference).total_seconds()


def compute_effective_max_duration(
    role_max_duration_seconds: int,
    requested_duration_seconds: int,
) -> int:
    """
    Return the effective session duration that AWS would grant, which is
    the minimum of the role's configured maximum and the requested value.

    Parameters
    ----------
    role_max_duration_seconds:
        The `MaxSessionDuration` configured on the IAM role (900–43200).
    requested_duration_seconds:
        The duration requested in the AssumeRole API call (900–43200).

    Returns
    -------
    int
        Effective duration in seconds.

    Raises
    ------
    ValueError
        If either value is outside the allowed STS bounds.
    """
    for label, value in (
        ("role_max_duration_seconds", role_max_duration_seconds),
        ("requested_duration_seconds", requested_duration_seconds),
    ):
        if not (_STS_MIN_DURATION_SECONDS <= value <= _STS_MAX_DURATION_SECONDS):
            raise ValueError(f"{label}={value} is outside STS bounds.")
    return min(role_max_duration_seconds, requested_duration_seconds)


def infer_expiry_from_cloudtrail(
    event_time: datetime,
    response_expiration: datetime | None,
    role_max_duration_seconds: int = 3_600,
) -> datetime:
    """
    Infer the session expiry timestamp.

    Uses the CloudTrail responseElements.credentials.expiration field if
    present; otherwise falls back to event_time + role_max_duration_seconds.

    Parameters
    ----------
    event_time:
        The UTC time the AssumeRole event occurred.
    response_expiration:
        Parsed datetime from responseElements.credentials.expiration, or None.
    role_max_duration_seconds:
        Role max session duration to use as fallback (default: 1 hour).

    Returns
    -------
    datetime
        Best-estimate UTC expiry for the credential.
    """
    if response_expiration is not None:
        return response_expiration
    return event_time + timedelta(seconds=role_max_duration_seconds)


def validate_path_session_chain(
    sessions: list[SessionSpec],
    grace_seconds: float = 30.0,
) -> list[str]:
    """
    Validate that a sequence of STS sessions is causally consistent: each
    session must be issued while the *previous* session was still valid
    (within a grace window for clock skew).

    Parameters
    ----------
    sessions:
        Ordered list of SessionSpec objects (earliest to latest).
    grace_seconds:
        Clock skew tolerance in seconds.

    Returns
    -------
    list[str]
        List of violation messages. Empty list means the chain is valid.
    """
    violations: list[str] = []
    for i in range(1, len(sessions)):
        prev = sessions[i - 1]
        curr = sessions[i]
        effective_expiry = prev.expiry + timedelta(seconds=grace_seconds)
        if curr.issued_at > effective_expiry:
            violations.append(
                f"Session {i} issued at {curr.issued_at.isoformat()} but "
                f"session {i - 1} expired at {prev.expiry.isoformat()} "
                f"(grace={grace_seconds}s)."
            )
    return violations
