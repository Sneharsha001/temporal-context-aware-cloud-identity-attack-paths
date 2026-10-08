"""Trust policy condition extraction (Session 12B).

Parses IAM role trust policies and detects condition keys that
restrict who can assume the role. Each detected condition creates
a TRUST_CONDITION constraint linked to every edge targeting that role.

Detects:
    sts:ExternalId       — cross-account assumption requires shared secret
    aws:SourceIp         — IP restriction on assumption
    aws:SourceVpc        — VPC restriction
    aws:SourceVpce       — VPC endpoint restriction
    aws:PrincipalOrgID   — org membership restriction
    aws:PrincipalOrgPaths — org path restriction
    aws:PrincipalTag/*   — tag-based restriction
    sts:RoleSessionName  — session name restriction
    aws:MultiFactorAuth* — MFA requirements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Condition keys that indicate meaningful trust restrictions
_TRUST_CONDITION_KEYS = {
    "sts:externalid": "EXTERNAL_ID",
    "aws:sourceip": "SOURCE_IP",
    "aws:sourcevpc": "SOURCE_VPC",
    "aws:sourcevpce": "SOURCE_VPCE",
    "aws:principalorgid": "ORG_MEMBERSHIP",
    "aws:principalorgpaths": "ORG_PATH",
    "aws:multifactorauthpresent": "MFA_REQUIRED",
    "aws:multifactorauthage": "MFA_AGE",
    "sts:rolesessionname": "SESSION_NAME",
}

# Prefix matches for tag-based conditions
_TAG_PREFIXES = [
    "aws:principaltag/",
    "aws:requesttag/",
    "aws:tagkeys",
]


@dataclass(frozen=True)
class TrustCondition:
    """A trust condition detected in a role's trust policy."""

    role_arn: str
    condition_type: str  # EXTERNAL_ID, SOURCE_IP, ORG_MEMBERSHIP, etc.
    condition_key: str   # the actual IAM condition key
    condition_operator: str  # StringEquals, IpAddress, etc.
    values: list[str]    # the condition values


def parse_trust_conditions(
    role_arn: str, trust_doc: dict
) -> list[TrustCondition]:
    """Extract meaningful conditions from a trust policy.

    Args:
        role_arn: The role's ARN.
        trust_doc: The trust policy document (AssumeRolePolicyDocument).

    Returns:
        List of TrustCondition objects found.
    """
    if not isinstance(trust_doc, dict):
        return []

    statements = trust_doc.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    results: list[TrustCondition] = []

    for stmt in statements:
        if not isinstance(stmt, dict):
            continue

        # Only look at Allow statements (these are trust grants with conditions)
        if stmt.get("Effect") != "Allow":
            continue

        condition = stmt.get("Condition", {})
        if not isinstance(condition, dict):
            continue

        for operator, key_values in condition.items():
            if not isinstance(key_values, dict):
                continue

            for key, values in key_values.items():
                ctype = _classify_condition_key(key)
                if ctype is None:
                    continue

                # Normalize values to list
                if isinstance(values, str):
                    values = [values]
                elif isinstance(values, bool):
                    values = [str(values).lower()]
                elif not isinstance(values, list):
                    values = [str(values)]

                results.append(
                    TrustCondition(
                        role_arn=role_arn,
                        condition_type=ctype,
                        condition_key=key,
                        condition_operator=operator,
                        values=[str(v) for v in values],
                    )
                )

    return results


def _classify_condition_key(key: str) -> str | None:
    """Classify an IAM condition key into a trust condition type.

    Returns None if the key is not a meaningful trust restriction.
    """
    lower = key.lower()

    # Exact matches
    if lower in _TRUST_CONDITION_KEYS:
        return _TRUST_CONDITION_KEYS[lower]

    # Tag-based conditions
    for prefix in _TAG_PREFIXES:
        if lower.startswith(prefix):
            return "TAG_CONDITION"

    return None


def resolve_trust_constraints(
    trust_policies: dict[str, dict],
    edges: list[dict],
    confidence_q: int = 800,
) -> tuple[list[dict], list[dict], list[str]]:
    """Create TRUST_CONDITION constraints for edges targeting conditioned roles.

    For each role with trust conditions, creates a constraint and links it
    to every edge whose destination is that role.

    Args:
        trust_policies: {role_arn: trust_policy_document}
        edges: ARF-RT format edges.
        confidence_q: Confidence for auto-derived constraints.

    Returns:
        (constraints, edge_constraints, warnings)
    """
    constraints: dict[str, dict] = {}
    edge_constraints: list[dict] = []
    warnings: list[str] = []

    # Build: role_arn → [TrustCondition, ...]
    role_conditions: dict[str, list[TrustCondition]] = {}
    for role_arn, trust_doc in trust_policies.items():
        conditions = parse_trust_conditions(role_arn, trust_doc)
        if conditions:
            role_conditions[role_arn] = conditions

    if not role_conditions:
        return [], [], []

    # For each edge targeting a conditioned role, create linkages
    for edge in edges:
        dst_arn = edge.get("dst", {}).get("provider_id", "")
        if dst_arn not in role_conditions:
            continue

        for cond in role_conditions[dst_arn]:
            # Create constraint (dedupe by role + condition type)
            ckey = f"trust|{dst_arn}|{cond.condition_type}"
            if ckey not in constraints:
                constraints[ckey] = {
                    "provider": "aws",
                    "constraint_type": "TRUST_CONDITION",
                    "scope_type": "ROLE",
                    "scope_id": dst_arn,
                    "region": "-",
                    "properties": {
                        "condition_type": cond.condition_type,
                        "condition_key": cond.condition_key,
                        "condition_operator": cond.condition_operator,
                        "required_values": cond.values,
                    },
                    "status": "ACTIVE",
                    "validation_status": "UNVALIDATED",
                    "confidence_q": confidence_q,
                }

            # Create edge_constraint linkage
            edge_ref = {
                "edge_type": edge["edge_type"],
                "src": edge["src"],
                "dst": edge["dst"],
                "region": edge.get("region", "-"),
            }
            constraint_ref = {
                "provider": "aws",
                "constraint_type": "TRUST_CONDITION",
                "scope_type": "ROLE",
                "scope_id": dst_arn,
                "region": "-",
                "properties": constraints[ckey]["properties"],
            }
            edge_constraints.append({
                "edge_ref": edge_ref,
                "constraint_ref": constraint_ref,
            })

    if constraints:
        logger.info(
            "Resolved %d trust conditions → %d edge-constraint linkages",
            len(constraints),
            len(edge_constraints),
        )

    return list(constraints.values()), edge_constraints, warnings
