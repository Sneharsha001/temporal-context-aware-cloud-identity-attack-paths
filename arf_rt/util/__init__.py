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
        match_wildcard_pattern,
        topological_sort,
        export_to_dot,
        export_to_cytoscape,
    )
"""

from arf_rt.util.retry import retry, RetryError
from arf_rt.util.text import (
    slugify,
    truncate,
    indent_block,
    wrap_text,
    join_with_oxford_comma,
    pluralize,
    snake_to_camel,
    camel_to_snake,
    strip_ansi,
    dedent,
    shorten,
    extract_version,
)
from arf_rt.util.structures import flatten_dict, deep_merge
from arf_rt.util.network import (
    parse_ip,
    parse_network,
    is_ip_in_network,
    is_ip_in_any_network,
    is_private_ip,
    network_overlaps,
    network_contains,
    get_network_bounds,
    calculate_subnet_split,
    format_cidr,
    is_reserved_ip,
)
from arf_rt.util.hashing import canonical_json, sha256_digest, canonical_hash
from arf_rt.util.datetime_helpers import (
    parse_iso8601,
    format_iso8601,
    is_within_temporal_window,
    parse_duration_seconds,
    time_range_overlaps,
    time_range_contains,
    intersect_time_ranges,
    format_duration_seconds,
)
from arf_rt.util.config_loader import load_profile, RuntimeProfile
from arf_rt.util.graph_traversal import find_all_simple_paths, detect_cycles
from arf_rt.util.math_stats import (
    shannon_entropy,
    normalize_distribution,
    kl_divergence,
    js_divergence,
    cosine_similarity,
    euclidean_distance,
    mean,
    variance,
    standard_deviation,
)
from arf_rt.util.policy_patterns import match_wildcard_pattern, match_any_pattern, sanitize_arn_pattern
from arf_rt.util.dag import topological_sort, get_ancestors
from arf_rt.util.visualization import export_to_dot, export_to_cytoscape

__all__ = [
    "retry",
    "RetryError",
    "slugify",
    "truncate",
    "indent_block",
    "wrap_text",
    "join_with_oxford_comma",
    "pluralize",
    "snake_to_camel",
    "camel_to_snake",
    "strip_ansi",
    "dedent",
    "shorten",
    "extract_version",
    "flatten_dict",
    "deep_merge",
    "parse_ip",
    "parse_network",
    "is_ip_in_network",
    "is_ip_in_any_network",
    "is_private_ip",
    "network_overlaps",
    "network_contains",
    "get_network_bounds",
    "calculate_subnet_split",
    "format_cidr",
    "is_reserved_ip",
    "canonical_json",
    "sha256_digest",
    "canonical_hash",
    "parse_iso8601",
    "format_iso8601",
    "is_within_temporal_window",
    "parse_duration_seconds",
    "time_range_overlaps",
    "time_range_contains",
    "intersect_time_ranges",
    "format_duration_seconds",
    "load_profile",
    "RuntimeProfile",
    "find_all_simple_paths",
    "detect_cycles",
    "shannon_entropy",
    "normalize_distribution",
    "kl_divergence",
    "js_divergence",
    "cosine_similarity",
    "euclidean_distance",
    "mean",
    "variance",
    "standard_deviation",
    "match_wildcard_pattern",
    "match_any_pattern",
    "sanitize_arn_pattern",
    "topological_sort",
    "get_ancestors",
    "export_to_dot",
    "export_to_cytoscape",
]
