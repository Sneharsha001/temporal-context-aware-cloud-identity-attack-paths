"""
tests/unit/test_temporal_config.py - Unit tests for arf_rt.temporal.config.

Verifies TemporalConfig default values, factory presets (strict/permissive),
and the is_enabled predicate.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.config import TemporalConfig


class TestTemporalConfigDefaults:
    def test_default_min_hop_delta(self) -> None:
        cfg = TemporalConfig()
        assert cfg.min_hop_delta_seconds == 0.5

    def test_default_stale_days(self) -> None:
        assert TemporalConfig().stale_credential_days == 90

    def test_default_grace_seconds(self) -> None:
        assert TemporalConfig().session_expiry_grace_seconds == 30.0

    def test_default_unknown_passthrough_is_true(self) -> None:
        assert TemporalConfig().unknown_passthrough is True

    def test_all_constraints_enabled_by_default(self) -> None:
        cfg = TemporalConfig()
        for cid in ("TC-1", "TC-2", "TC-3", "TC-4", "TC-5"):
            assert cfg.is_enabled(cid), f"{cid} should be enabled by default"

    def test_unknown_constraint_not_enabled(self) -> None:
        assert TemporalConfig().is_enabled("TC-99") is False


class TestTemporalConfigStrict:
    def test_strict_passthrough_is_false(self) -> None:
        assert TemporalConfig.strict().unknown_passthrough is False

    def test_strict_min_hop_delta_higher(self) -> None:
        assert TemporalConfig.strict().min_hop_delta_seconds >= 1.0

    def test_strict_stale_days_shorter(self) -> None:
        assert TemporalConfig.strict().stale_credential_days <= 30

    def test_strict_grace_is_zero(self) -> None:
        assert TemporalConfig.strict().session_expiry_grace_seconds == 0.0

    def test_strict_all_constraints_enabled(self) -> None:
        cfg = TemporalConfig.strict()
        for cid in ("TC-1", "TC-2", "TC-3", "TC-4", "TC-5"):
            assert cfg.is_enabled(cid)


class TestTemporalConfigPermissive:
    def test_permissive_passthrough_is_true(self) -> None:
        assert TemporalConfig.permissive().unknown_passthrough is True

    def test_permissive_stale_days_is_long(self) -> None:
        assert TemporalConfig.permissive().stale_credential_days >= 365

    def test_permissive_grace_is_large(self) -> None:
        assert TemporalConfig.permissive().session_expiry_grace_seconds >= 60.0

    def test_permissive_only_tc1_tc2_enabled(self) -> None:
        cfg = TemporalConfig.permissive()
        assert cfg.is_enabled("TC-1")
        assert cfg.is_enabled("TC-2")
        assert not cfg.is_enabled("TC-3")
        assert not cfg.is_enabled("TC-4")
        assert not cfg.is_enabled("TC-5")
