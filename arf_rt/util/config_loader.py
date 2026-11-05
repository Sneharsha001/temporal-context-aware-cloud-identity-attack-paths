"""
arf_rt/util/config_loader.py - Configuration profile loader and environment resolver.

Supports loading analysis profiles, setting default Q8 precision, and merging
environment variables prefixed with ARF_ into runtime settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeProfile:
    profile_name: str = "default"
    q8_precision: int = 8
    max_path_depth: int = 6
    top_k_paths: int = 5
    safe_replay_mode: bool = True
    extra_options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RuntimeProfile:
        return cls(
            profile_name=str(data.get("profile_name", "default")),
            q8_precision=int(data.get("q8_precision", 8)),
            max_path_depth=int(data.get("max_path_depth", 6)),
            top_k_paths=int(data.get("top_k_paths", 5)),
            safe_replay_mode=bool(data.get("safe_replay_mode", True)),
            extra_options={k: v for k, v in data.items() if k not in cls.__annotations__},
        )


def load_profile(file_path: Optional[Path] = None) -> RuntimeProfile:
    """Load configuration profile from a file or fall back to defaults, applying environment variables.

    Environment overrides:
    - ARF_PROFILE: sets profile_name
    - ARF_MAX_DEPTH: sets max_path_depth
    - ARF_TOP_K: sets top_k_paths
    - ARF_SAFE_MODE: sets safe_replay_mode
    """
    data: Dict[str, Any] = {}

    if file_path and file_path.is_file():
        text = file_path.read_text(encoding="utf-8")
        data = json.loads(text)

    profile = RuntimeProfile.from_dict(data)

    if "ARF_PROFILE" in os.environ:
        profile.profile_name = os.environ["ARF_PROFILE"]
    if "ARF_MAX_DEPTH" in os.environ:
        profile.max_path_depth = int(os.environ["ARF_MAX_DEPTH"])
    if "ARF_TOP_K" in os.environ:
        profile.top_k_paths = int(os.environ["ARF_TOP_K"])
    if "ARF_SAFE_MODE" in os.environ:
        profile.safe_replay_mode = os.environ["ARF_SAFE_MODE"].lower() in ("1", "true", "yes")

    return profile


def load_profile_from_yaml(file_path: Path) -> RuntimeProfile:
    """Load configuration profile from YAML file.

    Args:
        file_path: Path to YAML file.

    Returns:
        RuntimeProfile instance.

    Raises:
        ImportError: If PyYAML is not installed.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")

    if not file_path.is_file():
        raise FileNotFoundError(f"Config file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return RuntimeProfile.from_dict(data or {})


def load_profile_auto(file_path: Optional[Path] = None) -> RuntimeProfile:
    """Load profile with automatic format detection (JSON or YAML).

    Args:
        file_path: Path to config file.

    Returns:
        RuntimeProfile instance.
    """
    if file_path is None or not file_path.is_file():
        return load_profile(file_path)

    suffix = file_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_profile_from_yaml(file_path)
    elif suffix == ".json":
        return load_profile(file_path)
    else:
        # Try JSON first, then YAML
        try:
            return load_profile(file_path)
        except json.JSONDecodeError:
            try:
                return load_profile_from_yaml(file_path)
            except Exception:
                return RuntimeProfile()


def merge_profiles(base: RuntimeProfile, override: RuntimeProfile) -> RuntimeProfile:
    """Merge two profiles, with override taking precedence.

    Args:
        base: Base profile.
        override: Override profile.

    Returns:
        Merged RuntimeProfile.
    """
    base_dict = {
        "profile_name": base.profile_name,
        "q8_precision": base.q8_precision,
        "max_path_depth": base.max_path_depth,
        "top_k_paths": base.top_k_paths,
        "safe_replay_mode": base.safe_replay_mode,
        **base.extra_options,
    }
    override_dict = {
        "profile_name": override.profile_name,
        "q8_precision": override.q8_precision,
        "max_path_depth": override.max_path_depth,
        "top_k_paths": override.top_k_paths,
        "safe_replay_mode": override.safe_replay_mode,
        **override.extra_options,
    }
    return RuntimeProfile.from_dict({**base_dict, **override_dict})


def get_env_overrides() -> Dict[str, Any]:
    """Get all ARF_ environment variable overrides.

    Returns:
        Dictionary of environment variable overrides.
    """
    overrides = {}
    prefix = "ARF_"

    for key, value in os.environ.items():
        if key.startswith(prefix):
            config_key = key[len(prefix):].lower()
            # Try to convert to appropriate type
            if value.lower() in ("true", "false"):
                overrides[config_key] = value.lower() == "true"
            elif value.isdigit():
                overrides[config_key] = int(value)
            else:
                try:
                    overrides[config_key] = float(value)
                except ValueError:
                    overrides[config_key] = value

    return overrides


def apply_env_overrides(profile: RuntimeProfile) -> RuntimeProfile:
    """Apply environment variable overrides to a profile.

    Args:
        profile: Profile to modify.

    Returns:
        Modified profile (same instance).
    """
    overrides = get_env_overrides()

    for key, value in overrides.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
        else:
            profile.extra_options[key] = value

    return profile


def validate_profile(profile: RuntimeProfile) -> List[str]:
    """Validate profile and return warnings.

    Args:
        profile: Profile to validate.

    Returns:
        List of warning messages (empty if valid).
    """
    warnings = []

    if profile.q8_precision not in (4, 8, 16, 32):
        warnings.append(f"q8_precision should be 4, 8, 16, or 32, got {profile.q8_precision}")

    if profile.max_path_depth < 1:
        warnings.append("max_path_depth should be >= 1")

    if profile.top_k_paths < 1:
        warnings.append("top_k_paths should be >= 1")

    return warnings
