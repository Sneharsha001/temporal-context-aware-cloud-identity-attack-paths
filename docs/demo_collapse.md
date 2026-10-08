# ARF-RT Demo: Policy-Aware Attack Path Analysis

## What This Shows

PMapper identifies structurally reachable paths between AWS principals —
every way one IAM entity could pivot to another based on permissions alone.
ARF-RT extends this by applying organization policy semantics (SCPs, trust
conditions) and Bayesian correlation, filtering structural reachability down
to policy-viable paths with calibrated probability estimates.

## Environment

| | Detail |
|---|---|
| Accounts | 2 (dev: `100000000001`, prod: `200000000002`) |
| Principals | 5 (1 user, 4 roles across both accounts) |
| Structural edges | 5 (all `sts:AssumeRole`) |
| SCPs | 3 attached (2 unconditional, 1 conditional) |
| Observations | 5 probes (4 ALLOW, 1 CONSTRAINT_DENY) |
| Objective | attacker (dev) → ProdAdmin (prod) |

## Constraint Resolution (Automatic)

ARF-RT automatically resolved the following from the AWS Organizations export:

**1 SCP constraint(s) → 3 edge-constraint linkage(s)**

| SCP | Attached To | Denied Actions | Edges Affected |
|---|---|---|---|
| BlockAssumeRoleInProd | ou-prod | sts:AssumeRole | ProdDeploy→ProdDB, ProdDeploy→ProdAdmin, ProdDB→ProdAdmin |

**Skipped (conservative):** BlockAssumeUnlessVPN — denies `sts:AssumeRole` with
IP condition (`NotIpAddress: 10.0.0.0/8`). ARF-RT does not evaluate conditions;
the path remains open rather than risk a false negative. This is documented in
the import warnings.

## Edge Beliefs After Observation

| Edge | α | β | P(traverse) | Status | Source |
|---|---|---|---|---|---|
| attacker → JumpRole | 166 | 1 | 99.4% | CONFIRMED | 2× ALLOW probes |
| JumpRole → ProdDeploy | 162 | 1 | 99.4% | CONFIRMED | 2× ALLOW probes |
| ProdDeploy → ProdDB | 1 | 91 | 1.1% | REFUTED | 1× CONSTRAINT_DENY |
| ProdDeploy → ProdAdmin | 1 | 1 | 50.0% | HYPOTHESIZED | Prior only (unprobed) |
| ProdDB → ProdAdmin | 1 | 1 | 50.0% | HYPOTHESIZED | Prior only (unprobed) |

## Correlation

The SCP **BlockAssumeRoleInProd** governs all three edges within the prod account.
These edges form a **correlation group**: if the SCP blocks `sts:AssumeRole` for one,
it blocks it for all. The engine selects the edge with the lowest posterior probability
(strongest evidence of blockage) as the group representative. Representative selection
is deterministic and based on integer cross-multiply comparison; ties are resolved by
stable edge ordering.

| Edge | In SCP Group | Representative |
|---|---|---|
| ProdDeploy → ProdDB | ✓ | **Yes** (observed deny) |
| ProdDeploy → ProdAdmin | ✓ | No |
| ProdDB → ProdAdmin | ✓ | No |

**Representative:** ProdDeploy → ProdDB (α=1, β=91, P=1.1%)

When computing path probability through any edge in this group, the engine uses the
representative's probability (1.1%) instead of the edge's independent belief.
This is because the SCP is a shared structural control — observing it block one
edge is evidence that it blocks all edges it governs.

## Results

### Naive vs. Policy-Aware Comparison

The direct path (attacker → JumpRole → ProdDeploy → ProdAdmin):

| Analysis | Probability | Method |
|---|---|---|
| Structural (naive) | **49.4%** | Independent edge multiplication |
| Policy-aware (ARF-RT) | **1.07%** | SCP correlation with observed deny |
| **Reduction** | **46×** | |

### Paths Found

| Rank | Path | Hops | Correlated P | Band |
|---|---|---|---|---|
| 1 | attacker→JumpRole → JumpRole→ProdDeploy → ProdDeploy→ProdAdmin | 3 | 1.07% | VERY_LOW |
| 2 | attacker→JumpRole → JumpRole→ProdDeploy → ProdDeploy→ProdDB → ProdDB→ProdAdmin | 4 | 1.07% | VERY_LOW |

### Why the Collapse Happens

Naive analysis multiplies each edge's independent probability:
99.4% × 99.4% × 50.0% = **49.4%**

The 50% comes from ProdDeploy → ProdAdmin having no observations (uniform prior).
A structural tool would flag this as a significant risk path.

Policy-aware analysis recognizes that ProdDeploy → ProdAdmin shares an SCP with
ProdDeploy → ProdDB. ProdDeploy → ProdDB was probed and denied. Because the SCP
is a single policy control, that denial is evidence against all edges it governs:
99.4% × 99.4% × 1.1% = **1.07%**

The unprobed edge inherits the probed edge's evidence through their shared
constraint — not because they are similar, but because they are governed by
the same policy. This models shared control dependency, not statistical similarity.

## Limitations

- Only explicit `Deny` statements in SCPs are modeled. `Allow` statements and permission boundaries are not evaluated.
- SCP conditions (e.g., IP restrictions, VPC endpoints) are detected but not evaluated. Conditional denies are reported as warnings and the path remains open (conservative bias).
- If a constraint cannot be parsed with certainty (e.g., `NotAction`, complex resource patterns), it is not applied. False negatives (path stays open) are preferred over false positives (path incorrectly closed).
- Trust policy conditions (ExternalId, PrincipalOrgID, MFA) are detected and modeled as constraints, but the engine does not evaluate whether a given caller satisfies the condition — it flags the condition's existence.

## Reproducibility

All values in this report are generated from the engine, not hand-computed.
The pipeline is deterministic: identical inputs produce identical outputs
(verified by hash comparison across multiple runs). The golden test suite
(`tests/golden/test_demo_collapse.py`, 26 tests) pins every value shown above.

---

*Generated by ARF-RT from PMapper graph + AWS Organizations export.*
*Fixture: tests/fixtures/demo_pmapper_graph.json + tests/fixtures/demo_aws_org.json*
