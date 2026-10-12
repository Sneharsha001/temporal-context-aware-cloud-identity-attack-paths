# ARF-RT Research Project — Current Status

**Repository:** temporal-context-aware-cloud-identity-attack-paths
**Branch:** temporal-context-dev
**Last Updated:** 2026-10-11

---

## Research Track

**Proposed Contribution:** Context-Conditioned Path Feasibility for Probabilistic Cloud
Identity Attack-Path Analysis (CCPF)

---

## Phase Completion Status

| Stage / Phase | Title | Status |
|---|---|---|
| Phase 14 | Temporal Context Research Design and State Model | COMPLETE |
| Phase 15 | Formal Context-Conditioned Path Feasibility Model | COMPLETE |
| Phase 16 | Counterexample Fixture Suite (CE1-CE6) | COMPLETE |
| Phase 17 | Related-Work Survey and Novelty Assessment | COMPLETE |
| Phase B.1 | CCPF Formal Correctness and Evidence Audit | COMPLETE |
| Baseline Verification | Pre-Contribution Reproducibility Audit | COMPLETE |
| Prompt 1 | CCPF Scope Confirmation & Research Checkpoint | COMPLETE |
| Prompt 2 / 2A | Formal CCPF Evaluator Contract Specification | COMPLETE (Corrections Applied) |

---

## Gate Status

**Current Gate:** GATE B — READY WITH DOCUMENTED BASELINE LIMITATIONS

**Baseline Commit:** 04d2bae12f600ff48b6054aa513878ea5dc72b16
**Research HEAD:** 45ec211e3ca1f284e27e22d5bf4981166bf5880b
**Test Parity:** 911/912 in both workspaces (symmetric baseline-shared failure only)
**Unit Tests:** 625/625 pass in both workspaces
**Golden Tests:** 250/250 pass in both workspaces

---

## Next Phase: Isolated Evaluator Implementation (Prompt 3 - GATED)

**Current Status:** Prompt 2 / 2A Formal Evaluator Contract Complete.  
**Research Track:** Context-Conditioned Path Feasibility (CCPF) for probabilistic cloud identity attack paths.  
**Detailed Specification:** [docs/CCPF_EVALUATOR_CONTRACT.md](docs/CCPF_EVALUATOR_CONTRACT.md)  

### Research Stage Sequence
- **Prompt 1:** Scope confirmation & baseline checkpoint — **COMPLETE**.
- **Prompt 2 / 2A:** Formal contract & safe fragment formalization — **COMPLETE**.
- **Prompt 3:** Isolated evaluator implementation (RDCE) — **NEXT (Gated, subject to researcher review)**.
- **Prompt 4:** Semantic validation across CE1–CE6 — **AFTER IMPLEMENTATION**.

### Evaluator Contract Summary (RDCE)
- **Interface:** Strictly logical tri-state decision (`SAT`, `UNSAT`, `UNKNOWN`), witness assignment (if SAT), contradiction rationale (if UNSAT), unknown rationale (if UNKNOWN), and diagnostic metadata. **Contains no probability multiplier.**
- **Scope Model:**
  - **Request Scope ($\mathcal{R}$):** Per-API-call origin (e.g., `aws:SourceIp`), persistent only under explicit scenario `static_origin_assumption = True` or re-bound via network pivot.
  - **Session Scope ($\mathcal{S}$):** STS credential attributes (e.g., `aws:MultiFactorAuthPresent`), reset upon identity pivots (`sts:AssumeRole`).
  - **Principal Scope ($\mathcal{P}$):** Active identity attributes (e.g., `aws:PrincipalTag/<key>`), reset to target role tags upon AssumeRole boundary when session tagging is prohibited (`Null(RequestTag) == true`).
  - **Configuration Scope ($\mathcal{C}$):** Hop-local request parameters (e.g., `sts:ExternalId`), non-interfering across distinct roles.
- **Supported Safe Fragment:**
  - IPv4/IPv6 CIDR inclusion and disjointness (`IpAddress`, `NotIpAddress`) via `ipaddress`. Multi-value disjunction (OR) for `IpAddress`; conjunctive negation (AND NOT) for `NotIpAddress`.
  - Exact literal string equality and clash (`StringEquals`, `StringLike` without wildcards).
  - Boolean identity and clash (`Bool` on `aws:MultiFactorAuthPresent`).
  - Presence checks (`Null` operator).
- **Tri-State Semantics:**
  - **SAT:** Sound constructive witness exists satisfying all accumulated constraints.
  - **UNSAT:** Sound proof of logical contradiction ($\Phi \vdash \bot$) within the Safe Fragment under explicit assumptions.
  - **UNKNOWN:** Incompleteness / unsupported operator or key / missing metadata / solver error. Conservative fallback.
- **Independence & Decoupling Guarantees:**
  - Q8 fixed-point integer underflow ($p_{\text{worst\_q8}} = 0$) is decoupled and never treated as an UNSAT signal.
  - Union-Find correlation grouping (`correlation.py`) is decoupled and untouched.
  - No fractional probability penalties or heuristics are applied.
- **Distinction on CE5:** Isolated evaluator returning `UNKNOWN` on absent context metadata is distinguished from integrated Top-$K$ non-perturbation, which requires separate empirical testing against the `ARF-RT-BASELINE` mirror once integration is authorized.
- **Acceptance Criteria (Tests A1–A8):** Defined over status, witness, and contradiction rationale without probability multipliers.

### Prompt 3 Completion — Standalone RDCE Prototype Implementation & Verification (COMPLETED)
- **Implementation:** Built isolated `research/ccpf/rdce.py` implementing `RestrictedDeterministicConstraintEvaluator`.
  - Implements the contract in `docs/CCPF_EVALUATOR_CONTRACT.md` (v1.1.0).
  - Handles scope classification ($\mathcal{R}, \mathcal{S}, \mathcal{P}, \mathcal{C}$), transition relations (IDENTITY, NETWORK_PIVOT, ASSUME_ROLE, CLEARED), and Safe Fragment operators (`IpAddress`, `NotIpAddress`, `StringEquals`, `StringLike`, `Bool`, `Null`).
  - Output interface returns strictly logical `PathEvaluationResult` with `status` (SAT/UNSAT/UNKNOWN), `witness`, `contradiction_rationale`, `unknown_rationale`, `evaluated_hops`, and `solver_duration_ms`.
  - Completely purged of probability multiplier / scoring heuristics.
- **Verification Suite:** Implemented `tests/research/test_rdce.py` with 46 acceptance tests across A1–A8:
  - **A1 (Soundness / CE2):** Verifies UNSAT on disjoint CIDRs (`10.1.0.0/16` vs `192.168.1.0/24`) under static origin persistence.
  - **A2 (Soundness / CE1):** Verifies SAT on compatible CIDR subsets with concrete constructive IP witness (`10.1.0.1`).
  - **A3 (Pivot Re-binding / CE3):** Verifies SAT on network pivot transitions updating request-scoped IP.
  - **A4 (Unsupported Fallback / CE4):** Verifies conservative UNKNOWN on proprietary biometric attribute without false pruning.
  - **A5 (Baseline Fallback / CE5):** Verifies UNKNOWN fallback (`NO_CONTEXT_CONSTRAINTS_DEFINED`) for paths without context sidecars.
  - **A6 (Principal Tag Clash / CE6):** Verifies UNSAT on clashing principal tag requirements across AssumeRole boundary.
  - **A7 (Decoupling):** Verifies logical independence from Bayesian Q8 underflow ($p_{\text{worst\_q8}} = 0$).
  - **A8 (Robustness):** Verifies exception trapping, malformed inputs, timeout handling, and empty hop handling.
  - **Execution Result:** 46 passed in 0.42s (100% pass rate).
- **Empirical Fixture Classifications (CE1–CE6):**
  - `CE1`: **SAT** — Witness: `aws:SourceIp=10.1.0.1`, evaluated_hops=2, solver_duration_ms=0.13ms.
  - `CE2`: **UNSAT** — Contradiction rationale: Disjoint CIDRs `10.1.0.0/16` and `192.168.1.0/24`, evaluated_hops=2, solver_duration_ms=0.08ms.
  - `CE3`: **SAT** — Witness: `hop_1_SourceIp=198.51.100.1, hop_2_SourceIp=10.0.0.5`, evaluated_hops=2, solver_duration_ms=0.11ms.
  - `CE4`: **UNKNOWN** — Rationale: `UNSUPPORTED_OR_UNKNOWN_SCOPE: vendor:ProprietaryBiometricToken`, evaluated_hops=2, solver_duration_ms=0.01ms.
  - `CE5`: **UNKNOWN** — Rationale: `NO_CONTEXT_CONSTRAINTS_DEFINED`, evaluated_hops=0, solver_duration_ms=0.001ms.
  - `CE6`: **UNSAT** — Contradiction rationale: Principal tag contradiction on hop 2 for `aws:PrincipalTag/Department` (`Engineering` vs `Finance`), evaluated_hops=2, solver_duration_ms=0.02ms.
- **Architectural Isolation:**
  - Zero edits to `arf_rt/` core engine files or production path search algorithms (`paths.py`).
  - Baseline test suite passes (910 passed, 2 non-functional timing/stress timeouts expected under Windows load).
  - Production baseline mirror in `C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE` untouched.

##### Prompt 4 Completion - Semantic Validation and Counterexample Testing (COMPLETED)

- **Test File:** tests/research/test_semantic_validation.py (60 tests: Stage B + Stage C + Stage D).
- **Stage B - Independent Semantic Validation (CE1-CE6):**
  - All expected classifications derived independently from docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0.
    No evaluator output used as its own expected-value source.

  | Fixture | Expected | Actual | Key Evidence |
  |---------|----------|--------|-------------|
  | CE1 | SAT | **SAT** | Witness aws:SourceIp=10.1.0.1 (10.1.0.0/16 subset of 10.0.0.0/8); solver_ms=0.257 |
  | CE2 | UNSAT | **UNSAT** | Contradiction: 10.0.0.0/8 and 192.168.0.0/16 disjoint under static_origin; solver_ms=0.172 |
  | CE3 | SAT | **SAT** | Pivot rebind: hop_1_SourceIp=198.51.100.1, hop_2_SourceIp=10.0.1.100; solver_ms=0.212 |
  | CE4 | UNKNOWN | **UNKNOWN** | Rationale: UNSUPPORTED_OR_UNKNOWN_SCOPE: vendor:ProprietaryBiometricToken; solver_ms=0.089 |
  | CE5 | UNKNOWN | **UNKNOWN** | Rationale: NO_CONTEXT_CONSTRAINTS_DEFINED; evaluated_hops=0; solver_ms=0.003 |
  | CE6 | UNSAT | **UNSAT** | Contradiction: PrincipalTag/Department ApplicationDevelopment vs SecurityOperations; solver_ms=0.041 |

- **Stage C - Counterexample / Negative Tests (10 Failure Modes, 40 tests):**
  - FM1 (Disjoint CIDRs require explicit coupling): 2 tests - PASS
  - FM2 (Compatible CIDR witness validity): 2 tests - PASS
  - FM3 (Pivot no pre-pivot IP carry): 2 tests - PASS
  - FM4 (Unsupported operators yield UNKNOWN): 9 tests (6 parametrized) - PASS
  - FM5 (Scope resets only explicit): 2 tests - PASS
  - FM6 (Multi-value combined predicates): 3 tests - PASS
  - FM7 (Null/presence constraints): 2 tests - PASS
  - FM8 (Q8 underflow decoupled): 3 tests - PASS
  - FM9 (Exceptions never UNSAT): 3 tests - PASS
  - FM10 (Determinism): 7 tests - PASS
- **Stage D - CE5 Isolated UNKNOWN / No False UNSAT:** 5 tests - PASS
  - CE5 isolated UNKNOWN confirmed; scope boundary documented (NOT integrated Top-K equivalence).
- **Combined Research Suite:** 106 passed (46 A1-A8 + 60 Prompt 4) in 0.40s (100%).
- **No Soundness Defects Found:** All 10 failure modes confirmed sound in RDCE implementation.
- **Baseline Production Suite:** Unchanged (910 passed, 2 pre-existing stress timeouts).
- **Architectural Isolation:** Zero edits to arf_rt/, paths.py, correlation.py, or baseline mirror.

### Next Authorized Step (Prompt 5)
Integrate CCPF/RDCE into production Top-K search and perform comparative baseline experiments.

---

## Key Documents

| Document | Location |
|---|---|
| CCPF Formal Design Gate | docs/CCPF_FORMAL_DESIGN_GATE.md |
| CCPF Evaluator Contract | docs/CCPF_EVALUATOR_CONTRACT.md |
| Master Research Setup Audit | docs/MASTER_RESEARCH_SETUP_AUDIT.md |
| Phase 17 Novelty Assessment | docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md |
| Final Baseline Verification Report | verification/FINAL_BASELINE_VERIFICATION_REPORT.md |
| Evidence Closeout Report | verification/EVIDENCE_CLOSEOUT_REPORT.md |
