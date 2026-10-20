"""
arf_rt/util/policy_patterns.py - IAM policy wildcard pattern matching and condition evaluators.

Supports AWS IAM wildcard ('*', '?') matching on resource ARNs, action names,
and condition key values during replay analysis.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Sequence, Union


def match_wildcard_pattern(pattern: str, target: str, case_sensitive: bool = False) -> bool:
    """Evaluate whether target matches an AWS wildcard pattern containing '*' and '?'.

    Args:
        pattern: Pattern containing wildcards (e.g., 's3:Get*', 'arn:aws:iam::*:role/*').
        target: Target string to evaluate.
        case_sensitive: Whether match is case sensitive (default False for AWS actions).

    Returns:
        True if target matches pattern, False otherwise.
    """
    if not case_sensitive:
        pattern = pattern.lower()
        target = target.lower()

    return fnmatch.fnmatchcase(target, pattern)


def match_any_pattern(patterns: Sequence[str], target: str, case_sensitive: bool = False) -> bool:
    """Check if target matches at least one pattern in the provided sequence."""
    return any(match_wildcard_pattern(p, target, case_sensitive) for p in patterns)


def sanitize_arn_pattern(arn: str) -> str:
    """Normalize ARN by standardizing account wildcards and partition identifiers."""
    parts = arn.strip().split(":")
    if len(parts) >= 5 and parts[4] == "*":
        parts[4] = "[0-9]{12}"
    return ":".join(parts)
