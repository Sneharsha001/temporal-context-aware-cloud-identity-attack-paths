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

### Next Authorized Step (Prompt 3)
Implement the standalone RDCE prototype in isolated test/research space (`tests/research/test_rdce.py`) according to the Prompt 2A contract without modifying production engine files or the baseline mirror.

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
