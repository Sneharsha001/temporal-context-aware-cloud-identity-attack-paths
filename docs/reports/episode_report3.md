# ARF-RT Realized Gain Episode Report

**Probe target**: ProdDeploy→ProdApp (SCP correlation group representative)
**Baseline entropy**: 0.3013 nats
**P(allow)**: 0.0115
**EIG**: 0.1209
**Baseline hash**: `638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b`

## Why This Edge

ProdDeploy→ProdApp is the representative of the BlockCrossAccountAssumeProd SCP correlation group (6 edges across production and shared-infra accounts). It already has an observed DENY (α=1, β=86, P(allow)=1.1%). The planner selected it because it has the highest expected entropy reduction — if the SCP is actually not active (ALLOW), all 5 paths to ProdAdmin become viable simultaneously, producing a massive entropy swing that dominates the expectation despite low probability.

---

### Episode: ProdDeploy→ProdApp → DENY

| Metric | Value |
|--------|-------|
| Probe target | ProdDeploy→ProdApp |
| Outcome | DENY |
| H before | 0.3013 |
| H after | 0.1638 |
| **Realized Information Gain (RIG)** | **+0.1375** |
| Expected Information Gain (EIG) | 0.1209 |
| Planner predicted H after | 0.1638 |
| Prediction error | 0.0000 |
| Paths before | 5 |
| Paths after | 5 |
| Representative before | ProdDeploy→ProdApp |
| Representative after | ProdDeploy→ProdApp |
| Representative changed | No |
| Baseline hash | `638b76cd453f2a04565cc40d...` |
| Episode hash | `14d7d3cd5ca23468605b05c1...` |

Entropy decreased by 0.1375 nats — the DENY outcome reduced uncertainty about path viability.
Planner prediction matched deterministic replay (error = 0.0000).

---

### Episode: ProdDeploy→ProdApp → ALLOW

| Metric | Value |
|--------|-------|
| Probe target | ProdDeploy→ProdApp |
| Outcome | ALLOW |
| H before | 0.3013 |
| H after | 1.6094 |
| **Realized Information Gain (RIG)** | **-1.3082** |
| Expected Information Gain (EIG) | 0.1209 |
| Planner predicted H after | 1.6094 |
| Prediction error | 0.0000 |
| Paths before | 5 |
| Paths after | 5 |
| Representative before | ProdDeploy→ProdApp |
| Representative after | ProdDeploy→ProdDBAdmin |
| Representative changed | Yes |
| Baseline hash | `638b76cd453f2a04565cc40d...` |
| Episode hash | `4a3c2c9d2913c04242e4c69f...` |

Entropy increased by 1.3082 nats — the ALLOW outcome was a low-probability surprise that introduced new uncertainty.
Planner prediction matched deterministic replay (error = 0.0000).

---

## Cross-Episode Validation

| Property | Expected | Actual | Status |
|----------|----------|--------|--------|
| DENY reduces entropy | RIG > 0 | RIG = +0.1375 | ✅ |
| ALLOW increases entropy | RIG < 0 | RIG = -1.3082 | ✅ |
| DENY prediction accurate | error < 0.01 | error = 0.0000 | ✅ |
| ALLOW prediction accurate | error < 0.01 | error = 0.0000 | ✅ |
| EIG ≥ 0 (expectation invariant) | True | 0.1209 | ✅ |
| EIG = p·RIG_allow + (1-p)·RIG_deny | 0.1209 | 0.1209 | ✅ |
| DENY keeps representative | unchanged | unchanged | ✅ |
| Baseline not modified | hash stable | hash stable | ✅ |

## What This Proves

These episodes establish **calibration correctness** and **mathematical consistency**:

1. **Exact predictive entropy modeling**: The planner's predicted H_after matches realized H_after to machine precision for both outcomes. This means entropy computation, null complement handling, and fork simulation are faithful.
2. **EIG identity**: EIG = p(allow) × RIG_allow + (1-p) × RIG_deny matches under deterministic replay, confirming branch weighting is correct.
3. **EIG ≥ 0 invariant**: The expected information gain is non-negative, as required by the definition (expected entropy can only decrease or stay the same).
4. **Representative mechanics**: DENY preserves the representative; ALLOW triggers a representative flip to the next-worst edge (ProdDeploy→ProdDBAdmin), which is correct behavior.
5. **Deterministic reproducibility**: Same input → same hash → same entropy → same RIG.

## What This Does Not Yet Prove

These episodes do **not** establish that EIG is the optimal probe selection policy. That requires multi-step comparison against baselines (see Evaluation Report).

## Key Numbers

The planner identified ProdDeploy→ProdApp as the edge with the highest expected entropy reduction. Both forced outcomes confirmed calibration under deterministic replay:

- **DENY** (99% likely): H 0.3013 → 0.1638, RIG = +0.1375, prediction error = 0.0000
- **ALLOW** (1% surprise): H 0.3013 → 1.6094, RIG = -1.3082, prediction error = 0.0000
- **Identity**: 0.0115 × (-1.3082) + 0.9885 × (+0.1375) = 0.1209 = EIG

Baseline entropy under ALLOW = 1.6094 = ln(5) = 1.6094. This follows from ALLOW lifting the SCP block, making all 5 paths equally plausible — the null complement vanishes and entropy reaches its maximum.
