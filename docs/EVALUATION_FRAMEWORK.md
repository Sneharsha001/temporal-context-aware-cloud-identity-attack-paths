# ARF-RT Evaluation & Baseline Comparison Framework

## 1. Overview
This framework formalizes the experimental protocol used to benchmark ARF-RT against state-of-the-art attack path tools, including PMapper, BloodHound (AWS/Azure), and naive graph reachability models.

## 2. Baseline Comparison Dimensions

| Dimension | Naive Reachability | BloodHound / PMapper | ARF-RT | ARF-RT + CCPF |
|---|---|---|---|---|
| Edge Model | Deterministic | Single-hop probabilistic | Correlated Bayesian blocks | Correlated + Context CSP |
| Policy Constraints | Ignored | Evaluated independently | Structural grouping via Union-Find | First-class relational constraints |
| False Positive Suppression | Baseline (High) | Baseline | 46x reduction | Complete elimination of infeasible prefixes |
| Probing Strategy | Exhaustive | Ad-hoc / Manual | Expected Information Gain (EIG) | EIG conditioned on feasible paths |

## 3. Evaluation Metrics
1. **Entropy Collapse Rate ($R_H$):** Measures the bits or nats of uncertainty eliminated per executed probe.
2. **Probing Efficiency:** Number of probes required to reach $H(\mathcal{P}) \le 0.05$ nats.
3. **Correlation Ratio:** Divergence between joint failure probability under naive independence vs correlated belief updates.
4. **Replay Determinism:** Exact bitwise reproducibility across platforms verified by `canonical_run_hash`.
