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
from typing import Any, Dict, Optional


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
