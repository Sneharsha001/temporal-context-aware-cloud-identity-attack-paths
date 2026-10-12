"""Restricted Deterministic Constraint Evaluator (RDCE).

Formal context-conditioned path feasibility evaluator for cloud identity attack paths.
Implements the safe constraint fragment, scope tracking, and transition semantics
specified in docs/CCPF_EVALUATOR_CONTRACT.md.

Status-only interface: SAT, UNSAT, UNKNOWN.
Zero probability multiplier or Bayesian score modification.
"""

from __future__ import annotations

import ipaddress
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class ContextScope(str, Enum):
    """Context variable scope taxonomy."""
    REQUEST = "request"        # Per-API-call origin (e.g., aws:SourceIp)
    SESSION = "session"        # Bound to active STS token set (e.g., aws:MultiFactorAuthPresent)
    PRINCIPAL = "principal"    # Bound to active IAM identity entity (e.g., aws:PrincipalTag/<key>)
    CONFIG = "config"          # Hop-local call parameter (e.g., sts:ExternalId)
    UNKNOWN = "unknown"        # Unmapped or unclassified scope


class FeasibilityStatus(str, Enum):
    """Ternary logical feasibility status."""
    SAT = "SAT"          # Provably satisfiable under supported model and explicit assumptions
    UNSAT = "UNSAT"      # Provably contradictory under supported model and explicit assumptions
    UNKNOWN = "UNKNOWN"  # Undecidable, unsupported operator/key, incomplete metadata, or timeout


@dataclass(frozen=True)
class ContextPredicate:
    """A single required condition predicate on a path hop."""
    key: str
    operator: str
    values: List[str]
    scope: ContextScope
    description: Optional[str] = None


@dataclass(frozen=True)
class ProducedStateModification:
    """State modification produced by traversing an edge."""
    key: str
    operation: str
    value: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None


@dataclass(frozen=True)
class HopContextSpec:
    """Context specifications for a single hop along a path."""
    hop: int
    edge_type: str
    src_node_id: str
    dst_node_id: str
    required_context: List[ContextPredicate] = field(default_factory=list)
    produced_context: List[ProducedStateModification] = field(default_factory=list)


@dataclass(frozen=True)
class TransitionRelation:
    """Explicit inter-hop transition constraint."""
    from_hop: int
    to_hop: int
    variable: str
    relation_type: str  # "EQUAL", "PIVOT_TRANSITION", "IDENTITY_DERIVATION"
    formula: str
    rationale: Optional[str] = None


@dataclass(frozen=True)
class PathEvaluationInput:
    """Input representation for path feasibility evaluation."""
    path_id: str
    hops: List[HopContextSpec]
    transition_constraints: List[TransitionRelation] = field(default_factory=list)
    scenario_assumptions: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PathEvaluationResult:
    """Strictly logical evaluation result (no probability multiplier)."""
    path_id: str
    status: FeasibilityStatus
    witness: Optional[Dict[str, Any]] = None              # Valid assignment mapping (REQUIRED if SAT)
    contradiction_rationale: Optional[str] = None         # Formal clash proof (REQUIRED if UNSAT)
    unknown_rationale: Optional[str] = None               # Root cause of undecidability (REQUIRED if UNKNOWN)
    evaluated_hops: int = 0                               # Hops evaluated before decision
    solver_duration_ms: float = 0.0                       # Measured wall-clock duration
    timeout_occurred: bool = False                        # True if iteration ceiling was reached
    diagnostic_metadata: Dict[str, Any] = field(default_factory=dict)


# Supported Safe Fragment Operators
SUPPORTED_OPERATORS = {
    "IpAddress",
    "NotIpAddress",
    "StringEquals",
    "StringLike",  # Only without wildcards
    "Bool",
    "Null",
}


def parse_cidr_network(cidr_str: str) -> Union[ipaddress.IPv4Network, ipaddress.IPv6Network]:
    """Parse a CIDR string into an IPv4Network or IPv6Network object."""
    s = str(cidr_str).strip()
    if "/" not in s:
        # Check if single IP literal
        addr = ipaddress.ip_address(s)
        prefix = 32 if addr.version == 4 else 128
        return ipaddress.ip_network(f"{s}/{prefix}", strict=False)
    return ipaddress.ip_network(s, strict=False)


def intersect_two_cidrs(
    net1: Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
    net2: Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
) -> Optional[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """Compute the intersection of two CIDR networks. Returns None if disjoint."""
    if net1.version != net2.version:
        return None
    if net1.subnet_of(net2):
        return net1
    if net2.subnet_of(net1):
        return net2
    return None


def intersect_cidr_disjunctions(
    group1: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
    group2: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """Intersect two disjunctive (OR) lists of CIDRs. Returns surviving subnets."""
    surviving: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for n1 in group1:
        for n2 in group2:
            common = intersect_two_cidrs(n1, n2)
            if common is not None:
                if not any(common.subnet_of(existing) for existing in surviving):
                    surviving.append(common)
    return surviving


class RestrictedDeterministicConstraintEvaluator:
    """Domain-restricted deterministic constraint evaluator for CCPF."""

    MAX_ITERATIONS: int = 1000

    def evaluate(self, input_data: PathEvaluationInput) -> PathEvaluationResult:
        """Evaluate logical feasibility of a path under context constraints."""
        start_time = time.perf_counter()
        diag: Dict[str, Any] = {"steps_executed": 0, "scopes_observed": set()}

        try:
            # 1. Check for empty or unannotated path
            if not input_data.hops:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return PathEvaluationResult(
                    path_id=input_data.path_id,
                    status=FeasibilityStatus.UNKNOWN,
                    unknown_rationale="NO_CONTEXT_CONSTRAINTS_DEFINED",
                    evaluated_hops=0,
                    solver_duration_ms=elapsed_ms,
                    diagnostic_metadata=diag,
                )

            total_constraints = sum(len(h.required_context) for h in input_data.hops)
            if total_constraints == 0 and not input_data.transition_constraints:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return PathEvaluationResult(
                    path_id=input_data.path_id,
                    status=FeasibilityStatus.UNKNOWN,
                    unknown_rationale="NO_CONTEXT_CONSTRAINTS_DEFINED",
                    evaluated_hops=len(input_data.hops),
                    solver_duration_ms=elapsed_ms,
                    diagnostic_metadata=diag,
                )

            # 2. Scope bindings and state tracking
            # Active request IP constraints per hop
            hop_allowed_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}
            hop_denied_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}

            # Active principal tags: hop -> {tag_key: set_of_allowed_values}
            hop_principal_tags: Dict[int, Dict[str, Set[str]]] = {}

            # Active session bools: hop -> {key: bool_val}
            hop_session_bools: Dict[int, Dict[str, bool]] = {}

            # Produced state: hop -> {key: value_or_dict}
            produced_state: Dict[int, Dict[str, Any]] = {}

            # 3. Iterate through hops sequentially
            iteration_count = 0
            for hop_idx, hop in enumerate(input_data.hops, start=1):
                hop_num = hop.hop
                hop_principal_tags[hop_num] = {}
                hop_session_bools[hop_num] = {}
                produced_state[hop_num] = {}

                # Carry-over from previous hop unless reset by AssumeRole
                if hop_idx > 1:
                    prev_hop_num = input_data.hops[hop_idx - 2].hop
                    is_identity_pivot = (hop.edge_type == "sts:AssumeRole")

                    if not is_identity_pivot:
                        # Carry principal scope across standard action
                        hop_principal_tags[hop_num] = {
                            k: set(v) for k, v in hop_principal_tags[prev_hop_num].items()
                        }
                        # Carry session scope across standard action
                        hop_session_bools[hop_num] = dict(hop_session_bools[prev_hop_num])
                    else:
                        # AssumeRole boundary: session scope resets
                        hop_session_bools[hop_num] = {}
                        # Principal scope resets to target role identity
                        hop_principal_tags[hop_num] = {}

                # Ingest produced context for this hop
                for prod in hop.produced_context:
                    iteration_count += 1
                    diag["steps_executed"] = iteration_count
                    if iteration_count > self.MAX_ITERATIONS:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale="EVALUATOR_ITERATION_CEILING_EXCEEDED",
                            timeout_occurred=True,
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata=diag,
                        )

                    key = prod.key
                    val = prod.value
                    produced_state[hop_num][key] = val
                    if prod.attributes:
                        produced_state[hop_num][f"{key}_attrs"] = prod.attributes

                    # If AssumeRole produces static principal tags on target role
                    if key.startswith("aws:PrincipalTag/"):
                        tag_name = key
                        hop_principal_tags[hop_num][tag_name] = {val}

                # Evaluate required context for this hop
                for pred in hop.required_context:
                    iteration_count += 1
                    diag["steps_executed"] = iteration_count
                    if iteration_count > self.MAX_ITERATIONS:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale="EVALUATOR_ITERATION_CEILING_EXCEEDED",
                            timeout_occurred=True,
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata=diag,
                        )

                    scope = pred.scope
                    diag["scopes_observed"].add(str(scope))

                    # Rejection: unknown scope
                    if scope == ContextScope.UNKNOWN:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=f"UNSUPPORTED_OR_UNKNOWN_SCOPE: {pred.key}",
                            evaluated_hops=hop_idx,
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata=diag,
                        )

                    op = pred.operator
                    # Rejection: unsupported operator
                    if op not in SUPPORTED_OPERATORS:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=f"UNSUPPORTED_OPERATOR: {op} on key {pred.key}",
                            evaluated_hops=hop_idx,
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata=diag,
                        )

                    # Rejection: StringLike with wildcards
                    if op == "StringLike":
                        if any("*" in v or "?" in v for v in pred.values):
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"UNSUPPORTED_WILDCARD_PATTERN_IN_STRINGLIKE: {pred.values}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                    # 3.1 Operator: IpAddress
                    if op == "IpAddress":
                        parsed_list: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
                        for val_str in pred.values:
                            try:
                                parsed_list.append(parse_cidr_network(val_str))
                            except ValueError as ve:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=f"MALFORMED_CIDR_VALUE: {val_str} ({ve})",
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        if hop_num not in hop_allowed_cidrs:
                            hop_allowed_cidrs[hop_num] = parsed_list
                        else:
                            # Conjunction of IpAddress predicates on same hop
                            surviving = intersect_cidr_disjunctions(hop_allowed_cidrs[hop_num], parsed_list)
                            if not surviving:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Disjoint IP requirements on hop {hop_num}: "
                                        f"{hop_allowed_cidrs[hop_num]} and {parsed_list}"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            hop_allowed_cidrs[hop_num] = surviving

                    # 3.2 Operator: NotIpAddress
                    elif op == "NotIpAddress":
                        parsed_denied: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
                        for val_str in pred.values:
                            try:
                                parsed_denied.append(parse_cidr_network(val_str))
                            except ValueError as ve:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=f"MALFORMED_CIDR_VALUE: {val_str} ({ve})",
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                        hop_denied_cidrs.setdefault(hop_num, []).extend(parsed_denied)

                    # 3.3 Operator: StringEquals or exact StringLike
                    elif op in ("StringEquals", "StringLike"):
                        req_values = set(pred.values)
                        tag_key = pred.key

                        if scope == ContextScope.PRINCIPAL:
                            active_set = hop_principal_tags[hop_num].get(tag_key)
                            if active_set is not None:
                                overlap = active_set.intersection(req_values)
                                if not overlap:
                                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                    return PathEvaluationResult(
                                        path_id=input_data.path_id,
                                        status=FeasibilityStatus.UNSAT,
                                        contradiction_rationale=(
                                            f"Principal tag contradiction on hop {hop_num} for '{tag_key}': "
                                            f"Active principal tags {active_set} clash with required {req_values}"
                                        ),
                                        evaluated_hops=hop_idx,
                                        solver_duration_ms=elapsed_ms,
                                        diagnostic_metadata=diag,
                                    )
                                hop_principal_tags[hop_num][tag_key] = overlap
                            else:
                                hop_principal_tags[hop_num][tag_key] = req_values

                        elif scope == ContextScope.CONFIG:
                            # Config scope is consumed per-hop; does not contradict prior hops
                            pass

                    # 3.4 Operator: Bool
                    elif op == "Bool":
                        truth_str = pred.values[0].strip().lower() if pred.values else ""
                        if truth_str in ("true", "1"):
                            b_val = True
                        elif truth_str in ("false", "0"):
                            b_val = False
                        else:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"MALFORMED_BOOLEAN_VALUE: {pred.values}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        existing_b = hop_session_bools[hop_num].get(pred.key)
                        if existing_b is not None and existing_b != b_val:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Boolean identity contradiction on hop {hop_num} for '{pred.key}': "
                                    f"Active {existing_b} clashes with required {b_val}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        hop_session_bools[hop_num][pred.key] = b_val

                    # 3.5 Operator: Null
                    elif op == "Null":
                        null_truth = pred.values[0].strip().lower() in ("true", "1") if pred.values else True
                        if null_truth:
                            active_set = hop_principal_tags[hop_num].get(pred.key)
                            if active_set:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Null assertion failed on hop {hop_num} for '{pred.key}': "
                                        f"Key is required to be null, but active set is {active_set}"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

            # 4. Evaluate Inter-Hop Transition Constraints
            static_origin = bool(input_data.scenario_assumptions.get("static_origin_assumption", False))

            pivot_rebound_hops: Set[int] = set()
            for trans in input_data.transition_constraints:
                iteration_count += 1
                diag["steps_executed"] = iteration_count

                if trans.relation_type == "PIVOT_TRANSITION":
                    pivot_rebound_hops.add(trans.to_hop)
                    source_key = trans.variable
                    prod_from = produced_state.get(trans.from_hop, {})
                    rebound_ip = prod_from.get("network_execution_origin")

                    if rebound_ip:
                        try:
                            rebound_net = parse_cidr_network(rebound_ip)
                        except ValueError as ve:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"MALFORMED_PIVOT_IP: {rebound_ip} ({ve})",
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        allowed_for_target = hop_allowed_cidrs.get(trans.to_hop)
                        if allowed_for_target:
                            satisfies_pivot = any(
                                rebound_net.subnet_of(target_net) or target_net.subnet_of(rebound_net)
                                for target_net in allowed_for_target
                            )
                            if not satisfies_pivot:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Network pivot contradiction on hop {trans.to_hop}: "
                                        f"Pivot IP {rebound_ip} is outside allowed CIDRs {allowed_for_target}"
                                    ),
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                elif trans.relation_type == "IDENTITY_DERIVATION":
                    tag_var = trans.variable
                    prod_from = produced_state.get(trans.from_hop, {})
                    produced_tag = prod_from.get(tag_var)

                    req_tags_target = hop_principal_tags.get(trans.to_hop, {}).get(tag_var)
                    if produced_tag and req_tags_target:
                        if produced_tag not in req_tags_target:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Identity derivation contradiction across AssumeRole (hop {trans.from_hop} -> {trans.to_hop}): "
                                    f"Derived principal tag '{produced_tag}' for '{tag_var}' contradicts required set {req_tags_target}"
                                ),
                                evaluated_hops=len(input_data.hops),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

            # Check static origin assumption across sequential IP hops
            accumulated_static_subnets: Optional[List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = None
            if static_origin or any(t.relation_type == "EQUAL" for t in input_data.transition_constraints):
                hops_with_ip = [
                    h.hop for h in input_data.hops
                    if h.hop in hop_allowed_cidrs and h.hop not in pivot_rebound_hops
                ]

                if len(hops_with_ip) > 1:
                    accumulated = hop_allowed_cidrs[hops_with_ip[0]]
                    for next_hop in hops_with_ip[1:]:
                        next_allowed = hop_allowed_cidrs[next_hop]
                        surviving = intersect_cidr_disjunctions(accumulated, next_allowed)
                        if not surviving:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Contradictory persistent context under static origin assumption: "
                                    f"CIDRs on hop {hops_with_ip[0]} ({hop_allowed_cidrs[hops_with_ip[0]]}) "
                                    f"are disjoint from hop {next_hop} ({next_allowed})"
                                ),
                                evaluated_hops=len(input_data.hops),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        accumulated = surviving
                    accumulated_static_subnets = accumulated

            # Check denied CIDRs
            for hop_num, allowed_list in hop_allowed_cidrs.items():
                denied_list = hop_denied_cidrs.get(hop_num, [])
                if denied_list:
                    if all(any(a.subnet_of(d) for d in denied_list) for a in allowed_list):
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNSAT,
                            contradiction_rationale=f"Allowed CIDRs {allowed_list} fully denied by {denied_list} on hop {hop_num}",
                            evaluated_hops=len(input_data.hops),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata=diag,
                        )

            # 5. Construct satisfying witness
            witness: Dict[str, Any] = {}

            # Static origin witness: pick IP from accumulated intersection
            if accumulated_static_subnets:
                first_net = accumulated_static_subnets[0]
                try:
                    static_ip = str(next(first_net.hosts()))
                except StopIteration:
                    static_ip = str(first_net.network_address)
                witness["aws:SourceIp"] = static_ip
                for h_num in hop_allowed_cidrs:
                    if h_num not in pivot_rebound_hops:
                        witness[f"hop_{h_num}_SourceIp"] = static_ip
            else:
                for hop_num, allowed_list in hop_allowed_cidrs.items():
                    if allowed_list:
                        first_net = allowed_list[0]
                        try:
                            chosen_ip = str(next(first_net.hosts()))
                        except StopIteration:
                            chosen_ip = str(first_net.network_address)
                        witness[f"hop_{hop_num}_SourceIp"] = chosen_ip
                        if "aws:SourceIp" not in witness:
                            witness["aws:SourceIp"] = chosen_ip

            # If pivot transition occurred: record re-bound IP in witness
            for p_hop in pivot_rebound_hops:
                rebound_val = produced_state.get(p_hop - 1, {}).get("network_execution_origin")
                if rebound_val:
                    witness[f"hop_{p_hop}_SourceIp"] = rebound_val

            # Principal tags witness
            for hop_num, tags in hop_principal_tags.items():
                for tag_key, tag_vals in tags.items():
                    if tag_vals:
                        chosen_val = sorted(list(tag_vals))[0]
                        witness[f"hop_{hop_num}_{tag_key}"] = chosen_val
                        witness[tag_key] = chosen_val

            # Session bool witness
            for hop_num, bools in hop_session_bools.items():
                for b_key, b_val in bools.items():
                    witness[b_key] = b_val

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return PathEvaluationResult(
                path_id=input_data.path_id,
                status=FeasibilityStatus.SAT,
                witness=witness if witness else {"feasible": True},
                evaluated_hops=len(input_data.hops),
                solver_duration_ms=elapsed_ms,
                diagnostic_metadata=diag,
            )

        except Exception as exc:
            # Conservative exception trap: never classify unexpected errors as UNSAT
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return PathEvaluationResult(
                path_id=input_data.path_id,
                status=FeasibilityStatus.UNKNOWN,
                unknown_rationale=f"UNHANDLED_EVALUATOR_EXCEPTION: {type(exc).__name__}: {str(exc)}",
                solver_duration_ms=elapsed_ms,
                diagnostic_metadata=diag,
            )


def load_sidecar_context(sidecar_path: Union[str, Path]) -> PathEvaluationInput:
    """Ingest a .context.json research fixture sidecar into PathEvaluationInput."""
    path = Path(sidecar_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    fixture_id = data.get("fixture_id", path.stem)
    edge_specs_json = data.get("edge_context_specifications", [])
    trans_json = data.get("transition_constraints", [])
    context_vars_json = data.get("context_variables", [])

    scenario_assumptions: Dict[str, Any] = {}
    for cv in context_vars_json:
        if cv.get("persistence_model") == "persistent_under_static_origin_assumption":
            scenario_assumptions["static_origin_assumption"] = True

    hops: List[HopContextSpec] = []
    path_hops = data.get("path_under_evaluation", [])

    for spec in edge_specs_json:
        hop_num = spec.get("hop", 1)
        matching_path_hop = next((h for h in path_hops if h.get("hop") == hop_num), {})
        edge_type = matching_path_hop.get("edge_type", "unknown")
        src_id = matching_path_hop.get("src", {}).get("provider_id", "src")
        dst_id = matching_path_hop.get("dst", {}).get("provider_id", "dst")

        required_preds: List[ContextPredicate] = []
        for rc in spec.get("required_context", []):
            scope_str = rc.get("scope", "unknown").lower()
            try:
                scope_enum = ContextScope(scope_str)
            except ValueError:
                scope_enum = ContextScope.UNKNOWN

            required_preds.append(
                ContextPredicate(
                    key=rc.get("key", ""),
                    operator=rc.get("operator", ""),
                    values=rc.get("values", []),
                    scope=scope_enum,
                    description=rc.get("description"),
                )
            )

        produced_mods: List[ProducedStateModification] = []
        for pc in spec.get("produced_context", []):
            produced_mods.append(
                ProducedStateModification(
                    key=pc.get("key", ""),
                    operation=pc.get("operation", "SET"),
                    value=pc.get("value", ""),
                    attributes={k: v for k, v in pc.items() if k not in ("key", "operation", "value")},
                    description=pc.get("description"),
                )
            )

        hops.append(
            HopContextSpec(
                hop=hop_num,
                edge_type=edge_type,
                src_node_id=src_id,
                dst_node_id=dst_id,
                required_context=required_preds,
                produced_context=produced_mods,
            )
        )

    transitions: List[TransitionRelation] = []
    for tc in trans_json:
        transitions.append(
            TransitionRelation(
                from_hop=tc.get("from_hop", 1),
                to_hop=tc.get("to_hop", 2),
                variable=tc.get("variable", ""),
                relation_type=tc.get("relation", "EQUAL"),
                formula=tc.get("formula", ""),
                rationale=tc.get("rationale"),
            )
        )

    return PathEvaluationInput(
        path_id=fixture_id,
        hops=hops,
        transition_constraints=transitions,
        scenario_assumptions=scenario_assumptions,
    )


def evaluate_sidecar(sidecar_path: Union[str, Path]) -> PathEvaluationResult:
    """Convenience helper to load and evaluate a .context.json sidecar file."""
    eval_input = load_sidecar_context(sidecar_path)
    evaluator = RestrictedDeterministicConstraintEvaluator()
    return evaluator.evaluate(eval_input)
