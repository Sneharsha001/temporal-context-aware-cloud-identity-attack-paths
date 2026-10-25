"""
arf_rt/temporal/policy_window_validator.py - Validates credential windows against policy constraints.

Checks that a set of TemporalHint objects satisfies organizational policy rules such as
maximum session duration, mandatory rotation intervals, and minimum validity windows.
Returns structured validation results with per-hint pass/fail status and violation details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


@dataclass
class PolicyConfig:
    """Organizational policy constraints for credential window validation."""

    max_session_duration_seconds: float = 43200.0   # 12 h
    max_rotation_age_seconds: float = 7776000.0     # 90 days
    min_validity_window_seconds: float = 300.0      # 5 min minimum TTL
    allow_expired: bool = False                     # reject expired credentials


@dataclass
class PolicyViolation:
    """A single policy constraint violation for one edge."""

    edge_id: str
    rule: str
    detail: str


@dataclass
class PolicyValidationResult:
    """Validation outcome for a full collection of hints."""

    violations: list[PolicyViolation] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0

    def summary(self) -> str:
        lines = [
            f"Policy Validation: {'PASS' if self.is_valid else 'FAIL'}",
            f"  Passed : {self.passed_count}",
            f"  Failed : {self.failed_count}",
        ]
        for v in self.violations:
            lines.append(f"  [{v.rule}] {v.edge_id}: {v.detail}")
        return "\n".join(lines)


class PolicyWindowValidator:
    """
    Validates TemporalHint collections against :class:`PolicyConfig` rules.

    Parameters
    ----------
    policy:
        Policy configuration. Uses :class:`PolicyConfig` defaults when omitted.
    reference_time:
        Evaluation instant. Defaults to ``datetime.now(tz=timezone.utc)``.
    """

    def __init__(
        self,
        policy: PolicyConfig | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        self.policy = policy or PolicyConfig()
        self.reference_time = reference_time or datetime.now(tz=timezone.utc)

    def validate(self, hints: Sequence[TemporalHint]) -> PolicyValidationResult:
        """Validate all hints and return a :class:`PolicyValidationResult`."""
        result = PolicyValidationResult()
        for hint in hints:
            violations = self._validate_hint(hint)
            if violations:
                result.violations.extend(violations)
                result.failed_count += 1
            else:
                result.passed_count += 1
        return result

    # ------------------------------------------------------------------
    # Per-hint checks
    # ------------------------------------------------------------------

    def _validate_hint(self, hint: TemporalHint) -> list[PolicyViolation]:
        violations: list[PolicyViolation] = []
        now = self.reference_time

        # ── Rule 1: Expired credential check ──────────────────────────
        if hint.credential_expiry is not None:
            expiry = self._utc(hint.credential_expiry)
            if expiry <= now:
                if not self.policy.allow_expired:
                    violations.append(PolicyViolation(
                        edge_id=hint.edge_id,
                        rule="CREDENTIAL_EXPIRED",
                        detail=f"Credential expired at {expiry.isoformat()} (now={now.isoformat()})",
                    ))

        # ── Rule 2: Minimum validity window ───────────────────────────
            else:
                remaining = (expiry - now).total_seconds()
                if remaining < self.policy.min_validity_window_seconds:
                    violations.append(PolicyViolation(
                        edge_id=hint.edge_id,
                        rule="VALIDITY_WINDOW_TOO_SHORT",
                        detail=(
                            f"Remaining TTL {remaining:.0f}s is below minimum "
                            f"{self.policy.min_validity_window_seconds:.0f}s"
                        ),
                    ))

        # ── Rule 3: Session duration check ────────────────────────────
        if hint.credential_issued is not None and hint.credential_expiry is not None:
            issued = self._utc(hint.credential_issued)
            expiry = self._utc(hint.credential_expiry)
            duration = (expiry - issued).total_seconds()
            if duration > self.policy.max_session_duration_seconds:
                violations.append(PolicyViolation(
                    edge_id=hint.edge_id,
                    rule="SESSION_DURATION_EXCEEDED",
                    detail=(
                        f"Session duration {duration:.0f}s exceeds max "
                        f"{self.policy.max_session_duration_seconds:.0f}s"
                    ),
                ))

        # ── Rule 4: Rotation age check ────────────────────────────────
        if hint.last_used is not None:
            last_used = self._utc(hint.last_used)
            age = (now - last_used).total_seconds()
            if age > self.policy.max_rotation_age_seconds:
                violations.append(PolicyViolation(
                    edge_id=hint.edge_id,
                    rule="ROTATION_AGE_EXCEEDED",
                    detail=(
                        f"Credential last used {age:.0f}s ago exceeds max rotation age "
                        f"{self.policy.max_rotation_age_seconds:.0f}s"
                    ),
                ))

        return violations

    def _utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
