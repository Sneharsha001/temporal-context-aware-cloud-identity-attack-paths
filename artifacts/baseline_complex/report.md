# ARF-RT Analysis Report

## Summary

| Metric | Count |
|--------|-------|
| Nodes | 24 |
| Edges | 33 |
| Constraints | 6 |
| Objectives | 1 |
| Observations | 0 |

## Objective: reachability

**From:** attacker-dev (platform-dev)
**To:** PlatformProdAdmin (platform-prod), DataLakeAdmin (data-prod), SecurityAdmin (security), PaymentProdAdmin (payments-prod)
**Max depth:** 8, **K:** 15

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | LOW | 3 | PRIOR_ONLY |
| 2 | VERY_LOW | 3 | PRIOR_ONLY |
| 3 | VERY_LOW | 3 | PRIOR_ONLY |
| 4 | VERY_LOW | 3 | PRIOR_ONLY |
| 5 | VERY_LOW | 4 | PRIOR_ONLY |
| 6 | VERY_LOW | 4 | PRIOR_ONLY |
| 7 | VERY_LOW | 4 | PRIOR_ONLY |
| 8 | VERY_LOW | 4 | PRIOR_ONLY |
| 9 | VERY_LOW | 4 | PRIOR_ONLY |
| 10 | VERY_LOW | 4 | PRIOR_ONLY |
| 11 | VERY_LOW | 4 | PRIOR_ONLY |
| 12 | VERY_LOW | 4 | PRIOR_ONLY |
| 13 | VERY_LOW | 4 | PRIOR_ONLY |
| 14 | VERY_LOW | 5 | PRIOR_ONLY |
| 15 | VERY_LOW | 4 | PRIOR_ONLY |

**Path 1** (LOW):
  1. attacker-dev (platform-dev) →[repo:Write]→ AcmePlatform/api:actions (HYPOTHESIZED)
  2. AcmePlatform/api:actions →[oidc:AssumeRole]→ PlatformProdDeploy (platform-prod) (HYPOTHESIZED)
  3. PlatformProdDeploy (platform-prod) →[sts:AssumeRole_permission]→ PlatformProdAdmin (platform-prod) (HYPOTHESIZED)

**Path 2** (VERY_LOW):
  1. attacker-dev (platform-dev) →[repo:Write]→ AcmePlatform/infra:actions (HYPOTHESIZED)
  2. AcmePlatform/infra:actions →[oidc:AssumeRole]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  3. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ DataLakeAdmin (data-prod) (HYPOTHESIZED)

**Path 3** (VERY_LOW):
  1. attacker-dev (platform-dev) →[repo:Write]→ AcmePlatform/infra:actions (HYPOTHESIZED)
  2. AcmePlatform/infra:actions →[oidc:AssumeRole]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  3. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PlatformProdAdmin (platform-prod) (HYPOTHESIZED)

**Path 4** (VERY_LOW):
  1. attacker-dev (platform-dev) →[repo:Write]→ AcmePlatform/infra:actions (HYPOTHESIZED)
  2. AcmePlatform/infra:actions →[oidc:AssumeRole]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  3. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PaymentProdAdmin (payments-prod) (HYPOTHESIZED)

**Path 5** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ DataLakeAdmin (data-prod) (HYPOTHESIZED)

**Path 6** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PlatformProdAdmin (platform-prod) (HYPOTHESIZED)

**Path 7** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PaymentProdAdmin (payments-prod) (HYPOTHESIZED)

**Path 8** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformCIRole (platform-dev) (HYPOTHESIZED)
  2. PlatformCIRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ DataLakeAdmin (data-prod) (HYPOTHESIZED)

**Path 9** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformCIRole (platform-dev) (HYPOTHESIZED)
  2. PlatformCIRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PlatformProdAdmin (platform-prod) (HYPOTHESIZED)

**Path 10** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformCIRole (platform-dev) (HYPOTHESIZED)
  2. PlatformCIRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ InfraTerraformRole (shared-infra) (HYPOTHESIZED)
  4. InfraTerraformRole (shared-infra) →[sts:AssumeRole_permission]→ PaymentProdAdmin (payments-prod) (HYPOTHESIZED)

**Path 11** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ PaymentProcessorRole (payments-prod) (HYPOTHESIZED)
  4. PaymentProcessorRole (payments-prod) →[sts:AssumeRole_permission]→ PaymentProdAdmin (payments-prod) (HYPOTHESIZED)

**Path 12** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ DataPipelineRole (data-prod) (HYPOTHESIZED)
  4. DataPipelineRole (data-prod) →[sts:AssumeRole_permission]→ DataLakeAdmin (data-prod) (HYPOTHESIZED)

**Path 13** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ PlatformProdDeploy (platform-prod) (HYPOTHESIZED)
  4. PlatformProdDeploy (platform-prod) →[sts:AssumeRole_permission]→ PlatformProdAdmin (platform-prod) (HYPOTHESIZED)

**Path 14** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformDevRole (platform-dev) (HYPOTHESIZED)
  2. PlatformDevRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ DataPipelineRole (data-prod) (HYPOTHESIZED)
  4. DataPipelineRole (data-prod) →[sts:AssumeRole_permission]→ GlueJobRole (data-prod) (HYPOTHESIZED)
  5. GlueJobRole (data-prod) →[sts:AssumeRole_permission]→ DataLakeAdmin (data-prod) (HYPOTHESIZED)

**Path 15** (VERY_LOW):
  1. attacker-dev (platform-dev) →[sts:AssumeRole_permission]→ PlatformCIRole (platform-dev) (HYPOTHESIZED)
  2. PlatformCIRole (platform-dev) →[sts:AssumeRole_permission]→ InfraJumpRole (shared-infra) (HYPOTHESIZED)
  3. InfraJumpRole (shared-infra) →[sts:AssumeRole_permission]→ PaymentProcessorRole (payments-prod) (HYPOTHESIZED)
  4. PaymentProcessorRole (payments-prod) →[sts:AssumeRole_permission]→ PaymentProdAdmin (payments-prod) (HYPOTHESIZED)


## Evidence Coverage

**0** of **33** edges observed with DIRECT/DETERMINISTIC non-counterfactual evidence (**0%**).

## Constraint Validation

| Status | Count |
|--------|-------|
| UNVALIDATED | 6 |
