"""§VII-A primary realistic fixture for ARF-RT SeRIM 2026 paper.

Target: 14 principals, 16 edges, 4 accounts, 2 SCPs, 2 trust conditions,
        11 observations, baseline entropy 0.3013 nats, 5 attack paths,
        canonical_run_hash 638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b

Specification reconstructed from realistic_demo.md (v1.0 artifact lineage).

Edge belief table from realistic_demo.md (post-observation):
    attacker→DevOps              alpha=176 beta=1   ALLOW
    DevOps→CI-Runner             alpha=81  beta=1   ALLOW
    DevOps→LambdaDeploy          alpha=77  beta=1   ALLOW
    LambdaDeploy→StagingDeploy   alpha=81  beta=1   ALLOW
    CI-Runner→StagingDeploy      alpha=86  beta=1   ALLOW
    StagingDeploy→ProdDeploy     alpha=58  beta=1   ALLOW (trust validated)
    attacker→EC2Bastion          alpha=67  beta=1   ALLOW
    EC2Bastion→SharedInfra       alpha=48  beta=1   ALLOW (trust validated)
    StagingDeploy→StagingAdmin   alpha=1   beta=91  DENY (SCP)
    ProdDeploy→ProdApp           alpha=1   beta=86  DENY (SCP)
    StagingDeploy→StagingDB      alpha=1   beta=1   none
    ProdApp→ProdAdmin            alpha=1   beta=1   none
    ProdDBAdmin→ProdAdmin        alpha=1   beta=1   none
    ProdDeploy→ProdDBAdmin       alpha=1   beta=1   none
    SharedInfra→SharedSecrets    alpha=1   beta=1   none
    SharedSecrets→ProdAdmin      alpha=1   beta=1   none

Increment formula (arf_rt.engine.belief.compute_increment):
    inc = (base_w_q[strength] * signal_q) // 100

Strength weights:
    DETERMINISTIC=100, DIRECT=95, INFERRED=60, HEURISTIC=30

To hit the target alpha values from prior=(1,1):
    alpha=176: prior 1 + inc 175. With strength=DIRECT(95) need signal_q s.t. (95*sq)//100=175.
               That's not achievable in one obs (max is 95 at sq=100).
               Use 2 observations: inc=88 + inc=87 -> sq=92 + sq=91.
               Or inc=90 + inc=85 -> sq=94 + sq=89.
    alpha=81:  inc=80. (95*84)//100 = 79; (95*85)//100 = 80. -> sq=85
    alpha=77:  inc=76. (95*81)//100 = 76. -> sq=81
    alpha=86:  inc=85. (95*89)//100 = 84; (95*90)//100 = 85. -> sq=90
    alpha=58:  inc=57. (95*60)//100 = 57. -> sq=60
    alpha=67:  inc=66. (95*70)//100 = 66. -> sq=70
    alpha=48:  inc=47. (95*49)//100 = 46; (95*50)//100 = 47. -> sq=50

DENY observations:
    beta=91: inc=90. (95*95)//100 = 90. -> sq=95
    beta=86: inc=85. (95*90)//100 = 85. -> sq=90
"""

import json
import argparse
from pathlib import Path


def emit():
    nodes = []
    edges = []
    constraints = []
    edge_constraints = []
    observations = []

    # =========================================================
    # ACCOUNTS (4 accounts per paper §VII.A)
    # =========================================================
    accounts = {
        "dev-tooling":   "111111111111",
        "staging":       "222222222222",
        "production":    "333333333333",
        "shared-infra":  "444444444444",
    }

    # =========================================================
    # NODES (14 principals)
    # =========================================================
    principals = {}

    def add_node(name, ntype, acct_key, props=None):
        acct = accounts[acct_key]
        if ntype == "IAMUser":
            pid = f"arn:aws:iam::{acct}:user/{name}"
        elif ntype == "IAMRole":
            pid = f"arn:aws:iam::{acct}:role/{name}"
        elif ntype == "LambdaFunction":
            pid = f"arn:aws:lambda:us-east-1:{acct}:function:{name}"
        else:
            pid = f"arn:aws:iam::{acct}:{ntype}/{name}"
        node = {
            "provider": "aws", "node_type": ntype,
            "provider_id": pid, "region": "-",
            "display_name": name,
            "properties": {"account_id": acct, **(props or {})},
        }
        nodes.append(node)
        principals[name] = node
        return node

    # Per realistic_demo.md edge list. 14 principals total.
    add_node("attacker",       "IAMUser", "dev-tooling", {"compromised": True})
    add_node("DevOps",         "IAMRole", "dev-tooling")
    add_node("CI-Runner",      "IAMRole", "dev-tooling")
    add_node("LambdaDeploy",   "IAMRole", "dev-tooling")
    add_node("EC2Bastion",     "IAMRole", "dev-tooling")
    add_node("StagingDeploy",  "IAMRole", "staging")
    add_node("StagingAdmin",   "IAMRole", "staging")
    add_node("StagingDB",      "IAMRole", "staging")
    add_node("ProdDeploy",     "IAMRole", "production")
    add_node("ProdApp",        "IAMRole", "production")
    add_node("ProdDBAdmin",    "IAMRole", "production")
    add_node("ProdAdmin",      "IAMRole", "production", {"high_value": True})
    add_node("SharedInfra",    "IAMRole", "shared-infra")
    add_node("SharedSecrets",  "IAMRole", "shared-infra")
    assert len(nodes) == 14, f"expected 14 nodes, got {len(nodes)}"

    # =========================================================
    # EDGES (16 edges, prior (1,1))
    # =========================================================
    def add_edge(src_name, dst_name, etype="sts:AssumeRole_permission", features=None):
        s = principals[src_name]
        d = principals[dst_name]
        e = {
            "edge_type": etype,
            "src": {"provider": s["provider"], "node_type": s["node_type"],
                    "provider_id": s["provider_id"], "region": "-"},
            "dst": {"provider": d["provider"], "node_type": d["node_type"],
                    "provider_id": d["provider_id"], "region": "-"},
            "region": "-",
            "features": features or {},
            "alpha_i": 1, "beta_i": 1,
        }
        edges.append(e)
        return e

    # All 16 edges from realistic_demo.md, in the order they appear there.
    add_edge("attacker", "DevOps")
    add_edge("DevOps", "CI-Runner")
    add_edge("DevOps", "LambdaDeploy")
    add_edge("LambdaDeploy", "StagingDeploy",
             features={"cross_account": True})
    add_edge("CI-Runner", "StagingDeploy",
             features={"cross_account": True})
    add_edge("StagingDeploy", "ProdDeploy",
             features={"cross_account": True, "trust_external_id": True})
    add_edge("attacker", "EC2Bastion")
    add_edge("EC2Bastion", "SharedInfra",
             features={"cross_account": True, "trust_principal_org": True})
    add_edge("StagingDeploy", "StagingAdmin")  # SCP-blocked
    add_edge("ProdDeploy", "ProdApp",
             features={"cross_account": True})  # SCP-blocked
    add_edge("StagingDeploy", "StagingDB")
    add_edge("ProdApp", "ProdAdmin",
             features={"cross_account": True})  # SCP-blocked
    add_edge("ProdDBAdmin", "ProdAdmin",
             features={"cross_account": True})  # SCP-blocked
    add_edge("ProdDeploy", "ProdDBAdmin",
             features={"cross_account": True})  # SCP-blocked
    add_edge("SharedInfra", "SharedSecrets",
             features={"cross_account": True})  # SCP-blocked
    add_edge("SharedSecrets", "ProdAdmin",
             features={"cross_account": True})  # SCP-blocked
    assert len(edges) == 16, f"expected 16 edges, got {len(edges)}"

    # =========================================================
    # CONSTRAINTS (2 SCPs + 2 trust conditions = 4)
    # Per realistic_demo.md: BlockIAMWriteStaging governs StagingDeploy->StagingAdmin (1 edge).
    # BlockCrossAccountAssumeProd governs 6 edges:
    #   ProdDeploy->ProdApp, ProdDeploy->ProdDBAdmin, SharedSecrets->ProdAdmin,
    #   ProdDBAdmin->ProdAdmin, ProdApp->ProdAdmin, SharedInfra->SharedSecrets
    # ProdDeploy ExternalId trust: StagingDeploy->ProdDeploy (1 edge)
    # SharedInfra PrincipalOrgID trust: EC2Bastion->SharedInfra (1 edge)
    # =========================================================
    scp_staging = {
        "provider": "aws", "constraint_type": "SCP",
        "scope_type": "ou", "scope_id": "ou-staging", "region": "-",
        "properties": {
            "policy_id": "scp-BlockIAMWriteStaging",
            "statement_id": "DenyIAMWriteInStaging",
            "effect": "DENY", "action": "iam:*",
            "description": "Denies iam:CreateAccessKey, iam:CreateUser, iam:AttachRolePolicy",
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500,
    }
    constraints.append(scp_staging)

    scp_prod = {
        "provider": "aws", "constraint_type": "SCP",
        "scope_type": "ou", "scope_id": "ou-prod", "region": "-",
        "properties": {
            "policy_id": "scp-BlockCrossAccountAssumeProd",
            "statement_id": "DenyCrossAccountAssumeIntoProd",
            "effect": "DENY", "action": "sts:AssumeRole",
            "description": "Denies cross-account AssumeRole into production OU",
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500,
    }
    constraints.append(scp_prod)

    tc_externalid = {
        "provider": "aws", "constraint_type": "TRUST_CONDITION",
        "scope_type": "edge", "scope_id": "tc-prod-deploy-externalid", "region": "-",
        "properties": {
            "policy_id": "trust-prod-deploy",
            "statement_id": "RequireExternalId",
            "condition_key": "sts:ExternalId",
            "condition_value": "prod-deploy-xid-9281",
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500,
    }
    constraints.append(tc_externalid)

    tc_orgid = {
        "provider": "aws", "constraint_type": "TRUST_CONDITION",
        "scope_type": "edge", "scope_id": "tc-shared-infra-orgid", "region": "-",
        "properties": {
            "policy_id": "trust-shared-infra",
            "statement_id": "RequirePrincipalOrgID",
            "condition_key": "aws:PrincipalOrgID",
            "condition_value": "o-realdemo1",
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500,
    }
    constraints.append(tc_orgid)
    assert len(constraints) == 4, f"expected 4 constraints, got {len(constraints)}"

    def edge_ref(src_name, dst_name):
        s = principals[src_name]
        d = principals[dst_name]
        return {
            "edge_type": "sts:AssumeRole_permission",
            "src": {"provider": s["provider"], "node_type": s["node_type"],
                    "provider_id": s["provider_id"], "region": "-"},
            "dst": {"provider": d["provider"], "node_type": d["node_type"],
                    "provider_id": d["provider_id"], "region": "-"},
            "region": "-",
        }

    def constraint_ref(c):
        return {
            "provider": c["provider"], "constraint_type": c["constraint_type"],
            "scope_type": c["scope_type"], "scope_id": c["scope_id"], "region": "-",
            "properties": c["properties"],
        }

    # SCP Staging: 1 edge linkage
    edge_constraints.append({
        "edge_ref": edge_ref("StagingDeploy", "StagingAdmin"),
        "constraint_ref": constraint_ref(scp_staging),
    })
    # SCP Prod: 6 edge linkages (per realistic_demo.md correlation group members)
    for src, dst in [("ProdDeploy", "ProdApp"),
                     ("ProdDeploy", "ProdDBAdmin"),
                     ("SharedSecrets", "ProdAdmin"),
                     ("ProdDBAdmin", "ProdAdmin"),
                     ("ProdApp", "ProdAdmin"),
                     ("SharedInfra", "SharedSecrets")]:
        edge_constraints.append({
            "edge_ref": edge_ref(src, dst),
            "constraint_ref": constraint_ref(scp_prod),
        })
    # ExternalId trust: 1 edge
    edge_constraints.append({
        "edge_ref": edge_ref("StagingDeploy", "ProdDeploy"),
        "constraint_ref": constraint_ref(tc_externalid),
    })
    # PrincipalOrgID trust: 1 edge
    edge_constraints.append({
        "edge_ref": edge_ref("EC2Bastion", "SharedInfra"),
        "constraint_ref": constraint_ref(tc_orgid),
    })
    assert len(edge_constraints) == 9, f"expected 9 edge_constraints, got {len(edge_constraints)}"

    # =========================================================
    # OBSERVATIONS (11 total: 9 ALLOW + 2 DENY = 11 per paper §VII.A)
    # Targets the post-observation alpha/beta values in realistic_demo.md.
    # Increment formula: (base_w_q[strength] * signal_q) // 100
    # =========================================================
    def obs(src, dst, result, strength, signal_q, reason="UNKNOWN", evid_hash=None):
        s = principals[src]; d = principals[dst]
        observations.append({
            "edge_ref": {
                "edge_type": "sts:AssumeRole_permission",
                "src": {"provider": s["provider"], "node_type": s["node_type"],
                        "provider_id": s["provider_id"], "region": "-"},
                "dst": {"provider": d["provider"], "node_type": d["node_type"],
                        "provider_id": d["provider_id"], "region": "-"},
                "region": "-",
            },
            "result": result, "strength": strength, "signal_q": signal_q,
            "reason_class": reason, "is_counterfactual": False,
            "constraint_relevant": False,
            "evidence_hash": evid_hash or f"ev-{src}-{dst}-{result}",
        })

    # 9 ALLOW observations targeting the post-state alpha values:
    # alpha=176 needs inc 175. Two obs at DIRECT signal_q=92 (inc=87) + signal_q=93 (inc=88) = 175.
    # But that uses 2 of our 11 obs slots. Let's instead use one DETERMINISTIC obs.
    # alpha=176: 1 obs, DETERMINISTIC*sq -> inc=175. (100*175)//100 doesn't work. Use 2 obs.
    # Re-checking: we have 11 obs and need 9 ALLOW + 2 DENY. So 9 obs to cover 8 distinct edges.
    # That gives one edge with two obs. attacker->DevOps (alpha=176) is the natural double.
    obs("attacker", "DevOps",     "ALLOW", "DIRECT", 92)  # inc=87, alpha 1+87=88
    obs("attacker", "DevOps",     "ALLOW", "DIRECT", 93)  # inc=88, alpha 88+88=176
    obs("DevOps",   "CI-Runner",  "ALLOW", "DIRECT", 85)  # inc=80, alpha=81
    obs("DevOps",   "LambdaDeploy", "ALLOW", "DIRECT", 81)  # inc=76, alpha=77
    obs("LambdaDeploy", "StagingDeploy", "ALLOW", "DIRECT", 85)  # inc=80, alpha=81
    obs("CI-Runner", "StagingDeploy", "ALLOW", "DIRECT", 90)  # inc=85, alpha=86
    obs("StagingDeploy", "ProdDeploy", "ALLOW", "DIRECT", 60)  # inc=57, alpha=58
    obs("attacker", "EC2Bastion", "ALLOW", "DIRECT", 70)  # inc=66, alpha=67
    obs("EC2Bastion", "SharedInfra", "ALLOW", "DIRECT", 50)  # inc=47, alpha=48

    # 2 DENY observations targeting the SCP-refuted edges:
    obs("StagingDeploy", "StagingAdmin", "DENY", "DIRECT", 95,
        reason="CONSTRAINT_DENY")  # inc=90, beta=91
    obs("ProdDeploy", "ProdApp", "DENY", "DIRECT", 90,
        reason="CONSTRAINT_DENY")  # inc=85, beta=86

    assert len(observations) == 11, f"expected 11 obs, got {len(observations)}"

    # =========================================================
    # OBJECTIVES
    # =========================================================
    objectives = [{
        "objective_type": "REACHABILITY",
        "start_nodes": [{
            "provider": "aws", "node_type": "IAMUser",
            "provider_id": principals["attacker"]["provider_id"], "region": "-",
        }],
        "target_nodes": [{
            "provider": "aws", "node_type": "IAMRole",
            "provider_id": principals["ProdAdmin"]["provider_id"], "region": "-",
        }],
        "max_depth": 8,
        "k": 5,
    }]

    return {
        "metadata": {
            "fixture": "primary-realistic-vii-a",
            "accounts": len(accounts),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "constraint_count": len(constraints),
            "edge_constraint_count": len(edge_constraints),
            "observation_count": len(observations),
            "paper_section": "VII-A",
            "target_baseline_entropy_nats": 0.3013,
            "target_paths": 5,
            "target_canonical_run_hash":
                "638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b",
        },
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "edge_constraints": edge_constraints,
        "objectives": objectives,
        "observations": observations,
    }


def main():
    parser = argparse.ArgumentParser(description="Build the §VII-A primary realistic fixture")
    parser.add_argument("--output", required=True, help="Output scenario JSON path")
    args = parser.parse_args()
    scenario = emit()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(scenario, f, indent=2)
    m = scenario["metadata"]
    print(f"Wrote {args.output}")
    print(f"  nodes={m['node_count']} edges={m['edge_count']}")
    print(f"  constraints={m['constraint_count']} edge_constraints={m['edge_constraint_count']}")
    print(f"  observations={m['observation_count']}")
    print(f"  Targeting hash: {m['target_canonical_run_hash'][:16]}...")
    print()
    print("Next steps:")
    print(f"  arf-rt analyze {args.output} --format both -o /tmp/check")
    print(f"  arf-rt hash {args.output}")


if __name__ == "__main__":
    main()
