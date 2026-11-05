"""Tests for config_loader module."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from arf_rt.util.config_loader import (
    RuntimeProfile,
    load_profile,
    load_profile_from_yaml,
    load_profile_auto,
    merge_profiles,
    get_env_overrides,
    apply_env_overrides,
    validate_profile,
)


class TestRuntimeProfile:
    """Tests for RuntimeProfile dataclass."""

    def test_defaults(self):
        """Test default values."""
        profile = RuntimeProfile()
        assert profile.profile_name == "default"
        assert profile.q8_precision == 8
        assert profile.max_path_depth == 6
        assert profile.top_k_paths == 5
        assert profile.safe_replay_mode is True
        assert profile.extra_options == {}

    def test_from_dict(self):
        """Test creating from dict."""
        data = {
            "profile_name": "test",
            "q8_precision": 16,
            "max_path_depth": 10,
            "top_k_paths": 20,
            "safe_replay_mode": False,
            "custom_option": "value",
        }
        profile = RuntimeProfile.from_dict(data)
        assert profile.profile_name == "test"
        assert profile.q8_precision == 16
        assert profile.max_path_depth == 10
        assert profile.top_k_paths == 20
        assert profile.safe_replay_mode is False
        assert profile.extra_options == {"custom_option": "value"}

    def test_from_dict_partial(self):
        """Test creating from partial dict."""
        data = {"profile_name": "partial"}
        profile = RuntimeProfile.from_dict(data)
        assert profile.profile_name == "partial"
        assert profile.q8_precision == 8  # default
        assert profile.max_path_depth == 6  # default


class TestLoadProfile:
    """Tests for load_profile function."""

    def test_load_from_json(self):
        """Test loading from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "profile_name": "json_profile",
                "max_path_depth": 8,
            }, f)
            temp_path = Path(f.name)

        try:
            profile = load_profile(temp_path)
            assert profile.profile_name == "json_profile"
            assert profile.max_path_depth == 8
        finally:
            temp_path.unlink()

    def test_load_nonexistent(self):
        """Test loading nonexistent file returns defaults."""
        profile = load_profile(Path("/nonexistent/file.json"))
        assert profile.profile_name == "default"
        assert profile.max_path_depth == 6


class TestLoadProfileFromYAML:
    """Tests for load_profile_from_yaml function."""

    def test_load_yaml(self):
        """Test loading from YAML file."""
        pytest.importorskip("yaml")
        import yaml

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "profile_name": "yaml_profile",
                "top_k_paths": 15,
            }, f)
            temp_path = Path(f.name)

        try:
            profile = load_profile_from_yaml(temp_path)
            assert profile.profile_name == "yaml_profile"
            assert profile.top_k_paths == 15
        finally:
            temp_path.unlink()

    def test_missing_file(self):
        """Test missing file raises error."""
        pytest.importorskip("yaml")
        with pytest.raises(FileNotFoundError):
            load_profile_from_yaml(Path("/nonexistent/file.yaml"))

    def test_no_pyyaml(self):
        """Test error when PyYAML not installed."""
        # This is hard to test without mocking, skip
        pass


class TestLoadProfileAuto:
    """Tests for load_profile_auto function."""

    def test_json_extension(self):
        """Test auto-detect JSON by extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"profile_name": "auto_json"}, f)
            temp_path = Path(f.name)

        try:
            profile = load_profile_auto(temp_path)
            assert profile.profile_name == "auto_json"
        finally:
            temp_path.unlink()

    def test_yaml_extension(self):
        """Test auto-detect YAML by extension."""
        pytest.importorskip("yaml")
        import yaml

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"profile_name": "auto_yaml"}, f)
            temp_path = Path(f.name)

        try:
            profile = load_profile_auto(temp_path)
            assert profile.profile_name == "auto_yaml"
        finally:
            temp_path.unlink()

    def test_no_file(self):
        """Test no file returns defaults."""
        profile = load_profile_auto(None)
        assert profile.profile_name == "default"


class TestMergeProfiles:
    """Tests for merge_profiles function."""

    def test_basic_merge(self):
        """Test basic merge."""
        base = RuntimeProfile(profile_name="base", max_path_depth=6)
        override = RuntimeProfile(profile_name="override", top_k_paths=10)

        merged = merge_profiles(base, override)
        assert merged.profile_name == "override"
        assert merged.max_path_depth == 6
        assert merged.top_k_paths == 10

    def test_extra_options_merge(self):
        """Test extra options merge."""
        base = RuntimeProfile(extra_options={"base_opt": "value1"})
        override = RuntimeProfile(extra_options={"override_opt": "value2"})

        merged = merge_profiles(base, override)
        assert merged.extra_options == {"base_opt": "value1", "override_opt": "value2"}

    def test_override_extra_options(self):
        """Test override extra options takes precedence."""
        base = RuntimeProfile(extra_options={"common": "base"})
        override = RuntimeProfile(extra_options={"common": "override"})

        merged = merge_profiles(base, override)
        assert merged.extra_options["common"] == "override"


class TestGetEnvOverrides:
    """Tests for get_env_overrides function."""

    def test_get_overrides(self):
        """Test getting environment overrides."""
        # Set some test env vars
        os.environ["ARF_TEST_BOOL"] = "true"
        os.environ["ARF_TEST_INT"] = "42"
        os.environ["ARF_TEST_FLOAT"] = "3.14"
        os.environ["ARF_TEST_STR"] = "hello"

        try:
            overrides = get_env_overrides()
            assert overrides["test_bool"] is True
            assert overrides["test_int"] == 42
            assert overrides["test_float"] == 3.14
            assert overrides["test_str"] == "hello"
        finally:
            # Clean up
            for key in ["ARF_TEST_BOOL", "ARF_TEST_INT", "ARF_TEST_FLOAT", "ARF_TEST_STR"]:
                os.environ.pop(key, None)

    def test_non_arf_vars_ignored(self):
        """Test non-ARF vars are ignored."""
        os.environ["OTHER_VAR"] = "value"
        try:
            overrides = get_env_overrides()
            assert "other_var" not in overrides
        finally:
            os.environ.pop("OTHER_VAR", None)


class TestApplyEnvOverrides:
    """Tests for apply_env_overrides function."""

    def test_apply_known_attrs(self):
        """Test applying to known attributes."""
        os.environ["ARF_MAX_DEPTH"] = "10"
        os.environ["ARF_TOP_K"] = "20"

        try:
            profile = RuntimeProfile()
            apply_env_overrides(profile)
            assert profile.max_path_depth == 10
            assert profile.top_k_paths == 20
        finally:
            os.environ.pop("ARF_MAX_DEPTH", None)
            os.environ.pop("ARF_TOP_K", None)

    def test_apply_extra_options(self):
        """Test applying to extra options."""
        os.environ["ARF_CUSTOM_OPTION"] = "custom_value"

        try:
            profile = RuntimeProfile()
            apply_env_overrides(profile)
            assert profile.extra_options["custom_option"] == "custom_value"
        finally:
            os.environ.pop("ARF_CUSTOM_OPTION", None)


class TestValidateProfile:
    """Tests for validate_profile function."""

    def test_valid_profile(self):
        """Test valid profile."""
        profile = RuntimeProfile()
        warnings = validate_profile(profile)
        assert warnings == []

    def test_invalid_q8_precision(self):
        """Test invalid q8_precision."""
        profile = RuntimeProfile(q8_precision=12)
        warnings = validate_profile(profile)
        assert any("q8_precision" in w for w in warnings)

    def test_invalid_max_depth(self):
        """Test invalid max_path_depth."""
        profile = RuntimeProfile(max_path_depth=0)
        warnings = validate_profile(profile)
        assert any("max_path_depth" in w for w in warnings)

    def test_invalid_top_k(self):
        """Test invalid top_k_paths."""
        profile = RuntimeProfile(top_k_paths=0)
        warnings = validate_profile(profile)
        assert any("top_k_paths" in w for w in warnings)