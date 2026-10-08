# ARF-RT Paper Reproduction Results

- Diamond: 0.551865 -> 0.012055, ratio 45.78x
- Primary Table I reproduces exactly @5: EIG=0.2361, random=0.0119, uncertainty=0.0134, centrality=-0.0033
- Ratios: EIG/random=19.84x, EIG/uncertainty=17.63x
- Fork-replay hardening corrected complex fixture values: nodes=24, edges=33, constraints=6, paths=15, entropy=2.7008; complex top SCP component remains the dominant recommendation with corrected complex top EIG ≈ 1.072
- Complex after-DENY (current hardened engine, full Top-K): H=2.7008->1.0922; corrected after-DENY reduction is about 60% (camera-ready text reports rounded 0.64/76%; see README Reconciliation)
- OIDC enriched entropy=1.2130, path probabilities=[0.375, 0.333333, 0.25]

## Known limits
- Complex Table IV: fork-replay hardening corrected complex fixture values. The corrected complex top EIG ≈ 1.072, the complex top SCP component remains the dominant recommendation, and the corrected after-DENY reduction is about 60% after preserving non-uniform fixture priors during fork replay. Camera-ready text reports rounded 0.64 / 76%; do not present v1.2 as reproducing that value. See README Reconciliation section for analysis. Legacy truncation/uniform-prior exploration remains diagnostic only.
- 250k-edge runtime: 250k runtime remains hardware/topology-dependent and does not reproduce the camera-ready 40ms / <2s claim. Current post-fix measurements on the generated 250k medium fixture are about 31.7 s analyze and about 290 s planner internal time / 352 s wall time over 18 candidates and 36 forks. Table II 100/1k/10k scaling snapshot is part of the core reproduced results.
- Independent-control §VII-E supports uncertainty-like behavior: with uniform priors and no observations, EIG/uncertainty = 1.11x at step 5, near the paper's equality claim but not an exact-equality reproduction (small residual from EIG path-aware lookahead).
- Primary Table I reproduction uses the canonical fixture builder from tests/golden/test_eval.py to avoid divergent fixture copies.
- §VII-A canonical_run_hash differs from camera-ready (448661e2... vs 638b76cd...) due to non-pinnable serialization details; core reported quantitative metrics match.
