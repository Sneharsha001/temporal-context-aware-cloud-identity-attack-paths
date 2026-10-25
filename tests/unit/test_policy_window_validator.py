"""
tests/unit/test_policy_window_validator.py - Unit tests for PolicyWindowValidator.

Validates expired credential detection, minimum TTL enforcement, session duration
limits, rotation age limits, and allow_expired flag behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.policy_window_validator import (
    PolicyConfig,
    PolicyValidationResult,
    PolicyWindowValidator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _hint(
    edge_id: str = "e1",
    issued_offset: float | None = None,    # seconds from NOW
    expiry_offset: float | None = 7200,    # seconds from NOW
    last_used_offset: float | None = -3600,  # seconds from NOW (negative = past)
) -> TemporalHint:
    issued = (NOW + timedelta(seconds=issued_offset)) if issued_offset is not None else None
    expiry = (NOW + timedelta(seconds=expiry_offset)) if expiry_offset is not None else None
    last_used = (NOW + timedelta(seconds=last_used_offset)) if last_used_offset is not None else None
    return TemporalHint(
        edge_id=edge_id,
        credential_issued=issued,
        credential_expiry=expiry,
        last_used=last_used,
    )


def _validator(**kwargs) -> PolicyWindowValidator:
    policy = PolicyConfig(**kwargs) if kwargs else None
    return PolicyWindowValidator(policy=policy, reference_time=NOW)


# ---------------------------------------------------------------------------
# PolicyValidationResult
# ---------------------------------------------------------------------------

class TestPolicyValidationResult:
    def test_is_valid_no_violations(self):
        result = PolicyValidationResult(passed_count=3, failed_count=0)
        assert result.is_valid is True

    def test_is_not_valid_with_violations(self):
        from arf_rt.temporal.policy_window_validator import PolicyViolation
        v = PolicyViolation(edge_id="e", rule="RULE", detail="detail")
        result = PolicyValidationResult(violations=[v], failed_count=1)
        assert result.is_valid is False

    def test_summary_contains_pass_fail(self):
        v = _validator()
        result = v.validate([_hint()])
        summary = result.summary()
        assert "PASS" in summary or "FAIL" in summary


# ---------------------------------------------------------------------------
# Expired credential
# ---------------------------------------------------------------------------

class TestExpiredCredential:
    def test_expired_credential_fails(self):
        v = _validator()
        hint = _hint(expiry_offset=-600)  # expired 10 min ago
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "CREDENTIAL_EXPIRED" in rules

    def test_allow_expired_flag_passes_expired(self):
        v = _validator(allow_expired=True)
        hint = _hint(expiry_offset=-600)
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "CREDENTIAL_EXPIRED" not in rules

    def test_valid_expiry_no_violation(self):
        v = _validator()
        hint = _hint(expiry_offset=7200)
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "CREDENTIAL_EXPIRED" not in rules


# ---------------------------------------------------------------------------
# Minimum validity window
# ---------------------------------------------------------------------------

class TestMinValidityWindow:
    def test_short_ttl_fails(self):
        v = _validator(min_validity_window_seconds=600)
        hint = _hint(expiry_offset=120)   # 120 s TTL < 600 s minimum
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "VALIDITY_WINDOW_TOO_SHORT" in rules

    def test_sufficient_ttl_passes(self):
        v = _validator(min_validity_window_seconds=300)
        hint = _hint(expiry_offset=3600)  # 1 h TTL > 300 s minimum
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "VALIDITY_WINDOW_TOO_SHORT" not in rules

    def test_no_expiry_skipped(self):
        v = _validator(min_validity_window_seconds=300)
        hint = _hint(expiry_offset=None)
        result = v.validate([hint])
        assert result.is_valid


# ---------------------------------------------------------------------------
# Session duration
# ---------------------------------------------------------------------------

class TestSessionDuration:
    def test_long_session_fails(self):
        v = _validator(max_session_duration_seconds=3600)
        hint = _hint(issued_offset=-7200, expiry_offset=7200)  # 14400 s total
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "SESSION_DURATION_EXCEEDED" in rules

    def test_short_session_passes(self):
        v = _validator(max_session_duration_seconds=43200)
        hint = _hint(issued_offset=-1800, expiry_offset=1800)  # 3600 s total
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "SESSION_DURATION_EXCEEDED" not in rules

    def test_no_issued_skips_duration_check(self):
        v = _validator(max_session_duration_seconds=3600)
        hint = _hint(issued_offset=None, expiry_offset=7200)
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "SESSION_DURATION_EXCEEDED" not in rules


# ---------------------------------------------------------------------------
# Rotation age
# ---------------------------------------------------------------------------

class TestRotationAge:
    def test_old_last_used_fails(self):
        v = _validator(max_rotation_age_seconds=3600)
        hint = _hint(last_used_offset=-7200)  # 2 h ago > 1 h limit
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "ROTATION_AGE_EXCEEDED" in rules

    def test_recent_last_used_passes(self):
        v = _validator(max_rotation_age_seconds=86400)
        hint = _hint(last_used_offset=-3600)  # 1 h ago < 24 h limit
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "ROTATION_AGE_EXCEEDED" not in rules

    def test_no_last_used_skips_rotation_check(self):
        v = _validator(max_rotation_age_seconds=3600)
        hint = _hint(last_used_offset=None)
        result = v.validate([hint])
        rules = [viol.rule for viol in result.violations]
        assert "ROTATION_AGE_EXCEEDED" not in rules


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------

class TestAggregateStats:
    def test_passed_and_failed_counts(self):
        v = _validator()
        hints = [
            _hint("good", expiry_offset=7200, last_used_offset=-100),
            _hint("bad", expiry_offset=-600),  # expired
        ]
        result = v.validate(hints)
        assert result.passed_count == 1
        assert result.failed_count == 1

    def test_all_pass_empty_violations(self):
        v = _validator()
        hints = [_hint("a"), _hint("b")]
        result = v.validate(hints)
        assert result.is_valid
        assert result.violations == []

    def test_empty_hints_is_valid(self):
        v = _validator()
        result = v.validate([])
        assert result.is_valid
        assert result.passed_count == 0
