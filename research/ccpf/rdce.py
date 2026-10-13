"""Restricted Deterministic Constraint Evaluator (RDCE) for CCPF.

Domain-restricted, deterministic constraint feasibility evaluator implementing
the formal contract in docs/CCPF_EVALUATOR_CONTRACT.md (v1.1.0, Prompt 2A).

This module is strictly isolated from production path-search and Bayesian
probability scoring. It accepts a path prefix with context specifications and
returns a tri-state logical feasibility decision (SAT, UNSAT, UNKNOWN) along
with constructive witness or clash proof.

Branch: temporal-context-dev
Workspace: C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL
Contract: docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0
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
    """Formal scopes governing context variable lifecycle and persistence."""
    REQUEST = "request"        # Per-API-call origin (e.g., aws:SourceIp)
    SESSION = "session"        # Bound to active STS token set (e.g., aws:MultiFactorAuthPresent)
    PRINCIPAL = "principal"    # Bound to active IAM entity (e.g., aws:PrincipalTag/<key>)
    CONFIG = "config"          # Hop-local request parameter (e.g., sts:ExternalId)
    UNKNOWN = "unknown"        # Unmapped or unclassified scope


@dataclass(frozen=True)
class ContextPredicate:
    """A single context requirement asserted on a graph edge."""
    key: str
    operator: str
    values: List[str]
    scope: ContextScope
    description: Optional[str] = None


@dataclass(frozen=True)
class ProducedStateModification:
    """A state variable mutation produced upon traversing a graph edge."""
    key: str
    operation: str             # "SET", "CLEAR", "RESET"
    value: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None


@dataclass(frozen=True)
class HopContextSpec:
    """Context specifications bound to a single edge hop in a path prefix."""
    hop: int
    edge_type: str
    src_node_id: str
    dst_node_id: str
    required_context: List[ContextPredicate] = field(default_factory=list)
    produced_context: List[ProducedStateModification] = field(default_factory=list)


@dataclass(frozen=True)
class TransitionRelation:
    """Inter-hop transition constraint linking context across consecutive hops."""
    from_hop: int
    to_hop: int
    variable: str
    relation_type: str         # "EQUAL", "PIVOT_TRANSITION", "IDENTITY_DERIVATION"
    formula: str
    rationale: Optional[str] = None


class FeasibilityStatus(str, Enum):
    """Tri-state logical feasibility outcomes (Prompt 2A Contract)."""
    SAT = "SAT"
    UNSAT = "UNSAT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PathEvaluationInput:
    """Input bundle submitted to the deterministic evaluator."""
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
        addr = ipaddress.ip_address(s)
        prefix = 32 if addr.version == 4 else 128
        return ipaddress.ip_network(f"{s}/{prefix}", strict=False)
    return ipaddress.ip_network(s, strict=False)


def intersect_two_cidrs(
    net1: Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
    net2: Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
) -> Optional[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """Compute the intersection of two CIDR networks. Returns None if disjoint or different versions."""
    if net1.version != net2.version:
        return None
    if net1.subnet_of(net2):
        return net1
    if net2.subnet_of(net1):
        return net2
    return None


def check_ip_version_consistency(
    networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]
) -> Optional[str]:
    """Check if a list of networks contains mixed IP versions."""
    if not networks:
        return None
    versions = {net.version for net in networks}
    if len(versions) > 1:
        return f"UNSUPPORTED_MIXED_IP_VERSIONS: Mixed IPv4 and IPv6 in predicate values: {networks}"
    return None


def intersect_cidr_disjunctions(
    group1: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
    group2: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> Tuple[List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]], Optional[str]]:
    """Intersect two disjunctive (OR) lists of CIDRs. Returns (surviving_subnets, mixed_version_error)."""
    err1 = check_ip_version_consistency(group1)
    if err1:
        return [], err1
    err2 = check_ip_version_consistency(group2)
    if err2:
        return [], err2

    if group1 and group2:
        v1 = group1[0].version
        v2 = group2[0].version
        if v1 != v2:
            return [], f"UNSUPPORTED_MIXED_IP_VERSIONS: Cannot intersect IPv{v1} with IPv{v2} under static origin without dual-stack semantics"

    surviving: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for n1 in group1:
        for n2 in group2:
            common = intersect_two_cidrs(n1, n2)
            if common is not None:
                if not any(common.subnet_of(existing) for existing in surviving):
                    surviving.append(common)
    return surviving, None


def subtract_cidr_lists(
    allowed_list: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
    denied_list: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> Tuple[List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]], Optional[str]]:
    """Compute set difference: allowed_list \\ \\bigcup(denied_list). Returns (remaining_subnets, error)."""
    err_a = check_ip_version_consistency(allowed_list)
    if err_a:
        return [], err_a
    err_d = check_ip_version_consistency(denied_list)
    if err_d:
        return [], err_d

    current_subnets = list(allowed_list)
    for d in denied_list:
        next_subnets = []
        for a in current_subnets:
            if a.version != d.version:
                return [], f"UNSUPPORTED_MIXED_IP_VERSIONS: Cannot subtract IPv{d.version} network {d} from IPv{a.version} network {a}"
            if not a.overlaps(d):
                next_subnets.append(a)
            elif a.subnet_of(d):
                # Completely excluded by denied network
                pass
            elif d.subnet_of(a):
                # Partition a and exclude d
                next_subnets.extend(a.address_exclude(d))
        current_subnets = next_subnets
        if not current_subnets:
            break
    return current_subnets, None


def select_witness_ip(subnet: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]) -> str:
    """Safely extract a representative host IP address from a CIDR network block.

    Handles both iterator and list returns from .hosts() across prefix lengths
    (/32 in IPv4, /128 in IPv6, and arbitrary CIDR blocks). Falls back to
    subnet.network_address if no dedicated host address is available.
    """
    hosts_seq = subnet.hosts()
    if isinstance(hosts_seq, list):
        if hosts_seq:
            return str(hosts_seq[0])
        return str(subnet.network_address)
    try:
        return str(next(iter(hosts_seq)))
    except StopIteration:
        return str(subnet.network_address)


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

            # 2. Scope bindings and state tracking per hop
            hop_allowed_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}
            hop_denied_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}

            hop_principal_strings: Dict[int, Dict[str, Set[str]]] = {}
            hop_session_strings: Dict[int, Dict[str, Set[str]]] = {}
            hop_config_strings: Dict[int, Dict[str, Set[str]]] = {}
            hop_request_strings: Dict[int, Dict[str, Set[str]]] = {}

            hop_session_bool_domains: Dict[int, Dict[str, Set[bool]]] = {}
            hop_null_assertions: Dict[int, Dict[str, bool]] = {}

            produced_state: Dict[int, Dict[str, Any]] = {}
            produced_attrs: Dict[int, Dict[str, Any]] = {}

            # 3. Iterate through hops sequentially
            iteration_count = 0
            for hop_idx, hop in enumerate(input_data.hops, start=1):
                hop_num = hop.hop
                hop_principal_strings[hop_num] = {}
                hop_session_strings[hop_num] = {}
                hop_config_strings[hop_num] = {}
                hop_request_strings[hop_num] = {}
                hop_session_bool_domains[hop_num] = {}
                hop_null_assertions[hop_num] = {}
                produced_state[hop_num] = {}
                produced_attrs[hop_num] = {}

                # Carry-over / scope reset from previous hop
                if hop_idx > 1:
                    prev_hop = input_data.hops[hop_idx - 2]
                    prev_hop_num = prev_hop.hop

                    # Determine if transition entering hop_num was an AssumeRole boundary
                    is_role_assumption_transition = (
                        prev_hop.edge_type == "sts:AssumeRole"
                        or any(
                            t.from_hop == prev_hop_num
                            and t.to_hop == hop_num
                            and t.relation_type in ("IDENTITY_DERIVATION", "ROLE_ASSUMPTION")
                            for t in input_data.transition_constraints
                        )
                    )

                    if not is_role_assumption_transition:
                        # Standard action continuation: carry principal tags, session strings, and session bools
                        hop_principal_strings[hop_num] = {
                            k: set(v) for k, v in hop_principal_strings[prev_hop_num].items()
                        }
                        hop_session_strings[hop_num] = {
                            k: set(v) for k, v in hop_session_strings[prev_hop_num].items()
                        }
                        hop_session_bool_domains[hop_num] = {
                            k: set(v) for k, v in hop_session_bool_domains[prev_hop_num].items()
                        }
                    else:
                        # AssumeRole transition boundary:
                        # Caller session state (MFA, session strings) resets to fresh session
                        hop_session_strings[hop_num] = {}
                        hop_session_bool_domains[hop_num] = {}
                        # Caller principal tags reset (do not survive boundary)
                        hop_principal_strings[hop_num] = {}

                        # Target role attached tags produced in AssumeRole hop become initial principal tags on hop_num
                        for p_key, p_val in produced_state.get(prev_hop_num, {}).items():
                            if p_key.startswith("aws:PrincipalTag/") and isinstance(p_val, str):
                                hop_principal_strings[hop_num][p_key] = {p_val}

                # Evaluate required context predicates (PRECONDITIONS) for this hop first
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
                        if any("*" in str(v) or "?" in str(v) for v in pred.values):
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
                        if not pred.values:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"EMPTY_IP_VALUES: {pred.key}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

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

                        ver_err = check_ip_version_consistency(parsed_list)
                        if ver_err:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=ver_err,
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        if hop_null_assertions[hop_num].get(pred.key) is True:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Null assertion clash on hop {hop_num} for '{pred.key}': "
                                    f"Key required to be null, but IpAddress requires concrete CIDR {parsed_list}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        if hop_num not in hop_allowed_cidrs:
                            hop_allowed_cidrs[hop_num] = parsed_list
                        else:
                            surviving, mixed_err = intersect_cidr_disjunctions(hop_allowed_cidrs[hop_num], parsed_list)
                            if mixed_err:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=mixed_err,
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
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
                        if not pred.values:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"EMPTY_NOT_IP_VALUES: {pred.key}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

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

                        ver_err = check_ip_version_consistency(parsed_denied)
                        if ver_err:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=ver_err,
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        hop_denied_cidrs.setdefault(hop_num, []).extend(parsed_denied)

                    # 3.3 Operator: StringEquals or exact StringLike
                    elif op in ("StringEquals", "StringLike"):
                        if not pred.values:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"EMPTY_STRING_VALUES: {pred.key}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        if any(not isinstance(v, str) for v in pred.values):
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"NON_STRING_VALUE: {pred.key}",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        if hop_null_assertions[hop_num].get(pred.key) is True:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Null assertion clash on hop {hop_num} for '{pred.key}': "
                                    f"Key required to be null, but String predicate requires concrete {pred.values}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        req_values = set(pred.values)
                        tag_key = pred.key

                        if scope == ContextScope.PRINCIPAL:
                            target_store = hop_principal_strings[hop_num]
                            scope_desc = "Principal tag"
                        elif scope == ContextScope.SESSION:
                            target_store = hop_session_strings[hop_num]
                            scope_desc = "Session string"
                        elif scope == ContextScope.CONFIG:
                            target_store = hop_config_strings[hop_num]
                            scope_desc = "Config string"
                        elif scope == ContextScope.REQUEST:
                            target_store = hop_request_strings[hop_num]
                            scope_desc = "Request string"
                        else:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"UNSUPPORTED_OR_UNKNOWN_SCOPE: {tag_key} (scope: {scope})",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        active_set = target_store.get(tag_key)
                        if active_set is not None:
                            overlap = active_set.intersection(req_values)
                            if not overlap:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"{scope_desc} contradiction on hop {hop_num} ({scope.value} scope) for '{tag_key}': "
                                        f"Active values {active_set} clash with required {req_values}"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            target_store[tag_key] = overlap
                        else:
                            target_store[tag_key] = req_values

                    # 3.4 Operator: Bool (with full multi-value disjunction semantics)
                    elif op == "Bool":
                        if not pred.values:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"MALFORMED_BOOL_VALUE: Empty values list for '{pred.key}'",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        parsed_bools: Set[bool] = set()
                        for v in pred.values:
                            v_str = str(v).strip().lower()
                            if v_str in ("true", "1"):
                                parsed_bools.add(True)
                            elif v_str in ("false", "0"):
                                parsed_bools.add(False)
                            else:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=f"UNPARSEABLE_BOOL_VALUE: '{v}' for key '{pred.key}'",
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        if hop_null_assertions[hop_num].get(pred.key) is True:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Null assertion clash on hop {hop_num} for '{pred.key}': "
                                    f"Key required to be null, but Bool predicate requires {parsed_bools}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        existing_domain = hop_session_bool_domains[hop_num].get(pred.key)
                        if existing_domain is None:
                            new_domain = parsed_bools
                        else:
                            new_domain = existing_domain.intersection(parsed_bools)

                        if not new_domain:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Boolean identity contradiction on hop {hop_num} for '{pred.key}': "
                                    f"Active domain {existing_domain} clashes with required {parsed_bools}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        hop_session_bool_domains[hop_num][pred.key] = new_domain

                    # 3.5 Operator: Null (Commutative conjunction)
                    elif op == "Null":
                        if len(pred.values) != 1:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"INVALID_NULL_VALUES_COUNT: Expected exactly 1 value for Null condition '{pred.key}', "
                                    f"got {len(pred.values)}: {pred.values}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        val_str = str(pred.values[0]).strip().lower()
                        if val_str in ("true", "1"):
                            null_truth = True
                        elif val_str in ("false", "0"):
                            null_truth = False
                        else:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=f"UNPARSEABLE_NULL_VALUE: '{pred.values[0]}' for key '{pred.key}'",
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                        prev_null = hop_null_assertions[hop_num].get(pred.key)
                        if prev_null is not None and prev_null != null_truth:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Contradictory Null assertions on hop {hop_num} for '{pred.key}': "
                                    f"Cannot require both null (true) and non-null (false)"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        hop_null_assertions[hop_num][pred.key] = null_truth

                        if null_truth is True:
                            # Verify no active positive constraints exist across any scope
                            has_active_pos = (
                                (pred.key in hop_principal_strings[hop_num])
                                or (pred.key in hop_session_strings[hop_num])
                                or (pred.key in hop_config_strings[hop_num])
                                or (pred.key in hop_request_strings[hop_num])
                                or (pred.key in hop_session_bool_domains[hop_num])
                                or (pred.key == "aws:SourceIp" and hop_num in hop_allowed_cidrs)
                            )
                            if has_active_pos:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Null assertion failed on hop {hop_num} for '{pred.key}': "
                                        f"Key is required to be null, but active constraints require concrete value"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                # Ingest produced context (POSTCONDITIONS) for this hop after preconditions
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
                        produced_attrs[hop_num][key] = prod.attributes

                    # If this hop is not AssumeRole, produced principal tags update current hop
                    if hop.edge_type != "sts:AssumeRole":
                        if key.startswith("aws:PrincipalTag/") and isinstance(val, str):
                            hop_principal_strings[hop_num][key] = {val}

                # Post-hop commutativity verification for Null constraints
                for null_k, is_null in hop_null_assertions[hop_num].items():
                    if is_null is True:
                        has_pos = (
                            (null_k in hop_principal_strings[hop_num])
                            or (null_k in hop_session_strings[hop_num])
                            or (null_k in hop_config_strings[hop_num])
                            or (null_k in hop_request_strings[hop_num])
                            or (null_k in hop_session_bool_domains[hop_num])
                            or (null_k == "aws:SourceIp" and hop_num in hop_allowed_cidrs)
                        )
                        if has_pos:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Null assertion failed on hop {hop_num} for '{null_k}': "
                                    f"Key is required to be null, but active constraints require concrete value"
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

                    req_tags_target = hop_principal_strings.get(trans.to_hop, {}).get(tag_var)
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

            # 5. IP Constraint Resolution & Partition Subtraction
            accumulated_static_subnets: Optional[List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = None

            if static_origin or any(t.relation_type == "EQUAL" for t in input_data.transition_constraints):
                hops_with_ip = [
                    h.hop for h in input_data.hops
                    if (h.hop in hop_allowed_cidrs or h.hop in hop_denied_cidrs)
                    and h.hop not in pivot_rebound_hops
                ]

                if hops_with_ip:
                    # Accumulate positive allowed subnets across static origin hops
                    first_hop_with_allowed = next((h for h in hops_with_ip if h in hop_allowed_cidrs), None)
                    if first_hop_with_allowed is not None:
                        accumulated = hop_allowed_cidrs[first_hop_with_allowed]
                        for next_hop in hops_with_ip:
                            if next_hop == first_hop_with_allowed or next_hop not in hop_allowed_cidrs:
                                continue
                            next_allowed = hop_allowed_cidrs[next_hop]
                            surviving, mixed_err = intersect_cidr_disjunctions(accumulated, next_allowed)
                            if mixed_err:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=mixed_err,
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            if not surviving:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Contradictory persistent context under static origin assumption: "
                                        f"CIDRs on hop {first_hop_with_allowed} ({hop_allowed_cidrs[first_hop_with_allowed]}) "
                                        f"are disjoint from hop {next_hop} ({next_allowed})"
                                    ),
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            accumulated = surviving
                        accumulated_static_subnets = accumulated
                    else:
                        # Only NotIpAddress constraints under static origin: default to IPv4 0.0.0.0/0
                        all_denied = [d for h in hops_with_ip for d in hop_denied_cidrs.get(h, [])]
                        def_ver = all_denied[0].version if all_denied else 4
                        default_univ = ipaddress.ip_network("0.0.0.0/0" if def_ver == 4 else "::/0")
                        accumulated_static_subnets = [default_univ]

                    # Apply all static origin denied CIDRs to the accumulated allowed subnets
                    all_static_denied: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
                    for h in hops_with_ip:
                        all_static_denied.extend(hop_denied_cidrs.get(h, []))

                    if all_static_denied and accumulated_static_subnets:
                        surviving_after_denial, mixed_err = subtract_cidr_lists(accumulated_static_subnets, all_static_denied)
                        if mixed_err:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=mixed_err,
                                evaluated_hops=len(input_data.hops),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        if not surviving_after_denial:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Allowed CIDRs {accumulated_static_subnets} fully denied by {all_static_denied} "
                                    f"under static origin assumption"
                                ),
                                evaluated_hops=len(input_data.hops),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        accumulated_static_subnets = surviving_after_denial

            else:
                # Independent per-hop IP constraints
                all_hops_with_ip = set(hop_allowed_cidrs.keys()).union(hop_denied_cidrs.keys())
                for h_num in all_hops_with_ip:
                    denied_list = hop_denied_cidrs.get(h_num, [])
                    if h_num in hop_allowed_cidrs:
                        allowed_list = hop_allowed_cidrs[h_num]
                        if denied_list:
                            surviving_after_denial, mixed_err = subtract_cidr_lists(allowed_list, denied_list)
                            if mixed_err:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=mixed_err,
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            if not surviving_after_denial:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=f"Allowed CIDRs {allowed_list} fully denied by {denied_list} on hop {h_num}",
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            hop_allowed_cidrs[h_num] = surviving_after_denial
                    else:
                        # Only NotIpAddress on this hop
                        if denied_list:
                            def_ver = denied_list[0].version
                            default_univ = ipaddress.ip_network("0.0.0.0/0" if def_ver == 4 else "::/0")
                            surviving_after_denial, mixed_err = subtract_cidr_lists([default_univ], denied_list)
                            if mixed_err:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=mixed_err,
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            if not surviving_after_denial:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=f"Entire address space denied by {denied_list} on hop {h_num}",
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            hop_allowed_cidrs[h_num] = surviving_after_denial

            # 6. Construct Satisfying Witness
            witness: Dict[str, Any] = {}

            # Construct IP witness
            if accumulated_static_subnets:
                chosen_subnet = accumulated_static_subnets[0]
                static_ip = select_witness_ip(chosen_subnet)
                witness["aws:SourceIp"] = static_ip
                for h_num in input_data.hops:
                    if h_num.hop not in pivot_rebound_hops:
                        witness[f"hop_{h_num.hop}_SourceIp"] = static_ip
            else:
                for hop_num, allowed_list in hop_allowed_cidrs.items():
                    if allowed_list:
                        chosen_subnet = allowed_list[0]
                        chosen_ip = select_witness_ip(chosen_subnet)
                        witness[f"hop_{hop_num}_SourceIp"] = chosen_ip
                        if "aws:SourceIp" not in witness:
                            witness["aws:SourceIp"] = chosen_ip

            # Re-bound IP for pivot transitions
            for p_hop in pivot_rebound_hops:
                rebound_val = produced_state.get(p_hop - 1, {}).get("network_execution_origin")
                if rebound_val:
                    witness[f"hop_{p_hop}_SourceIp"] = rebound_val

            # Principal tags witness
            for hop_num, tags in hop_principal_strings.items():
                for tag_key, tag_vals in tags.items():
                    if tag_vals:
                        chosen_val = sorted(list(tag_vals))[0]
                        witness[f"hop_{hop_num}_{tag_key}"] = chosen_val
                        witness[tag_key] = chosen_val

            # Session strings witness
            for hop_num, s_strings in hop_session_strings.items():
                for s_key, s_vals in s_strings.items():
                    if s_vals:
                        chosen_val = sorted(list(s_vals))[0]
                        witness[f"hop_{hop_num}_{s_key}"] = chosen_val
                        witness[s_key] = chosen_val

            # Config strings witness
            for hop_num, c_strings in hop_config_strings.items():
                for c_key, c_vals in c_strings.items():
                    if c_vals:
                        chosen_val = sorted(list(c_vals))[0]
                        witness[f"hop_{hop_num}_{c_key}"] = chosen_val
                        witness[c_key] = chosen_val

            # Request strings witness
            for hop_num, r_strings in hop_request_strings.items():
                for r_key, r_vals in r_strings.items():
                    if r_vals:
                        chosen_val = sorted(list(r_vals))[0]
                        witness[f"hop_{hop_num}_{r_key}"] = chosen_val
                        witness[r_key] = chosen_val

            # Session bools witness
            for hop_num, bool_domains in hop_session_bool_domains.items():
                for b_key, b_domain in bool_domains.items():
                    if b_domain == {True}:
                        b_val = True
                    elif b_domain == {False}:
                        b_val = False
                    else:
                        # Unconstrained / vacuous disjunction: default to False
                        b_val = False
                    witness[b_key] = b_val
                    witness[f"hop_{hop_num}_{b_key}"] = b_val

            # Enforce Null assertions on witness (exclude keys required to be null)
            for hop_num, null_dict in hop_null_assertions.items():
                for n_key, must_be_null in null_dict.items():
                    if must_be_null is True:
                        witness.pop(n_key, None)
                        witness.pop(f"hop_{hop_num}_{n_key}", None)
                    else:
                        # Must exist
                        if n_key not in witness:
                            witness[n_key] = "present"

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
    try:
        eval_input = load_sidecar_context(sidecar_path)
        evaluator = RestrictedDeterministicConstraintEvaluator()
        return evaluator.evaluate(eval_input)
    except Exception as exc:
        return PathEvaluationResult(
            path_id=Path(sidecar_path).stem,
            status=FeasibilityStatus.UNKNOWN,
            unknown_rationale=f"SIDECAR_LOAD_EXCEPTION: {type(exc).__name__}: {str(exc)}",
        )
