# ARF-RT Analysis Report

## Summary

| Metric | Count |
|--------|-------|
| Nodes | 26 |
| Edges | 41 |
| Constraints | 2 |
| Objectives | 2 |
| Observations | 3 |

## Objective: REACHABILITY

**From:** user/pentester (arn:aws:iam::111111111111:user/pentester)
**To:** role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole)
**Max depth:** 6, **K:** 10

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | MEDIUM | 2 | — |
| 2 | LOW | 2 | — |
| 3 | LOW | 2 | PRIOR_ONLY |
| 4 | VERY_LOW | 4 | — |
| 5 | VERY_LOW | 4 | PRIOR_ONLY |
| 6 | VERY_LOW | 4 | PRIOR_ONLY |

**Path 1** (MEDIUM):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (HYPOTHESIZED)

**Path 2** (LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (CONFIRMED)

**Path 3** (LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/MgmtOpsRole (arn:aws:iam::111111111111:role/MgmtOpsRole) (HYPOTHESIZED)
  2. role/MgmtOpsRole (arn:aws:iam::111111111111:role/MgmtOpsRole) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (HYPOTHESIZED)

**Path 4** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) (HYPOTHESIZED)
  4. role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (HYPOTHESIZED)

**Path 5** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) (HYPOTHESIZED)
  4. role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (HYPOTHESIZED)

**Path 6** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/DevBuildRunner (arn:aws:iam::222222222222:role/DevBuildRunner) (HYPOTHESIZED)
  3. role/DevBuildRunner (arn:aws:iam::222222222222:role/DevBuildRunner) →[sts:AssumeRole]→ role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) (HYPOTHESIZED)
  4. role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) →[sts:AssumeRole]→ role/BillingAdminRole (arn:aws:iam::333333333333:role/BillingAdminRole) (HYPOTHESIZED)


## Objective: REACHABILITY

**From:** user/pentester (arn:aws:iam::111111111111:user/pentester)
**To:** role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole)
**Max depth:** 8, **K:** 10

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | LOW | 3 | — |
| 2 | LOW | 3 | — |
| 3 | VERY_LOW | 3 | PRIOR_ONLY |
| 4 | VERY_LOW | 3 | PRIOR_ONLY |
| 5 | VERY_LOW | 4 | — |
| 6 | VERY_LOW | 4 | — |
| 7 | VERY_LOW | 4 | — |
| 8 | VERY_LOW | 4 | PRIOR_ONLY |
| 9 | VERY_LOW | 4 | PRIOR_ONLY |
| 10 | VERY_LOW | 4 | PRIOR_ONLY |

**Path 1** (LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  3. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 2** (LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) (HYPOTHESIZED)
  3. role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 3** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  3. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 4** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/MgmtOpsRole (arn:aws:iam::111111111111:role/MgmtOpsRole) (HYPOTHESIZED)
  2. role/MgmtOpsRole (arn:aws:iam::111111111111:role/MgmtOpsRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  3. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 5** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  3. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) (HYPOTHESIZED)
  4. role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 6** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) (HYPOTHESIZED)
  4. role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) →[lambda:InvokeFunction]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 7** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) (CONFIRMED)
  2. role/DevJumpRole (arn:aws:iam::222222222222:role/DevJumpRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  4. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 8** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) (HYPOTHESIZED)
  4. role/SharedLambdaDeploy (arn:aws:iam::222222222222:role/SharedLambdaDeploy) →[lambda:InvokeFunction]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 9** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) (HYPOTHESIZED)
  3. role/DevDeployRole (arn:aws:iam::222222222222:role/DevDeployRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  4. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)

**Path 10** (VERY_LOW):
  1. user/pentester (arn:aws:iam::111111111111:user/pentester) →[sts:AssumeRole]→ role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) (HYPOTHESIZED)
  2. role/DevCIRole (arn:aws:iam::222222222222:role/DevCIRole) →[sts:AssumeRole]→ role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) (HYPOTHESIZED)
  3. role/ProdDeployRole (arn:aws:iam::333333333333:role/ProdDeployRole) →[sts:AssumeRole]→ role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) (HYPOTHESIZED)
  4. role/ProdDBRole (arn:aws:iam::333333333333:role/ProdDBRole) →[sts:AssumeRole]→ role/ProdAdminRole (arn:aws:iam::333333333333:role/ProdAdminRole) (HYPOTHESIZED)


## Evidence Coverage

**3** of **41** edges observed with DIRECT/DETERMINISTIC non-counterfactual evidence (**7%**).

## Constraint Validation

| Status | Count |
|--------|-------|
| UNVALIDATED | 1 |
| VALIDATED | 1 |
