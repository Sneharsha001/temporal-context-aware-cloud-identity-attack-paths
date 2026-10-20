"""
tests/unit/test_policy_patterns.py - Unit tests for wildcard pattern matching.
"""

from arf_rt.util.policy_patterns import (
    match_wildcard_pattern,
    match_any_pattern,
    sanitize_arn_pattern,
)


def test_match_wildcard_pattern_actions():
    assert match_wildcard_pattern("s3:Get*", "s3:GetObject") is True
    assert match_wildcard_pattern("s3:Get*", "s3:PutObject") is False
    assert match_wildcard_pattern("iam:*Role", "iam:AssumeRole") is True


def test_match_wildcard_pattern_arns():
    pattern = "arn:aws:iam::123456789012:role/*"
    assert match_wildcard_pattern(pattern, "arn:aws:iam::123456789012:role/admin") is True
    assert match_wildcard_pattern(pattern, "arn:aws:iam::999999999999:role/admin") is False


def test_match_any_pattern():
    patterns = ["s3:Get*", "ec2:Describe*"]
    assert match_any_pattern(patterns, "s3:GetObject") is True
    assert match_any_pattern(patterns, "ec2:DescribeInstances") is True
    assert match_any_pattern(patterns, "dynamodb:PutItem") is False


def test_sanitize_arn_pattern():
    sanitized = sanitize_arn_pattern("arn:aws:iam:*:*:role/test")
    assert "[0-9]{12}" in sanitized
