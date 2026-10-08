"""ARF-RT canonicalization and quantization primitives (spec §§3–4).

This module is the foundation of determinism in ARF-RT. Every hash input,
every deterministic ID, every fingerprint flows through these functions.

Rules enforced here:
  - No floats in canonical state / hash inputs (spec §3.1)
  - Keys sorted by UTF-8 byte order (spec §3.1)
  - NULL/empty region normalized to sentinel (spec §3.3)
  - signal_q is int 0..100, confidence_q is int 0..1000 (spec §3.4)
  - All IDs are sha256 of canonical_tuple prefixed by type tag (spec §4.3)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from arf_rt.config import (
    CONFIDENCE_Q_MAX,
    CONFIDENCE_Q_MIN,
    Q8,
    REGION_NULL_SENTINEL,
    SIGNAL_Q_MAX,
    SIGNAL_Q_MIN,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ARFValidationError(ValueError):
    """Raised when input violates ARF-RT validation rules."""


class ARFCanonError(ARFValidationError):
    """Raised when canonical encoding encounters disallowed types (e.g. floats)."""


# ---------------------------------------------------------------------------
# §3.1 — Canonical JSON encoding
# ---------------------------------------------------------------------------

class _NoFloatEncoder(json.JSONEncoder):
    """JSON encoder that rejects floats in canonical state.

    Floats are allowed only in planner computations (not hashed).
    All canonical state must use integers, strings, bools, None, lists, dicts.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["sort_keys"] = True
        kwargs["separators"] = (",", ":")
        kwargs["ensure_ascii"] = True
        super().__init__(**kwargs)

    def encode(self, o: Any) -> str:
        # Walk the structure to reject floats before encoding
        _check_no_floats(o)
        return super().encode(o)

    def default(self, o: Any) -> Any:
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _check_no_floats(obj: Any) -> None:
    """Recursively check that no floats appear in the object tree."""
    if isinstance(obj, float):
        raise ARFCanonError(
            f"Float {obj!r} is not permitted in canonical JSON. "
            "Use integers for all canonical state."
        )
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_no_floats(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_no_floats(item)


# Singleton encoder instance
_CANON_ENCODER = _NoFloatEncoder()


def canonical_json(x: Any) -> str:
    """Produce deterministic canonical JSON string.

    Spec §3.1:
      - UTF-8 output
      - Object keys sorted by lexicographic byte order of UTF-8 encoded key strings
      - separators (',', ':')
      - ensure_ascii=True
      - No floats permitted in canonical state content

    Returns:
        Canonical JSON string (ASCII-safe, UTF-8 compatible).

    Raises:
        ARFCanonError: If a float is encountered.
    """
    return _CANON_ENCODER.encode(x)


# ---------------------------------------------------------------------------
# §3.2 — Canonical tuple encoding
# ---------------------------------------------------------------------------

def canonical_tuple(parts: list[str]) -> str:
    """Produce canonical JSON array of strings for hash input.

    Spec §3.2: All parts must be strings. Returns canonical_json(parts).

    Raises:
        ARFValidationError: If any part is not a string.
    """
    for i, p in enumerate(parts):
        if not isinstance(p, str):
            raise ARFValidationError(
                f"canonical_tuple part[{i}] must be str, got {type(p).__name__}: {p!r}"
            )
    return canonical_json(parts)


# ---------------------------------------------------------------------------
# §3.3 — NULL/empty normalization
# ---------------------------------------------------------------------------

def region_norm(region: str | None) -> str:
    """Normalize region to canonical form.

    Spec §3.3:
      - None -> REGION_NULL_SENTINEL
      - empty/whitespace -> REGION_NULL_SENTINEL
      - else stripped string
    """
    if region is None:
        return REGION_NULL_SENTINEL
    r = region.strip()
    if r == "":
        return REGION_NULL_SENTINEL
    return r


# ---------------------------------------------------------------------------
# §3.4 — Quantization helpers
# ---------------------------------------------------------------------------

def clamp_int(x: Any, lo: int, hi: int) -> int:
    """Validate that x is an integer in [lo, hi].

    Spec §3.4: Raise validation error unless explicitly allow-clamp.
    MVP: strict — no clamping, only validation.

    Raises:
        ARFValidationError: If x is not an int or is out of range.
    """
    if isinstance(x, bool):
        raise ARFValidationError(
            f"Expected int in [{lo}, {hi}], got bool: {x!r}"
        )
    if not isinstance(x, int):
        raise ARFValidationError(
            f"Expected int in [{lo}, {hi}], got {type(x).__name__}: {x!r}"
        )
    if x < lo or x > hi:
        raise ARFValidationError(
            f"Integer {x} out of range [{lo}, {hi}]"
        )
    return x


def clamp_signal_q_int(q: Any) -> int:
    """Validate signal_q as int 0..100. Rejects floats.

    Spec §3.4 + §18.3: Scenario MUST provide signal_q as int 0..100.
    """
    return clamp_int(q, SIGNAL_Q_MIN, SIGNAL_Q_MAX)


def clamp_confidence_q_int(q: Any) -> int:
    """Validate confidence_q as int 0..1000. Rejects floats.

    Spec §3.4 + §18.3: Scenario MUST provide confidence_q as int 0..1000.
    """
    return clamp_int(q, CONFIDENCE_Q_MIN, CONFIDENCE_Q_MAX)


def signal_q_from_unit_float(x01: float) -> int:
    """Convert unit float [0.0, 1.0] to signal_q int 0..100.

    Spec §3.4: Optional helper. NOT accepted in scenario JSON in MVP.
    Available for internal/planner use only.
    """
    if not isinstance(x01, (int, float)):
        raise ARFValidationError(f"Expected numeric, got {type(x01).__name__}")
    raw = int(x01 * 100 + 0.5)
    return max(SIGNAL_Q_MIN, min(SIGNAL_Q_MAX, raw))


def confidence_q_from_unit_float(x01: float) -> int:
    """Convert unit float [0.0, 1.0] to confidence_q int 0..1000.

    Spec §3.4: Optional helper. NOT accepted in scenario JSON in MVP.
    """
    if not isinstance(x01, (int, float)):
        raise ARFValidationError(f"Expected numeric, got {type(x01).__name__}")
    raw = int(x01 * 1000 + 0.5)
    return max(CONFIDENCE_Q_MIN, min(CONFIDENCE_Q_MAX, raw))


# ---------------------------------------------------------------------------
# §3.4 — Fixed-point probability
# ---------------------------------------------------------------------------

def edge_p_q8(alpha_i: int, beta_i: int) -> int:
    """Compute fixed-point probability p = alpha / (alpha + beta) scaled by Q8.

    Spec §3.4:
      edge_p_q8 = floor(alpha_i * Q8 / (alpha_i + beta_i))

    Uses Python integer division (floor by default for positive operands).
    """
    if alpha_i < 0 or beta_i < 0:
        raise ARFValidationError(f"alpha_i={alpha_i}, beta_i={beta_i} must be non-negative")
    total = alpha_i + beta_i
    if total == 0:
        raise ARFValidationError("alpha_i + beta_i must be > 0")
    return (alpha_i * Q8) // total


def grouped_product_q8(p_q8: int, edge_p_q8_val: int) -> int:
    """Multiply grouped probability by edge probability in Q8 fixed-point.

    Spec §3.4:
      p_q8 = floor(p_q8 * edge_p_q8 / Q8) in deterministic order
    """
    return (p_q8 * edge_p_q8_val) // Q8


# ---------------------------------------------------------------------------
# Hashing helper
# ---------------------------------------------------------------------------

def _sha256_hex(data: str) -> str:
    """SHA-256 of UTF-8 encoded string, returned as lowercase hex."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# §4.1 — Fingerprints
# ---------------------------------------------------------------------------

def features_fp(features: dict) -> str:
    """Compute features fingerprint: sha256(canonical_json(features)).

    Spec §4.1.
    """
    return _sha256_hex(canonical_json(features))


def properties_fp(properties: dict) -> str:
    """Compute properties fingerprint: sha256(canonical_json(properties)).

    Spec §4.1.
    """
    return _sha256_hex(canonical_json(properties))


# ---------------------------------------------------------------------------
# §4.3 — Deterministic IDs
# ---------------------------------------------------------------------------

def make_node_id(provider: str, node_type: str, provider_id: str, region: str) -> str:
    """Deterministic node ID.

    Spec §4.3:
      node_id = sha256("node|" + canonical_tuple([provider, node_type, provider_id, region_norm]))

    Note: `region` must already be normalized via region_norm() before calling.
    """
    payload = "node|" + canonical_tuple([provider, node_type, provider_id, region])
    return _sha256_hex(payload)


def make_template_id(
    provider: str, edge_type: str, feat_fp: str, feature_schema_version: int
) -> str:
    """Deterministic template ID.

    Spec §4.3:
      template_id = sha256("tpl|" + canonical_tuple([provider, edge_type, features_fp, str(feature_schema_version)]))
    """
    payload = "tpl|" + canonical_tuple([provider, edge_type, feat_fp, str(feature_schema_version)])
    return _sha256_hex(payload)


def make_edge_id(
    edge_type: str,
    src_node_id: str,
    dst_node_id: str,
    region: str,
    template_id: str,
) -> str:
    """Deterministic edge ID.

    Spec §4.3:
      edge_id = sha256("edge|" + canonical_tuple([edge_type, src_node_id, dst_node_id, region_norm, template_id]))
    """
    payload = "edge|" + canonical_tuple([edge_type, src_node_id, dst_node_id, region, template_id])
    return _sha256_hex(payload)


def make_constraint_id(
    provider: str,
    constraint_type: str,
    scope_type: str,
    scope_id: str,
    region: str,
    prop_fp: str,
) -> str:
    """Deterministic constraint ID.

    Spec §4.3:
      constraint_id = sha256("cst|" + canonical_tuple([provider, constraint_type, scope_type, scope_id, region_norm, properties_fp]))
    """
    payload = "cst|" + canonical_tuple([
        provider, constraint_type, scope_type, scope_id, region, prop_fp
    ])
    return _sha256_hex(payload)


def make_objective_id(
    objective_type: str,
    start_node_ids: list[str],
    target_node_ids: list[str],
    max_depth: int,
    k: int,
) -> str:
    """Deterministic objective ID.

    Spec §4.3:
      starts_json = canonical_json(sorted(start_node_ids))
      targets_json = canonical_json(sorted(target_node_ids))
      objective_id = sha256("obj|" + canonical_tuple([objective_type, starts_json, targets_json, str(max_depth), str(k)]))
    """
    starts_json = canonical_json(sorted(start_node_ids))
    targets_json = canonical_json(sorted(target_node_ids))
    payload = "obj|" + canonical_tuple([
        objective_type, starts_json, targets_json, str(max_depth), str(k)
    ])
    return _sha256_hex(payload)


# ---------------------------------------------------------------------------
# §4.2 — Human-readable keys (never parsed; for debugging/display)
# ---------------------------------------------------------------------------

def make_template_key(provider: str, edge_type: str, feat_fp: str) -> str:
    """Human-readable template key (spec §4.2). Never parsed programmatically."""
    return f"{provider}|{edge_type}|f={feat_fp}"


def make_constraint_key(
    provider: str,
    constraint_type: str,
    scope_type: str,
    scope_id: str,
    region: str,
    prop_fp: str,
) -> str:
    """Human-readable constraint key (spec §4.2). Never parsed programmatically."""
    return f"{provider}|{constraint_type}|{scope_type}|{scope_id}|r={region}|p={prop_fp}"


# ---------------------------------------------------------------------------
# §7.4 — Canonical flags_json shape
# ---------------------------------------------------------------------------

DEFAULT_FLAGS: dict[str, bool] = {
    "conflict": False,
    "counterfactual_override": False,
    "prior_only": False,
    "stale": False,
}


def make_flags_json(**overrides: bool) -> str:
    """Produce canonical flags_json with all required keys.

    Spec §7.4: Always include conflict, counterfactual_override, prior_only, stale
    with defaults. Returns canonical JSON string ready for DB storage.
    """
    flags = dict(DEFAULT_FLAGS)
    for k, v in overrides.items():
        if k not in DEFAULT_FLAGS:
            raise ARFValidationError(f"Unknown flag key: {k!r}")
        if not isinstance(v, bool):
            raise ARFValidationError(f"Flag {k!r} must be bool, got {type(v).__name__}")
        flags[k] = v
    return canonical_json(flags)
