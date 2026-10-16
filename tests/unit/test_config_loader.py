"""
tests/unit/test_config_loader.py - Unit tests for configuration profile loader.
"""

import os
from arf_rt.util.config_loader import load_profile, RuntimeProfile


def test_default_profile():
    profile = load_profile(None)
    assert profile.profile_name == "default"
    assert profile.max_path_depth == 6
    assert profile.top_k_paths == 5
    assert profile.safe_replay_mode is True


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("ARF_PROFILE", "custom-ci")
    monkeypatch.setenv("ARF_MAX_DEPTH", "10")
    monkeypatch.setenv("ARF_TOP_K", "15")
    monkeypatch.setenv("ARF_SAFE_MODE", "0")

    profile = load_profile(None)
    assert profile.profile_name == "custom-ci"
    assert profile.max_path_depth == 10
    assert profile.top_k_paths == 15
    assert profile.safe_replay_mode is False
