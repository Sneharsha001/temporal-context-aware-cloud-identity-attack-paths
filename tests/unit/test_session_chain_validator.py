"""
tests/unit/test_session_chain_validator.py - Tests for SessionChainValidator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.session_chain_validator import (
    ChainViolation,
    SessionChainValidator,
)


UTC = timezone.utc


class TestSessionChainValidator:
    def test_valid_chain(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=4))
        # Chained hop 2 issued at 10:05 with 30-min duration (< 3600s)
        h2 = TemporalHint(edge_id="e2", credential_issued=t0 + timedelta(minutes=5), credential_expiry=t0 + timedelta(minutes=35))

        val = SessionChainValidator(max_chain_depth=4)
        res = val.validate_chain(["e1", "e2"], {"e1": h1, "e2": h2})

        assert res.is_valid is True
        assert len(res.violations) == 0
        assert res.chain_depth == 2
        assert res.total_duration_seconds > 0

    def test_max_depth_exceeded(self) -> None:
        val = SessionChainValidator(max_chain_depth=2)
        res = val.validate_chain(["e1", "e2", "e3"], {})

        assert res.is_valid is False
        assert any(v.rule == "MAX_CHAIN_DEPTH_EXCEEDED" for v in res.violations)
        assert res.chain_depth == 3

    def test_chained_duration_exceeded_1hour_rule(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=4))
        # Hop 2 is chained, duration is 2 hours (7200s > 3600s cap)
        h2 = TemporalHint(edge_id="e2", credential_issued=t0 + timedelta(minutes=10), credential_expiry=t0 + timedelta(hours=2, minutes=10))

        val = SessionChainValidator(enforce_1hour_chain_rule=True)
        res = val.validate_chain(["e1", "e2"], {"e1": h1, "e2": h2})

        assert res.is_valid is False
        assert any(v.rule == "CHAINED_SESSION_DURATION_EXCEEDED" for v in res.violations)

    def test_causal_inversion_in_issuance(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        # Hop 1 issued at 10:00
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        # Hop 2 issued at 09:50 (before hop 1!)
        h2 = TemporalHint(edge_id="e2", credential_issued=t0 - timedelta(minutes=10), credential_expiry=t0 + timedelta(minutes=20))

        val = SessionChainValidator()
        res = val.validate_chain(["e1", "e2"], {"e1": h1, "e2": h2})

        assert res.is_valid is False
        assert any(v.rule == "CAUSAL_ISSUANCE_INVERSION" for v in res.violations)

    def test_to_dict(self) -> None:
        val = SessionChainValidator(max_chain_depth=1)
        res = val.validate_chain(["e1", "e2"], {})
        d = res.to_dict()
        assert d["is_valid"] is False
        assert d["chain_depth"] == 2
        assert len(d["violations"]) >= 1
