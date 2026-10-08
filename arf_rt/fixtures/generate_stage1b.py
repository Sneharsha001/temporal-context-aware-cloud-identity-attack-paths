"""Stage 1b — Realistic multi-account AWS fixture with bypass path.

Mimics a real AWS Organization topology:
  - 3 accounts: mgmt (111111111111), dev (222222222222), prod (333333333333)
  - 2 OUs: ou-dev (dev), ou-prod (prod)
  - 1 SCP on ou-prod: DenyAssumeRoleProd (6 governed edges)
  - 1 Trust condition: ExternalIdRequired (4 governed edges)
  - ~35 nodes, ~55 edges
  - 2 objectives, 3 observations

Critical design:
  1. One path looks strong naively but collapses under SCP correlation
  2. One alternative path BYPASSES the SCP group (ungoverned)
  3. Trust condition creates a second component for planner choice diversity
  4. Dead ends exercise candidate pruning

The bypass path is what makes EIG beat uncertainty:
  - Uncertainty sees two p=0.50 edges (SCP rep vs bypass edge) as equal
  - EIG prefers the SCP rep because it resolves 6 edges, not 1

Usage:
    python -m arf_rt.fixtures.generate_stage1b > tests/fixtures/stage1b_realistic.json
"""
from __future__ import annotations

import json
import sys


ACCT_MGMT = "111111111111"
ACCT_DEV = "222222222222"
ACCT_PRD = "333333333333"


def generate_stage1b() -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    constraints: list[dict] = []
    edge_constraints: list[dict] = []
    observations: list[dict] = []

    # ── Helpers ───────────────────────────────────────────────

    def _arn(acct: str, name: str, kind: str = "role") -> str:
        return f"arn:aws:iam::{acct}:{kind}/{name}"

    def node(acct: str, name: str, kind: str = "role") -> dict:
        ntype = "IAMUser" if kind == "user" else "IAMRole"
        n = {
            "provider": "aws",
            "node_type": ntype,
            "provider_id": _arn(acct, name, kind),
            "region": "-",
        }
        nodes.append(n)
        return n

    def edge(src: dict, dst: dict, etype: str = "sts:AssumeRole") -> dict:
        e = {
            "edge_type": etype,
            "src": {k: v for k, v in src.items()},
            "dst": {k: v for k, v in dst.items()},
            "region": "-",
            "features": {},
        }
        edges.append(e)
        return e

    def scp(scope_id: str, policy_name: str,
            denied_actions: list[str] | None = None) -> dict:
        c = {
            "provider": "aws",
            "constraint_type": "SCP",
            "scope_type": "OU",
            "scope_id": scope_id,
            "region": "-",
            "properties": {
                "policy_id": f"p-{policy_name.lower().replace(' ', '-')}",
                "policy_name": policy_name,
                "ou_name": scope_id,
                "denied_actions": denied_actions or ["sts:AssumeRole"],
            },
            "status": "ACTIVE",
            "validation_status": "UNVALIDATED",
            "confidence_q": 800,
        }
        constraints.append(c)
        return c

    def trust_condition(scope_id: str, name: str) -> dict:
        c = {
            "provider": "aws",
            "constraint_type": "TRUST_CONDITION",
            "scope_type": "OU",
            "scope_id": scope_id,
            "region": "-",
            "properties": {
                "policy_id": f"p-{name.lower().replace(' ', '-')}",
                "policy_name": name,
                "ou_name": scope_id,
                "condition_type": "sts:ExternalId",
                "denied_actions": ["sts:AssumeRole"],
            },
            "status": "ACTIVE",
            "validation_status": "UNVALIDATED",
            "confidence_q": 800,
        }
        constraints.append(c)
        return c

    def bind(e: dict, c: dict) -> None:
        edge_constraints.append({
            "edge_ref": {
                "edge_type": e["edge_type"],
                "src": e["src"], "dst": e["dst"],
                "region": e["region"],
            },
            "constraint_ref": {
                "provider": c["provider"],
                "constraint_type": c["constraint_type"],
                "scope_type": c["scope_type"],
                "scope_id": c["scope_id"],
                "region": c["region"],
                "properties": c["properties"],
            },
        })

    def observe(e: dict, result: str, signal_q: int = 90,
                constraint_relevant: bool = False, tag: str = "") -> None:
        observations.append({
            "edge_ref": {
                "edge_type": e["edge_type"],
                "src": e["src"], "dst": e["dst"],
                "region": e["region"],
            },
            "probe_type": "REPLAY_SCRIPTED",
            "result": result,
            "reason_class": "UNKNOWN",
            "strength": "DIRECT",
            "signal_q": signal_q,
            "is_counterfactual": False,
            "constraint_relevant": constraint_relevant,
            "evidence_hash": tag or f"obs_{len(observations)}",
        })

    # ══════════════════════════════════════════════════════════
    # TOPOLOGY
    # ══════════════════════════════════════════════════════════

    # ── Mgmt Account (111) — attacker starts here ─────────────
    attacker = node(ACCT_MGMT, "pentester", "user")
    mgmt_ops = node(ACCT_MGMT, "MgmtOpsRole")

    # ── Dev Account (222) ─────────────────────────────────────
    dev_jump = node(ACCT_DEV, "DevJumpRole")
    dev_ci = node(ACCT_DEV, "DevCIRole")
    dev_deploy = node(ACCT_DEV, "DevDeployRole")
    dev_lambda = node(ACCT_DEV, "SharedLambdaDeploy")
    dev_readonly = node(ACCT_DEV, "DevReadOnly")
    dev_build = node(ACCT_DEV, "DevBuildRunner")

    # ── Prod Account (333) ────────────────────────────────────
    prd_deploy = node(ACCT_PRD, "ProdDeployRole")
    prd_admin = node(ACCT_PRD, "ProdAdminRole")
    prd_db = node(ACCT_PRD, "ProdDBRole")
    prd_lambda = node(ACCT_PRD, "ProdLambdaExec")
    prd_readonly = node(ACCT_PRD, "ProdReadOnly")
    prd_backup = node(ACCT_PRD, "ProdBackupRole")
    billing_admin = node(ACCT_PRD, "BillingAdminRole")

    # ── Intra-mgmt edges ──────────────────────────────────────
    e_atk_ops = edge(attacker, mgmt_ops)
    e_atk_jump = edge(attacker, dev_jump)
    e_atk_ci = edge(attacker, dev_ci)
    edge(mgmt_ops, dev_jump)  # MgmtOps can reach dev (ungoverned)

    # ── Intra-dev edges ───────────────────────────────────────
    edge(dev_jump, dev_deploy)
    edge(dev_jump, dev_readonly)
    edge(dev_ci, dev_deploy)
    edge(dev_ci, dev_build)
    edge(dev_deploy, dev_lambda)
    edge(dev_build, dev_lambda)

    # ══════════════════════════════════════════════════════════
    # SCP-GOVERNED CLUSTER (collapse path)
    # 6 edges governed by ou-prod SCP
    # Mix of cross-account AND intra-prod — SCP blocks the last
    # hops to target, not just the boundary crossing
    # ══════════════════════════════════════════════════════════

    e_gov1 = edge(dev_jump, prd_deploy)      # DevJump → ProdDeploy (cross-acct)
    e_gov2 = edge(dev_ci, prd_deploy)        # DevCI → ProdDeploy (cross-acct)
    e_gov3 = edge(dev_lambda, prd_deploy)    # SharedLambda → ProdDeploy (cross-acct)
    e_gov4 = edge(dev_jump, prd_db)          # DevJump → ProdDB (cross-acct)
    e_gov5 = edge(prd_deploy, prd_admin)     # ProdDeploy → ProdAdmin (INTRA-prod, governed)
    e_gov6 = edge(prd_deploy, prd_db)        # ProdDeploy → ProdDB (INTRA-prod, governed)

    # Intra-prod edges NOT governed (normal within-prod movement)
    edge(prd_db, prd_admin)   # ProdDB → ProdAdmin (ungoverned)
    edge(prd_lambda, prd_deploy)
    edge(prd_deploy, prd_readonly)
    edge(prd_backup, prd_db)

    # ══════════════════════════════════════════════════════════
    # BYPASS PATH (ungoverned — avoids SCP entirely)
    # attacker → DevJump → SharedLambdaDeploy → ProdAdminRole
    # The SharedLambda→ProdAdmin edge is sts:AssumeRole but was
    # not included in the SCP binding (misconfigured exclusion).
    # This is the realistic scenario: one role slips through.
    # ══════════════════════════════════════════════════════════

    e_bypass = edge(dev_lambda, prd_admin)  # NOT governed — the gap

    # ══════════════════════════════════════════════════════════
    # TRUST CONDITION CLUSTER (4 edges)
    # ExternalId required for billing access
    # ══════════════════════════════════════════════════════════

    e_tc1 = edge(dev_ci, billing_admin)
    e_tc2 = edge(dev_jump, billing_admin)
    e_tc3 = edge(dev_lambda, billing_admin)
    e_tc4 = edge(mgmt_ops, billing_admin)

    # Billing bypass: ProdDB → BillingAdmin (ungoverned, no trust condition)
    # If you can reach ProdDB, you can reach BillingAdmin without ExternalId
    edge(prd_db, billing_admin)

    # ══════════════════════════════════════════════════════════
    # DEAD ENDS (15 edges, never reach objectives)
    # ══════════════════════════════════════════════════════════

    dead = [node(ACCT_DEV, f"DeadEnd{i:02d}") for i in range(8)]
    # Fan out from dev
    edge(dev_readonly, dead[0])
    edge(dev_readonly, dead[1])
    edge(dev_build, dead[2])
    edge(dead[0], dead[3])
    edge(dead[1], dead[4])
    edge(dead[2], dead[5])
    edge(dead[3], dead[6])
    edge(dead[4], dead[7])
    edge(dead[5], dead[0])  # cycle
    edge(dead[6], dead[1])  # cycle
    edge(dead[7], dead[2])  # cycle
    # Prod dead ends
    dead_prd = [node(ACCT_PRD, f"ProdDead{i:02d}") for i in range(3)]
    edge(prd_readonly, dead_prd[0])
    edge(prd_backup, dead_prd[1])
    edge(dead_prd[0], dead_prd[2])
    edge(dead_prd[1], dead_prd[2])

    # ══════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ══════════════════════════════════════════════════════════

    # SCP on ou-prod: governs all 6 cross-account edges into prod
    scp_prod = scp("ou-prod", "DenyAssumeRoleProd")
    for e in [e_gov1, e_gov2, e_gov3, e_gov4, e_gov5, e_gov6]:
        bind(e, scp_prod)

    # Trust condition: ExternalId on billing edges
    tc_billing = trust_condition("ou-billing", "ExternalIdRequired")
    for e in [e_tc1, e_tc2, e_tc3, e_tc4]:
        bind(e, tc_billing)

    # ══════════════════════════════════════════════════════════
    # OBSERVATIONS
    # SCP group LEFT UNINFORMED — planner must discover it
    # Trust condition has one ALLOW (partial collapse)
    # Attacker recon confirms initial reachability
    # ══════════════════════════════════════════════════════════

    # Attacker → DevJump confirmed (establishes reachability)
    observe(e_atk_jump, "ALLOW", signal_q=95, tag="recon_01")

    # Attacker → DevCI confirmed
    observe(e_atk_ci, "ALLOW", signal_q=90, tag="recon_02")

    # One trust condition edge observed ALLOW (partial component info)
    observe(e_tc1, "ALLOW", signal_q=85, tag="tc_allow_01")

    # ══════════════════════════════════════════════════════════
    # OBJECTIVES
    # ══════════════════════════════════════════════════════════

    objectives = [
        {
            "objective_type": "REACHABILITY",
            "start_nodes": [_noderef(attacker)],
            "target_nodes": [_noderef(prd_admin)],
            "max_depth": 8,
            "k": 10,
        },
        {
            "objective_type": "REACHABILITY",
            "start_nodes": [_noderef(attacker)],
            "target_nodes": [_noderef(billing_admin)],
            "max_depth": 6,
            "k": 10,
        },
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "edge_constraints": edge_constraints,
        "objectives": objectives,
        "observations": observations,
    }


def _noderef(n: dict) -> dict:
    return {
        "provider": n["provider"],
        "node_type": n["node_type"],
        "provider_id": n["provider_id"],
        "region": n["region"],
    }


def main() -> None:
    scenario = generate_stage1b()
    print(json.dumps(scenario, indent=2), file=sys.stdout)
    print(
        f"# Stage 1b: {len(scenario['nodes'])} nodes, "
        f"{len(scenario['edges'])} edges, "
        f"{len(scenario['constraints'])} constraints, "
        f"{len(scenario['edge_constraints'])} edge_constraints, "
        f"{len(scenario['objectives'])} objectives, "
        f"{len(scenario['observations'])} observations",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
