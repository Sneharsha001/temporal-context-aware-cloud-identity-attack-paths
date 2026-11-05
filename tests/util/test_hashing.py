"""Tests for hashing module."""

from __future__ import annotations

import os
import tempfile

import pytest

from arf_rt.util.hashing import (
    canonical_json,
    sha256_digest,
    canonical_hash,
    short_hash,
    hmac_sha256,
    hash_chain,
    hash_file,
    hash_combine,
    stable_hash,
)


class TestCanonicalJSON:
    """Tests for canonical_json function."""

    def test_dict_ordering(self):
        """Test that dict keys are sorted."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_nested_dict(self):
        """Test nested dict ordering."""
        obj = {"b": {"z": 1, "a": 2}, "a": 1}
        result = canonical_json(obj)
        assert result == '{"a":1,"b":{"a":2,"z":1}}'

    def test_list_preserved(self):
        """Test that list order is preserved."""
        obj = {"items": [3, 1, 2]}
        result = canonical_json(obj)
        assert result == '{"items":[3,1,2]}'

    def test_no_whitespace(self):
        """Test no extraneous whitespace."""
        obj = {"a": 1, "b": 2}
        result = canonical_json(obj)
        assert " " not in result

    def test_unicode_escaped(self):
        """Test unicode is escaped to ASCII."""
        obj = {"key": "café"}
        result = canonical_json(obj)
        assert "caf\\u00e9" in result


class TestSHA256Digest:
    """Tests for sha256_digest function."""

    def test_string_input(self):
        """Test hashing string input."""
        result = sha256_digest("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_bytes_input(self):
        """Test hashing bytes input."""
        result = sha256_digest(b"hello")
        assert len(result) == 64

    def test_deterministic(self):
        """Test deterministic output."""
        assert sha256_digest("hello") == sha256_digest("hello")

    def test_different_inputs(self):
        """Test different inputs produce different hashes."""
        assert sha256_digest("hello") != sha256_digest("world")

    def test_known_hash(self):
        """Test known hash value."""
        # SHA-256 of empty string
        result = sha256_digest("")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestCanonicalHash:
    """Tests for canonical_hash function."""

    def test_basic(self):
        """Test basic canonical hash."""
        obj = {"a": 1, "b": 2}
        result = canonical_hash(obj)
        assert len(result) == 64

    def test_with_prefix(self):
        """Test hash with prefix."""
        obj = {"a": 1}
        result = canonical_hash(obj, prefix="test_")
        assert result.startswith("test_")
        assert len(result) == 64 + 5

    def test_deterministic(self):
        """Test deterministic output."""
        obj = {"a": 1, "b": 2}
        assert canonical_hash(obj) == canonical_hash(obj)

    def test_different_objects(self):
        """Test different objects produce different hashes."""
        assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


class TestShortHash:
    """Tests for short_hash function."""

    def test_default_length(self):
        """Test default hash length."""
        obj = {"a": 1}
        result = short_hash(obj)
        assert len(result) == 12

    def test_custom_length(self):
        """Test custom hash length."""
        obj = {"a": 1}
        result = short_hash(obj, length=8)
        assert len(result) == 8

    def test_deterministic(self):
        """Test deterministic output."""
        obj = {"a": 1}
        assert short_hash(obj) == short_hash(obj)


class TestHMACSHA256:
    """Tests for hmac_sha256 function."""

    def test_string_key_and_data(self):
        """Test HMAC with string key and data."""
        key = "secret"
        data = "message"
        result = hmac_sha256(key, data)
        assert len(result) == 64

    def test_bytes_key_and_data(self):
        """Test HMAC with bytes key and data."""
        key = b"secret"
        data = b"message"
        result = hmac_sha256(key, data)
        assert len(result) == 64

    def test_deterministic(self):
        """Test deterministic output."""
        key = "secret"
        data = "message"
        assert hmac_sha256(key, data) == hmac_sha256(key, data)

    def test_different_key(self):
        """Test different keys produce different HMACs."""
        assert hmac_sha256("key1", "msg") != hmac_sha256("key2", "msg")

    def test_different_data(self):
        """Test different data produce different HMACs."""
        assert hmac_sha256("key", "msg1") != hmac_sha256("key", "msg2")


class TestHashChain:
    """Tests for hash_chain function."""

    def test_single_item(self):
        """Test chaining single item."""
        result = hash_chain("item1")
        assert len(result) == 64

    def test_multiple_items(self):
        """Test chaining multiple items."""
        result = hash_chain("item1", "item2", "item3")
        assert len(result) == 64

    def test_deterministic(self):
        """Test deterministic output."""
        assert hash_chain("a", "b") == hash_chain("a", "b")

    def test_order_matters(self):
        """Test that order of items matters."""
        assert hash_chain("a", "b") != hash_chain("b", "a")


class TestHashFile:
    """Tests for hash_file function."""

    def test_hash_file(self):
        """Test hashing a file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("hello world")
            temp_path = f.name

        try:
            result = hash_file(temp_path)
            assert len(result) == 64
            # SHA-256 of "hello world"
            assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        finally:
            os.unlink(temp_path)

    def test_empty_file(self):
        """Test hashing empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            result = hash_file(temp_path)
            assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        finally:
            os.unlink(temp_path)


class TestHashCombine:
    """Tests for hash_combine function."""

    def test_combine_two(self):
        """Test combining two hashes."""
        h1 = "a" * 64
        h2 = "b" * 64
        result = hash_combine(h1, h2)
        assert len(result) == 64

    def test_combine_many(self):
        """Test combining many hashes."""
        hashes = [f"{i:064x}" for i in range(10)]
        result = hash_combine(*hashes)
        assert len(result) == 64

    def test_order_independent(self):
        """Test that combination is order-independent (sorted)."""
        h1 = "a" * 64
        h2 = "b" * 64
        assert hash_combine(h1, h2) == hash_combine(h2, h1)

    def test_deterministic(self):
        """Test deterministic output."""
        h1 = "a" * 64
        h2 = "b" * 64
        assert hash_combine(h1, h2) == hash_combine(h1, h2)


class TestStableHash:
    """Tests for stable_hash function."""

    def test_returns_int(self):
        """Test returns integer."""
        result = stable_hash({"a": 1})
        assert isinstance(result, int)

    def test_64_bit(self):
        """Test returns 64-bit value."""
        result = stable_hash({"a": 1})
        assert 0 <= result < (1 << 64)

    def test_deterministic(self):
        """Test deterministic output."""
        obj = {"a": 1, "b": 2}
        assert stable_hash(obj) == stable_hash(obj)

    def test_different_objects(self):
        """Test different objects produce different hashes."""
        # Not guaranteed but very likely
        assert stable_hash({"a": 1}) != stable_hash({"a": 2})