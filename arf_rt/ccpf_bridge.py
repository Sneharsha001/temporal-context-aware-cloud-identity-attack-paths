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


class ConstraintIndex(dict):
    """In-memory index mapping edge_id to list of ContextPredicates.

    Subclasses dict[str, list[ContextPredicate]] to ensure strict backward
    compatibility with callers expecting a mapping, while carrying explicit
    loading status metadata to distinguish:
    - Successful constraint loading with verified records (load_error is None).
    - Confirmed absence of contextual constraints (empty dict, load_error is None).
    - Missing, unavailable, malformed or ambiguous constraint metadata (tracked per record).
    - Constraint-index construction failure (load_error is not None).
    """

    def __init__(
        self,
        predicates_by_edge: dict[str, list[ContextPredicate]] | None = None,
        load_error: str | None = None,
        malformed_count: int = 0,
    ):
        super().__init__(predicates_by_edge or {})
        self.load_error = load_error
        self.malformed_count = malformed_count


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
    Distinguishes:
    - Verified absence of contextual constraints (returns empty list).
    - Malformed or invalid JSON structure (returns UNKNOWN predicate).
    - Missing key or value metadata (returns UNKNOWN predicate; never silently drops).
    - Unsupported operators or scopes (returns UNKNOWN predicate).
    - Legitimate supported conditions (returns properly scoped predicates).

    Prompt 7A Rule:
    Never invent policy values (e.g. StringEquals(["*"])) for unavailable ExternalId.
    If ExternalId values are unavailable or wildcarded, map to ContextScope.UNKNOWN.
    """
    predicates: list[ContextPredicate] = []

    if not isinstance(properties, dict):
        return [
            ContextPredicate(
                key="malformed_properties",
                operator="Unsupported",
                values=[],
                scope=ContextScope.UNKNOWN,
                description=f"constraint:{constraint_id}: properties is not a dict",
            )
        ]

    # Explicit JSON parse failure captured during index loading
    if "__malformed_json_error__" in properties:
        return [
            ContextPredicate(
                key="malformed_constraint_json",
                operator="Unsupported",
                values=[],
                scope=ContextScope.UNKNOWN,
                description=f"constraint:{constraint_id}: malformed JSON ({properties['__malformed_json_error__']})",
            )
        ]

    # Format 1: Explicit conditions list (e.g. [{"key": ..., "operator": ..., "values": [...]}])
    if "conditions" in properties:
        cond_list = properties["conditions"]
        if not isinstance(cond_list, list):
            return [
                ContextPredicate(
                    key="malformed_conditions_list",
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}: conditions field is not a list",
                )
            ]

        # Explicitly documented interpretation of empty condition lists:
        # If a contextual TRUST constraint defines an empty conditions list, this indicates
        # missing condition metadata (a trust condition without conditions is ambiguous).
        # For non-contextual constraints, an empty list means confirmed absence of context conditions.
        if len(cond_list) == 0:
            if constraint_type in ("TRUST_CONDITION", "TRUST"):
                return [
                    ContextPredicate(
                        key="empty_trust_conditions_list",
                        operator="Unsupported",
                        values=[],
                        scope=ContextScope.UNKNOWN,
                        description=f"constraint:{constraint_id}: trust condition has empty conditions list",
                    )
                ]
            return []

        for item in cond_list:
            if not isinstance(item, dict):
                predicates.append(
                    ContextPredicate(
                        key="malformed_condition_item",
                        operator="Unsupported",
                        values=[],
                        scope=ContextScope.UNKNOWN,
                        description=f"constraint:{constraint_id}: condition entry is not a dict",
                    )
                )
                continue

            k = str(item.get("key") or "").strip()
            op = str(item.get("operator") or "").strip()
            raw_vals = item.get("values")

            # Missing key or value metadata must NOT silently disappear
            if not k or raw_vals is None:
                predicates.append(
                    ContextPredicate(
                        key=k or "missing_condition_key",
                        operator="Unsupported",
                        values=[],
                        scope=ContextScope.UNKNOWN,
                        description=f"constraint:{constraint_id}: missing key or values in condition",
                    )
                )
                continue

            if not isinstance(raw_vals, list):
                raw_vals = [raw_vals]
            vals = [str(v) for v in raw_vals if v is not None]

            if not vals:
                predicates.append(
                    ContextPredicate(
                        key=k,
                        operator="Unsupported",
                        values=[],
                        scope=ContextScope.UNKNOWN,
                        description=f"constraint:{constraint_id}: empty condition values list",
                    )
                )
                continue

            # ExternalId handling: do NOT invent wildcard or treat unavailable value as supported
            if k.lower() == "sts:externalid":
                if vals == ["*"]:
                    predicates.append(
                        ContextPredicate(
                            key=k,
                            operator="Unsupported",
                            values=[],
                            scope=ContextScope.UNKNOWN,
                            description=f"constraint:{constraint_id}: external_id value unavailable or wildcard",
                        )
                    )
                    continue

            scope = infer_scope(k)
            predicates.append(
                ContextPredicate(
                    key=k,
                    operator=op or "StringEquals",
                    values=vals,
                    scope=scope,
                    description=f"constraint:{constraint_id}",
                )
            )
        return predicates

    # Format 2: Direct condition fields (trust_policy_parser output or DB row)
    if "condition_key" in properties or "condition_type" in properties:
        has_actual_key = "condition_key" in properties and bool(str(properties.get("condition_key") or "").strip())
        if not has_actual_key:
            # Audit finding (Prompt 7B): condition_type represents an internal classification category,
            # NOT an IAM condition key. Do not assume interchangeability or fabricate semantics.
            ctype_cat = str(properties.get("condition_type") or "").strip()
            return [
                ContextPredicate(
                    key=ctype_cat or "missing_condition_key",
                    operator=str(properties.get("condition_operator") or "Unsupported").strip(),
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}: internal category '{ctype_cat}' without actual condition_key",
                )
            ]

        k = str(properties.get("condition_key")).strip()
        op = str(properties.get("condition_operator") or "StringEquals").strip()
        raw_vals = (
            properties.get("required_values")
            or properties.get("values")
            or properties.get("condition_value")
        )

        if raw_vals is None:
            return [
                ContextPredicate(
                    key=k,
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}: missing condition values metadata",
                )
            ]

        if not isinstance(raw_vals, list):
            raw_vals = [raw_vals]
        vals = [str(v) for v in raw_vals if v is not None]

        if not vals:
            return [
                ContextPredicate(
                    key=k,
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}: empty required_values metadata",
                )
            ]

        # ExternalId handling: if ExternalId values are unavailable or wildcarded, map to UNKNOWN
        if k.lower() == "sts:externalid":
            if vals == ["*"]:
                return [
                    ContextPredicate(
                        key="sts:ExternalId",
                        operator="Unsupported",
                        values=[],
                        scope=ContextScope.UNKNOWN,
                        description=f"constraint:{constraint_id}: external_id value unavailable or wildcard",
                    )
                ]
            scope = ContextScope.CONFIG
            return [
                ContextPredicate(
                    key="sts:ExternalId",
                    operator=op,
                    values=vals,
                    scope=scope,
                    description=f"constraint:{constraint_id}",
                )
            ]

        scope = infer_scope(k)
        return [
            ContextPredicate(
                key=k,
                operator=op,
                values=vals,
                scope=scope,
                description=f"constraint:{constraint_id}",
            )
        ]

    # Format 3: Simple string condition flag (e.g. {"condition": "mfa_required"})
    if "condition" in properties:
        cond_str = str(properties.get("condition", "")).strip()
        cond_lower = cond_str.lower()
        if cond_lower == "mfa_required":
            return [
                ContextPredicate(
                    key="aws:MultiFactorAuthPresent",
                    operator="Bool",
                    values=["true"],
                    scope=ContextScope.SESSION,
                    description=f"constraint:{constraint_id}",
                )
            ]
        elif cond_lower.startswith("sts:externalid") or cond_lower == "external_id":
            # Prompt 7A: Remove invented StringEquals(["*"]) shortcut!
            # Since string condition flag provides no actual secret value, represent as UNKNOWN.
            return [
                ContextPredicate(
                    key="sts:ExternalId",
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}: external_id value unavailable from string condition flag",
                )
            ]
        else:
            return [
                ContextPredicate(
                    key=cond_str or "unsupported_condition",
                    operator="Unsupported",
                    values=[],
                    scope=ContextScope.UNKNOWN,
                    description=f"constraint:{constraint_id}",
                )
            ]

    # If the constraint is a TRUST_CONDITION but contains no recognized condition fields,
    # treat as missing/unsupported trust condition metadata (UNKNOWN scope).
    if constraint_type in ("TRUST_CONDITION", "TRUST"):
        return [
            ContextPredicate(
                key="empty_trust_condition",
                operator="Unsupported",
                values=[],
                scope=ContextScope.UNKNOWN,
                description=f"constraint:{constraint_id}: trust condition missing recognizable condition fields",
            )
        ]

    # Non-contextual policy constraints (e.g. unconditional SCP or boundary) assert no context requirements.
    return []


def build_constraint_index(
    conn: sqlite3.Connection,
    edge_ids: Any = None,
) -> ConstraintIndex:
    """Build in-memory index mapping edge_id to list of ContextPredicates.

    Loads active constraints linked via edge_constraints and translates them
    into ContextPredicate objects.

    If edge_ids is provided, loads constraints only for the specified edges
    (Opportunity A: query scoping), preserving chunking limits, ordering independence,
    and explicit load-error diagnostics.

    Returns:
        ConstraintIndex mapping edge_id to list[ContextPredicate], with explicit
        load_error attribute distinguishing construction failures from genuine
        absence of constraints.
    """
    predicates_by_edge: dict[str, list[ContextPredicate]] = {}
    malformed_count = 0

    if edge_ids is not None:
        e_list = list(set(edge_ids))
        if not e_list:
            return ConstraintIndex(predicates_by_edge={}, load_error=None, malformed_count=0)
    else:
        e_list = None

    try:
        rows = []
        if e_list is not None:
            chunk_size = 500
            for i in range(0, len(e_list), chunk_size):
                chunk = e_list[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cur = conn.execute(
                    f"""
                    SELECT ec.edge_id, c.constraint_id, c.constraint_type, c.properties_json
                    FROM edge_constraints ec
                    JOIN constraints c ON ec.constraint_id = c.constraint_id
                    WHERE c.status = 'ACTIVE' AND ec.edge_id IN ({placeholders})
                    ORDER BY ec.edge_id COLLATE BINARY, c.constraint_id COLLATE BINARY
                    """,
                    chunk,
                )
                rows.extend(cur.fetchall())
        else:
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
        err_msg = f"{type(ex).__name__}: {ex}"
        logger.warning("CCPF bridge: constraint index query failed: %s", err_msg)
        return ConstraintIndex(predicates_by_edge={}, load_error=err_msg)

    for row in rows:
        eid = row["edge_id"]
        cid = row["constraint_id"]
        ctype = row["constraint_type"]
        pjson = row["properties_json"]

        try:
            if isinstance(pjson, str):
                props = json.loads(pjson)
            elif isinstance(pjson, dict):
                props = pjson
            elif pjson is None:
                props = {}
            else:
                props = {"__malformed_type__": type(pjson).__name__}
        except Exception as json_err:
            props = {"__malformed_json_error__": str(json_err)}
            malformed_count += 1

        preds = extract_predicates_from_constraint(cid, ctype, props)
        if preds:
            if eid not in predicates_by_edge:
                predicates_by_edge[eid] = []
            predicates_by_edge[eid].extend(preds)

    return ConstraintIndex(
        predicates_by_edge=predicates_by_edge,
        load_error=None,
        malformed_count=malformed_count,
    )


def evaluate_candidate_hop(
    eid: str,
    edge_data: dict[str, Any],
    constraint_index: dict[str, list[ContextPredicate]] | ConstraintIndex,
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
    edge_type = str(edge_data.get("edge_type", ""))
    src = str(edge_data.get("src", ""))
    dst = str(edge_data.get("dst", ""))

    # 1. Distinguish constraint-index loading failure from genuine absence of constraints
    load_error = getattr(constraint_index, "load_error", None)
    if load_error is not None:
        result = PathEvaluationResult(
            path_id=eid,
            status=FeasibilityStatus.UNKNOWN,
            unknown_rationale=f"CONSTRAINT_INDEX_LOAD_FAILURE: {load_error}",
            evaluated_hops=1,
            solver_duration_ms=0.0,
            diagnostic_metadata={"load_error": load_error, "index_construction_failed": True},
        )
        if audit_sink is not None:
            try:
                audit_sink.append(
                    {
                        "edge_id": eid,
                        "edge_type": edge_type,
                        "src_node_id": src,
                        "dst_node_id": dst,
                        "status": result.status.value,
                        "contradiction_rationale": None,
                        "unknown_rationale": result.unknown_rationale,
                        "solver_duration_ms": 0.0,
                        "predicates_count": 0,
                    }
                )
            except Exception as sink_ex:
                logger.debug("Failed to append diagnostic to audit sink: %s", sink_ex)
        return result

    required_context = constraint_index.get(eid, [])

    # 2. Invoke RDCE evaluator
    if evaluator is None:
        evaluator = RestrictedDeterministicConstraintEvaluator()

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
        try:
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
        except Exception as sink_ex:
            logger.debug("Failed to append diagnostic to audit sink: %s", sink_ex)

    return result



def annotate_paths_feasibility(
    paths: list[dict[str, Any]],
    conn: sqlite3.Connection,
    constraint_index: dict[str, list[ContextPredicate]] | ConstraintIndex | None = None,
    evaluator: RestrictedDeterministicConstraintEvaluator | None = None,
    scenario_assumptions: dict[str, Any] | None = None,
    annotation_sink: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate full-path logical feasibility for a list of Top-K search paths.

    Strictly Post-Search Diagnostic Layer (Prompt 9 / 9B / 9C):
    - Reconstructs complete, ordered sequences of hops for each returned path.
    - Preserves hop boundaries and sequence order.
    - Evaluates each full path jointly via RestrictedDeterministicConstraintEvaluator.
    - Does NOT mutate the input path dictionaries.
    - Does NOT alter baseline Q8 probability scores, ranking, or ordering.
    - Does NOT prune edges or discard paths.
    - Isolates evaluation failures so search results remain untouched.

    Optimizations (Prompt 9C):
    - Scopes constraint and edge queries strictly to unique edges on returned paths (Opportunity A).
    - Merges edge metadata and constraint retrieval into a single LEFT JOIN query when index is None.
    - Precomputes hop prototype tuples for unique edges across paths to eliminate duplicate lookups (Opportunity B).

    Args:
        paths: List of path dicts as returned by search_top_k() or search_and_store_top_k().
        conn: SQLite connection to retrieve edge metadata and active constraints.
        constraint_index: Optional pre-built ConstraintIndex. If None, built from conn.
        evaluator: Optional RDCE instance. If None, instantiates a new one.
        scenario_assumptions: Optional caller-supplied assumptions (e.g. static_origin_assumption).
                              MUST NOT be silently defaulted or assumed.
        annotation_sink: Optional list to append annotation records to for caller inspection.

    Returns:
        List of path annotation dictionaries, one per input path in matching order:
          [{rank, edge_id_sequence, status, witness, contradiction_rationale,
            unknown_rationale, evaluated_hops, solver_duration_ms, timeout_occurred,
            diagnostic_metadata}]
    """
    if not paths:
        return []

    # 1. Parse edge sequences from paths
    parsed_paths: list[tuple[dict[str, Any], list[str]]] = []
    all_eids: set[str] = set()

    for p in paths:
        seq_raw = p.get("edge_id_sequence")
        if isinstance(seq_raw, str):
            try:
                parsed = json.loads(seq_raw)
                e_list = [str(x) for x in parsed] if isinstance(parsed, list) else []
            except Exception:
                e_list = []
        elif isinstance(seq_raw, (list, tuple)):
            e_list = [str(x) for x in seq_raw]
        else:
            e_list = []
        parsed_paths.append((p, e_list))
        all_eids.update(e_list)

    if not all_eids:
        # All paths are empty or malformed
        annotations: list[dict[str, Any]] = []
        for p, _ in parsed_paths:
            rec = {
                "rank": p.get("rank"),
                "edge_id_sequence": p.get("edge_id_sequence"),
                "status": FeasibilityStatus.UNKNOWN.value,
                "witness": None,
                "contradiction_rationale": None,
                "unknown_rationale": "EMPTY_EDGE_SEQUENCE",
                "evaluated_hops": 0,
                "solver_duration_ms": 0.0,
                "timeout_occurred": False,
                "diagnostic_metadata": {"empty_path": True},
            }
            annotations.append(rec)
            if annotation_sink is not None:
                try:
                    annotation_sink.append(rec)
                except Exception as sink_ex:
                    logger.warning("Failed to append record to annotation_sink: %s", sink_ex)
        return annotations

    eid_list = list(all_eids)
    edge_map: dict[str, dict[str, Any]] = {}
    predicates_by_edge: dict[str, list[ContextPredicate]] = {}
    malformed_count = 0
    load_error = None

    # 2. Combined edge metadata & constraint index resolution (Opportunity A & B)
    if constraint_index is None:
        chunk_size = 500
        for i in range(0, len(eid_list), chunk_size):
            chunk = eid_list[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            try:
                cur = conn.execute(
                    f"""
                    SELECT e.edge_id, e.edge_type, e.src_node_id, e.dst_node_id,
                           c.constraint_id, c.constraint_type, c.properties_json
                    FROM edges e
                    LEFT JOIN edge_constraints ec ON e.edge_id = ec.edge_id
                    LEFT JOIN constraints c ON ec.constraint_id = c.constraint_id AND c.status = 'ACTIVE'
                    WHERE e.edge_id IN ({placeholders})
                    ORDER BY e.edge_id COLLATE BINARY, c.constraint_id COLLATE BINARY
                    """,
                    chunk,
                )
                for r in cur.fetchall():
                    eid = r["edge_id"]
                    if eid not in edge_map:
                        edge_map[eid] = {
                            "edge_type": str(r["edge_type"] or ""),
                            "src": str(r["src_node_id"] or ""),
                            "dst": str(r["dst_node_id"] or ""),
                        }
                    cid = r["constraint_id"]
                    if cid is not None:
                        ctype = r["constraint_type"]
                        pjson = r["properties_json"]
                        try:
                            if isinstance(pjson, str):
                                props = json.loads(pjson)
                            elif isinstance(pjson, dict):
                                props = pjson
                            elif pjson is None:
                                props = {}
                            else:
                                props = {"__malformed_type__": type(pjson).__name__}
                        except Exception as json_err:
                            props = {"__malformed_json_error__": str(json_err)}
                            malformed_count += 1
                        preds = extract_predicates_from_constraint(cid, ctype, props)
                        if preds:
                            if eid not in predicates_by_edge:
                                predicates_by_edge[eid] = []
                            predicates_by_edge[eid].extend(preds)
            except Exception as ex:
                load_error = f"{type(ex).__name__}: {ex}"
                logger.warning("CCPF post-search combined edge/constraint query failed: %s", load_error)
                break
        c_idx: Any = ConstraintIndex(
            predicates_by_edge=predicates_by_edge,
            load_error=load_error,
            malformed_count=malformed_count,
        )
    else:
        c_idx = constraint_index
        load_error = getattr(c_idx, "load_error", None)
        chunk_size = 500
        for i in range(0, len(eid_list), chunk_size):
            chunk = eid_list[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            try:
                cur = conn.execute(
                    f"SELECT edge_id, edge_type, src_node_id, dst_node_id FROM edges WHERE edge_id IN ({placeholders})",
                    chunk,
                )
                for r in cur.fetchall():
                    edge_map[r["edge_id"]] = {
                        "edge_type": str(r["edge_type"] or ""),
                        "src": str(r["src_node_id"] or ""),
                        "dst": str(r["dst_node_id"] or ""),
                    }
            except Exception as ex:
                logger.warning("CCPF post-search edge query failed: %s", ex)

    if evaluator is None:
        evaluator = RestrictedDeterministicConstraintEvaluator()

    # 3. Pre-build hop prototype tuples for observed unique edges
    edge_hop_proto = {
        eid: (
            ed.get("edge_type", ""),
            ed.get("src", ""),
            ed.get("dst", ""),
            c_idx.get(eid, []),
        )
        for eid in all_eids
        if (ed := edge_map.get(eid)) is not None
    }

    annotations = []
    assumptions = scenario_assumptions or {}

    # 4. Evaluate each path in matching rank order
    for p, e_list in parsed_paths:
        rank = p.get("rank")
        edge_seq_str = p.get("edge_id_sequence")
        path_id = f"path_rank_{rank}"

        if load_error is not None:
            record = {
                "rank": rank,
                "edge_id_sequence": edge_seq_str,
                "status": FeasibilityStatus.UNKNOWN.value,
                "witness": None,
                "contradiction_rationale": None,
                "unknown_rationale": f"CONSTRAINT_INDEX_LOAD_FAILURE: {load_error}",
                "evaluated_hops": 0,
                "solver_duration_ms": 0.0,
                "timeout_occurred": False,
                "diagnostic_metadata": {"load_error": load_error, "index_construction_failed": True},
            }
        elif not e_list:
            record = {
                "rank": rank,
                "edge_id_sequence": edge_seq_str,
                "status": FeasibilityStatus.UNKNOWN.value,
                "witness": None,
                "contradiction_rationale": None,
                "unknown_rationale": "EMPTY_EDGE_SEQUENCE",
                "evaluated_hops": 0,
                "solver_duration_ms": 0.0,
                "timeout_occurred": False,
                "diagnostic_metadata": {"empty_path": True},
            }
        else:
            hops = [
                HopContextSpec(
                    hop=hop_num,
                    edge_type=proto[0],
                    src_node_id=proto[1],
                    dst_node_id=proto[2],
                    required_context=proto[3],
                )
                for hop_num, eid in enumerate(e_list, start=1)
                if (proto := edge_hop_proto.get(eid)) is not None
            ]

            eval_input = PathEvaluationInput(
                path_id=path_id,
                hops=hops,
                scenario_assumptions=assumptions,
            )

            try:
                eval_result = evaluator.evaluate(eval_input)
            except Exception as ex:
                logger.warning("CCPF post-search evaluation failed for path rank %s: %s", rank, ex)
                eval_result = PathEvaluationResult(
                    path_id=path_id,
                    status=FeasibilityStatus.UNKNOWN,
                    unknown_rationale=f"ANNOTATION_EXCEPTION: {type(ex).__name__}: {str(ex)[:80]}",
                    evaluated_hops=len(hops),
                    solver_duration_ms=0.0,
                    diagnostic_metadata={"exception": str(ex)[:200]},
                )

            record = {
                "rank": rank,
                "edge_id_sequence": edge_seq_str,
                "status": eval_result.status.value,
                "witness": eval_result.witness,
                "contradiction_rationale": eval_result.contradiction_rationale,
                "unknown_rationale": eval_result.unknown_rationale,
                "evaluated_hops": eval_result.evaluated_hops,
                "solver_duration_ms": eval_result.solver_duration_ms,
                "timeout_occurred": eval_result.timeout_occurred,
                "diagnostic_metadata": eval_result.diagnostic_metadata,
            }

        annotations.append(record)
        if annotation_sink is not None:
            try:
                annotation_sink.append(record)
            except Exception as sink_ex:
                logger.warning("Failed to append record to annotation_sink: %s", sink_ex)

    return annotations
