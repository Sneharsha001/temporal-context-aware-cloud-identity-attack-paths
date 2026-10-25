"""
arf_rt/temporal/hints.py - TemporalHint dataclass for per-edge timestamp data.

Each edge in the privilege graph may carry an optional TemporalHint
populated from CloudTrail events, STS metadata, or IAM last-used data.
When a field is None the evaluator treats that constraint as UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TemporalHint:
    """
    Carries time-related metadata for a single privilege graph edge.

    All fields are optional.  A hint with all None fields is valid and
    causes all temporal constraints to evaluate as UNKNOWN (pass-through).

    Attributes
    ----------
    earliest_observed:
        Earliest timestamp of a matching CloudTrail event for this edge.
    latest_observed:
        Latest timestamp of a matching CloudTrail event for this edge.
    credential_issued:
        UTC datetime the STS session token was issued (AssumeRole response).
    credential_expiry:
        UTC datetime the STS session token expires
        (= credential_issued + MaxSessionDuration).
    last_used:
        UTC datetime the IAM credential was last used (from IAM GetCredentialReport).
    edge_id:
        Opaque identifier for the edge this hint belongs to.
    """

    earliest_observed: datetime | None = None
    latest_observed: datetime | None = None
    credential_issued: datetime | None = None
    credential_expiry: datetime | None = None
    last_used: datetime | None = None
    edge_id: str = field(default="")

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    def has_observation_window(self) -> bool:
        """Return True if both earliest and latest observed times are present."""
        return self.earliest_observed is not None and self.latest_observed is not None

    def has_credential_lifetime(self) -> bool:
        """Return True if credential issued and expiry times are both present."""
        return self.credential_issued is not None and self.credential_expiry is not None

    def session_duration_seconds(self) -> float | None:
        """
        Return the total session duration in seconds, or None if unavailable.
        """
        if self.has_credential_lifetime():
            delta = self.credential_expiry - self.credential_issued  # type: ignore[operator]
            return delta.total_seconds()
        return None

    def is_expired_at(self, reference: datetime) -> bool | None:
        """
        Return True if the credential is expired at ``reference``, False if
        not, or None if credential lifetime data is unavailable.
        """
        if not self.has_credential_lifetime():
            return None
        return reference >= self.credential_expiry  # type: ignore[operator]

    def days_since_last_use(self, reference: datetime) -> float | None:
        """
        Return the number of days between last_used and ``reference``, or
        None if last_used is unavailable.
        """
        if self.last_used is None:
            return None
        return (reference - self.last_used).total_seconds() / 86_400.0

    def to_dict(self) -> dict:
        """Serialize the TemporalHint into a dictionary of ISO strings."""
        return {
            "edge_id": self.edge_id,
            "earliest_observed": self.earliest_observed.isoformat() if self.earliest_observed else None,
            "latest_observed": self.latest_observed.isoformat() if self.latest_observed else None,
            "credential_issued": self.credential_issued.isoformat() if self.credential_issued else None,
            "credential_expiry": self.credential_expiry.isoformat() if self.credential_expiry else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TemporalHint:
        """Deserialize a dictionary with optional ISO timestamp strings into a TemporalHint."""
        def _parse(val: object) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            if isinstance(val, str) and val.strip():
                clean = val.strip().replace("Z", "+00:00")
                return datetime.fromisoformat(clean)
            return None

        return cls(
            edge_id=str(data.get("edge_id", "")),
            earliest_observed=_parse(data.get("earliest_observed")),
            latest_observed=_parse(data.get("latest_observed")),
            credential_issued=_parse(data.get("credential_issued")),
            credential_expiry=_parse(data.get("credential_expiry")),
            last_used=_parse(data.get("last_used")),
        )

    def __repr__(self) -> str:  # pragma: no cover
        obs = (
            f"{self.earliest_observed!r}..{self.latest_observed!r}"
            if self.has_observation_window()
            else "no-obs"
        )
        cred = (
            f"expires={self.credential_expiry!r}"
            if self.has_credential_lifetime()
            else "no-cred"
        )
        return f"TemporalHint(edge={self.edge_id!r}, obs={obs}, {cred})"

