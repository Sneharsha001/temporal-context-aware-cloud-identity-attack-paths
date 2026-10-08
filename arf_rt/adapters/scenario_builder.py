"""Scenario builder: PMapper + AWS Org + Trust Policies → ARF-RT ScenarioInput.

Combines all 12A/12B sources into a single scenario JSON that can be
fed directly to `python -m arf_rt analyze`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from arf_rt.adapters.aws_org import load_org_structure, resolve_scp_constraints
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.adapters.trust_policy_parser import resolve_trust_constraints

logger = logging.getLogger(__name__)


def build_scenario(
    pmapper_path: str | Path,
    org_path: str | Path | None = None,
    objectives: list[dict] | None = None,
    objectives_path: str | Path | None = None,
    observations: list[dict] | None = None,
    observations_path: str | Path | None = None,
    scp_confidence_q: int = 800,
    trust_confidence_q: int = 800,
) -> dict:
    """Build a complete ARF-RT scenario from external data sources.

    Args:
        pmapper_path: Path to PMapper graph JSON or directory.
        org_path: Path to AWS Organizations JSON (optional).
        objectives: Objectives list (direct).
        objectives_path: Path to objectives JSON file (alternative to objectives).
        observations: Observations list (direct).
        observations_path: Path to observations JSON file.
        scp_confidence_q: Confidence for SCP-derived constraints.
        trust_confidence_q: Confidence for trust-derived constraints.

    Returns:
        Complete scenario dict ready for ScenarioInput validation.
    """
    # Step 1: Translate PMapper graph
    translated = translate_from_file(pmapper_path)
    all_warnings = list(translated.warnings)

    logger.info(
        "PMapper: %d nodes, %d edges, %d admins",
        translated.node_count,
        translated.edge_count,
        len(translated.admin_arns),
    )

    # Step 2: Resolve SCP constraints (if org data provided)
    all_constraints: list[dict] = []
    all_edge_constraints: list[dict] = []

    if org_path:
        org = load_org_structure(org_path)
        scp_constraints, scp_edge_constraints, scp_warnings = (
            resolve_scp_constraints(org, translated.edges, scp_confidence_q)
        )
        all_constraints.extend(scp_constraints)
        all_edge_constraints.extend(scp_edge_constraints)
        all_warnings.extend(scp_warnings)

        logger.info(
            "SCPs: %d constraints, %d edge linkages",
            len(scp_constraints),
            len(scp_edge_constraints),
        )

    # Step 3: Resolve trust conditions (from trust policies in PMapper data)
    if translated.trust_policies:
        trust_constraints, trust_edge_constraints, trust_warnings = (
            resolve_trust_constraints(
                translated.trust_policies,
                translated.edges,
                trust_confidence_q,
            )
        )
        all_constraints.extend(trust_constraints)
        all_edge_constraints.extend(trust_edge_constraints)
        all_warnings.extend(trust_warnings)

        logger.info(
            "Trust: %d constraints, %d edge linkages",
            len(trust_constraints),
            len(trust_edge_constraints),
        )

    # Step 4: Load objectives
    if objectives_path and not objectives:
        with open(objectives_path) as f:
            objectives = json.load(f)
    if not objectives:
        objectives = []

    # Step 5: Load observations
    if observations_path and not observations:
        with open(observations_path) as f:
            observations = json.load(f)
    if not observations:
        observations = []

    # Step 6: Assemble scenario
    scenario = {
        "nodes": translated.nodes,
        "edges": translated.edges,
        "constraints": all_constraints,
        "edge_constraints": all_edge_constraints,
        "objectives": objectives,
        "observations": observations,
    }

    # Log summary
    if all_warnings:
        for w in all_warnings:
            logger.warning("Import warning: %s", w)

    logger.info(
        "Scenario: %d nodes, %d edges, %d constraints, "
        "%d edge_constraints, %d objectives, %d observations",
        len(scenario["nodes"]),
        len(scenario["edges"]),
        len(scenario["constraints"]),
        len(scenario["edge_constraints"]),
        len(scenario["objectives"]),
        len(scenario["observations"]),
    )

    return scenario


def build_and_save(
    pmapper_path: str | Path,
    output_path: str | Path,
    **kwargs: Any,
) -> dict:
    """Build scenario and save to disk."""
    scenario = build_scenario(pmapper_path, **kwargs)
    output_path = Path(output_path)
    with open(output_path, "w") as f:
        json.dump(scenario, f, indent=2, sort_keys=True)
    logger.info("Saved scenario to %s", output_path)
    return scenario
