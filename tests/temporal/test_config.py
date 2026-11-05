"""Tests for temporal config module."""

from __future__ import annotations

import pytest

from arf_rt.temporal.config import TemporalConfig


class TestTemporalConfigDefaults:
    """Tests for default configuration values."""

    def test_defaults(self):
        """Test default config values."""
        config = TemporalConfig()
        assert config.min_hop_delta_seconds == 0.5
        assert config.stale_credential_days == 90
        assert config.session_expiry_grace_seconds == 30.0
        assert config.unknown_passthrough is True
        assert config.max_path_length == 10
        assert config.max_concurrent_sessions == 5
        assert config.credential_reuse_window_seconds == 3600.0
        assert config.enabled_constraints == frozenset({"TC-1", "TC-2", "TC-3", "TC-4", "TC-5"})

    def test_is_enabled_default(self):
        """Test is_enabled with default constraints."""
        config = TemporalConfig()
        for tc in ["TC-1", "TC-2", "TC-3", "TC-4", "TC-5"]:
            assert config.is_enabled(tc) is True
        assert config.is_enabled("TC-6") is False


class TestTemporalConfigPresets:
    """Tests for preset configurations."""

    def test_strict_preset(self):
        """Test strict preset."""
        config = TemporalConfig.strict()
        assert config.min_hop_delta_seconds == 1.0
        assert config.stale_credential_days == 30
        assert config.session_expiry_grace_seconds == 0.0
        assert config.unknown_passthrough is False
        assert config.max_path_length == 5
        assert config.max_concurrent_sessions == 2
        assert config.credential_reuse_window_seconds == 1800.0
        assert all(config.is_enabled(tc) for tc in ["TC-1", "TC-2", "TC-3", "TC-4", "TC-5"])

    def test_permissive_preset(self):
        """Test permissive preset."""
        config = TemporalConfig.permissive()
        assert config.min_hop_delta_seconds == 0.0
        assert config.stale_credential_days == 365
        assert config.session_expiry_grace_seconds == 120.0
        assert config.unknown_passthrough is True
        assert config.max_path_length == 20
        assert config.max_concurrent_sessions == 10
        assert config.credential_reuse_window_seconds == 7200.0
        assert config.is_enabled("TC-1") is True
        assert config.is_enabled("TC-2") is True
        assert config.is_enabled("TC-3") is False
        assert config.is_enabled("TC-4") is False
        assert config.is_enabled("TC-5") is False

    def test_balanced_preset(self):
        """Test balanced preset."""
        config = TemporalConfig.balanced()
        assert config.min_hop_delta_seconds == 0.5
        assert config.stale_credential_days == 90
        assert config.session_expiry_grace_seconds == 30.0
        assert config.unknown_passthrough is True
        assert config.max_path_length == 10
        assert config.max_concurrent_sessions == 5
        assert config.credential_reuse_window_seconds == 3600.0
        assert all(config.is_enabled(tc) for tc in ["TC-1", "TC-2", "TC-3", "TC-4", "TC-5"])


class TestTemporalConfigCustom:
    """Tests for custom configuration."""

    def test_custom_values(self):
        """Test setting custom values."""
        config = TemporalConfig(
            min_hop_delta_seconds=1.0,
            stale_credential_days=60,
            session_expiry_grace_seconds=10.0,
            unknown_passthrough=False,
            enabled_constraints=frozenset({"TC-1", "TC-3"}),
            max_path_length=8,
            max_concurrent_sessions=3,
            credential_reuse_window_seconds=1800.0,
        )
        assert config.min_hop_delta_seconds == 1.0
        assert config.stale_credential_days == 60
        assert config.session_expiry_grace_seconds == 10.0
        assert config.unknown_passthrough is False
        assert config.enabled_constraints == frozenset({"TC-1", "TC-3"})
        assert config.max_path_length == 8
        assert config.max_concurrent_sessions == 3
        assert config.credential_reuse_window_seconds == 1800.0

    def test_validate_valid(self):
        """Test validation of valid config."""
        config = TemporalConfig()
        warnings = config.validate()
        assert warnings == []

    def test_validate_invalid_negative_delta(self):
        """Test validation catches negative min_hop_delta_seconds."""
        config = TemporalConfig(min_hop_delta_seconds=-1.0)
        warnings = config.validate()
        assert "min_hop_delta_seconds should be non-negative" in warnings

    def test_validate_invalid_stale_days(self):
        """Test validation catches negative stale_credential_days."""
        config = TemporalConfig(stale_credential_days=-1)
        warnings = config.validate()
        assert "stale_credential_days should be non-negative" in warnings

    def test_validate_invalid_grace(self):
        """Test validation catches negative session_expiry_grace_seconds."""
        config = TemporalConfig(session_expiry_grace_seconds=-1.0)
        warnings = config.validate()
        assert "session_expiry_grace_seconds should be non-negative" in warnings

    def test_validate_invalid_max_path(self):
        """Test validation catches invalid max_path_length."""
        config = TemporalConfig(max_path_length=0)
        warnings = config.validate()
        assert "max_path_length should be at least 1" in warnings

    def test_validate_invalid_max_sessions(self):
        """Test validation catches invalid max_concurrent_sessions."""
        config = TemporalConfig(max_concurrent_sessions=0)
        warnings = config.validate()
        assert "max_concurrent_sessions should be at least 1" in warnings

    def test_validate_invalid_reuse_window(self):
        """Test validation catches negative credential_reuse_window_seconds."""
        config = TemporalConfig(credential_reuse_window_seconds=-1.0)
        warnings = config.validate()
        assert "credential_reuse_window_seconds should be non-negative" in warnings


class TestTemporalConfigSerialization:
    """Tests for config serialization."""

    def test_to_dict(self):
        """Test serialization to dict."""
        config = TemporalConfig(
            min_hop_delta_seconds=1.0,
            stale_credential_days=60,
        )
        d = config.to_dict()
        assert d["min_hop_delta_seconds"] == 1.0
        assert d["stale_credential_days"] == 60
        assert "enabled_constraints" in d
        assert isinstance(d["enabled_constraints"], list)

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "min_hop_delta_seconds": 1.0,
            "stale_credential_days": 60,
            "session_expiry_grace_seconds": 10.0,
            "unknown_passthrough": False,
            "enabled_constraints": ["TC-1", "TC-3"],
            "max_path_length": 8,
            "max_concurrent_sessions": 3,
            "credential_reuse_window_seconds": 1800.0,
        }
        config = TemporalConfig.from_dict(data)
        assert config.min_hop_delta_seconds == 1.0
        assert config.stale_credential_days == 60
        assert config.session_expiry_grace_seconds == 10.0
        assert config.unknown_passthrough is False
        assert config.enabled_constraints == frozenset({"TC-1", "TC-3"})
        assert config.max_path_length == 8
        assert config.max_concurrent_sessions == 3
        assert config.credential_reuse_window_seconds == 1800.0

    def test_from_dict_partial(self):
        """Test deserialization with partial dict (uses defaults)."""
        data = {"min_hop_delta_seconds": 2.0}
        config = TemporalConfig.from_dict(data)
        assert config.min_hop_delta_seconds == 2.0
        assert config.stale_credential_days == 90  # default
        assert config.session_expiry_grace_seconds == 30.0  # default


class TestTemporalConfigWithOverrides:
    """Tests for with_overrides method."""

    def test_with_overrides(self):
        """Test creating new config with overrides."""
        config = TemporalConfig()
        new_config = config.with_overrides(min_hop_delta_seconds=2.0, stale_credential_days=30)

        assert new_config.min_hop_delta_seconds == 2.0
        assert new_config.stale_credential_days == 30
        # Other values unchanged
        assert new_config.session_expiry_grace_seconds == 30.0
        assert new_config.unknown_passthrough is True

    def test_original_unchanged(self):
        """Test original config is not modified."""
        config = TemporalConfig()
        new_config = config.with_overrides(min_hop_delta_seconds=2.0)

        assert config.min_hop_delta_seconds == 0.5
        assert new_config.min_hop_delta_seconds == 2.0

    def test_multiple_overrides(self):
        """Test multiple overrides."""
        config = TemporalConfig.strict()
        new_config = config.with_overrides(
            min_hop_delta_seconds=0.5,
            unknown_passthrough=True,
        )

        assert new_config.min_hop_delta_seconds == 0.5
        assert new_config.unknown_passthrough is True
        assert new_config.stale_credential_days == 30  # from strict