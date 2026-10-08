# ARF-RT Realized Gain Episode Report

**Probe target**: ProdDeploy→ProdApp (SCP correlation group representative)
**Baseline entropy**: 0.3013 nats
**P(allow)**: 0.0115
**EIG**: 0.1209
**Baseline hash**: `638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b`

## Why This Edge

ProdDeploy→ProdApp is the representative of the BlockCrossAccountAssumeProd SCP correlation group (6 edges across production and shared-infra accounts). It already has an observed DENY (α=1, β=86, P(allow)=1.1%). The planner selected it because its outcome has the highest leverage on path uncertainty — if the SCP is actually not active (ALLOW), all 5 paths to ProdAdmin become viable simultaneously.

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

Entropy increased by 1.3082 nats — the ALLOW outcome introduced new uncertainty (more paths became plausible).
Planner prediction matched deterministic replay (error = 0.0000).

---

## Cross-Episode Validation

| Property | Expected | Actual | Status |
|----------|----------|--------|--------|
| DENY reduces entropy | RIG > 0 | RIG = +0.1375 | ✅ |
| ALLOW increases entropy | RIG < 0 | RIG = -1.3082 | ✅ |
| DENY prediction accurate | error < 0.01 | error = 0.0000 | ✅ |
| ALLOW prediction accurate | error < 0.01 | error = 0.0000 | ✅ |
| EIG = p·RIG_allow + (1-p)·RIG_deny | 0.1209 | 0.1209 | ✅ |
| DENY keeps representative | unchanged | unchanged | ✅ |
| Baseline not modified | hash stable | hash stable | ✅ |

## Interpretation

The planner predicted that probing ProdDeploy→ProdApp would reduce expected entropy by 0.1209 nats (EIG). Both forced outcomes validated the prediction:

When the probe returned **DENY** (99% likely given current beliefs), entropy dropped from 0.3013 to 0.1638 — the system became more certain that the SCP blocks all production paths. The realized gain (+0.1375) matched the planner's prediction within 0.0000 nats.

When the probe returned **ALLOW** (1% likely — a surprise), entropy jumped from 0.3013 to 1.6094 — suddenly all 5 paths became viable, massively increasing uncertainty. The realized gain (-1.3082) again matched prediction within 0.0000 nats.

The mathematical identity EIG = p(allow)·RIG_allow + (1-p)·RIG_deny matched under deterministic replay: 0.0115 × -1.3082 + 0.9885 × +0.1375 = 0.1209 ≈ EIG 0.1209.

**The planner correctly identified the single edge whose outcome most changes uncertainty about path viability. Realized outcomes matched predicted direction and magnitude.**
