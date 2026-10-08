# ARF-RT Analysis Report

**Objective**: Can `attacker` reach `ProdAdmin`?

## Environment

| Metric | Value |
|--------|-------|
| Principals | 14 |
| Edges | 16 |
| SCP Constraints | 2 |
| Trust Conditions | 2 |
| Observations | 11 |

## Constraints

**BlockIAMWriteStaging** (SCP, attached to ou-staging, 1 edge linkage)
- Denied actions: iam:CreateAccessKey, iam:CreateUser, iam:AttachRolePolicy

**BlockCrossAccountAssumeProd** (SCP, attached to ou-prod, 6 edge linkages)
- Denied actions: sts:AssumeRole

**ProdDeploy** (Trust condition, 1 edge linkage)
- Requires: sts:ExternalId = ['prod-deploy-xid-9281']

**SharedInfra** (Trust condition, 1 edge linkage)
- Requires: aws:PrincipalOrgID = ['o-realdemo1']

## Edge Beliefs

| Source | Target | α | β | P(allow) | Status |
|--------|--------|---|---|----------|--------|
| CI-Runner | StagingDeploy | 86 | 1 | 98.9% | CONFIRMED |
| DevOps | CI-Runner | 81 | 1 | 98.8% | CONFIRMED |
| DevOps | LambdaDeploy | 77 | 1 | 98.7% | CONFIRMED |
| EC2Bastion | SharedInfra | 48 | 1 | 98.0% | CONFIRMED |
| LambdaDeploy | StagingDeploy | 81 | 1 | 98.8% | CONFIRMED |
| attacker | DevOps | 176 | 1 | 99.4% | CONFIRMED |
| attacker | EC2Bastion | 67 | 1 | 98.5% | CONFIRMED |
| StagingDeploy | StagingAdmin | 1 | 91 | 1.1% | REFUTED |
| StagingDeploy | StagingDB | 1 | 1 | 50.0% | HYPOTHESIZED |
| StagingDeploy | ProdDeploy | 58 | 1 | 98.3% | CONFIRMED |
| ProdApp | ProdAdmin | 1 | 1 | 50.0% | HYPOTHESIZED |
| ProdDBAdmin | ProdAdmin | 1 | 1 | 50.0% | HYPOTHESIZED |
| ProdDeploy | ProdApp | 1 | 86 | 1.1% | REFUTED |
| ProdDeploy | ProdDBAdmin | 1 | 1 | 50.0% | HYPOTHESIZED |
| SharedInfra | SharedSecrets | 1 | 1 | 50.0% | HYPOTHESIZED |
| SharedSecrets | ProdAdmin | 1 | 1 | 50.0% | HYPOTHESIZED |

## Correlation Groups

**SCP: BlockCrossAccountAssumeProd** (6 edges)
- Representative: ProdDeploy→ProdApp
- Members: ProdDeploy→ProdApp, ProdDeploy→ProdDBAdmin, SharedSecrets→ProdAdmin, ProdDBAdmin→ProdAdmin, ProdApp→ProdAdmin, SharedInfra→SharedSecrets
- Shared SCP governance — edges in this component share the same Service Control Policy; p_worst uses the component representative.

**SCP: BlockIAMWriteStaging** (1 edge)
- Representative: StagingDeploy→StagingAdmin
- Members: StagingDeploy→StagingAdmin
- Shared SCP governance — edges in this component share the same Service Control Policy; p_worst uses the component representative.

**Trust: ProdDeploy ExternalId** (1 edge)
- Representative: StagingDeploy→ProdDeploy
- Members: StagingDeploy→ProdDeploy
- Shared trust condition — edges in this component share the same trust policy constraint; p_worst uses the component representative.

**Trust: SharedInfra PrincipalOrgID** (1 edge)
- Representative: EC2Bastion→SharedInfra
- Members: EC2Bastion→SharedInfra
- Shared trust condition — edges in this component share the same trust policy constraint; p_worst uses the component representative.

## Paths Found

**Rank 1**: p_worst = 1.11%
- attacker→EC2Bastion → EC2Bastion→SharedInfra → SharedInfra→SharedSecrets → SharedSecrets→ProdAdmin

**Rank 2**: p_worst = 1.10%
- attacker→DevOps → DevOps→CI-Runner → CI-Runner→StagingDeploy → StagingDeploy→ProdDeploy → ProdDeploy→ProdApp → ProdApp→ProdAdmin

**Rank 3**: p_worst = 1.10%
- attacker→DevOps → DevOps→CI-Runner → CI-Runner→StagingDeploy → StagingDeploy→ProdDeploy → ProdDeploy→ProdDBAdmin → ProdDBAdmin→ProdAdmin

**Rank 4**: p_worst = 1.10%
- attacker→DevOps → DevOps→LambdaDeploy → LambdaDeploy→StagingDeploy → StagingDeploy→ProdDeploy → ProdDeploy→ProdApp → ProdApp→ProdAdmin

**Rank 5**: p_worst = 1.10%
- attacker→DevOps → DevOps→LambdaDeploy → LambdaDeploy→StagingDeploy → StagingDeploy→ProdDeploy → ProdDeploy→ProdDBAdmin → ProdDBAdmin→ProdAdmin

## Probe Recommendations

Baseline entropy: 0.3013 nats | 14 candidates | 28 pipeline forks | 104.9ms

**#1: ProdDeploy→ProdApp** (EIG = 0.1170)
- P(allow) = 0.01 | H if ALLOW = 1.6094 | H if DENY = 0.1677
- Why: appears on a Top-K path, in SCP correlation component, current correlation group representative, no timestamp on last observation

**#2: ProdDeploy→ProdDBAdmin** (EIG = 0.0067)
- P(allow) = 0.50 | H if ALLOW = 0.3013 | H if DENY = 0.2879
- Why: appears on a Top-K path, in SCP correlation component, high uncertainty (p=0.50, α≈β), never directly probed

**#3: SharedSecrets→ProdAdmin** (EIG = 0.0067)
- P(allow) = 0.50 | H if ALLOW = 0.3013 | H if DENY = 0.2879
- Why: appears on a Top-K path, in SCP correlation component, high uncertainty (p=0.50, α≈β), never directly probed

**#4: ProdDBAdmin→ProdAdmin** (EIG = 0.0067)
- P(allow) = 0.50 | H if ALLOW = 0.3013 | H if DENY = 0.2879
- Why: appears on a Top-K path, in SCP correlation component, high uncertainty (p=0.50, α≈β), never directly probed

**#5: ProdApp→ProdAdmin** (EIG = 0.0067)
- P(allow) = 0.50 | H if ALLOW = 0.3013 | H if DENY = 0.2879
- Why: appears on a Top-K path, in SCP correlation component, high uncertainty (p=0.50, α≈β), never directly probed

### Component Summary

| Component | Edges | Best Probe | EIG |
|-----------|-------|------------|-----|
| SCP: BlockCrossAccountAssumeProd | 6 | ProdDeploy→ProdApp | 0.1170 |
| Trust: ProdDeploy ExternalId | 1 | StagingDeploy→ProdDeploy | 0.0002 |
| Trust: SharedInfra PrincipalOrgID | 1 | EC2Bastion→SharedInfra | 0.0001 |
| Uncorrelated: DevOps→LambdaDeploy | 1 | DevOps→LambdaDeploy | 0.0001 |
| Uncorrelated: DevOps→CI-Runner | 1 | DevOps→CI-Runner | 0.0000 |
| Uncorrelated: LambdaDeploy→StagingDeploy | 1 | LambdaDeploy→StagingDeploy | 0.0000 |
| Uncorrelated: CI-Runner→StagingDeploy | 1 | CI-Runner→StagingDeploy | 0.0000 |
| Uncorrelated: attacker→EC2Bastion | 1 | attacker→EC2Bastion | 0.0000 |
| Uncorrelated: attacker→DevOps | 1 | attacker→DevOps | 0.0000 |

## Executor Audit Log

Mode: DRY_RUN | Run hash: `638b76cd453f2a04565cc40d...` | 14 probes logged

## Reproducibility

Pipeline hash: `638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b`. Deterministic. Decay not active (no `--as-of`).