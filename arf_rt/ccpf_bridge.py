"""CCPF Passive Audit Bridge (Mode A: Zero Pruning).

This module provides the narrow integration boundary between ARF-RT's
graph search engine and the Restricted Deterministic Constraint Evaluator (RDCE).

Under Mode A (Passive Audit Only), this bridge is purely observational:
- It extracts edge and constraint metadata from ARF-RT data structures.
- It constructs HopContextSpec and PathEvaluationInput objects.
- It invokes RDCE to evaluate candidate hops.
- It records SAT, UNSAT, and UNKNOWN feasibility diagnostics.
- ABSOLUTE INVARIANT: It performs ZERO pruning. It does not alter candidate
  eligibility, does not skip edges, does not mutate Q8 probability scores,
  and does not modify heap ordering or tie-break mechanics.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from research.ccpf.rdce import (
    ContextPredicate,
    ContextScope,
    FeasibilityStatus,
    HopContextSpec,
    PathEvaluationInput,
    PathEvaluationResult,
    RestrictedDeterministicConstraintEvaluator,
    SUPPORTED_OPERATORS,
)

logger = logging.getLogger(__name__)


def infer_scope(condition_key: str | None) -> ContextScope:
    """Infer formal ContextScope from an IAM condition key.

    Maps supported condition keys to their lifecycle scopes:
    - aws:SourceIp -> REQUEST
    - aws:PrincipalTag/* -> PRINCIPAL
    - aws:MultiFactorAuthPresent -> SESSION
    - sts:ExternalId -> CONFIG

    All other keys (e.g., aws:SourceVpc, aws:PrincipalOrgID, sts:RoleSessionName,
    aws:MultiFactorAuthAge, aws:RequestTag/*, etc.) or unrecognized keys map to
    ContextScope.UNKNOWN, which RDCE evaluates to FeasibilityStatus.UNKNOWN.
    """
    if not condition_key:
        return ContextScope.UNKNOWN

    k = condition_key.strip().lower()

    if k == "aws:sourceip" or k.startswith("aws:sourceip/"):
        return ContextScope.REQUEST
    if k.startswith("aws:principaltag/"):
        return ContextScope.PRINCIPAL
    if k == "aws:multifactorauthpresent":
        return ContextScope.SESSION
    if k == "sts:externalid":
        return ContextScope.CONFIG

    return ContextScope.UNKNOWN


def extract_predicates_from_constraint(
    constraint_id: str,
    constraint_type: str,
    properties: dict[str, Any],
) -> list[ContextPredicate]:
    """Extract RDCE ContextPredicates from a constraint properties dictionary.

    Extracts operational context requirements (e.g., source IP, MFA, tags, external ID).
    If the constraint does not define context condition keys (e.g., unconditional SCP),
    returns an empty list.

    If a condition key or operator is present but unsupported, maps to ContextScope.UNKNOWN
    so RDCE conservatively returns FeasibilityStatus.UNKNOWN.
    """
    predicates: list[ContextPredicate] = []

    if not isinstance(properties, dict):
        return [
            ContextPredicate(
                key="malformed_properties",
                operator="Unsupported",
                values=[],
                scope=ContextScope.UNKNOWN,
                description=f"constraint:{constraint_id}",
            )
        ]

    # Format 1: Explicit conditions list (e.g. [{"key": ..., "operator": ..., "values": [...]}])
    if "conditions" in properties and isinstance(properties["conditions"], list):
        for item in properties["conditions"]:
            if isinstance(item, dict):
                k = str(item.get("key") or "")
                op = str(item.get("operator") or "")
                vals = item.get("values") or []
                if not isinstance(vals, list):
                    vals = [str(vals)]
                scope = infer_scope(k)
                predicates.append(
                    ContextPredicate(
                        key=k,
                        operator=op,
                        values=[str(v) for v in vals],
                        scope=scope,
                        description=f"constraint:{constraint_id}",
                    )
                )
        return predicates

    # Format 2: Direct condition key/operator/values (trust_policy_parser output or DB row)
    if "condition_key" in properties or "condition_type" in properties:
        k = str(properties.get("condition_key") or properties.get("condition_type") or "")
        op = str(properties.get("condition_operator") or "StringEquals")
        vals = (
            properties.get("required_values")
            or properties.get("values")
            or properties.get("condition_value")
            or []
        )
        if not isinstance(vals, list):
            vals = [str(vals)]
        scope = infer_scope(k)
        predicates.append(
            ContextPredicate(
                key=k,
                operator=op,
                values=[str(v) for v in vals],
                scope=scope,
                description=f"constraint:{constraint_id}",
            )
        )
        return predicates

    # Format 3: Simple string condition flag (e.g. {"condition": "mfa_required"})
    if "condition" in properties:
        cond_str = str(properties.get("condition", ""))
        cond_lower = cond_str.lower()
        if cond_lower == "mfa_required":
            predicates.append(
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent",
                    operator="Bool",
                    values=["true"],
                    scope=ContextScope.SESSION,
                    description=f"constraint:{constraint_id}",
                )
            )
            return predicates
        elif cond_lower.startswith("sts:externalid"):
            predicates.append(
                ContextPredicate(
                    key="sts:ExternalId",
                    operator="StringEquals",
                    values=["*"],
                    scope=ContextScope.CONFIG,
                    description=f"constraint:{constraint_id}",
                )
            )
            return predicates
        else:
            predicates.append(
                ContextPredicate(
                    key=cond_str,
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}",
                )
            )
            return predicates

    # If the constraint is a TRUST_CONDITION but contains no recognized condition fields,
    # treat as malformed/unsupported trust condition (UNKNOWN scope).
    if constraint_type in ("TRUST_CONDITION", "TRUST"):
        return [
            ContextPredicate(
                key="empty_trust_condition",
                operator="Unsupported",
                values=[],
                scope=ContextScope.UNKNOWN,
                description=f"constraint:{constraint_id}",
            )
        ]

    # Non-contextual policy constraints (e.g. unconditional SCP or boundary) assert no context requirements.
    return []


def build_constraint_index(conn: sqlite3.Connection) -> dict[str, list[ContextPredicate]]:
    """Build pre-search in-memory index mapping edge_id to list of ContextPredicates.

    Loads active constraints linked via edge_constraints and translates them
    into ContextPredicate objects.

    Returns:
        dict[edge_id, list[ContextPredicate]]
    """
    index: dict[str, list[ContextPredicate]] = {}

    try:
        cur = conn.execute(
            """
            SELECT ec.edge_id, c.constraint_id, c.constraint_type, c.properties_json
            FROM edge_constraints ec
            JOIN constraints c ON ec.constraint_id = c.constraint_id
            WHERE c.status = 'ACTIVE'
            ORDER BY ec.edge_id COLLATE BINARY, c.constraint_id COLLATE BINARY
            """
        )
        rows = cur.fetchall()
    except Exception as ex:
        logger.debug("CCPF bridge: unable to query edge constraints: %s", ex)
        return index

    for row in rows:
        eid = row["edge_id"]
        cid = row["constraint_id"]
        ctype = row["constraint_type"]
        pjson = row["properties_json"]

        try:
            props = json.loads(pjson) if isinstance(pjson, str) else (pjson or {})
        except Exception:
            props = {}

        preds = extract_predicates_from_constraint(cid, ctype, props)
        if preds:
            if eid not in index:
                index[eid] = []
            index[eid].extend(preds)

    return index


def evaluate_candidate_hop(
    eid: str,
    edge_data: dict[str, Any],
    constraint_index: dict[str, list[ContextPredicate]],
    evaluator: RestrictedDeterministicConstraintEvaluator | None = None,
    audit_sink: list[dict[str, Any]] | None = None,
    scenario_assumptions: dict[str, Any] | None = None,
) -> PathEvaluationResult:
    """Evaluate candidate hop feasibility under Mode A (Passive Audit Only).

    Invokes RDCE to determine if the candidate edge's required context is
    satisfiable, records the diagnostic result, and returns the PathEvaluationResult.

    CRITICAL INVARIANT (MODE A):
    This evaluation is strictly observational. The caller must NEVER prune
    on UNSAT or alter path probabilities / ranking based on this return value.
    """
    if evaluator is None:
        evaluator = RestrictedDeterministicConstraintEvaluator()

    edge_type = str(edge_data.get("edge_type", ""))
    src = str(edge_data.get("src", ""))
    dst = str(edge_data.get("dst", ""))
    required_context = constraint_index.get(eid, [])

    try:
        hop_spec = HopContextSpec(
            hop=1,
            edge_type=edge_type,
            src_node_id=src,
            dst_node_id=dst,
            required_context=required_context,
        )
        eval_input = PathEvaluationInput(
            path_id=eid,
            hops=[hop_spec],
            scenario_assumptions=scenario_assumptions or {},
        )
        result = evaluator.evaluate(eval_input)
    except Exception as ex:
        # Failure isolation: bridge or evaluator exceptions must never crash search
        logger.warning("CCPF bridge evaluation failed for edge %s: %s", eid, ex)
        result = PathEvaluationResult(
            path_id=eid,
            status=FeasibilityStatus.UNKNOWN,
            unknown_rationale=f"BRIDGE_EXCEPTION: {type(ex).__name__}: {str(ex)[:80]}",
            evaluated_hops=1,
            solver_duration_ms=0.0,
            diagnostic_metadata={"exception": str(ex)[:200]},
        )

    # Diagnostic recording for passive audit
    if audit_sink is not None:
        # Bounded diagnostic record omitting sensitive secret values
        audit_sink.append(
            {
                "edge_id": eid,
                "edge_type": edge_type,
                "src_node_id": src,
                "dst_node_id": dst,
                "status": result.status.value,
                "contradiction_rationale": result.contradiction_rationale,
                "unknown_rationale": result.unknown_rationale,
                "solver_duration_ms": result.solver_duration_ms,
                "predicates_count": len(required_context),
            }
        )

    return result
