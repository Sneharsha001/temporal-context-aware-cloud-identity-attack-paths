"""Feature schema registry for ARF-RT (spec §4.1).

Maps (provider, edge_type, schema_version) → set of required feature keys.
Used to validate that edge features contain the expected keys for their
template type. If no schema is registered, any features dict is accepted.

The registry is intentionally simple: a module-level dict that adapters
populate at scenario load time and engine modules query during ingest.
"""

from __future__ import annotations

from arf_rt.util.canon import ARFValidationError

# Registry: (provider, edge_type, schema_version) → frozenset of required keys
_REGISTRY: dict[tuple[str, str, int], frozenset[str]] = {}


def register(
    provider: str,
    edge_type: str,
    schema_version: int,
    required_keys: set[str] | frozenset[str],
) -> None:
    """Register a feature schema for (provider, edge_type, schema_version).

    Args:
        provider: Cloud provider string (e.g. "aws", "azure").
        edge_type: Edge type string (e.g. "AssumeRole", "sts:AssumeRole").
        schema_version: Integer version for the feature schema.
        required_keys: Set of keys that must appear in the features dict.

    Raises:
        ARFValidationError: If the key triple is already registered with
            different required_keys (immutable once set).
    """
    key = (provider, edge_type, schema_version)
    frozen = frozenset(required_keys)

    if key in _REGISTRY:
        if _REGISTRY[key] != frozen:
            raise ARFValidationError(
                f"Feature schema already registered for {key} with "
                f"different keys: existing={sorted(_REGISTRY[key])}, "
                f"new={sorted(frozen)}"
            )
        return  # idempotent re-registration with same keys

    _REGISTRY[key] = frozen


def get_required_keys(
    provider: str,
    edge_type: str,
    schema_version: int,
) -> frozenset[str] | None:
    """Look up required feature keys for a schema triple.

    Returns:
        frozenset of required keys, or None if no schema registered.
    """
    return _REGISTRY.get((provider, edge_type, schema_version))


def validate_features(
    provider: str,
    edge_type: str,
    schema_version: int,
    features: dict,
) -> list[str]:
    """Validate features dict against registered schema.

    Returns:
        List of missing key names (empty = valid or no schema registered).
    """
    required = get_required_keys(provider, edge_type, schema_version)
    if required is None:
        return []
    return sorted(required - set(features.keys()))


def clear() -> None:
    """Clear all registered schemas. For testing only."""
    _REGISTRY.clear()
