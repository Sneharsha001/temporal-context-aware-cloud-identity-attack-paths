"""
tests/unit/test_hashing.py - Unit tests for deterministic canonical hashing utilities.
"""

from arf_rt.util.hashing import (
    canonical_json,
    sha256_digest,
    canonical_hash,
    short_hash,
)


def test_canonical_json_sorting():
    obj1 = {"b": 2, "a": 1, "c": 3}
    obj2 = {"c": 3, "a": 1, "b": 2}
    assert canonical_json(obj1) == '{"a":1,"b":2,"c":3}'
    assert canonical_json(obj1) == canonical_json(obj2)


def test_sha256_digest_reproducible():
    dig1 = sha256_digest("test-payload")
    dig2 = sha256_digest("test-payload")
    assert dig1 == dig2
    assert len(dig1) == 64


def test_canonical_hash_with_prefix():
    h = canonical_hash({"foo": "bar"}, prefix="state_")
    assert h.startswith("state_")
    assert len(h) == len("state_") + 64


def test_short_hash():
    sh = short_hash({"test": 123}, length=8)
    assert len(sh) == 8
