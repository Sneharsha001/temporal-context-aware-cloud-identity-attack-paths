"""Normalize raw scenario JSON into a validated ScenarioInput (spec §18).

This module is the entry point for scenario data. It:
  1. Accepts a raw dict (parsed from JSON file)
  2. Validates via Pydantic ScenarioInput (extra="forbid")
  3. Returns the validated model

All structural validation (field types, enum membership, signal_q domain)
is handled by ScenarioInput and its nested models. This adapter handles
only pre-processing that must happen before Pydantic sees the data.
"""

from __future__ import annotations

import json
from pathlib import Path

from arf_rt.config import MAX_SCENARIO_SIZE_BYTES
from arf_rt.models.core import ScenarioInput
from arf_rt.util.canon import ARFValidationError


def load_scenario_file(path: str | Path) -> ScenarioInput:
    """Load and validate a scenario JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Validated ScenarioInput.

    Raises:
        ARFValidationError: If the file is too large, not valid JSON,
            or fails ScenarioInput validation.
    """
    p = Path(path)

    if not p.is_file():
        raise ARFValidationError(f"Scenario file not found: {p}")

    size = p.stat().st_size
    if size > MAX_SCENARIO_SIZE_BYTES:
        raise ARFValidationError(
            f"Scenario file too large: {size} bytes "
            f"(max {MAX_SCENARIO_SIZE_BYTES})"
        )

    raw_text = p.read_text(encoding="utf-8")
    return load_scenario_string(raw_text)


def load_scenario_string(raw_text: str) -> ScenarioInput:
    """Parse and validate a scenario JSON string.

    Args:
        raw_text: Raw JSON string.

    Returns:
        Validated ScenarioInput.

    Raises:
        ARFValidationError: If not valid JSON or fails validation.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ARFValidationError(f"Invalid JSON in scenario: {e}") from e

    return load_scenario_dict(data)


def load_scenario_dict(data: dict) -> ScenarioInput:
    """Validate a scenario dict into ScenarioInput.

    Args:
        data: Parsed JSON dict.

    Returns:
        Validated ScenarioInput.

    Raises:
        ARFValidationError: If validation fails.
    """
    if not isinstance(data, dict):
        raise ARFValidationError(
            f"Scenario must be a JSON object, got {type(data).__name__}"
        )

    # Pydantic ScenarioInput handles all structural validation
    try:
        return ScenarioInput(**data)
    except Exception as e:
        raise ARFValidationError(str(e)) from e
