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
    REQUEST = "request"        # Per-API-call origin (e.g., aws:SourceIp, aws:RequestTag/*)
    SESSION = "session"        # Bound to active STS token set (e.g., aws:MultiFactorAuthPresent)
    PRINCIPAL = "principal"    # Bound to active IAM entity (e.g., aws:PrincipalTag/<key>)
    CONFIG = "config"          # Hop-local request parameter (e.g., sts:ExternalId)
    UNKNOWN = "unknown"        # Unmapped or unclassified scope


class ConfigInputStatus(str, Enum):
    """Status of a caller-supplied CONFIG value for a given hop."""
    PRESENT = "present"          # Caller provided a value
    MISSING = "missing"          # No value supplied by caller
    INVALID = "invalid"          # Value provided but fails validation


class InitializerSource(str, Enum):
    """Source metadata for RESET(SCOPE) initialization."""
    NEW_SESSION_ATTRIBUTES = "new_session_attributes"           # SESSION on AssumeRole
    TARGET_ROLE_ATTRIBUTES = "target_role_attributes"           # PRINCIPAL on AssumeRole/IDENTITY_DERIVATION
    NETWORK_EXECUTION_ORIGIN = "network_execution_origin"       # REQUEST SourceIp on PIVOT_TRANSITION


class TargetType(str, Enum):
    """Target scope for RESET operations."""
    KEY = "key"          # Single key reset
    SCOPE = "scope"      # Full scope reset (all registered keys in scope)


class ResetValidationResult(str, Enum):
    """Result of RESET validation."""
    VALID = "valid"
    INVALID_TARGET = "invalid_target"
    UNSUPPORTED_KEY = "unsupported_key"
    UNSUPPORTED_INITIALIZER = "unsupported_initializer"
    MISSING_INITIALIZER = "missing_initializer"
    INCOMPLETE_SCOPE = "incomplete_scope"
    CONFLICT = "conflict"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class ResetMetadata:
    """Typed metadata for a RESET operation."""
    target_type: TargetType
    target_key: Optional[str] = None           # For KEY-level RESET
    target_scope: Optional[ContextScope] = None  # For SCOPE-level RESET
    initializer_source: Optional[InitializerSource] = None
    generation_boundary: int = 0               # New generation identifier
    provenance: Dict[str, Any] = field(default_factory=dict)  # Source provenance
    validation_result: ResetValidationResult = ResetValidationResult.VALID
    validation_detail: Optional[str] = None


@dataclass(frozen=True)
class GenerationInfo:
    """Generation and provenance tracking for a context key."""
    generation: int = 0
    initializer_source: Optional[InitializerSource] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    is_reset: bool = False                     # Whether this generation was established by RESET
    previous_generation: int = 0               # Previous generation before RESET


class KeyState(str, Enum):
    """Three-state model for context key presence (Phase 2)."""
    PRESENT = "present"        # Concrete value established
    ABSENT = "absent"          # Explicitly known to be absent (CLEAR)
    UNCONSTRAINED = "unconstrained"  # Never mentioned / unknown


@dataclass(frozen=True)
class KeyStatus:
    """Typed representation of a key's state with optional value."""
    state: KeyState
    value: Optional[str] = None  # Only meaningful when state == PRESENT


def make_present(value: str) -> KeyStatus:
    return KeyStatus(state=KeyState.PRESENT, value=value)


def make_absent() -> KeyStatus:
    return KeyStatus(state=KeyState.ABSENT, value=None)


def make_unconstrained() -> KeyStatus:
    return KeyStatus(state=KeyState.UNCONSTRAINED, value=None)


@dataclass(frozen=True)
class CallerConfigInput:
    """Actual caller-supplied CONFIG value for a single hop."""
    key: str
    status: ConfigInputStatus
    value: Optional[str] = None
    validation_error: Optional[str] = None


@dataclass(frozen=True)
class HopCallerInputs:
    """All caller-supplied CONFIG inputs for a single hop."""
    hop: int
    inputs: Dict[str, CallerConfigInput]


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
    operation: str             # Contract enum: "SET", "CLEAR", "RESET"
    value: str
    scope: ContextScope = ContextScope.UNKNOWN        # MANDATORY — no default, but backward compat
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
    # Optional caller-supplied CONFIG inputs for this hop (backward compatible)
    caller_config_inputs: Optional[HopCallerInputs] = None


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
    # Per-hop caller-supplied CONFIG inputs (backward compatible)
    caller_config_inputs: Dict[int, HopCallerInputs] = field(default_factory=dict)


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


# Supported Safe Fragment Operators
SUPPORTED_OPERATORS = {
    "IpAddress",
    "NotIpAddress",
    "StringEquals",
    "StringLike",  # Only without wildcards
    "Bool",
    "Null",
}


# Tier 2 Safe Fragment Registry (Normative)
# Only these (scope, key, operator) combinations may produce SAT/UNSAT.
# All others → UNKNOWN.
# Format: (scope, key_pattern) -> set(operators)
TIER2_REGISTRY: Dict[Tuple[str, str], Set[str]] = {
    # REQUEST scope
    ("request", "aws:SourceIp"): {"IpAddress", "NotIpAddress"},
    ("request", "aws:RequestTag/*"): {"StringEquals", "Null"},
    # SESSION scope
    ("session", "aws:MultiFactorAuthPresent"): {"Bool"},
    ("session", "aws:SessionIssuer"): {"StringEquals"},
    # PRINCIPAL scope
    ("principal", "aws:PrincipalTag/*"): {"StringEquals", "Null"},
    ("principal", "aws:PrincipalArn"): {"StringEquals"},
    # CONFIG scope
    ("config", "sts:ExternalId"): {"StringEquals"},
}


def is_tier2_supported(scope: ContextScope, key: str, operator: str) -> bool:
    """Check if (scope, key, operator) is in Tier 2 Safe Fragment."""
    # Exact key match
    if (scope.value, key) in TIER2_REGISTRY:
        return operator in TIER2_REGISTRY[(scope.value, key)]
    # Wildcard pattern match for tag keys
    for (reg_scope, reg_key), ops in TIER2_REGISTRY.items():
        if reg_scope != scope.value:
            continue
        if reg_key.endswith("/*") and key.startswith(reg_key[:-1]):
            return operator in ops
    return False


def get_tier2_operators(scope: ContextScope, key: str) -> Set[str]:
    """Get the supported Tier 2 operators for a (scope, key) combination."""
    if (scope.value, key) in TIER2_REGISTRY:
        return TIER2_REGISTRY[(scope.value, key)]
    for (reg_scope, reg_key), ops in TIER2_REGISTRY.items():
        if reg_scope != scope.value:
            continue
        if reg_key.endswith("/*") and key.startswith(reg_key[:-1]):
            return ops
    return set()


# RESET Registry: Mapping of supported keys to their approved initializer sources per scope
# Only these four registry entries are initially supported for RESET
RESET_REGISTRY: Dict[Tuple[str, str], InitializerSource] = {
    # SESSION scope
    ("session", "aws:SessionTag/*"): InitializerSource.NEW_SESSION_ATTRIBUTES,
    ("session", "aws:SessionIssuer"): InitializerSource.NEW_SESSION_ATTRIBUTES,
    # PRINCIPAL scope
    ("principal", "aws:PrincipalArn"): InitializerSource.TARGET_ROLE_ATTRIBUTES,
    # REQUEST scope
    ("request", "aws:UserAgent"): InitializerSource.NETWORK_EXECUTION_ORIGIN,
}


# Registry of all keys per scope for SCOPE-level RESET completeness checking
SCOPE_KEY_REGISTRY: Dict[str, List[str]] = {
    "session": ["aws:SessionTag/*", "aws:SessionIssuer"],
    "principal": ["aws:PrincipalArn", "aws:PrincipalTag/*"],
    "request": ["aws:UserAgent"],
    "config": ["sts:ExternalId"],
}


def get_reset_initializer_source(scope: ContextScope, key: str) -> Optional[InitializerSource]:
    """Get the approved initializer source for a RESET-targeted key."""
    # Exact key match
    if (scope.value, key) in RESET_REGISTRY:
        return RESET_REGISTRY[(scope.value, key)]
    # Wildcard pattern match for tag keys
    for (reg_scope, reg_key), init_src in RESET_REGISTRY.items():
        if reg_scope != scope.value:
            continue
        if reg_key.endswith("/*") and key.startswith(reg_key[:-1]):
            return init_src
    return None


def get_scope_registered_keys(scope: ContextScope) -> List[str]:
    """Get all registered keys for a scope (for SCOPE-level RESET completeness)."""
    return SCOPE_KEY_REGISTRY.get(scope.value, [])


def is_key_reset_supported(scope: ContextScope, key: str) -> bool:
    """Check if a key supports RESET for the given scope."""
    return get_reset_initializer_source(scope, key) is not None


def is_scope_reset_supported(scope: ContextScope) -> bool:
    """Check if a scope supports SCOPE-level RESET (complete key coverage)."""
    registered_keys = get_scope_registered_keys(scope)
    # For SCOPE-level RESET, ALL registered keys must have initializer support
    for key in registered_keys:
        if not is_key_reset_supported(scope, key):
            return False
    return len(registered_keys) > 0


def validate_reset_operation(
    target_type: TargetType,
    target_key: Optional[str],
    target_scope: Optional[ContextScope],
    initializer_source: Optional[InitializerSource],
) -> Tuple[ResetValidationResult, Optional[str]]:
    """Validate a RESET operation before execution.
    
    Returns (validation_result, detail_message).
    """
    # Validate target type
    if target_type == TargetType.KEY:
        if not target_key or not target_key.strip():
            return ResetValidationResult.INVALID_TARGET, "KEY-level RESET requires non-empty target_key"
        if not target_scope:
            return ResetValidationResult.INVALID_TARGET, "KEY-level RESET requires target_scope"
        # Check if key supports RESET
        if not is_key_reset_supported(target_scope, target_key):
            return ResetValidationResult.UNSUPPORTED_KEY, f"Key '{target_key}' in scope '{target_scope.value}' does not support RESET"
        # Check initializer source match
        expected_init = get_reset_initializer_source(target_scope, target_key)
        if expected_init and initializer_source != expected_init:
            return ResetValidationResult.UNSUPPORTED_INITIALIZER, (
                f"Initializer '{initializer_source.value if initializer_source else 'None'}' "
                f"does not match required '{expected_init.value}' for key '{target_key}'"
            )
        if not initializer_source:
            return ResetValidationResult.MISSING_INITIALIZER, f"KEY-level RESET requires initializer_source for '{target_key}'"
    
    elif target_type == TargetType.SCOPE:
        if not target_scope:
            return ResetValidationResult.INVALID_TARGET, "SCOPE-level RESET requires target_scope"
        if not is_scope_reset_supported(target_scope):
            return ResetValidationResult.INCOMPLETE_SCOPE, (
                f"Scope '{target_scope.value}' does not support SCOPE-level RESET: "
                f"not all registered keys have initializer support"
            )
        if not initializer_source:
            return ResetValidationResult.MISSING_INITIALIZER, "SCOPE-level RESET requires initializer_source"
    
    else:
        return ResetValidationResult.INVALID_TARGET, f"Unknown target_type: {target_type}"
    
    return ResetValidationResult.VALID, None


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
            # 1. Check for empty or malformed path input.
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

            # HopContextSpec.hop is a positive, 1-indexed path position.
            # Evaluator stores are keyed by this field, so duplicate or
            # non-increasing identifiers can alias or misbind independent
            # scopes. Sparse positions are allowed when evaluating a path
            # excerpt that retains its original full-path indices.
            # Treat malformed identifiers as UNKNOWN: never infer UNSAT.
            observed_hop_numbers = [getattr(hop, "hop", None) for hop in input_data.hops]
            valid_hop_sequence = (
                all(type(hop_number) is int and hop_number > 0 for hop_number in observed_hop_numbers)
                and all(
                    left < right
                    for left, right in zip(observed_hop_numbers, observed_hop_numbers[1:])
                )
            )
            if not valid_hop_sequence:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return PathEvaluationResult(
                    path_id=input_data.path_id,
                    status=FeasibilityStatus.UNKNOWN,
                    unknown_rationale=(
                        "INVALID_HOP_SEQUENCE: expected positive, unique, strictly "
                        f"increasing 1-indexed path identifiers; got {observed_hop_numbers}"
                    ),
                    evaluated_hops=0,
                    solver_duration_ms=elapsed_ms,
                    diagnostic_metadata={
                        "validation_error": "INVALID_HOP_SEQUENCE",
                        "observed_hop_numbers": observed_hop_numbers,
                    },
                )

            # TransitionRelation endpoints are 1-indexed predecessor/successor
            # references into the validated path sequence. Unknown relation
            # kinds or dangling/backward/self references are unsupported or
            # malformed metadata and must not be silently ignored.
            supported_transition_types = {
                "EQUAL",
                "PIVOT_TRANSITION",
                "IDENTITY_DERIVATION",
                "ROLE_ASSUMPTION",
            }
            valid_hop_numbers = set(observed_hop_numbers)
            for trans_index, trans in enumerate(input_data.transition_constraints):
                from_hop = getattr(trans, "from_hop", None)
                to_hop = getattr(trans, "to_hop", None)
                relation_type = getattr(trans, "relation_type", None)
                variable = getattr(trans, "variable", None)
                if (
                    type(from_hop) is not int
                    or type(to_hop) is not int
                    or from_hop not in valid_hop_numbers
                    or to_hop not in valid_hop_numbers
                    or from_hop >= to_hop
                ):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return PathEvaluationResult(
                        path_id=input_data.path_id,
                        status=FeasibilityStatus.UNKNOWN,
                        unknown_rationale=(
                            f"INVALID_TRANSITION_ENDPOINTS: transition {trans_index} "
                            f"must reference an existing predecessor/successor pair; "
                            f"got from_hop={from_hop!r}, to_hop={to_hop!r}"
                        ),
                        solver_duration_ms=elapsed_ms,
                        diagnostic_metadata={
                            "validation_error": "INVALID_TRANSITION_ENDPOINTS",
                            "transition_index": trans_index,
                        },
                    )
                if relation_type not in supported_transition_types:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return PathEvaluationResult(
                        path_id=input_data.path_id,
                        status=FeasibilityStatus.UNKNOWN,
                        unknown_rationale=(
                            f"UNSUPPORTED_TRANSITION_TYPE: {relation_type!r} "
                            f"at transition {trans_index}"
                        ),
                        solver_duration_ms=elapsed_ms,
                        diagnostic_metadata={
                            "validation_error": "UNSUPPORTED_TRANSITION_TYPE",
                            "transition_index": trans_index,
                        },
                    )
                if not isinstance(variable, str) or not variable.strip():
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return PathEvaluationResult(
                        path_id=input_data.path_id,
                        status=FeasibilityStatus.UNKNOWN,
                        unknown_rationale=(
                            f"MISSING_TRANSITION_VARIABLE: transition {trans_index} "
                            "must name the variable it relates"
                        ),
                        solver_duration_ms=elapsed_ms,
                        diagnostic_metadata={
                            "validation_error": "MISSING_TRANSITION_VARIABLE",
                            "transition_index": trans_index,
                        },
                    )

            # ProducedStateModification declares SET/CLEAR/RESET at the data
            # boundary. This RDCE implementation supports SET, CLEAR, and RESET.
            for hop_index, hop in enumerate(input_data.hops):
                for produced_index, produced in enumerate(hop.produced_context):
                    operation = getattr(produced, "operation", None)
                    key = getattr(produced, "key", None)
                    value = getattr(produced, "value", None)
                    if operation not in ("SET", "CLEAR", "RESET"):
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=(
                                f"UNSUPPORTED_PRODUCED_OPERATION: {operation!r} "
                                f"at hop index {hop_index}, produced item {produced_index}; "
                                "RDCE supports SET, CLEAR, and RESET only"
                            ),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata={
                                "validation_error": "UNSUPPORTED_PRODUCED_OPERATION",
                                "hop_index": hop_index,
                                "produced_index": produced_index,
                            },
                        )
                    if not isinstance(key, str) or not key.strip():
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=(
                                f"INVALID_PRODUCED_CONTEXT_KEY: hop index {hop_index}, "
                                f"produced item {produced_index} must name a non-empty key"
                            ),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata={
                                "validation_error": "INVALID_PRODUCED_CONTEXT_KEY",
                                "hop_index": hop_index,
                                "produced_index": produced_index,
                            },
                        )
                    if not isinstance(value, str):
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=(
                                f"INVALID_PRODUCED_CONTEXT_VALUE: hop index {hop_index}, "
                                f"produced item {produced_index} must contain a string value"
                            ),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata={
                                "validation_error": "INVALID_PRODUCED_CONTEXT_VALUE",
                                "hop_index": hop_index,
                                "produced_index": produced_index,
                            },
                        )

                    # CLEAR-specific validation: value must be empty
                    if operation == "CLEAR" and value != "":
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=(
                                f"CLEAR operation must have empty value: hop index {hop_index}, "
                                f"produced item {produced_index} has non-empty value"
                            ),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata={
                                "validation_error": "CLEAR_NON_EMPTY_VALUE",
                                "hop_index": hop_index,
                                "produced_index": produced_index,
                            },
                        )

                    # CLEAR-specific validation: scope and key must be valid per Tier 2 registry
                    if operation == "CLEAR":
                        scope_str = produced.scope.value if isinstance(produced.scope, ContextScope) else str(produced.scope)
                        # Check if (scope, key) is in Tier 2 registry (exact or wildcard)
                        tier2_supported = False
                        for (reg_scope, reg_key), ops in TIER2_REGISTRY.items():
                            if reg_scope != scope_str:
                                continue
                            if reg_key == key or (reg_key.endswith("/*") and key.startswith(reg_key[:-1])):
                                tier2_supported = True
                                break
                        if not tier2_supported:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"CLEAR operation on unsupported (scope, key): ({scope_str}, {key})"
                                ),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata={
                                    "validation_error": "CLEAR_UNSUPPORTED_KEY",
                                    "hop_index": hop_index,
                                    "produced_index": produced_index,
                                },
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

            # RESET-specific validation: must have reset_metadata in attributes
            for hop_index, hop in enumerate(input_data.hops):
                for produced_index, produced in enumerate(hop.produced_context):
                    operation = getattr(produced, "operation", None)
                    if operation == "RESET":
                        # RESET must have reset_metadata in attributes
                        reset_metadata = produced.attributes.get("reset_metadata") if produced.attributes else None
                        if not reset_metadata:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"RESET operation missing reset_metadata: hop index {hop_index}, "
                                    f"produced item {produced_index}"
                                ),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata={
                                    "validation_error": "RESET_MISSING_METADATA",
                                    "hop_index": hop_index,
                                    "produced_index": produced_index,
                                },
                            )
                        # Validate target_type and required fields
                        target_type = reset_metadata.target_type
                        if target_type == TargetType.KEY:
                            if not reset_metadata.target_key or not reset_metadata.target_key.strip():
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"KEY-level RESET requires non-empty target_key: hop {hop_index}"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISSING_TARGET_KEY",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            if not reset_metadata.target_scope:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"KEY-level RESET requires target_scope: hop {hop_index}"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISSING_TARGET_SCOPE",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            # Validate key supports RESET
                            if not is_key_reset_supported(reset_metadata.target_scope, reset_metadata.target_key):
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Key '{reset_metadata.target_key}' in scope "
                                        f"'{reset_metadata.target_scope.value}' does not support RESET"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_UNSUPPORTED_KEY",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            # Validate initializer source
                            expected_init = get_reset_initializer_source(
                                reset_metadata.target_scope, reset_metadata.target_key
                            )
                            if expected_init and reset_metadata.initializer_source != expected_init:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Initializer '{reset_metadata.initializer_source.value if reset_metadata.initializer_source else 'None'}' "
                                        f"does not match required '{expected_init.value}' for key "
                                        f"'{reset_metadata.target_key}'"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISMATCHED_INITIALIZER",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            if not reset_metadata.initializer_source:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"KEY-level RESET requires initializer_source for "
                                        f"'{reset_metadata.target_key}'"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISSING_INITIALIZER",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                        elif target_type == TargetType.SCOPE:
                            if not reset_metadata.target_scope:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"SCOPE-level RESET requires target_scope: hop {hop_index}"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISSING_TARGET_SCOPE",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            if not is_scope_reset_supported(reset_metadata.target_scope):
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Scope '{reset_metadata.target_scope.value}' does not support "
                                        f"SCOPE-level RESET: incomplete key coverage"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_INCOMPLETE_SCOPE",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                            if not reset_metadata.initializer_source:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"SCOPE-level RESET requires initializer_source"
                                    ),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata={
                                        "validation_error": "RESET_MISSING_INITIALIZER",
                                        "hop_index": hop_index,
                                        "produced_index": produced_index,
                                    },
                                )
                        else:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"Unknown RESET target_type: {target_type}"
                                ),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata={
                                    "validation_error": "RESET_UNKNOWN_TARGET_TYPE",
                                    "hop_index": hop_index,
                                    "produced_index": produced_index,
                                },
                            )

            # 2. Scope bindings and state tracking per hop
            hop_allowed_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}
            hop_denied_cidrs: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}

            # Three-state key storage: key -> KeyStatus
            hop_principal_keys: Dict[int, Dict[str, KeyStatus]] = {}
            hop_session_keys: Dict[int, Dict[str, KeyStatus]] = {}
            hop_config_keys: Dict[int, Dict[str, KeyStatus]] = {}
            hop_request_keys: Dict[int, Dict[str, KeyStatus]] = {}

            hop_session_bool_domains: Dict[int, Dict[str, Set[bool]]] = {}
            hop_null_assertions: Dict[int, Dict[str, bool]] = {}

            # RESET session keys tracking for AssumeRole boundary carry-over
            reset_session_keys: Dict[int, Dict[str, str]] = {}  # hop_num -> {key: value}

            produced_state: Dict[int, Dict[str, Any]] = {}
            produced_attrs: Dict[int, Dict[str, Any]] = {}

            # RESET conflict detection: track operations per hop/key
            # Conflict rules:
            # - CLEAR + SET on same key/hop → UNKNOWN
            # - CLEAR + RESET on same key/hop → UNKNOWN
            # - SET + RESET on same key/hop → UNKNOWN
            # - RESET + RESET on same key/hop → UNKNOWN
            # - Identical SET + SET → idempotent (allowed)
            hop_operations: Dict[int, Dict[str, List[str]]] = {}  # hop_num -> key -> [operations]
            for hop_index, hop in enumerate(input_data.hops):
                hop_num = hop.hop
                hop_operations[hop_num] = {}
                for produced in hop.produced_context:
                    operation = getattr(produced, "operation", None)
                    key = getattr(produced, "key", None)
                    if operation and key:
                        if key not in hop_operations[hop_num]:
                            hop_operations[hop_num][key] = []
                        hop_operations[hop_num][key].append(operation)

            # Validate conflicts per hop/key
            for hop_num, key_ops in hop_operations.items():
                for key, ops in key_ops.items():
                    op_set = set(ops)
                    # Check for conflicts
                    if "RESET" in op_set:
                        if len(ops) > 1:
                            # RESET conflicts with any other operation on same key
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"RESET conflict on hop {hop_num} for key '{key}': "
                                    f"RESET cannot coexist with other operations ({', '.join(ops)})"
                                ),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata={
                                    "validation_error": "RESET_CONFLICT",
                                    "hop": hop_num,
                                    "key": key,
                                    "operations": ops,
                                },
                            )
                        # Also check for duplicate RESET on same key (should not happen due to len>1 check above)
                    if "CLEAR" in op_set and "SET" in op_set:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return PathEvaluationResult(
                            path_id=input_data.path_id,
                            status=FeasibilityStatus.UNKNOWN,
                            unknown_rationale=(
                                f"CLEAR + SET conflict on hop {hop_num} for key '{key}'"
                            ),
                            solver_duration_ms=elapsed_ms,
                            diagnostic_metadata={
                                "validation_error": "CLEAR_SET_CONFLICT",
                                "hop": hop_num,
                                "key": key,
                            },
                        )
                    # Check for duplicate CLEAR (idempotent, allowed)
                    # Check for duplicate SET (idempotent, allowed)
                    # Note: Multiple SET on same key with different values would be caught later

            # 3. Iterate through hops sequentially
            iteration_count = 0
            for hop_idx, hop in enumerate(input_data.hops, start=1):
                hop_num = hop.hop
                import sys
                print(f"DEBUG HOP START: hop_idx={hop_idx}, hop_num={hop_num}, edge_type={hop.edge_type}, caller_config={hop.caller_config_inputs}", file=sys.stderr)
                hop_principal_keys[hop_num] = {}
                hop_session_keys[hop_num] = {}
                hop_config_keys[hop_num] = {}
                hop_request_keys[hop_num] = {}
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
                        # Standard action continuation: carry principal keys, session keys, request keys, config keys, and session bools
                        hop_principal_keys[hop_num] = {
                            k: v for k, v in hop_principal_keys[prev_hop_num].items()
                        }
                        hop_session_keys[hop_num] = {
                            k: v for k, v in hop_session_keys[prev_hop_num].items()
                        }
                        hop_request_keys[hop_num] = {
                            k: v for k, v in hop_request_keys[prev_hop_num].items()
                        }
                        hop_config_keys[hop_num] = {}  # CONFIG is hop-local, fresh each hop
                        hop_session_bool_domains[hop_num] = {
                            k: v for k, v in hop_session_bool_domains[prev_hop_num].items()
                        }
                    else:
                        # AssumeRole transition boundary:
                        hop_session_keys[hop_num] = {}
                        hop_session_bool_domains[hop_num] = {}
                        hop_request_keys[hop_num] = {}
                        hop_config_keys[hop_num] = {}
                        # Caller principal keys reset (do not survive boundary)
                        hop_principal_keys[hop_num] = {}

                        # Target role attached tags produced in AssumeRole hop become initial principal keys on hop_num
                        for p_key, p_val in produced_state.get(prev_hop_num, {}).items():
                            if p_key.startswith("aws:PrincipalTag/") and isinstance(p_val, str):
                                hop_principal_keys[hop_num][p_key] = make_present(p_val)

                        # Carry over RESET session keys from previous hop (established by RESET on AssumeRole hop)
                        if prev_hop_num in reset_session_keys:
                            for r_key, r_val in reset_session_keys[prev_hop_num].items():
                                hop_session_keys[hop_num][r_key] = make_present(r_val)

                # Apply incoming transition constraints (IDENTITY_DERIVATION, PIVOT_TRANSITION, EQUAL)
                # per spec §3.2: transitions applied BEFORE requirement evaluation
                for trans in input_data.transition_constraints:
                    if trans.to_hop != hop_num:
                        continue
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

                    source_produced = produced_state.get(trans.from_hop, {})
                    if trans.relation_type == "IDENTITY_DERIVATION":
                        derived_value = source_produced.get(trans.variable)
                        if derived_value is None or derived_value == "":
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    "MISSING_IDENTITY_PRODUCTION: IDENTITY_DERIVATION "
                                    f"{trans.from_hop}->{trans.to_hop} has no source-produced "
                                    f"value for {trans.variable!r}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata={
                                    "validation_error": "MISSING_IDENTITY_PRODUCTION",
                                    "transition_index": trans_index,
                                },
                            )
                        # Apply derived value to the appropriate scope store
                        if trans.variable.startswith("aws:PrincipalTag/"):
                            hop_principal_keys[hop_num][trans.variable] = make_present(derived_value)
                        elif trans.variable.startswith("aws:SessionTag/") or trans.variable.startswith("aws:SessionIssuer") or trans.variable == "aws:MultiFactorAuthPresent":
                            hop_session_keys[hop_num][trans.variable] = make_present(derived_value)
                        elif trans.variable.startswith("aws:RequestTag/") or trans.variable == "aws:SourceIp" or trans.variable == "aws:UserAgent" or trans.variable == "aws:CurrentTime":
                            hop_request_keys[hop_num][trans.variable] = make_present(derived_value)
                        elif trans.variable == "sts:ExternalId":
                            hop_config_keys[hop_num][trans.variable] = make_present(derived_value)

                    elif trans.relation_type == "PIVOT_TRANSITION":
                        # PIVOT rebinds SourceIp from network_execution_origin
                        pivot_ip = source_produced.get("network_execution_origin")
                        if pivot_ip is not None and pivot_ip != "":
                            # Apply concrete rebound IP to REQUEST scope
                            hop_request_keys[hop_num]["aws:SourceIp"] = make_present(pivot_ip)
                        # If no produced origin, leave as UNCONSTRAINED for free variable resolution later

                    elif trans.relation_type == "EQUAL" and trans.variable == "aws:SourceIp":
                        # EQUAL linkage for SourceIp - handled later in IP constraint resolution
                        pass

                # Load caller-supplied CONFIG inputs for this hop (if provided)
                if hop.caller_config_inputs:
                    for key, value in hop.caller_config_inputs.items():
                        if isinstance(value, str):
                            # Find the predicate for this key to determine the correct scope
                            pred_scope = None
                            for pred in hop.required_context:
                                if pred.key == key:
                                    pred_scope = pred.scope
                                    break
                            import sys
                            print(f"DEBUG CALLER_CONFIG: hop={hop_num}, key={key}, value={value}, pred_scope={pred_scope}", file=sys.stderr)
                            if pred_scope == ContextScope.SESSION:
                                hop_session_keys[hop_num][key] = make_present(value)
                                print(f"  -> Set in hop_session_keys[{hop_num}]", file=sys.stderr)
                            elif pred_scope == ContextScope.REQUEST:
                                hop_request_keys[hop_num][key] = make_present(value)
                                print(f"  -> Set in hop_request_keys[{hop_num}]", file=sys.stderr)
                            elif pred_scope == ContextScope.CONFIG:
                                hop_config_keys[hop_num][key] = make_present(value)
                                print(f"  -> Set in hop_config_keys[{hop_num}]", file=sys.stderr)
                            elif pred_scope == ContextScope.PRINCIPAL:
                                hop_principal_keys[hop_num][key] = make_present(value)
                                print(f"  -> Set in hop_principal_keys[{hop_num}]", file=sys.stderr)
                            else:
                                # Default to CONFIG for backward compatibility
                                hop_config_keys[hop_num][key] = make_present(value)
                                print(f"  -> Set in hop_config_keys[{hop_num}] (default)", file=sys.stderr)

                # Evaluate required context predicates (PRECONDITIONS) for this hop
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

                        # Check for Null(true) assertion clash with String predicate
                        # Per Decision 9: only clash if key is PRESENT (concrete value).
                        # If key is UNCONSTRAINED, both Null and StringEquals are UNKNOWN.
                        if hop_null_assertions[hop_num].get(pred.key) is True:
                            # Check current key state
                            current_state = KeyState.UNCONSTRAINED
                            for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                          hop_config_keys[hop_num], hop_request_keys[hop_num]):
                                ks = store.get(pred.key)
                                if ks is not None:
                                    current_state = ks.state
                                    break
                            if current_state == KeyState.PRESENT:
                                # Key has concrete value, Null(true) clashes with String predicate
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
                            else:
                                # Key is UNCONSTRAINED or ABSENT: both Null and StringEquals are UNKNOWN
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Null/StringEquals clash on unconstrained key '{pred.key}' on hop {hop_num}: "
                                        f"Cannot verify concrete value"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        req_values = set(pred.values)
                        tag_key = pred.key

                        if scope == ContextScope.PRINCIPAL:
                            target_store = hop_principal_keys[hop_num]
                            scope_desc = "Principal tag"
                        elif scope == ContextScope.SESSION:
                            target_store = hop_session_keys[hop_num]
                            scope_desc = "Session string"
                        elif scope == ContextScope.CONFIG:
                            target_store = hop_config_keys[hop_num]
                            scope_desc = "Config string"
                        elif scope == ContextScope.REQUEST:
                            target_store = hop_request_keys[hop_num]
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

                        existing_status = target_store.get(tag_key)
                        if existing_status is not None and existing_status.state == KeyState.PRESENT:
                            active_vals = {existing_status.value} if existing_status.value is not None else set()
                            overlap = active_vals.intersection(req_values)
                            if not overlap:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"{scope_desc} contradiction on hop {hop_num} ({scope.value} scope) for '{tag_key}': "
                                        f"Active value {existing_status.value} clashes with required {req_values}"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            target_store[tag_key] = make_present(next(iter(overlap)))
                        elif existing_status is not None and existing_status.state == KeyState.ABSENT:
                            # ABSENT + StringEquals -> UNKNOWN (per approved spec)
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"StringEquals on explicitly absent key '{tag_key}' on hop {hop_num}: "
                                    f"ABSENT key cannot satisfy StringEquals requirement"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        else:
                            # UNCONSTRAINED: StringEquals on UNCONSTRAINED is UNKNOWN per Decision 9
                            # Never return SAT merely because a key was not mentioned
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"StringEquals on unconstrained key '{tag_key}' on hop {hop_num}: "
                                    f"Cannot verify equality on never-mentioned key"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

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

                        # Handle tautology and contradiction at the constraint level
                        is_tautology = parsed_bools == {True, False}
                        is_contradiction = len(parsed_bools) == 0  # Empty after parsing would be caught above, but keep for safety

                        # Per Decision 9: Tautology is always satisfied (SAT for this predicate), contradiction is always UNSAT
                        if is_tautology:
                            # Tautology: this predicate is always satisfied, new_domain is {True, False}
                            new_domain = parsed_bools
                        elif is_contradiction:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNSAT,
                                contradiction_rationale=(
                                    f"Bool predicate with no satisfiable values on hop {hop_num} for '{pred.key}'"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        else:
                            # Check for contradiction with existing Bool domain
                            existing_domain = hop_session_bool_domains[hop_num].get(pred.key)
                            if existing_domain is not None:
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
                                new_domain = new_domain
                            else:
                                new_domain = parsed_bools

                        # Check for contradiction with Null assertions
                        if hop_null_assertions[hop_num].get(pred.key) is True:
                            # Per Decision 9: only clash if key is PRESENT (concrete value).
                            # If key is UNCONSTRAINED or ABSENT, both Null and Bool are UNKNOWN.
                            current_state = KeyState.UNCONSTRAINED
                            for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                          hop_config_keys[hop_num], hop_request_keys[hop_num]):
                                ks = store.get(pred.key)
                                if ks is not None:
                                    current_state = ks.state
                                    break
                            if current_state == KeyState.PRESENT:
                                # Key has concrete value, Null(true) clashes with Bool predicate
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
                            else:
                                # Key is UNCONSTRAINED or ABSENT: both Null and Bool are UNKNOWN
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Null/Bool clash on unconstrained key '{pred.key}' on hop {hop_num}: "
                                        f"Cannot verify concrete value"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        # For Bool on UNCONSTRAINED: return UNKNOWN per Decision 9
                        # Check if key is currently UNCONSTRAINED
                        current_state = KeyState.UNCONSTRAINED
                        for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                      hop_config_keys[hop_num], hop_request_keys[hop_num]):
                            ks = store.get(pred.key)
                            if ks is not None:
                                current_state = ks.state
                                break
                        # DEBUG
                        import sys
                        print(f"DEBUG BOOL STATE: hop={hop_num}, pred.key={pred.key}, current_state={current_state}, is_tautology={is_tautology}", file=sys.stderr)
                        if current_state == KeyState.UNCONSTRAINED:
                            # Bool on UNCONSTRAINED is UNKNOWN per Decision 9
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"Bool on unconstrained key '{pred.key}' on hop {hop_num}: "
                                    f"Cannot verify boolean value on unconstrained key"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        elif current_state == KeyState.PRESENT:
                            # Bool on PRESENT: check if the actual value matches the predicate's allowed values
                            actual_bool = False
                            for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                          hop_config_keys[hop_num], hop_request_keys[hop_num]):
                                ks = store.get(pred.key)
                                if ks is not None and ks.state == KeyState.PRESENT and ks.value is not None:
                                    actual_bool = ks.value.lower() in ("true", "1")
                                    break
                            # DEBUG
                            import sys
                            print(f"DEBUG BOOL PRESENT: hop={hop_num}, pred.key={pred.key}, actual_bool={actual_bool}, parsed_bools={parsed_bools}, is_tautology={is_tautology}, current_state={current_state}", file=sys.stderr)
                            # Check if actual value is in the predicate's allowed values
                            if actual_bool not in parsed_bools:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Bool predicate failed on hop {hop_num} for '{pred.key}': "
                                        f"Key has value '{'true' if actual_bool else 'false'}' but predicate requires one of "
                                        f"{'true' if True in parsed_bools else ''}{', ' if True in parsed_bools and False in parsed_bools else ''}{'false' if False in parsed_bools else ''}"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        # For Bool, we record the constraint and continue
                        # Tautology (both true and false) is always SAT
                        # Specific values constrain the key
                        # Contradiction with existing Bool domain handled above

                        hop_session_bool_domains[hop_num][pred.key] = new_domain

                        # Record Bool requirement as PRESENT in session keys (for witness)
                        # Only record specific values, not tautology
                        if not is_tautology:
                            hop_session_keys[hop_num][pred.key] = make_present("true" if True in parsed_bools else "false")

                        # For UNCONSTRAINED keys, we don't return UNKNOWN immediately
                        # Constraints are checked for consistency at the end of hop processing
                        # (handled by post-hop verification)

                    # 3.5 Operator: Null (Commutative conjunction) - Phase 2 corrected semantics
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

                        # Check current key state across all scopes
                        def get_key_state(key: str) -> KeyState:
                            for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                          hop_config_keys[hop_num], hop_request_keys[hop_num]):
                                ks = store.get(key)
                                if ks is not None:
                                    return ks.state
                            if key in hop_session_bool_domains[hop_num]:
                                return KeyState.PRESENT
                            if key == "aws:SourceIp" and hop_num in hop_allowed_cidrs:
                                return KeyState.PRESENT
                            return KeyState.UNCONSTRAINED

                        current_state = get_key_state(pred.key)

                        if null_truth is True:
                            # Null(true): key must be absent
                            if current_state == KeyState.PRESENT:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Null(true) assertion failed on hop {hop_num} for '{pred.key}': "
                                        f"Key is present with concrete value"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            elif current_state == KeyState.ABSENT:
                                # ABSENT satisfies Null(true) - SAT (no action needed)
                                pass
                            else:
                                # UNCONSTRAINED: Null(true) on UNCONSTRAINED is UNKNOWN per Decision 9
                                # Never return UNSAT merely because a key was not mentioned
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Null(true) assertion on hop {hop_num} for '{pred.key}': "
                                        f"Key is unconstrained, cannot verify absence"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                        else:
                            # Null(false): key must be present
                            if current_state == KeyState.PRESENT:
                                # PRESENT satisfies Null(false) - SAT (no action needed)
                                pass
                            elif current_state == KeyState.ABSENT:
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Null(false) assertion failed on hop {hop_num} for '{pred.key}': "
                                        f"Key is explicitly absent"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            else:
                                # UNCONSTRAINED: Null(false) on UNCONSTRAINED is UNKNOWN per Decision 9
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Null(false) assertion on hop {hop_num} for '{pred.key}': "
                                        f"Key is unconstrained, cannot verify presence"
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
                    operation = prod.operation

                    if operation == "SET":
                        produced_state[hop_num][key] = val
                        if prod.attributes:
                            produced_attrs[hop_num][key] = prod.attributes

                        # If this hop is not AssumeRole, produced principal tags update current hop
                        if hop.edge_type != "sts:AssumeRole":
                            if key.startswith("aws:PrincipalTag/") and isinstance(val, str):
                                hop_principal_keys[hop_num][key] = make_present(val)
                        # For other scopes, SET behavior depends on scope
                        scope_val = prod.scope if hasattr(prod, 'scope') and prod.scope else ContextScope.UNKNOWN
                        if scope_val == ContextScope.SESSION and isinstance(val, str):
                            hop_session_keys[hop_num][key] = make_present(val)
                        elif scope_val == ContextScope.REQUEST and isinstance(val, str):
                            hop_request_keys[hop_num][key] = make_present(val)
                        elif scope_val == ContextScope.CONFIG and isinstance(val, str):
                            hop_config_keys[hop_num][key] = make_present(val)

                    elif operation == "CLEAR":
                        # CLEAR marks exactly one key as ABSENT in the outgoing state
                        # Apply to the appropriate scope store
                        scope_val = prod.scope if hasattr(prod, 'scope') and prod.scope else ContextScope.UNKNOWN
                        if scope_val == ContextScope.PRINCIPAL:
                            hop_principal_keys[hop_num][key] = make_absent()
                        elif scope_val == ContextScope.SESSION:
                            hop_session_keys[hop_num][key] = make_absent()
                        elif scope_val == ContextScope.CONFIG:
                            hop_config_keys[hop_num][key] = make_absent()
                        elif scope_val == ContextScope.REQUEST:
                            hop_request_keys[hop_num][key] = make_absent()
                        else:
                            # Unknown scope - still mark as ABSENT in a generic store if needed
                            pass
                        # CLEAR does not add to produced_state (key is absent for successors)

                    elif operation == "RESET":
                        # RESET establishes a new generation for the targeted context
                        # This must be integrated at the correct transition position per §3.2
                        # Validation was done earlier; here we apply the state transition
                        scope_val = prod.scope if hasattr(prod, 'scope') and prod.scope else ContextScope.UNKNOWN
                        reset_metadata = prod.attributes.get("reset_metadata") if prod.attributes else None
                        
                        if not reset_metadata:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"RESET operation missing reset_metadata: hop {hop_num}, key {key}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        
                        # Apply RESET based on target type
                        if reset_metadata.target_type == TargetType.KEY:
                            result = self._apply_key_reset(
                                hop_num=hop_num,
                                key=reset_metadata.target_key,
                                scope=reset_metadata.target_scope,
                                initializer_source=reset_metadata.initializer_source,
                                generation=reset_metadata.generation_boundary,
                                provenance=reset_metadata.provenance,
                                diag=diag,
                                hop_idx=hop_idx,
                                start_time=start_time,
                                reset_session_keys=reset_session_keys,
                            )
                            if result:
                                return result
                        elif reset_metadata.target_type == TargetType.SCOPE:
                            result = self._apply_scope_reset(
                                hop_num=hop_num,
                                scope=reset_metadata.target_scope,
                                initializer_source=reset_metadata.initializer_source,
                                generation=reset_metadata.generation_boundary,
                                provenance=reset_metadata.provenance,
                                diag=diag,
                                hop_idx=hop_idx,
                                start_time=start_time,
                                reset_session_keys=reset_session_keys,
                            )
                            if result:
                                return result
                        else:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"Unknown RESET target_type: {reset_metadata.target_type}"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )

                # Post-hop commutativity verification for Null constraints
                for null_k, is_null in hop_null_assertions[hop_num].items():
                    if is_null is True:
                        # Null(true): key must be absent
                        has_pos = False
                        has_absent = False
                        for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                      hop_config_keys[hop_num], hop_request_keys[hop_num]):
                            ks = store.get(null_k)
                            if ks is not None:
                                if ks.state == KeyState.PRESENT:
                                    has_pos = True
                                    break
                                elif ks.state == KeyState.ABSENT:
                                    has_absent = True
                        if not has_pos and null_k in hop_session_bool_domains[hop_num]:
                            has_pos = True
                        if not has_pos and null_k == "aws:SourceIp" and hop_num in hop_allowed_cidrs:
                            has_pos = True
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
                        elif not has_absent:
                            # Key is UNCONSTRAINED in all stores - Null(true) on UNCONSTRAINED is UNKNOWN (Decision 9)
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return PathEvaluationResult(
                                path_id=input_data.path_id,
                                status=FeasibilityStatus.UNKNOWN,
                                unknown_rationale=(
                                    f"Null(true) assertion on hop {hop_num} for '{null_k}': "
                                    f"Key is unconstrained, cannot verify absence"
                                ),
                                evaluated_hops=hop_idx,
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        # If has_absent is True and not has_pos, Null(true) is SAT (explicit ABSENT)
                    else:
                        # is_null is False: Null(false) - key must be present
                        has_pos = False
                        for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                      hop_config_keys[hop_num], hop_request_keys[hop_num]):
                            ks = store.get(null_k)
                            if ks is not None and ks.state == KeyState.PRESENT:
                                has_pos = True
                                break
                        if not has_pos and null_k in hop_session_bool_domains[hop_num]:
                            has_pos = True
                        if not has_pos and null_k == "aws:SourceIp" and hop_num in hop_allowed_cidrs:
                            has_pos = True
                        if not has_pos:
                            # Check if key is explicitly ABSENT
                            has_absent = False
                            for store in (hop_principal_keys[hop_num], hop_session_keys[hop_num],
                                          hop_config_keys[hop_num], hop_request_keys[hop_num]):
                                ks = store.get(null_k)
                                if ks is not None and ks.state == KeyState.ABSENT:
                                    has_absent = True
                                    break
                            if has_absent:
                                # ABSENT + Null(false) = UNSAT
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Null(false) assertion failed on hop {hop_num} for '{null_k}': "
                                        f"Key is explicitly absent"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            else:
                                # Key is UNCONSTRAINED in all stores - Null(false) on UNCONSTRAINED is UNKNOWN (Decision 9)
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNKNOWN,
                                    unknown_rationale=(
                                        f"Null(false) assertion on hop {hop_num} for '{null_k}': "
                                        f"Key is unconstrained, cannot verify presence"
                                    ),
                                    evaluated_hops=hop_idx,
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

            static_origin = bool(input_data.scenario_assumptions.get("static_origin_assumption", False))

            pivot_rebound_hops: Set[int] = set()
            # Pivot hops whose rebound origin was concretely produced and
            # parsed. Their request-scope IP constraints (allowed AND denied)
            # are discharged against that concrete IP in this phase, so §5
            # must not re-resolve them as free variables (doing so is unsound
            # in both directions) nor drop them (which loses contradictions).
            pivot_rebound_active: Set[int] = set()
            pivot_rebound_from: Dict[int, int] = {}
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

                        # Denied CIDRs of the rebound target constrain the concrete
                        # rebound origin exactly as its allowed CIDRs do: the origin
                        # is rebound, not a free variable. A rebound IP inside a
                        # denied range is a contradiction in every evaluation branch,
                        # independent of static origin or EQUAL linkage (O3 monotonic
                        # UNSAT: this check must not depend on which §5 branch runs).
                        for denied_net in hop_denied_cidrs.get(trans.to_hop, []):
                            if denied_net.version != rebound_net.version:
                                continue
                            if rebound_net.subnet_of(denied_net):
                                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                                return PathEvaluationResult(
                                    path_id=input_data.path_id,
                                    status=FeasibilityStatus.UNSAT,
                                    contradiction_rationale=(
                                        f"Network pivot contradiction on hop {trans.to_hop}: "
                                        f"Pivot IP {rebound_ip} is inside denied CIDR {denied_net}"
                                    ),
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )

                        pivot_rebound_active.add(trans.to_hop)
                        pivot_rebound_from[trans.to_hop] = trans.from_hop

                elif trans.relation_type == "IDENTITY_DERIVATION":
                    tag_var = trans.variable
                    prod_from = produced_state.get(trans.from_hop, {})
                    produced_tag = prod_from.get(tag_var)

                    req_status = hop_principal_keys[trans.to_hop].get(tag_var)
                    req_tags_target = {req_status.value} if req_status and req_status.state == KeyState.PRESENT and req_status.value else set()
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
            static_origin = bool(input_data.scenario_assumptions.get("static_origin_assumption", False))
            equal_ip_pairs = [
                (t.from_hop, t.to_hop)
                for t in input_data.transition_constraints
                if t.relation_type == "EQUAL" and t.variable == "aws:SourceIp"
            ]

            # Hops whose request-scope IP is linked to other hops' IPs, mapped to
            # the surviving subnets of their linkage component. Under the static
            # origin assumption all non-pivot IP hops form one component; under
            # EQUAL transitions exactly the EQUAL-linked pairs form components
            # (CCPF_FORMAL_DESIGN_GATE.md §6.2: request-scoped variables remain
            # step-indexed and independent unless an explicit continuity rule or
            # scenario assumption mandates identity).
            linked_surviving: Dict[int, List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]] = {}

            if static_origin or equal_ip_pairs:
                hops_with_ip = [
                    h.hop for h in input_data.hops
                    if (h.hop in hop_allowed_cidrs or h.hop in hop_denied_cidrs)
                    and h.hop not in pivot_rebound_hops
                ]

                if static_origin:
                    components: List[List[int]] = [list(hops_with_ip)] if hops_with_ip else []
                else:
                    # Union-find over EQUAL-linked pairs; unlinked hops are singletons.
                    parent: Dict[int, int] = {h: h for h in hops_with_ip}

                    def _find(x: int) -> int:
                        while parent[x] != x:
                            parent[x] = parent[parent[x]]
                            x = parent[x]
                        return x

                    for a, b in equal_ip_pairs:
                        if a in parent and b in parent:
                            ra, rb = _find(a), _find(b)
                            if ra != rb:
                                parent[ra] = rb
                    comp_map: Dict[int, List[int]] = {}
                    for h in hops_with_ip:
                        comp_map.setdefault(_find(h), []).append(h)
                    components = list(comp_map.values())

                for component in components:
                    if len(component) == 1 and not static_origin:
                        # Unlinked singleton: independent origin, resolved per hop below.
                        continue

                    # Accumulate positive allowed subnets across the component
                    comp_allowed_hops = [h for h in component if h in hop_allowed_cidrs]
                    if comp_allowed_hops:
                        first_hop_with_allowed = comp_allowed_hops[0]
                        accumulated = hop_allowed_cidrs[first_hop_with_allowed]
                        for next_hop in comp_allowed_hops[1:]:
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
                                        f"Contradictory persistent context under linked origin "
                                        f"(static origin or EQUAL SourceIp transitions): "
                                        f"CIDRs on hop {first_hop_with_allowed} ({hop_allowed_cidrs[first_hop_with_allowed]}) "
                                        f"are disjoint from hop {next_hop} ({next_allowed})"
                                    ),
                                    evaluated_hops=len(input_data.hops),
                                    solver_duration_ms=elapsed_ms,
                                    diagnostic_metadata=diag,
                                )
                            accumulated = surviving
                    else:
                        # Only NotIpAddress constraints in this component: default to universe
                        all_denied = [d for h in component for d in hop_denied_cidrs.get(h, [])]
                        def_ver = all_denied[0].version if all_denied else 4
                        accumulated = [ipaddress.ip_network("0.0.0.0/0" if def_ver == 4 else "::/0")]

                    # Apply the component's denied CIDRs to its accumulated allowed subnets
                    comp_denied: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
                    for h in component:
                        comp_denied.extend(hop_denied_cidrs.get(h, []))

                    if comp_denied and accumulated:
                        surviving_after_denial, mixed_err = subtract_cidr_lists(accumulated, comp_denied)
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
                                    f"Allowed CIDRs {accumulated} fully denied by {comp_denied} "
                                    f"under linked origin (static origin or EQUAL SourceIp transitions)"
                                ),
                                evaluated_hops=len(input_data.hops),
                                solver_duration_ms=elapsed_ms,
                                diagnostic_metadata=diag,
                            )
                        accumulated = surviving_after_denial

                    for h in component:
                        linked_surviving[h] = accumulated

            # Independent per-hop IP resolution for every IP-constrained hop that
            # is not part of a linked component. Actively rebound pivot hops are
            # excluded in EVERY branch: their origin is the concrete rebound IP
            # and their allowed/denied constraints were already discharged
            # against that IP in phase 4. Pivot hops without a concrete rebound
            # retain free-variable semantics and are resolved here, so their
            # constraints are never silently dropped.
            all_hops_with_ip = set(hop_allowed_cidrs.keys()).union(hop_denied_cidrs.keys())
            for h_num in all_hops_with_ip:
                if h_num in linked_surviving:
                    continue
                if h_num in pivot_rebound_active:
                    continue
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
            if linked_surviving:
                # Linked-origin witness: each linked hop takes the witness IP of
                # its own linkage component. Under static origin there is exactly
                # one component, so every non-pivot hop shares one origin IP
                # (including hops without explicit IP constraints — historical
                # static-origin behavior).
                for h_num in input_data.hops:
                    if h_num.hop in pivot_rebound_hops:
                        continue
                    if h_num.hop in linked_surviving and linked_surviving[h_num.hop]:
                        chosen_ip = select_witness_ip(linked_surviving[h_num.hop][0])
                    elif static_origin:
                        chosen_ip = next(
                            (select_witness_ip(subnets[0]) for subnets in linked_surviving.values() if subnets),
                            None,
                        )
                        if chosen_ip is None:
                            continue
                    else:
                        continue
                    witness[f"hop_{h_num.hop}_SourceIp"] = chosen_ip
                    if "aws:SourceIp" not in witness:
                        witness["aws:SourceIp"] = chosen_ip
            # Per-hop witness for independently resolved (unlinked) hops and for
            # the non-linked case (covers the historical else branch).
            for hop_num, allowed_list in hop_allowed_cidrs.items():
                if f"hop_{hop_num}_SourceIp" in witness:
                    continue
                if allowed_list:
                    chosen_subnet = allowed_list[0]
                    chosen_ip = select_witness_ip(chosen_subnet)
                    witness[f"hop_{hop_num}_SourceIp"] = chosen_ip
                    if "aws:SourceIp" not in witness:
                        witness["aws:SourceIp"] = chosen_ip

            # Re-bound IP for pivot transitions: use the recorded transition
            # source hop rather than assuming p_hop - 1.
            for p_hop in pivot_rebound_active:
                src_hop = pivot_rebound_from.get(p_hop, p_hop - 1)
                rebound_val = produced_state.get(src_hop, {}).get("network_execution_origin")
                if rebound_val:
                    witness[f"hop_{p_hop}_SourceIp"] = rebound_val

            # Principal tags witness
            for hop_num, tags in hop_principal_keys.items():
                for tag_key, tag_status in tags.items():
                    if tag_status.state == KeyState.PRESENT and tag_status.value:
                        chosen_val = tag_status.value
                        witness[f"hop_{hop_num}_{tag_key}"] = chosen_val
                        witness[tag_key] = chosen_val

            # Session strings witness
            for hop_num, s_keys in hop_session_keys.items():
                for s_key, s_status in s_keys.items():
                    if s_status.state == KeyState.PRESENT and s_status.value:
                        chosen_val = s_status.value
                        witness[f"hop_{hop_num}_{s_key}"] = chosen_val
                        witness[s_key] = chosen_val

            # Config strings witness
            for hop_num, c_keys in hop_config_keys.items():
                for c_key, c_status in c_keys.items():
                    if c_status.state == KeyState.PRESENT and c_status.value:
                        chosen_val = c_status.value
                        witness[f"hop_{hop_num}_{c_key}"] = chosen_val
                        witness[c_key] = chosen_val

            # Request strings witness
            for hop_num, r_keys in hop_request_keys.items():
                for r_key, r_status in r_keys.items():
                    if r_status.state == KeyState.PRESENT and r_status.value:
                        chosen_val = r_status.value
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

    # =========================================================================
    # RESET Helper Methods
    # =========================================================================

    def _apply_key_reset(
        self,
        hop_num: int,
        key: str,
        scope: ContextScope,
        initializer_source: InitializerSource,
        generation: int,
        provenance: Dict[str, Any],
        diag: Dict[str, Any],
        hop_idx: int,
        start_time: float,
        reset_session_keys: Dict[int, Dict[str, str]],
    ) -> Optional[PathEvaluationResult]:
        """Apply a KEY-level RESET for a single key with generation tracking."""
        # Get the appropriate scope store
        if scope == ContextScope.PRINCIPAL:
            store = hop_principal_keys[hop_num]
        elif scope == ContextScope.SESSION:
            store = hop_session_keys[hop_num]
        elif scope == ContextScope.REQUEST:
            store = hop_request_keys[hop_num]
        elif scope == ContextScope.CONFIG:
            store = hop_config_keys[hop_num]
        else:
            return None  # Unknown scope - handled as UNKNOWN by caller
        
        # Check if we have the initializer value from provenance
        initializer_value = provenance.get(key)
        
        if initializer_value is not None and isinstance(initializer_value, str):
            # Initialize with the provided value - new generation
            store[key] = make_present(initializer_value)
            # Record generation info in diag
            if "reset_generations" not in diag:
                diag["reset_generations"] = {}
            diag["reset_generations"][f"hop_{hop_num}_{key}"] = {
                "generation": generation,
                "initializer_source": initializer_source.value,
                "provenance": provenance,
                "is_reset": True,
            }
            # Track RESET session keys for AssumeRole boundary carry-over
            if scope == ContextScope.SESSION:
                if hop_num not in reset_session_keys:
                    reset_session_keys[hop_num] = {}
                reset_session_keys[hop_num][key] = initializer_value
        else:
            # Missing initializer value - return UNKNOWN
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return PathEvaluationResult(
                path_id=input_data.path_id if 'input_data' in dir(self) else "unknown",
                status=FeasibilityStatus.UNKNOWN,
                unknown_rationale=(
                    f"RESET missing initializer value for key '{key}' from source '{initializer_source.value}'"
                ),
                evaluated_hops=hop_idx,
                solver_duration_ms=elapsed_ms,
                diagnostic_metadata=diag,
            )
        
        # Record RESET provenance in diagnostic metadata
        if "reset_operations" not in diag:
            diag["reset_operations"] = []
        diag["reset_operations"].append({
            "target_type": "key",
            "key": key,
            "scope": scope.value,
            "generation": generation,
            "initializer_source": initializer_source.value,
            "provenance": provenance,
            "hop": hop_num,
        })
        
        return None  # Success

    def _apply_scope_reset(
        self,
        hop_num: int,
        scope: ContextScope,
        initializer_source: InitializerSource,
        generation: int,
        provenance: Dict[str, Any],
        diag: Dict[str, Any],
        hop_idx: int,
        start_time: float,
        reset_session_keys: Dict[int, Dict[str, str]],
    ) -> Optional[PathEvaluationResult]:
        """Apply a SCOPE-level RESET for all registered keys in a scope."""
        # Get all registered keys for this scope
        registered_keys = get_scope_registered_keys(scope)
        
        # Check completeness: all keys must have initializer values
        for key in registered_keys:
            if key not in provenance or not isinstance(provenance.get(key), str):
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return PathEvaluationResult(
                    path_id=input_data.path_id if 'input_data' in dir(self) else "unknown",
                    status=FeasibilityStatus.UNKNOWN,
                    unknown_rationale=(
                        f"SCOPE-level RESET incomplete: missing initializer for key '{key}' "
                        f"in scope '{scope.value}'"
                    ),
                    evaluated_hops=hop_idx,
                    solver_duration_ms=elapsed_ms,
                    diagnostic_metadata=diag,
                )
        
        # Apply RESET to all keys
        for key in registered_keys:
            result = self._apply_key_reset(
                hop_num=hop_num,
                key=key,
                scope=scope,
                initializer_source=initializer_source,
                generation=generation,
                provenance=provenance,
                diag=diag,
                hop_idx=hop_idx,
                start_time=start_time,
                reset_session_keys=reset_session_keys,
            )
            if result:
                return result  # Error from _apply_key_reset
        
        return None  # Success


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
            scope_str = pc.get("scope", "unknown").lower()
            try:
                scope_enum = ContextScope(scope_str)
            except ValueError:
                scope_enum = ContextScope.UNKNOWN
            produced_mods.append(
                ProducedStateModification(
                    key=pc.get("key", ""),
                    operation=pc.get("operation", "SET"),
                    value=pc.get("value", ""),
                    scope=scope_enum,
                    attributes={k: v for k, v in pc.items() if k not in ("key", "operation", "value", "scope")},
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
