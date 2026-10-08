"""AWS Organizations constraint resolution (Session 12B).

Resolves SCP → edge linkages automatically from:
  1. OU hierarchy (which accounts are in which OUs)
  2. SCP attachments (which SCPs are attached to which OUs/accounts)
  3. SCP policy documents (what actions each SCP denies)

For each edge in the graph, walks the source principal's account up
the OU ancestor chain, checks if any attached SCP explicitly denies
the edge's action, and creates the edge-constraint linkage.

Conservative: if we can't parse an SCP (conditions, NotAction, complex
resource patterns), we don't create a constraint. False negatives
(paths stay) are safe; false positives (paths disappear) are dangerous.
"""

from __future__ import annotations

import fnmatch
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arf_rt.adapters.arn import extract_account_id
from arf_rt.util.canon import ARFValidationError

logger = logging.getLogger(__name__)


# ===================================================================
# Data model for AWS Organizations
# ===================================================================


@dataclass
class OUNode:
    """An OU in the Organizations hierarchy."""

    ou_id: str
    name: str
    parent_id: str  # parent OU ID or root ID


@dataclass
class SCPAttachment:
    """An SCP attached to a target (OU or account)."""

    policy_id: str
    target_id: str  # OU ID or account ID
    target_type: str  # "OU" or "ACCOUNT"


@dataclass
class SCPPolicy:
    """An SCP policy document."""

    policy_id: str
    name: str
    document: dict  # IAM-style policy document


@dataclass
class DeniedAction:
    """An action denied by an SCP, with provenance."""

    action_pattern: str  # exact action or glob (e.g. "sts:*")
    scp_id: str
    scp_name: str
    attached_to: str  # OU/account where the SCP is attached
    has_conditions: bool  # True if the Deny statement has Condition keys


@dataclass
class OrgStructure:
    """Parsed AWS Organizations hierarchy."""

    org_id: str
    root_id: str
    ous: dict[str, OUNode]         # ou_id → OUNode
    accounts: dict[str, str]       # account_id → parent ou_id
    scp_attachments: list[SCPAttachment]
    scp_policies: dict[str, SCPPolicy]  # policy_id → SCPPolicy

    # Pre-computed
    _scp_by_target: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Index: target_id → [policy_id, ...]
        self._scp_by_target = {}
        for att in self.scp_attachments:
            self._scp_by_target.setdefault(att.target_id, []).append(
                att.policy_id
            )


def load_org_structure(path: str | Path) -> OrgStructure:
    """Load AWS Organizations structure from JSON.

    Expected format:
    {
      "org_id": "o-xxx",
      "root_id": "r-xxx",
      "ous": [
        {"ou_id": "ou-xxx", "name": "Production", "parent_id": "r-xxx"},
        ...
      ],
      "accounts": [
        {"account_id": "123456789012", "parent_id": "ou-xxx"},
        ...
      ],
      "scp_attachments": [
        {"policy_id": "p-xxx", "target_id": "ou-xxx", "target_type": "OU"},
        ...
      ],
      "scp_policies": [
        {"policy_id": "p-xxx", "name": "DenyAssumeRole", "document": {...}},
        ...
      ]
    }
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    ous = {}
    for ou in data.get("ous", []):
        ous[ou["ou_id"]] = OUNode(
            ou_id=ou["ou_id"],
            name=ou["name"],
            parent_id=ou["parent_id"],
        )

    accounts = {}
    for acc in data.get("accounts", []):
        accounts[acc["account_id"]] = acc["parent_id"]

    attachments = [
        SCPAttachment(
            policy_id=a["policy_id"],
            target_id=a["target_id"],
            target_type=a.get("target_type", "OU"),
        )
        for a in data.get("scp_attachments", [])
    ]

    policies = {}
    for p in data.get("scp_policies", []):
        policies[p["policy_id"]] = SCPPolicy(
            policy_id=p["policy_id"],
            name=p["name"],
            document=p["document"],
        )

    return OrgStructure(
        org_id=data.get("org_id", ""),
        root_id=data.get("root_id", ""),
        ous=ous,
        accounts=accounts,
        scp_attachments=attachments,
        scp_policies=policies,
    )


# ===================================================================
# OU hierarchy traversal
# ===================================================================


def account_ancestors(org: OrgStructure, account_id: str) -> list[str]:
    """Return the OU chain from account up to root (inclusive).

    Returns [parent_ou, grandparent_ou, ..., root_id].
    If account is not found, returns empty list.
    """
    if account_id not in org.accounts:
        return []

    chain: list[str] = []
    current = org.accounts[account_id]
    seen: set[str] = set()

    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        if current == org.root_id:
            break
        if current in org.ous:
            current = org.ous[current].parent_id
        else:
            break

    return chain


def scps_for_account(
    org: OrgStructure, account_id: str
) -> list[tuple[str, SCPPolicy]]:
    """Return all SCPs that apply to an account.

    Walks ancestor chain. An SCP attached to ANY ancestor applies.
    Also checks SCPs attached directly to the account.

    Returns: [(attached_target_id, SCPPolicy), ...]
    """
    result: list[tuple[str, SCPPolicy]] = []

    # SCPs attached directly to the account
    for pid in org._scp_by_target.get(account_id, []):
        if pid in org.scp_policies:
            result.append((account_id, org.scp_policies[pid]))

    # SCPs attached to ancestor OUs
    for ancestor_id in account_ancestors(org, account_id):
        for pid in org._scp_by_target.get(ancestor_id, []):
            if pid in org.scp_policies:
                result.append((ancestor_id, org.scp_policies[pid]))

    return result


# ===================================================================
# SCP policy parsing (minimal viable)
# ===================================================================


def scp_denied_actions(policy: SCPPolicy) -> list[DeniedAction]:
    """Extract all explicitly denied actions from an SCP.

    Handles:
        {"Effect": "Deny", "Action": "sts:AssumeRole"}        → exact
        {"Effect": "Deny", "Action": "*"}                      → all
        {"Effect": "Deny", "Action": "sts:*"}                  → prefix
        {"Effect": "Deny", "Action": ["sts:AssumeRole", ...]}  → list

    Skips:
        NotAction statements (log warning)
        Allow statements (not relevant for deny detection)

    Tracks whether conditions are present (for reporting, not evaluation).
    """
    doc = policy.document
    if not isinstance(doc, dict):
        return []

    statements = doc.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    result: list[DeniedAction] = []

    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        if stmt.get("Effect") != "Deny":
            continue

        # Skip NotAction — too complex for MVP
        if "NotAction" in stmt:
            logger.info(
                "SCP %s has NotAction in Deny — skipping (too complex for MVP)",
                policy.policy_id,
            )
            continue

        has_conditions = "Condition" in stmt

        actions = stmt.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]

        for action in actions:
            if not isinstance(action, str):
                continue
            result.append(
                DeniedAction(
                    action_pattern=action,
                    scp_id=policy.policy_id,
                    scp_name=policy.name,
                    attached_to="",  # filled by caller
                    has_conditions=has_conditions,
                )
            )

    return result


def action_matches_pattern(action: str, pattern: str) -> bool:
    """Check if an AWS action matches an SCP action pattern.

    Patterns:
        "*"              → matches everything
        "sts:*"          → matches all sts actions
        "sts:AssumeRole" → exact match
        "iam:Create*"    → prefix with wildcard

    Case-insensitive (AWS actions are case-insensitive).
    """
    return fnmatch.fnmatch(action.lower(), pattern.lower())


def scp_denies_action(
    policy: SCPPolicy, action: str, skip_conditional: bool = True
) -> list[DeniedAction]:
    """Check if an SCP explicitly denies a specific action.

    Args:
        policy: The SCP to check.
        action: The AWS API action (e.g., "sts:AssumeRole").
        skip_conditional: If True, skip Deny statements that have conditions.
            Conservative: conditions might allow the action, so don't claim
            it's denied unless we're sure.

    Returns:
        List of matching DeniedAction objects (empty if no deny).
    """
    matches: list[DeniedAction] = []

    for denied in scp_denied_actions(policy):
        if skip_conditional and denied.has_conditions:
            logger.debug(
                "SCP %s denies %s but has conditions — skipping (conservative)",
                policy.policy_id,
                denied.action_pattern,
            )
            continue

        if action_matches_pattern(action, denied.action_pattern):
            matches.append(denied)

    return matches


# ===================================================================
# Edge-constraint resolution
# ===================================================================


@dataclass
class ResolvedConstraint:
    """A constraint automatically derived from AWS Organizations data."""

    constraint: dict  # ARF-RT ConstraintInput format
    affected_edges: list[int]  # indices into the edge list


def resolve_scp_constraints(
    org: OrgStructure,
    edges: list[dict],
    confidence_q: int = 800,
) -> tuple[list[dict], list[dict], list[str]]:
    """Resolve SCP → edge linkages for all edges.

    For each edge:
    1. Extract account_id from source ARN
    2. Get all SCPs for that account (via ancestor chain)
    3. Check if any SCP denies the edge's action
    4. If yes: create constraint + edge_constraint

    Args:
        org: Parsed AWS Organizations structure.
        edges: ARF-RT format edges (from PMapper translation).
        confidence_q: Confidence for auto-derived constraints (0-1000).

    Returns:
        (constraints, edge_constraints, warnings)
        All in ARF-RT scenario input format.
    """
    constraints: dict[str, dict] = {}  # dedupe by constraint key
    edge_constraints: list[dict] = []
    warnings: list[str] = []
    skipped_conditional: list[str] = []

    for i, edge in enumerate(edges):
        action = edge.get("features", {}).get("action", "")
        if not action or action in ("UNKNOWN", "ADMIN_ACCESS"):
            continue

        # Get source principal's account
        src_arn = edge.get("src", {}).get("provider_id", "")
        if not src_arn:
            continue

        try:
            src_account = extract_account_id(src_arn)
        except ARFValidationError:
            continue

        if not src_account:
            continue

        # Get all SCPs for this account
        for attached_to, scp in scps_for_account(org, src_account):
            # Check unconditional denies
            denies = scp_denies_action(scp, action, skip_conditional=True)

            # Track conditional denies for reporting
            conditional = scp_denies_action(scp, action, skip_conditional=False)
            cond_only = [d for d in conditional if d.has_conditions and d not in denies]
            for d in cond_only:
                msg = (
                    f"SCP {scp.name} ({scp.policy_id}) denies {d.action_pattern} "
                    f"with conditions — not modeled (conservative)"
                )
                if msg not in skipped_conditional:
                    skipped_conditional.append(msg)

            if not denies:
                continue

            # Create constraint (dedupe by SCP + attachment point)
            constraint_key = f"scp|{scp.policy_id}|{attached_to}"
            if constraint_key not in constraints:
                # Determine scope_type from attachment
                scope_type = "OU" if attached_to.startswith("ou-") or attached_to.startswith("r-") else "ACCOUNT"
                ou_name = ""
                if attached_to in org.ous:
                    ou_name = org.ous[attached_to].name

                constraints[constraint_key] = {
                    "provider": "aws",
                    "constraint_type": "SCP",
                    "scope_type": scope_type,
                    "scope_id": attached_to,
                    "region": "-",
                    "properties": {
                        "policy_id": scp.policy_id,
                        "policy_name": scp.name,
                        "ou_name": ou_name,
                        "denied_actions": [d.action_pattern for d in scp_denied_actions(scp) if not d.has_conditions],
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
                "constraint_type": "SCP",
                "scope_type": constraints[constraint_key]["scope_type"],
                "scope_id": attached_to,
                "region": "-",
                "properties": {
                    "policy_id": scp.policy_id,
                    "policy_name": scp.name,
                    "ou_name": constraints[constraint_key]["properties"]["ou_name"],
                    "denied_actions": constraints[constraint_key]["properties"]["denied_actions"],
                },
            }
            edge_constraints.append({
                "edge_ref": edge_ref,
                "constraint_ref": constraint_ref,
            })

    warnings.extend(skipped_conditional)

    if constraints:
        logger.info(
            "Resolved %d SCP constraints → %d edge-constraint linkages",
            len(constraints),
            len(edge_constraints),
        )

    return list(constraints.values()), edge_constraints, warnings
