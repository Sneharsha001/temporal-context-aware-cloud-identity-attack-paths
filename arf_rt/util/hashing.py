"""
arf_rt/util/hashing.py - Deterministic cryptographic hashing and digest utilities.

Ensures bit-for-bit reproducibility of state snapshots, scenario configurations,
and graph element digests across heterogeneous platforms.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Union


def canonical_json(obj: Any) -> str:
    """Serialize a Python object into canonical JSON.

    Key guarantees:
    - Dict keys are sorted alphabetically.
    - No extraneous whitespace around delimiters.
    - Encoded in standard ASCII/UTF-8.

    Args:
        obj: JSON-serializable Python data structure.

    Returns:
        Canonical JSON formatted string.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_digest(data: Union[str, bytes]) -> str:
    """Compute standard lowercase SHA-256 hexadecimal digest.

    Args:
        data: String or bytes to hash.

    Returns:
        64-character lowercase hex digest string.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj: Any, prefix: str = "") -> str:
    """Produce deterministic SHA-256 hash of any JSON-serializable object.

    Args:
        obj: Data object to hash.
        prefix: Optional prefix prepended to hash output.

    Returns:
        Prefixed hexadecimal hash.
    """
    c_json = canonical_json(obj)
    digest = sha256_digest(c_json)
    return f"{prefix}{digest}" if prefix else digest


def short_hash(obj: Any, length: int = 12) -> str:
    """Compute truncated canonical hash suitable for concise identifiers.

    Args:
        obj: Data object to hash.
        length: Desired length of truncated hash (default: 12).

    Returns:
        Truncated hash string.
    """
    return sha256_digest(canonical_json(obj))[:length]
