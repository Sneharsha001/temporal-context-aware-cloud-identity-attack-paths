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


def unflatten_dict(
    flat_dict: Mapping[str, Any],
    separator: str = ".",
) -> Dict[str, Any]:
    """Reconstruct nested dictionary from dot-notated flat keys.

    Args:
        flat_dict: Flat dictionary with dot-notated keys.
        separator: Delimiter between key levels (default: ".").

    Returns:
        Nested dictionary.

    Examples:
        >>> unflatten_dict({"a.b": 1, "a.c": 2, "d": 3})
        {'a': {'b': 1, 'c': 2}, 'd': 3}
    """
    result: Dict[str, Any] = {}
    for key, value in flat_dict.items():
        parts = key.split(separator)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result


def filter_dict(
    data: Mapping[str, Any],
    allowed_keys: set[str] | None = None,
    blocked_keys: set[str] | None = None,
) -> Dict[str, Any]:
    """Filter dictionary by allowed/blocked keys.

    Args:
        data: Input dictionary.
        allowed_keys: If provided, only these keys are kept.
        blocked_keys: If provided, these keys are removed.

    Returns:
        Filtered dictionary.

    Raises:
        ValueError: If both allowed_keys and blocked_keys are provided.
    """
    if allowed_keys is not None and blocked_keys is not None:
        raise ValueError("Cannot specify both allowed_keys and blocked_keys")

    if allowed_keys is not None:
        return {k: v for k, v in data.items() if k in allowed_keys}

    if blocked_keys is not None:
        return {k: v for k, v in data.items() if k not in blocked_keys}

    return dict(data)


def map_values(
    data: Mapping[str, Any],
    transform: callable,
) -> Dict[str, Any]:
    """Apply a transformation function to all values in a dictionary.

    Args:
        data: Input dictionary.
        transform: Function to apply to each value.

    Returns:
        New dictionary with transformed values.
    """
    return {k: transform(v) for k, v in data.items()}


def map_keys(
    data: Mapping[str, Any],
    transform: callable,
) -> Dict[str, Any]:
    """Apply a transformation function to all keys in a dictionary.

    Args:
        data: Input dictionary.
        transform: Function to apply to each key.

    Returns:
        New dictionary with transformed keys.
    """
    return {transform(k): v for k, v in data.items()}


def get_nested(
    data: Mapping[str, Any],
    path: str,
    default: Any = None,
    separator: str = ".",
) -> Any:
    """Get nested value using dot-notation path.

    Args:
        data: Input dictionary.
        path: Dot-notated path (e.g., "a.b.c").
        default: Default value if path not found.
        separator: Path separator (default: ".").

    Returns:
        Value at path or default.

    Examples:
        >>> get_nested({"a": {"b": 1}}, "a.b")
        1
        >>> get_nested({"a": {"b": 1}}, "a.c", default=0)
        0
    """
    current = data
    for part in path.split(separator):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return default
    return current


def set_nested(
    data: Dict[str, Any],
    path: str,
    value: Any,
    separator: str = ".",
) -> None:
    """Set nested value using dot-notation path, creating intermediate dicts.

    Args:
        data: Dictionary to modify (in-place).
        path: Dot-notated path (e.g., "a.b.c").
        value: Value to set.
        separator: Path separator (default: ".").

    Examples:
        >>> d = {}
        >>> set_nested(d, "a.b.c", 1)
        >>> d
        {'a': {'b': {'c': 1}}}
    """
    parts = path.split(separator)
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        elif not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
