"""
arf_rt/util/structures.py - Collection and nested dictionary manipulation utilities.

Provides helper routines for flattening nested configurations, deep merging dictionaries,
and filtering structured evaluation outputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping


def flatten_dict(
    nested_dict: Mapping[str, Any],
    parent_key: str = "",
    separator: str = ".",
) -> Dict[str, Any]:
    """Flatten a nested dictionary structure into dot-notated single-level keys.

    Args:
        nested_dict: The dictionary with potentially nested sub-dictionaries.
        parent_key: Prefix for nested keys (used internally for recursion).
        separator: Delimiter between key levels (default: ".").

    Returns:
        Flattened single-level dictionary.

    Examples:
        >>> flatten_dict({"a": {"b": 1, "c": 2}, "d": 3})
        {'a.b': 1, 'a.c': 2, 'd': 3}
    """
    items: List[tuple[str, Any]] = []
    for k, v in nested_dict.items():
        new_key = f"{parent_key}{separator}{k}" if parent_key else str(k)
        if isinstance(v, Mapping):
            items.extend(flatten_dict(v, new_key, separator=separator).items())
        else:
            items.append((new_key, v))
    return dict(items)


def deep_merge(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recursively merge two dictionaries with override taking precedence.

    Args:
        base: The base dictionary.
        override: The overriding dictionary.

    Returns:
        A new merged dictionary without mutating either input.
    """
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into consecutive chunks of maximum length chunk_size.

    Args:
        items: List to be chunked.
        chunk_size: Maximum size per chunk.

    Returns:
        List of chunks.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
