# ARF-RT Analysis Report

## Summary

| Metric | Count |
|--------|-------|
| Nodes | 14 |
| Edges | 16 |
| Constraints | 4 |
| Objectives | 1 |
| Observations | 11 |

## Objective: REACHABILITY

**From:** attacker
**To:** ProdAdmin
**Max depth:** 8, **K:** 5

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | VERY_LOW | 4 | — |
| 2 | VERY_LOW | 6 | — |
| 3 | VERY_LOW | 6 | — |
| 4 | VERY_LOW | 6 | — |
| 5 | VERY_LOW | 6 | — |

**Path 1** (VERY_LOW):
  1. attacker →[sts:AssumeRole_permission]→ EC2Bastion (CONFIRMED)
  2. EC2Bastion →[sts:AssumeRole_permission]→ SharedInfra (CONFIRMED)
  3. SharedInfra →[sts:AssumeRole_permission]→ SharedSecrets (HYPOTHESIZED)
  4. SharedSecrets →[sts:AssumeRole_permission]→ ProdAdmin (HYPOTHESIZED)

**Path 2** (VERY_LOW):
  1. attacker →[sts:AssumeRole_permission]→ DevOps (CONFIRMED)
  2. DevOps →[sts:AssumeRole_permission]→ CI-Runner (CONFIRMED)
  3. CI-Runner →[sts:AssumeRole_permission]→ StagingDeploy (CONFIRMED)
  4. StagingDeploy →[sts:AssumeRole_permission]→ ProdDeploy (CONFIRMED)
  5. ProdDeploy →[sts:AssumeRole_permission]→ ProdApp (REFUTED)
  6. ProdApp →[sts:AssumeRole_permission]→ ProdAdmin (HYPOTHESIZED)

**Path 3** (VERY_LOW):
  1. attacker →[sts:AssumeRole_permission]→ DevOps (CONFIRMED)
  2. DevOps →[sts:AssumeRole_permission]→ CI-Runner (CONFIRMED)
  3. CI-Runner →[sts:AssumeRole_permission]→ StagingDeploy (CONFIRMED)
  4. StagingDeploy →[sts:AssumeRole_permission]→ ProdDeploy (CONFIRMED)
  5. ProdDeploy →[sts:AssumeRole_permission]→ ProdDBAdmin (HYPOTHESIZED)
  6. ProdDBAdmin →[sts:AssumeRole_permission]→ ProdAdmin (HYPOTHESIZED)

**Path 4** (VERY_LOW):
  1. attacker →[sts:AssumeRole_permission]→ DevOps (CONFIRMED)
  2. DevOps →[sts:AssumeRole_permission]→ LambdaDeploy (CONFIRMED)
  3. LambdaDeploy →[sts:AssumeRole_permission]→ StagingDeploy (CONFIRMED)
  4. StagingDeploy →[sts:AssumeRole_permission]→ ProdDeploy (CONFIRMED)
  5. ProdDeploy →[sts:AssumeRole_permission]→ ProdApp (REFUTED)
  6. ProdApp →[sts:AssumeRole_permission]→ ProdAdmin (HYPOTHESIZED)

**Path 5** (VERY_LOW):
  1. attacker →[sts:AssumeRole_permission]→ DevOps (CONFIRMED)
  2. DevOps →[sts:AssumeRole_permission]→ LambdaDeploy (CONFIRMED)
  3. LambdaDeploy →[sts:AssumeRole_permission]→ StagingDeploy (CONFIRMED)
  4. StagingDeploy →[sts:AssumeRole_permission]→ ProdDeploy (CONFIRMED)
  5. ProdDeploy →[sts:AssumeRole_permission]→ ProdDBAdmin (HYPOTHESIZED)
  6. ProdDBAdmin →[sts:AssumeRole_permission]→ ProdAdmin (HYPOTHESIZED)


## Evidence Coverage

**10** of **16** edges observed with DIRECT/DETERMINISTIC non-counterfactual evidence (**62%**).

## Constraint Validation

| Status | Count |
|--------|-------|
| UNVALIDATED | 2 |
| VALIDATED | 2 |
