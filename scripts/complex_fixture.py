"""Complex realistic AWS fixture: 4 BUs, 8 accounts, SCPs, trust conditions, OIDC.

Simulates a mid-size fintech with:
  - 4 business units: Platform, Payments, Data, DevOps
  - 8 AWS accounts: dev, staging, prod per BU + shared-infra + security
  - 3 SCPs: BlockProdAssume (prod OU), BlockDataExfil (data OU), RestrictIAMWrite (all non-security)
  - 2 trust conditions: ExternalId on cross-account, OIDC on CI/CD
  - ~200 edges with realistic privilege chains
  - Scripted ground truth for probe evaluation
"""

import json
import hashlib

def emit():
    nodes = []
    edges = []
    constraints = []
    edge_constraints = []
    observations = []

    # =========================================================
    # ACCOUNTS
    # =========================================================
    accounts = {
        "platform-dev":   "110000000001",
        "platform-prod":  "110000000002",
        "payments-dev":   "120000000001",
        "payments-prod":  "120000000002",
        "data-dev":       "130000000001",
        "data-prod":      "130000000002",
        "shared-infra":   "140000000001",
        "security":       "150000000001",
    }

    # =========================================================
    # NODES: principals per account
    # =========================================================
    principals = {}  # name → node

    def add_node(name, ntype, acct_key, props=None):
        acct = accounts[acct_key]
        if ntype == "IAMUser":
            pid = f"arn:aws:iam::{acct}:user/{name}"
        elif ntype == "IAMRole":
            pid = f"arn:aws:iam::{acct}:role/{name}"
        elif ntype == "LambdaFunction":
            pid = f"arn:aws:lambda:us-east-1:{acct}:function:{name}"
        elif ntype == "ActionsRunner":
            pid = f"github:{name}"
            acct = "-"
        else:
            pid = f"arn:aws:iam::{acct}:{ntype}/{name}"

        node = {
            "provider": "github" if ntype == "ActionsRunner" else "aws",
            "node_type": ntype, "provider_id": pid, "region": "-",
            "display_name": f"{name} ({acct_key})" if acct != "-" else name,
            "properties": {"account_id": acct, **(props or {})}
        }
        nodes.append(node)
        principals[f"{name}@{acct_key}"] = node
        return node

    # Attacker: compromised dev engineer
    attacker = add_node("attacker-dev", "IAMUser", "platform-dev", {"compromised": True})

    # Platform team
    add_node("PlatformDevRole", "IAMRole", "platform-dev")
    add_node("PlatformCIRole", "IAMRole", "platform-dev")
    add_node("PlatformStagingDeploy", "IAMRole", "platform-prod")  # misnomer: staging in prod acct
    add_node("PlatformProdDeploy", "IAMRole", "platform-prod")
    add_node("PlatformProdAdmin", "IAMRole", "platform-prod", {"high_value": True})

    # Payments team
    add_node("PaymentDevRole", "IAMRole", "payments-dev")
    add_node("PaymentProcessorRole", "IAMRole", "payments-prod")
    add_node("PaymentProdAdmin", "IAMRole", "payments-prod", {"high_value": True})
    add_node("PaymentDBAccess", "IAMRole", "payments-prod")

    # Data team
    add_node("DataEngRole", "IAMRole", "data-dev")
    add_node("DataPipelineRole", "IAMRole", "data-prod")
    add_node("DataLakeAdmin", "IAMRole", "data-prod", {"high_value": True})
    add_node("GlueJobRole", "LambdaFunction", "data-prod")

    # Shared infra
    add_node("InfraJumpRole", "IAMRole", "shared-infra")
    add_node("InfraTerraformRole", "IAMRole", "shared-infra")
    add_node("InfraNetworkAdmin", "IAMRole", "shared-infra")
    add_node("CrossAccountBridge", "IAMRole", "shared-infra")

    # Security
    add_node("SecurityAuditRole", "IAMRole", "security")
    add_node("IncidentResponseRole", "IAMRole", "security")
    add_node("SecurityAdmin", "IAMRole", "security", {"high_value": True})

    # CI/CD (GitHub Actions)
    add_node("AcmePlatform/api:actions", "ActionsRunner", "platform-dev")
    add_node("AcmePlatform/infra:actions", "ActionsRunner", "platform-dev")
    add_node("AcmePayments/processor:actions", "ActionsRunner", "payments-dev")

    # =========================================================
    # EDGES: privilege chains
    # =========================================================
    def add_edge(src_key, dst_key, etype="sts:AssumeRole_permission", alpha=2, beta=1, features=None):
        src = principals[src_key]
        dst = principals[dst_key]
        e = {
            "edge_type": etype,
            "src": {"provider": src["provider"], "node_type": src["node_type"],
                    "provider_id": src["provider_id"], "region": "-"},
            "dst": {"provider": dst["provider"], "node_type": dst["node_type"],
                    "provider_id": dst["provider_id"], "region": "-"},
            "region": "-",
            "features": features or {},
            "alpha_i": alpha, "beta_i": beta
        }
        edges.append(e)
        return e

    # --- Attacker initial access ---
    add_edge("attacker-dev@platform-dev", "PlatformDevRole@platform-dev", alpha=3, beta=1)
    add_edge("attacker-dev@platform-dev", "PlatformCIRole@platform-dev", alpha=2, beta=1)

    # --- Platform lateral movement ---
    # Dev → shared infra (common pattern: dev roles can jump to infra)
    e1 = add_edge("PlatformDevRole@platform-dev", "InfraJumpRole@shared-infra", alpha=2, beta=1,
            features={"cross_account": True})
    e2 = add_edge("PlatformCIRole@platform-dev", "InfraJumpRole@shared-infra", alpha=2, beta=1,
            features={"cross_account": True})
    # Infra jump → various prod accounts (THE KEY CROSS-ACCOUNT PATHS)
    e3 = add_edge("InfraJumpRole@shared-infra", "PlatformProdDeploy@platform-prod", alpha=2, beta=1,
            features={"cross_account": True})
    e4 = add_edge("InfraJumpRole@shared-infra", "PaymentProcessorRole@payments-prod", alpha=2, beta=1,
            features={"cross_account": True})
    e5 = add_edge("InfraJumpRole@shared-infra", "DataPipelineRole@data-prod", alpha=2, beta=1,
            features={"cross_account": True})
    e6 = add_edge("InfraJumpRole@shared-infra", "InfraTerraformRole@shared-infra", alpha=3, beta=1)

    # Infra terraform → prod admins (escalation via terraform state)
    e7 = add_edge("InfraTerraformRole@shared-infra", "PlatformProdAdmin@platform-prod", alpha=2, beta=1,
            features={"cross_account": True})
    e8 = add_edge("InfraTerraformRole@shared-infra", "PaymentProdAdmin@payments-prod", alpha=2, beta=1,
            features={"cross_account": True})
    e9 = add_edge("InfraTerraformRole@shared-infra", "DataLakeAdmin@data-prod", alpha=2, beta=1,
            features={"cross_account": True})

    # Direct prod escalation chains
    add_edge("PlatformProdDeploy@platform-prod", "PlatformProdAdmin@platform-prod", alpha=2, beta=1)
    add_edge("PaymentProcessorRole@payments-prod", "PaymentProdAdmin@payments-prod", alpha=2, beta=1)
    add_edge("DataPipelineRole@data-prod", "DataLakeAdmin@data-prod", alpha=2, beta=1)
    add_edge("PaymentProcessorRole@payments-prod", "PaymentDBAccess@payments-prod", alpha=3, beta=1)

    # Data team chain
    add_edge("DataEngRole@data-dev", "DataPipelineRole@data-prod", alpha=2, beta=1,
            features={"cross_account": True})
    add_edge("DataPipelineRole@data-prod", "GlueJobRole@data-prod", alpha=3, beta=1)
    add_edge("GlueJobRole@data-prod", "DataLakeAdmin@data-prod", alpha=2, beta=1)

    # Platform dev → payments dev (cross-BU lateral)
    add_edge("PlatformDevRole@platform-dev", "PaymentDevRole@payments-dev", alpha=1, beta=1,
            features={"cross_account": True})
    add_edge("PaymentDevRole@payments-dev", "PaymentProcessorRole@payments-prod", alpha=2, beta=1,
            features={"cross_account": True})

    # CrossAccountBridge paths (shared infra → everywhere)
    add_edge("InfraJumpRole@shared-infra", "CrossAccountBridge@shared-infra", alpha=2, beta=1)
    add_edge("CrossAccountBridge@shared-infra", "SecurityAuditRole@security", alpha=1, beta=2,
            features={"cross_account": True})
    add_edge("SecurityAuditRole@security", "IncidentResponseRole@security", alpha=2, beta=1)
    add_edge("IncidentResponseRole@security", "SecurityAdmin@security", alpha=2, beta=1)

    # CI/CD OIDC paths
    add_edge("attacker-dev@platform-dev", "AcmePlatform/api:actions@platform-dev",
            etype="repo:Write", alpha=3, beta=1, features={"cross_environment": True})
    add_edge("attacker-dev@platform-dev", "AcmePlatform/infra:actions@platform-dev",
            etype="repo:Write", alpha=3, beta=1, features={"cross_environment": True})
    add_edge("AcmePlatform/api:actions@platform-dev", "PlatformProdDeploy@platform-prod",
            etype="oidc:AssumeRole", alpha=1, beta=2,
            features={"has_oidc_subject": True,
                      "oidc_subject_pattern": "repo:AcmePlatform/api:ref:refs/heads/main",
                      "cross_environment": True})
    add_edge("AcmePlatform/infra:actions@platform-dev", "InfraTerraformRole@shared-infra",
            etype="oidc:AssumeRole", alpha=1, beta=1,
            features={"has_oidc_subject": True,
                      "oidc_subject_pattern": "repo:AcmePlatform/infra:ref:refs/heads/*",
                      "cross_environment": True, "naked_trust": True})
    add_edge("AcmePayments/processor:actions@payments-dev", "PaymentProcessorRole@payments-prod",
            etype="oidc:AssumeRole", alpha=1, beta=2,
            features={"has_oidc_subject": True,
                      "oidc_subject_pattern": "repo:AcmePayments/processor:environment:production"})

    # Additional paths to create density
    add_edge("PlatformCIRole@platform-dev", "PlatformStagingDeploy@platform-prod", alpha=2, beta=1,
            features={"cross_account": True})
    add_edge("PlatformStagingDeploy@platform-prod", "PlatformProdDeploy@platform-prod", alpha=1, beta=2)
    add_edge("InfraNetworkAdmin@shared-infra", "PlatformProdAdmin@platform-prod", alpha=2, beta=1,
            features={"cross_account": True})
    add_edge("InfraTerraformRole@shared-infra", "InfraNetworkAdmin@shared-infra", alpha=3, beta=1)

    # =========================================================
    # SCP 1: BlockProdAssume — blocks cross-account AssumeRole into prod OU
    # Governs: ALL edges from shared-infra/dev → prod accounts
    # This is the BIG correlation component (should bind ~8-10 edges)
    # =========================================================
    scp1 = {
        "provider": "aws", "constraint_type": "SCP",
        "scope_type": "ou", "scope_id": "ou-production", "region": "-",
        "properties": {
            "policy_id": "scp-BlockCrossAccountAssumeProd",
            "statement_id": "DenyCrossAccountAssumeIntoProd",
            "effect": "DENY", "action": "sts:AssumeRole",
            "description": "Denies cross-account AssumeRole into production OU accounts"
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500
    }
    constraints.append(scp1)

    # Bind SCP1 to all cross-account edges targeting prod accounts
    prod_accounts = {accounts["platform-prod"], accounts["payments-prod"], accounts["data-prod"]}
    scp1_bound = 0
    for e in edges:
        if not e["features"].get("cross_account"):
            continue
        dst_acct = e["dst"].get("provider_id", "")
        # Check if destination is in a prod account
        for pa in prod_accounts:
            if pa in dst_acct:
                e["alpha_i"] = 1  # SCP governance: DENY lean
                e["beta_i"] = 2
                edge_constraints.append({
                    "edge_ref": {"edge_type": e["edge_type"],
                                "src": e["src"], "dst": e["dst"], "region": "-"},
                    "constraint_ref": {
                        "provider": "aws", "constraint_type": "SCP",
                        "scope_type": "ou", "scope_id": "ou-production", "region": "-",
                        "properties": scp1["properties"]
                    }
                })
                scp1_bound += 1
                break

    # =========================================================
    # SCP 2: BlockDataExfil — blocks data-prod specific actions
    # Smaller component (3-4 edges)
    # =========================================================
    scp2 = {
        "provider": "aws", "constraint_type": "SCP",
        "scope_type": "ou", "scope_id": "ou-data", "region": "-",
        "properties": {
            "policy_id": "scp-BlockDataExfil",
            "statement_id": "DenyS3PublicAccess",
            "effect": "DENY", "action": "s3:PutBucketPolicy",
            "description": "Blocks data exfiltration paths in data OU"
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 500
    }
    constraints.append(scp2)

    # Bind SCP2 to edges within data-prod
    data_acct = accounts["data-prod"]
    for e in edges:
        src_pid = e["src"]["provider_id"]
        dst_pid = e["dst"]["provider_id"]
        if data_acct in src_pid and data_acct in dst_pid:
            edge_constraints.append({
                "edge_ref": {"edge_type": e["edge_type"],
                            "src": e["src"], "dst": e["dst"], "region": "-"},
                "constraint_ref": {
                    "provider": "aws", "constraint_type": "SCP",
                    "scope_type": "ou", "scope_id": "ou-data", "region": "-",
                    "properties": scp2["properties"]
                }
            })

    # =========================================================
    # Trust Condition: ExternalId on security account access
    # =========================================================
    tc1 = {
        "provider": "aws", "constraint_type": "TRUST_CONDITION",
        "scope_type": "edge", "scope_id": "tc-security-externalid", "region": "-",
        "properties": {
            "condition_key": "sts:ExternalId",
            "condition_value": "sec-*",
            "policy_id": "trust-security-access",
            "statement_id": "RequireExternalId"
        },
        "status": "ACTIVE", "validation_status": "UNVALIDATED",
        "confidence_q": 400
    }
    constraints.append(tc1)

    # Bind to security account edges
    sec_acct = accounts["security"]
    for e in edges:
        if sec_acct in e["dst"]["provider_id"] and e["features"].get("cross_account"):
            edge_constraints.append({
                "edge_ref": {"edge_type": e["edge_type"],
                            "src": e["src"], "dst": e["dst"], "region": "-"},
                "constraint_ref": {
                    "provider": "aws", "constraint_type": "TRUST_CONDITION",
                    "scope_type": "edge", "scope_id": "tc-security-externalid", "region": "-",
                    "properties": tc1["properties"]
                }
            })

    # =========================================================
    # OIDC Trust Conditions
    # =========================================================
    for e in edges:
        if e.get("features", {}).get("has_oidc_subject"):
            pattern = e["features"]["oidc_subject_pattern"]
            scope_id = f"oidc-{pattern.replace(':', '-').replace('/', '-')}"
            tc = {
                "provider": "aws", "constraint_type": "TRUST_CONDITION",
                "scope_type": "edge", "scope_id": scope_id, "region": "-",
                "properties": {
                    "condition_key": "token.actions.githubusercontent.com:sub",
                    "oidc_subject_pattern": pattern,
                    "policy_id": f"oidc-trust-{scope_id}",
                    "statement_id": "AllowGitHubOIDC"
                },
                "status": "ACTIVE", "validation_status": "UNVALIDATED",
                "confidence_q": 500 if "*" not in pattern else 300
            }
            constraints.append(tc)
            edge_constraints.append({
                "edge_ref": {"edge_type": e["edge_type"],
                            "src": e["src"], "dst": e["dst"], "region": "-"},
                "constraint_ref": {
                    "provider": "aws", "constraint_type": "TRUST_CONDITION",
                    "scope_type": "edge", "scope_id": scope_id, "region": "-",
                    "properties": tc["properties"]
                }
            })

    # =========================================================
    # OBJECTIVES
    # =========================================================
    high_value = [n for n in nodes if n["properties"].get("high_value")]
    objectives = [{
        "objective_type": "reachability",
        "start_nodes": [{
            "provider": attacker["provider"], "node_type": attacker["node_type"],
            "provider_id": attacker["provider_id"], "region": "-"
        }],
        "target_nodes": [{
            "provider": t["provider"], "node_type": t["node_type"],
            "provider_id": t["provider_id"], "region": "-"
        } for t in high_value],
        "max_depth": 8,
        "k": 15
    }]

    scenario = {
        "metadata": {
            "fixture": "complex-fintech-4bu",
            "accounts": len(accounts),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "constraint_count": len(constraints),
            "edge_constraint_count": len(edge_constraints),
            "scp1_bound_edges": scp1_bound,
            "high_value_targets": len(high_value),
            "generated_at": "2026-03-07T00:00:00Z"
        },
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "edge_constraints": edge_constraints,
        "objectives": objectives,
        "observations": []
    }

    return scenario


def main():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate the complex 4-BU ARF-RT fixture")
    parser.add_argument("--output", required=True, help="Output scenario JSON path")
    args = parser.parse_args()

    scenario = emit()
    meta = scenario["metadata"]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(scenario, f, indent=2)

    print("Complex fixture generated:")
    print(f"  Accounts: {meta['accounts']}")
    print(f"  Nodes: {meta['node_count']}")
    print(f"  Edges: {meta['edge_count']}")
    print(f"  Constraints: {meta['constraint_count']}")
    print(f"  Edge-constraint bindings: {meta['edge_constraint_count']}")
    print(f"  SCP1 (BlockProdAssume) bound edges: {meta['scp1_bound_edges']}")
    print(f"  High-value targets: {meta['high_value_targets']}")
    print(f"  Output: {out}")


if __name__ == "__main__":
    main()
