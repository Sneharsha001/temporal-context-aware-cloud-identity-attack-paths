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


def hmac_sha256(key: Union[str, bytes], data: Union[str, bytes]) -> str:
    """Compute HMAC-SHA256 digest.

    Args:
        key: Secret key for HMAC.
        data: Data to authenticate.

    Returns:
        Lowercase hexadecimal HMAC digest.
    """
    import hmac

    if isinstance(key, str):
        key = key.encode("utf-8")
    if isinstance(data, str):
        data = data.encode("utf-8")

    return hmac.new(key, data, hashlib.sha256).hexdigest()


def hash_chain(*items: Any) -> str:
    """Compute hash of concatenated canonical hashes (Merkle-like).

    Args:
        *items: Items to hash together.

    Returns:
        SHA-256 hash of concatenated individual hashes.
    """
    hashes = [canonical_hash(item) for item in items]
    concatenated = "".join(hashes)
    return sha256_digest(concatenated)


def hash_file(path: str, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        path: Path to file.
        chunk_size: Read chunk size in bytes.

    Returns:
        Lowercase hexadecimal digest.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_combine(*hashes: str) -> str:
    """Combine multiple hashes into a single deterministic hash.

    Args:
        *hashes: Hexadecimal hash strings to combine.

    Returns:
        Combined SHA-256 hash.
    """
    sorted_hashes = sorted(hashes)
    return sha256_digest("".join(sorted_hashes))


def stable_hash(obj: Any) -> int:
    """Compute a stable 64-bit integer hash for use in hash tables.

    Args:
        obj: JSON-serializable object.

    Returns:
        64-bit integer hash value.
    """
    # Use SHA-256 and take first 8 bytes as integer
    digest = sha256_digest(canonical_json(obj))
    return int(digest[:16], 16)  # First 64 bits
