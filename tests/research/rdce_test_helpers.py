"""RDCE test helper utilities for CCPF research tests.

Provides convenience builders and assertion helpers used across
tests/research/test_rdce.py and tests/research/test_semantic_validation.py.

These utilities are strictly read-only with respect to production code and
do not import from arf_rt/.

Branch: temporal-context-dev
"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Import the RDCE public API
# ---------------------------------------------------------------------------
import sys
import os

# Ensure the workspace root is on sys.path so tests can import research/.
_workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from research.ccpf.rdce import (
    ContextPredicate,
    ContextScope,
    FeasibilityStatus,
    HopContextSpec,
    PathContextBundle,
    ProducedStateModification,
    RDCEResult,
    TransitionRelation,
    evaluate_path_feasibility,
)


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def make_hop(
    hop: int,
    edge_type: str = "iam:PassRole",
    src: str = "node-src",
    dst: str = "node-dst",
    required: Optional[List[ContextPredicate]] = None,
    produced: Optional[List[ProducedStateModification]] = None,
) -> HopContextSpec:
    """Construct a HopContextSpec with sensible defaults."""
    return HopContextSpec(
        hop=hop,
        edge_type=edge_type,
        src_node_id=src,
        dst_node_id=dst,
        required_context=required or [],
        produced_context=produced or [],
    )


def make_ip_pred(
    operator: str,
    values: List[str],
    key: str = "aws:SourceIp",
) -> ContextPredicate:
    """Build an IP-address ContextPredicate."""
    return ContextPredicate(
        key=key,
        operator=operator,
        values=values,
        scope=ContextScope.REQUEST,
    )


def make_bool_pred(
    values: List[str],
    key: str = "aws:MultiFactorAuthPresent",
) -> ContextPredicate:
    """Build a Bool ContextPredicate."""
    return ContextPredicate(
        key=key,
        operator="Bool",
        values=values,
        scope=ContextScope.SESSION,
    )


def make_null_pred(
    null_value: str,
    key: str = "aws:PrincipalTag/env",
) -> ContextPredicate:
    """Build a Null ContextPredicate. null_value is 'true' or 'false'."""
    return ContextPredicate(
        key=key,
        operator="Null",
        values=[null_value],
        scope=ContextScope.PRINCIPAL,
    )


def make_string_pred(
    values: List[str],
    key: str = "aws:PrincipalTag/team",
    scope: ContextScope = ContextScope.SESSION,
    operator: str = "StringEquals",
) -> ContextPredicate:
    """Build a StringEquals ContextPredicate."""
    return ContextPredicate(
        key=key,
        operator=operator,
        values=values,
        scope=scope,
    )


def make_bundle(
    hops: List[HopContextSpec],
    path_id: str = "test-path",
    transitions: Optional[List[TransitionRelation]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> PathContextBundle:
    """Wrap hops into a PathContextBundle."""
    return PathContextBundle(
        path_id=path_id,
        hops=hops,
        transitions=transitions or [],
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def assert_sat(result: RDCEResult, msg: str = "") -> None:
    """Assert the result is SAT and has a non-empty witness."""
    assert result.status == FeasibilityStatus.SAT, (
        f"Expected SAT, got {result.status}. {msg}\n"
        f"  rationale: {result.unknown_rationale}\n"
        f"  clash:     {result.clash_proof}"
    )
    assert result.witness is not None, f"SAT result must carry a witness. {msg}"


def assert_unsat(result: RDCEResult, msg: str = "") -> None:
    """Assert the result is UNSAT and has a clash proof."""
    assert result.status == FeasibilityStatus.UNSAT, (
        f"Expected UNSAT, got {result.status}. {msg}\n"
        f"  witness:   {result.witness}\n"
        f"  rationale: {result.unknown_rationale}"
    )
    assert result.clash_proof, f"UNSAT result must carry a clash_proof. {msg}"


def assert_unknown(result: RDCEResult, msg: str = "") -> None:
    """Assert the result is UNKNOWN and has a rationale."""
    assert result.status == FeasibilityStatus.UNKNOWN, (
        f"Expected UNKNOWN, got {result.status}. {msg}\n"
        f"  witness:     {result.witness}\n"
        f"  clash_proof: {result.clash_proof}"
    )
    assert result.unknown_rationale, f"UNKNOWN result must carry a rationale. {msg}"


def assert_witness_in_cidr(result: RDCEResult, cidr: str) -> None:
    """Assert the SAT witness IP is contained within the given CIDR."""
    assert result.witness is not None, "No witness to check."
    network = ipaddress.ip_network(cidr, strict=False)
    witness_ip_str = result.witness.get("aws:SourceIp")
    assert witness_ip_str, f"Witness has no aws:SourceIp. witness={result.witness}"
    witness_ip = ipaddress.ip_address(witness_ip_str)
    assert witness_ip in network, (
        f"Witness IP {witness_ip} is not in allowed CIDR {cidr}"
    )


def assert_witness_not_in_cidr(result: RDCEResult, cidr: str) -> None:
    """Assert the SAT witness IP is NOT contained within the given CIDR."""
    assert result.witness is not None, "No witness to check."
    network = ipaddress.ip_network(cidr, strict=False)
    witness_ip_str = result.witness.get("aws:SourceIp")
    assert witness_ip_str, f"Witness has no aws:SourceIp. witness={result.witness}"
    witness_ip = ipaddress.ip_address(witness_ip_str)
    assert witness_ip not in network, (
        f"Witness IP {witness_ip} is incorrectly inside forbidden CIDR {cidr}"
    )


def assert_witness_bool(result: RDCEResult, key: str, expected: str) -> None:
    """Assert the SAT witness Bool value for the given key."""
    assert result.witness is not None, "No witness to check."
    val = result.witness.get(key)
    assert val is not None, f"Witness has no key {key!r}. witness={result.witness}"
    assert str(val).lower() == expected.lower(), (
        f"Witness key {key!r}: expected {expected!r}, got {val!r}"
    )
