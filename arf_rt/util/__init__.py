"""
arf_rt/util/__init__.py - Utility sub-package for ARF-RT.

Re-exports the most commonly used utilities for convenient import:

    from arf_rt.util import (
        retry,
        slugify,
        flatten_dict,
        parse_ip,
        canonical_json,
        parse_iso8601,
        load_profile,
        find_all_simple_paths,
        shannon_entropy,
    )
"""

from arf_rt.util.retry import retry, RetryError
from arf_rt.util.text import slugify, truncate, indent_block
from arf_rt.util.structures import flatten_dict, deep_merge
from arf_rt.util.network import parse_ip, parse_network, is_ip_in_network
from arf_rt.util.hashing import canonical_json, sha256_digest, canonical_hash
from arf_rt.util.datetime_helpers import parse_iso8601, format_iso8601, is_within_temporal_window
from arf_rt.util.config_loader import load_profile, RuntimeProfile
from arf_rt.util.graph_traversal import find_all_simple_paths, detect_cycles
from arf_rt.util.math_stats import shannon_entropy, normalize_distribution, kl_divergence

__all__ = [
    "retry",
    "RetryError",
    "slugify",
    "truncate",
    "indent_block",
    "flatten_dict",
    "deep_merge",
    "parse_ip",
    "parse_network",
    "is_ip_in_network",
    "canonical_json",
    "sha256_digest",
    "canonical_hash",
    "parse_iso8601",
    "format_iso8601",
    "is_within_temporal_window",
    "load_profile",
    "RuntimeProfile",
    "find_all_simple_paths",
    "detect_cycles",
    "shannon_entropy",
    "normalize_distribution",
    "kl_divergence",
]
