"""Tests for structures module."""

from __future__ import annotations

import pytest

from arf_rt.util.structures import (
    flatten_dict,
    deep_merge,
    chunk_list,
    unflatten_dict,
    filter_dict,
    map_values,
    map_keys,
    get_nested,
    set_nested,
)


class TestFlattenDict:
    """Tests for flatten_dict function."""

    def test_basic(self):
        """Test basic flattening."""
        nested = {"a": {"b": 1, "c": 2}, "d": 3}
        flat = flatten_dict(nested)
        assert flat == {"a.b": 1, "a.c": 2, "d": 3}

    def test_deep_nesting(self):
        """Test deep nesting."""
        nested = {"a": {"b": {"c": {"d": 1}}}}
        flat = flatten_dict(nested)
        assert flat == {"a.b.c.d": 1}

    def test_custom_separator(self):
        """Test custom separator."""
        nested = {"a": {"b": 1}}
        flat = flatten_dict(nested, separator="/")
        assert flat == {"a/b": 1}

    def test_empty(self):
        """Test empty dict."""
        assert flatten_dict({}) == {}

    def test_no_nesting(self):
        """Test dict with no nesting."""
        nested = {"a": 1, "b": 2}
        flat = flatten_dict(nested)
        assert flat == {"a": 1, "b": 2}


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_basic(self):
        """Test basic merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dict merge."""
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}, "b": 5}
        result = deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}, "b": 5}

    def test_no_mutation(self):
        """Test inputs are not mutated."""
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        result = deep_merge(base, override)
        assert base == {"a": {"x": 1}}
        assert override == {"a": {"y": 2}}
        assert result == {"a": {"x": 1, "y": 2}}

    def test_override_non_dict(self):
        """Test overriding nested dict with non-dict."""
        base = {"a": {"x": 1}}
        override = {"a": 5}
        result = deep_merge(base, override)
        assert result == {"a": 5}


class TestChunkList:
    """Tests for chunk_list function."""

    def test_basic(self):
        """Test basic chunking."""
        items = [1, 2, 3, 4, 5]
        chunks = chunk_list(items, 2)
        assert chunks == [[1, 2], [3, 4], [5]]

    def test_exact_division(self):
        """Test exact division."""
        items = [1, 2, 3, 4]
        chunks = chunk_list(items, 2)
        assert chunks == [[1, 2], [3, 4]]

    def test_chunk_size_one(self):
        """Test chunk size of 1."""
        items = [1, 2, 3]
        chunks = chunk_list(items, 1)
        assert chunks == [[1], [2], [3]]

    def test_chunk_size_equals_length(self):
        """Test chunk size equals list length."""
        items = [1, 2, 3]
        chunks = chunk_list(items, 3)
        assert chunks == [[1, 2, 3]]

    def test_empty_list(self):
        """Test empty list."""
        chunks = chunk_list([], 2)
        assert chunks == []

    def test_invalid_chunk_size(self):
        """Test invalid chunk size raises error."""
        with pytest.raises(ValueError):
            chunk_list([1, 2], 0)
        with pytest.raises(ValueError):
            chunk_list([1, 2], -1)


class TestUnflattenDict:
    """Tests for unflatten_dict function."""

    def test_basic(self):
        """Test basic unflattening."""
        flat = {"a.b": 1, "a.c": 2, "d": 3}
        nested = unflatten_dict(flat)
        assert nested == {"a": {"b": 1, "c": 2}, "d": 3}

    def test_deep_nesting(self):
        """Test deep unflattening."""
        flat = {"a.b.c.d": 1}
        nested = unflatten_dict(flat)
        assert nested == {"a": {"b": {"c": {"d": 1}}}}

    def test_custom_separator(self):
        """Test custom separator."""
        flat = {"a/b": 1, "a/c": 2}
        nested = unflatten_dict(flat, separator="/")
        assert nested == {"a": {"b": 1, "c": 2}}

    def test_round_trip(self):
        """Test flatten -> unflatten round trip."""
        original = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
        flat = flatten_dict(original)
        nested = unflatten_dict(flat)
        assert nested == original


class TestFilterDict:
    """Tests for filter_dict function."""

    def test_allowed_keys(self):
        """Test filtering with allowed keys."""
        data = {"a": 1, "b": 2, "c": 3}
        filtered = filter_dict(data, allowed_keys={"a", "c"})
        assert filtered == {"a": 1, "c": 3}

    def test_blocked_keys(self):
        """Test filtering with blocked keys."""
        data = {"a": 1, "b": 2, "c": 3}
        filtered = filter_dict(data, blocked_keys={"b"})
        assert filtered == {"a": 1, "c": 3}

    def test_no_filter(self):
        """Test no filtering."""
        data = {"a": 1, "b": 2}
        filtered = filter_dict(data)
        assert filtered == {"a": 1, "b": 2}

    def test_both_raises(self):
        """Test both allowed and blocked raises error."""
        data = {"a": 1}
        with pytest.raises(ValueError):
            filter_dict(data, allowed_keys={"a"}, blocked_keys={"b"})


class TestMapValues:
    """Tests for map_values function."""

    def test_basic(self):
        """Test basic value mapping."""
        data = {"a": 1, "b": 2, "c": 3}
        result = map_values(data, lambda x: x * 2)
        assert result == {"a": 2, "b": 4, "c": 6}

    def test_string_transform(self):
        """Test string transformation."""
        data = {"a": "hello", "b": "world"}
        result = map_values(data, str.upper)
        assert result == {"a": "HELLO", "b": "WORLD"}


class TestMapKeys:
    """Tests for map_keys function."""

    def test_basic(self):
        """Test basic key mapping."""
        data = {"a": 1, "b": 2}
        result = map_keys(data, str.upper)
        assert result == {"A": 1, "B": 2}

    def test_prefix(self):
        """Test key prefixing."""
        data = {"a": 1, "b": 2}
        result = map_keys(data, lambda k: f"prefix_{k}")
        assert result == {"prefix_a": 1, "prefix_b": 2}


class TestGetNested:
    """Tests for get_nested function."""

    def test_basic(self):
        """Test basic nested get."""
        data = {"a": {"b": {"c": 1}}}
        assert get_nested(data, "a.b.c") == 1

    def test_not_found(self):
        """Test not found returns default."""
        data = {"a": {"b": 1}}
        assert get_nested(data, "a.c", default=42) == 42

    def test_none_default(self):
        """Test None default."""
        data = {"a": {"b": 1}}
        assert get_nested(data, "a.c") is None

    def test_custom_separator(self):
        """Test custom separator."""
        data = {"a": {"b": 1}}
        assert get_nested(data, "a/b", separator="/") == 1


class TestSetNested:
    """Tests for set_nested function."""

    def test_basic(self):
        """Test basic nested set."""
        data = {}
        set_nested(data, "a.b.c", 1)
        assert data == {"a": {"b": {"c": 1}}}

    def test_overwrite(self):
        """Test overwriting existing."""
        data = {"a": {"b": 1}}
        set_nested(data, "a.b", 2)
        assert data == {"a": {"b": 2}}

    def test_create_intermediate(self):
        """Test creating intermediate dicts."""
        data = {"a": 1}
        set_nested(data, "a.b.c", 2)
        assert data == {"a": {"b": {"c": 2}}}

    def test_custom_separator(self):
        """Test custom separator."""
        data = {}
        set_nested(data, "a/b/c", 1, separator="/")
        assert data == {"a": {"b": {"c": 1}}}