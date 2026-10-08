"""Tests for ARF-RT canonicalization and quantization primitives.

Covers spec §§3–4 requirements:
  - Canonical JSON key sorting (UTF-8 byte order)
  - No floats in canonical state
  - Canonical tuple encoding
  - Region normalization
  - Integer-only signal_q/confidence_q domains
  - Deterministic ID stability
  - Fixed-point probability
  - Fingerprints
  - Flags JSON canonical shape
"""

import hashlib
import json

import pytest

from arf_rt.config import Q8, REGION_NULL_SENTINEL
from arf_rt.util.canon import (
    ARFCanonError,
    ARFValidationError,
    canonical_json,
    canonical_tuple,
    clamp_confidence_q_int,
    clamp_int,
    clamp_signal_q_int,
    confidence_q_from_unit_float,
    edge_p_q8,
    features_fp,
    grouped_product_q8,
    make_constraint_id,
    make_constraint_key,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_objective_id,
    make_template_id,
    make_template_key,
    properties_fp,
    region_norm,
    signal_q_from_unit_float,
)


# ===================================================================
# §3.1 — Canonical JSON encoding
# ===================================================================

class TestCanonicalJson:
    """Tests for canonical_json() — spec §3.1."""

    def test_key_sort_utf8_lex_order(self):
        """Keys must be sorted by UTF-8 byte order."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_key_sort_nested(self):
        """Nested objects also sorted."""
        obj = {"b": {"d": 1, "c": 2}, "a": 3}
        result = canonical_json(obj)
        assert result == '{"a":3,"b":{"c":2,"d":1}}'

    def test_separators_no_spaces(self):
        """Separators must be (',', ':') with no spaces."""
        obj = {"key": [1, 2, 3]}
        result = canonical_json(obj)
        assert " " not in result
        assert result == '{"key":[1,2,3]}'

    def test_ensure_ascii(self):
        """Non-ASCII chars must be escaped."""
        obj = {"name": "café"}
        result = canonical_json(obj)
        assert "\\u" in result
        assert "café" not in result

    def test_no_floats_in_output_raises(self):
        """Floats must be rejected with ARFCanonError."""
        with pytest.raises(ARFCanonError, match="Float"):
            canonical_json({"score": 3.14})

    def test_no_floats_in_list_raises(self):
        with pytest.raises(ARFCanonError, match="Float"):
            canonical_json([1, 2.0, 3])

    def test_no_floats_nested_raises(self):
        with pytest.raises(ARFCanonError, match="Float"):
            canonical_json({"a": {"b": 0.5}})

    def test_integers_allowed(self):
        assert canonical_json({"val": 42}) == '{"val":42}'

    def test_none_encoded_as_null(self):
        assert canonical_json(None) == "null"

    def test_bool_encoded(self):
        assert canonical_json({"flag": True}) == '{"flag":true}'
        assert canonical_json({"flag": False}) == '{"flag":false}'

    def test_string_encoded(self):
        assert canonical_json("hello") == '"hello"'

    def test_list_encoded(self):
        assert canonical_json([1, 2, 3]) == "[1,2,3]"

    def test_empty_dict(self):
        assert canonical_json({}) == "{}"

    def test_empty_list(self):
        assert canonical_json([]) == "[]"

    def test_null_in_list(self):
        """JSON null must be used for None values (critical for obs_digest)."""
        result = canonical_json([1, None, "test"])
        assert result == '[1,null,"test"]'

    def test_deterministic_across_calls(self):
        """Same input must always produce same output."""
        obj = {"z": 1, "a": [None, True, 3], "m": {"x": 10, "b": 20}}
        results = [canonical_json(obj) for _ in range(100)]
        assert len(set(results)) == 1

    def test_key_order_matches_python_sort_keys(self):
        """Our implementation should match json.dumps sort_keys for ASCII keys."""
        obj = {"zebra": 1, "alpha": 2, "BETA": 3, "beta": 4}
        expected = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert canonical_json(obj) == expected


# ===================================================================
# §3.2 — Canonical tuple encoding
# ===================================================================

class TestCanonicalTuple:
    """Tests for canonical_tuple() — spec §3.2."""

    def test_produces_json_array_of_strings(self):
        result = canonical_tuple(["a", "b", "c"])
        parsed = json.loads(result)
        assert parsed == ["a", "b", "c"]
        assert all(isinstance(x, str) for x in parsed)

    def test_rejects_non_string_int(self):
        with pytest.raises(ARFValidationError, match="must be str"):
            canonical_tuple(["a", 1, "c"])

    def test_rejects_non_string_none(self):
        with pytest.raises(ARFValidationError, match="must be str"):
            canonical_tuple(["a", None])

    def test_rejects_non_string_bool(self):
        with pytest.raises(ARFValidationError, match="must be str"):
            canonical_tuple(["a", True])

    def test_empty_list(self):
        assert canonical_tuple([]) == "[]"

    def test_deterministic(self):
        parts = ["provider", "edge_type", "abc123"]
        results = {canonical_tuple(parts) for _ in range(50)}
        assert len(results) == 1

    def test_output_is_canonical_json(self):
        """Output must be identical to canonical_json of same list."""
        parts = ["x", "y", "z"]
        assert canonical_tuple(parts) == canonical_json(parts)


# ===================================================================
# §3.3 — Region normalization
# ===================================================================

class TestRegionNorm:
    """Tests for region_norm() — spec §3.3."""

    def test_none_to_sentinel(self):
        assert region_norm(None) == REGION_NULL_SENTINEL

    def test_empty_string_to_sentinel(self):
        assert region_norm("") == REGION_NULL_SENTINEL

    def test_whitespace_only_to_sentinel(self):
        assert region_norm("   ") == REGION_NULL_SENTINEL

    def test_tabs_to_sentinel(self):
        assert region_norm("\t\n") == REGION_NULL_SENTINEL

    def test_normal_region_unchanged(self):
        assert region_norm("us-east-1") == "us-east-1"

    def test_strips_whitespace(self):
        assert region_norm("  us-east-1  ") == "us-east-1"

    def test_sentinel_value_is_dash(self):
        assert REGION_NULL_SENTINEL == "-"


# ===================================================================
# §3.4 — Quantization helpers
# ===================================================================

class TestClampInt:
    """Tests for clamp_int() and domain validators."""

    def test_valid_int_in_range(self):
        assert clamp_int(50, 0, 100) == 50

    def test_boundary_low(self):
        assert clamp_int(0, 0, 100) == 0

    def test_boundary_high(self):
        assert clamp_int(100, 0, 100) == 100

    def test_rejects_float(self):
        with pytest.raises(ARFValidationError, match="got float"):
            clamp_int(50.0, 0, 100)

    def test_rejects_bool(self):
        """Bool is a subclass of int in Python — must be explicitly rejected."""
        with pytest.raises(ARFValidationError, match="got bool"):
            clamp_int(True, 0, 100)

    def test_rejects_string(self):
        with pytest.raises(ARFValidationError, match="got str"):
            clamp_int("50", 0, 100)

    def test_rejects_below_range(self):
        with pytest.raises(ARFValidationError, match="out of range"):
            clamp_int(-1, 0, 100)

    def test_rejects_above_range(self):
        with pytest.raises(ARFValidationError, match="out of range"):
            clamp_int(101, 0, 100)


class TestSignalQ:
    """Tests for clamp_signal_q_int() — spec §3.4 + §18.3."""

    def test_valid(self):
        assert clamp_signal_q_int(50) == 50

    def test_min(self):
        assert clamp_signal_q_int(0) == 0

    def test_max(self):
        assert clamp_signal_q_int(100) == 100

    def test_rejects_float(self):
        """Spec §18.3: Scenario MUST provide signal_q as int. Floats rejected."""
        with pytest.raises(ARFValidationError):
            clamp_signal_q_int(50.0)

    def test_rejects_101(self):
        with pytest.raises(ARFValidationError):
            clamp_signal_q_int(101)

    def test_rejects_negative(self):
        with pytest.raises(ARFValidationError):
            clamp_signal_q_int(-1)


class TestConfidenceQ:
    """Tests for clamp_confidence_q_int() — spec §3.4 + §18.3."""

    def test_valid(self):
        assert clamp_confidence_q_int(500) == 500

    def test_min(self):
        assert clamp_confidence_q_int(0) == 0

    def test_max(self):
        assert clamp_confidence_q_int(1000) == 1000

    def test_rejects_float(self):
        with pytest.raises(ARFValidationError):
            clamp_confidence_q_int(500.0)

    def test_rejects_1001(self):
        with pytest.raises(ARFValidationError):
            clamp_confidence_q_int(1001)


class TestOptionalConversions:
    """Tests for signal_q_from_unit_float and confidence_q_from_unit_float."""

    def test_signal_q_midpoint(self):
        assert signal_q_from_unit_float(0.5) == 50

    def test_signal_q_zero(self):
        assert signal_q_from_unit_float(0.0) == 0

    def test_signal_q_one(self):
        assert signal_q_from_unit_float(1.0) == 100

    def test_signal_q_clamps_above(self):
        assert signal_q_from_unit_float(1.5) == 100

    def test_confidence_q_midpoint(self):
        assert confidence_q_from_unit_float(0.5) == 500

    def test_confidence_q_one(self):
        assert confidence_q_from_unit_float(1.0) == 1000


# ===================================================================
# §3.4 — Fixed-point probability
# ===================================================================

class TestEdgePQ8:
    """Tests for edge_p_q8() — spec §3.4."""

    def test_equal_alpha_beta(self):
        """50/50 should give Q8/2."""
        assert edge_p_q8(100, 100) == Q8 // 2

    def test_saturated_allow(self):
        """9900/100 should give 99% of Q8."""
        result = edge_p_q8(9900, 100)
        assert result == (9900 * Q8) // 10000

    def test_saturated_deny(self):
        """100/9900 should give 1% of Q8."""
        result = edge_p_q8(100, 9900)
        assert result == (100 * Q8) // 10000

    def test_integer_only(self):
        """Result must be an integer."""
        result = edge_p_q8(3, 7)
        assert isinstance(result, int)

    def test_zero_alpha(self):
        assert edge_p_q8(0, 100) == 0

    def test_zero_beta(self):
        assert edge_p_q8(100, 0) == Q8

    def test_zero_both_raises(self):
        with pytest.raises(ARFValidationError, match="must be > 0"):
            edge_p_q8(0, 0)

    def test_negative_raises(self):
        with pytest.raises(ARFValidationError):
            edge_p_q8(-1, 100)


class TestGroupedProductQ8:
    """Tests for grouped_product_q8() — spec §3.4."""

    def test_identity(self):
        """Multiplying by Q8 (p=1.0) should give same value."""
        assert grouped_product_q8(Q8, Q8) == Q8

    def test_half_times_half(self):
        """0.5 * 0.5 = 0.25 in Q8."""
        half = Q8 // 2
        result = grouped_product_q8(half, half)
        assert result == (half * half) // Q8

    def test_zero(self):
        assert grouped_product_q8(0, Q8) == 0
        assert grouped_product_q8(Q8, 0) == 0


# ===================================================================
# §4.1 — Fingerprints
# ===================================================================

class TestFingerprints:
    """Tests for features_fp() and properties_fp() — spec §4.1."""

    def test_features_fp_deterministic(self):
        f = {"key_a": 1, "key_b": 2}
        results = {features_fp(f) for _ in range(50)}
        assert len(results) == 1

    def test_features_fp_key_order_independent(self):
        """Different key insertion order must produce same fingerprint."""
        f1 = {"a": 1, "b": 2}
        f2 = {"b": 2, "a": 1}
        assert features_fp(f1) == features_fp(f2)

    def test_features_fp_is_sha256_hex(self):
        fp = features_fp({"x": 1})
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_features_fp_matches_manual(self):
        f = {"x": 1}
        expected = hashlib.sha256(canonical_json(f).encode("utf-8")).hexdigest()
        assert features_fp(f) == expected

    def test_properties_fp_deterministic(self):
        p = {"type": "SCP", "scope": "account"}
        results = {properties_fp(p) for _ in range(50)}
        assert len(results) == 1


# ===================================================================
# §4.3 — Deterministic IDs
# ===================================================================

class TestDeterministicIds:
    """Tests for make_*_id() functions — spec §4.3."""

    def test_node_id_stable_across_calls(self):
        """Same inputs -> same sha256. THE determinism test."""
        id1 = make_node_id("aws", "identity", "arn:aws:iam::123:role/Admin", "us-east-1")
        id2 = make_node_id("aws", "identity", "arn:aws:iam::123:role/Admin", "us-east-1")
        assert id1 == id2

    def test_node_id_includes_provider_no_collision(self):
        """Different providers with same other fields must produce different IDs."""
        id_aws = make_node_id("aws", "identity", "admin", "-")
        id_gcp = make_node_id("gcp", "identity", "admin", "-")
        assert id_aws != id_gcp

    def test_node_id_is_sha256_hex(self):
        nid = make_node_id("aws", "identity", "test", "-")
        assert len(nid) == 64

    def test_node_id_region_matters(self):
        id1 = make_node_id("aws", "identity", "test", "us-east-1")
        id2 = make_node_id("aws", "identity", "test", "eu-west-1")
        assert id1 != id2

    def test_template_id_deterministic(self):
        fp = features_fp({"service": "iam"})
        id1 = make_template_id("aws", "assume_role", fp, 1)
        id2 = make_template_id("aws", "assume_role", fp, 1)
        assert id1 == id2

    def test_template_id_schema_version_matters(self):
        fp = features_fp({"service": "iam"})
        id_v1 = make_template_id("aws", "assume_role", fp, 1)
        id_v2 = make_template_id("aws", "assume_role", fp, 2)
        assert id_v1 != id_v2

    def test_edge_id_deterministic(self):
        src = make_node_id("aws", "identity", "a", "-")
        dst = make_node_id("aws", "role", "b", "-")
        fp = features_fp({"service": "iam"})
        tid = make_template_id("aws", "assume_role", fp, 1)
        id1 = make_edge_id("assume_role", src, dst, "-", tid)
        id2 = make_edge_id("assume_role", src, dst, "-", tid)
        assert id1 == id2

    def test_edge_id_direction_matters(self):
        """A->B must differ from B->A."""
        n1 = make_node_id("aws", "identity", "a", "-")
        n2 = make_node_id("aws", "role", "b", "-")
        fp = features_fp({})
        tid = make_template_id("aws", "assume_role", fp, 1)
        id_ab = make_edge_id("assume_role", n1, n2, "-", tid)
        id_ba = make_edge_id("assume_role", n2, n1, "-", tid)
        assert id_ab != id_ba

    def test_constraint_id_deterministic(self):
        pp = properties_fp({"effect": "deny"})
        id1 = make_constraint_id("aws", "SCP", "ACCOUNT", "123456", "-", pp)
        id2 = make_constraint_id("aws", "SCP", "ACCOUNT", "123456", "-", pp)
        assert id1 == id2

    def test_constraint_id_includes_provider(self):
        pp = properties_fp({"effect": "deny"})
        id_aws = make_constraint_id("aws", "SCP", "ACCOUNT", "123456", "-", pp)
        id_gcp = make_constraint_id("gcp", "SCP", "ACCOUNT", "123456", "-", pp)
        assert id_aws != id_gcp

    def test_objective_id_deterministic(self):
        id1 = make_objective_id("privilege_escalation", ["node_a"], ["node_c"], 3, 5)
        id2 = make_objective_id("privilege_escalation", ["node_a"], ["node_c"], 3, 5)
        assert id1 == id2

    def test_objective_id_sorts_nodes(self):
        """Node lists must be sorted before hashing."""
        id1 = make_objective_id("pe", ["c", "a", "b"], ["z", "x"], 3, 5)
        id2 = make_objective_id("pe", ["a", "b", "c"], ["x", "z"], 3, 5)
        assert id1 == id2

    def test_objective_id_different_k(self):
        id1 = make_objective_id("pe", ["a"], ["b"], 3, 5)
        id2 = make_objective_id("pe", ["a"], ["b"], 3, 10)
        assert id1 != id2


# ===================================================================
# §4.2 — Human-readable keys
# ===================================================================

class TestKeys:
    """Tests for make_template_key() and make_constraint_key()."""

    def test_template_key_format(self):
        fp = features_fp({"svc": "iam"})
        key = make_template_key("aws", "assume_role", fp)
        assert key == f"aws|assume_role|f={fp}"

    def test_constraint_key_format(self):
        pp = properties_fp({"effect": "deny"})
        key = make_constraint_key("aws", "SCP", "ACCOUNT", "123", "us-east-1", pp)
        assert key == f"aws|SCP|ACCOUNT|123|r=us-east-1|p={pp}"


# ===================================================================
# §7.4 — Canonical flags_json
# ===================================================================

class TestFlagsJson:
    """Tests for make_flags_json() — spec §7.4."""

    def test_default_shape(self):
        result = make_flags_json()
        parsed = json.loads(result)
        assert parsed == {
            "conflict": False,
            "counterfactual_override": False,
            "prior_only": False,
            "stale": False,
        }

    def test_keys_sorted(self):
        """Canonical JSON means keys are sorted."""
        result = make_flags_json()
        keys = list(json.loads(result).keys())
        assert keys == sorted(keys)

    def test_override_conflict(self):
        result = make_flags_json(conflict=True)
        parsed = json.loads(result)
        assert parsed["conflict"] is True
        assert parsed["stale"] is False  # others unchanged

    def test_override_counterfactual(self):
        result = make_flags_json(counterfactual_override=True)
        parsed = json.loads(result)
        assert parsed["counterfactual_override"] is True

    def test_unknown_key_raises(self):
        with pytest.raises(ARFValidationError, match="Unknown flag key"):
            make_flags_json(unknown_flag=True)

    def test_non_bool_value_raises(self):
        with pytest.raises(ARFValidationError, match="must be bool"):
            make_flags_json(conflict=1)

    def test_canonical_at_write_time(self):
        """Output must be canonical JSON (no extra spaces, sorted keys)."""
        result = make_flags_json()
        reparsed = canonical_json(json.loads(result))
        assert result == reparsed

    def test_all_flags_true(self):
        result = make_flags_json(
            conflict=True, counterfactual_override=True,
            prior_only=True, stale=True,
        )
        parsed = json.loads(result)
        assert all(v is True for v in parsed.values())
