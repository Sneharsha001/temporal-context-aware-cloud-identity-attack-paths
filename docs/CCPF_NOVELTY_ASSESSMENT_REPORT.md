# CCPF Novelty Assessment Report
## Context-Conditioned Path Feasibility for Probabilistic Cloud Identity Attack-Path Analysis

**Project:** ARF-RT v1.2 Temporal Extension  
**Branch:** `temporal-context-dev`  
**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Date:** 2026-10-22  
**Assessment Type:** Evidence-first literature review and novelty comparison

---

## 1. Executive Summary

**Verdict: MORE EVIDENCE REQUIRED (with PROMISING engineering contribution)**

The CCPF (Context-Conditioned Path Feasibility) extension implements a formally specified, deterministic constraint evaluator (RDCE) that integrates with ARF-RT's Bayesian best-first search engine to provide post-search diagnostic annotation of multi-hop IAM attack paths. The implementation is correct, well-tested, and architecturally isolated from the baseline search engine.

**However, the scientific novelty claim requires additional evidence before a conference publication claim can be substantiated.** The core contribution—hop-by-hop IAM condition constraint propagation with typed-scope semantics integrated into a probabilistic graph search—is a genuine engineering advancement for the ARF-RT codebase, but the scientific novelty relative to the broader literature requires additional verification of several open questions.

---

## 2. Current Implementation Status (Verified)

### 2.1 Implementation Completeness
| Component | Status | Evidence |
|-----------|--------|----------|
| RDCE Evaluator (`research/ccpf/rdce.py`) | ✅ Complete | 184/184 research tests pass |
| Post-Search Annotation Bridge (`arf_rt/ccpf_bridge.py`) | ✅ Complete | 35/35 integration tests pass |
| Search Invariance Tests | ✅ Complete | 7/7 parametrized tests pass (G2 gate PASSED) |
| Correctness Fixtures (CE1–CE9) | ✅ Complete | All 9 fixtures pass with contract-compliant verdicts |
| Trust Policy Parser | ✅ Fixed | Preserves statement alternatives, handles Deny correctly |
| Performance Gate | ⚠️ UNMET | +45.71% minimal, +34.33% complex (micro-fixtures) |

### 2.2 Correctness Fixtures (All Passing)
| Fixture | Type | Path Length | Verdict | Contract Compliance |
|---------|------|-------------|---------|---------------------|
| CE1 (Compatible Persistent) | Positive | 2 hops | SAT | ✅ |
| CE2 (Contradictory Persistent) | Counterexample | 2 hops | UNSAT | ✅ |
| CE3 (Pivot Transition) | Positive | 2 hops | SAT | ✅ |
| CE4 (Unsupported Metadata) | Out-of-scope | 2 hops | UNKNOWN | ✅ |
| CE5 (Baseline Compatibility) | Out-of-scope | 0 hops | UNKNOWN | ✅ |
| CE6 (Principal Scope Boundary) | Counterexample | 2 hops | UNSAT | ✅ |
| CE7 (Multi-Hop Chain) | Counterexample | 4 hops | UNSAT | ✅ |
| CE8 (Mixed Types) | Counterexample | 3 hops | UNSAT | ✅ |
| CE9 (Partial Unknown) | Partial | 3 hops | UNKNOWN | ✅ |

All 184 research tests pass. The RDCE correctly implements the formal contract.

---

## 3. Literature Review Summary

Based on the comprehensive literature review in `docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md` (audited 2026-10-10, updated 2026-10-22 with Phase 17.2 findings), here is the comparison matrix:

### 3.1 Prior Work Comparison Matrix

| Property | Zelkova (FMCAD 2018) | IAM-MultiPolicyAnalyzer (FMCAD 2025) | IP Model Counting (FMCAD 2024) | PMapper (nccgroup) | CNAPPs (Wiz/Orca/Prisma) | **CCPF (Implemented)** |
|----------|---------------------|-------------------------------------|--------------------------------|-------------------|------------------------|------------------------|
| **Unit of analysis** | Single policy | Multi-policy composition | Single policy + IP cardinality | Principal graph | Whole-env graph | **Multi-hop path traversal** |
| **Context-scoped attribute semantics** | Single request | Single request | IP addresses only | Per-query input only | Proprietary/Unknown | **Per-hop, typed scope (R/S/P/C)** |
| **Carries state across hops** | No | No | No | No | Unknown | **Yes — CarriedContext propagation** |
| **Probabilistic path ranking** | No | No | No | No | Heuristic | **Yes — Bayesian q8 product** |
| **Admissibility proof for search bound** | N/A | N/A | N/A | N/A | None | **OPEN (conditional proof only)** |
| **Open reproducible benchmark** | Yes (ACL2 proofs) | Partial (internal) | Yes | Yes (open source) | No | **Yes — CE1–CE9 fixture suite** |
| **IAM role boundary context tracking** | No | No | No | Session policy discarded | Unknown | **Yes — per-scope continuity model** |
| **Binary feasibility filter during search** | No | No | No | No | Unknown | **Yes — SAT/UNSAT/UNKNOWN trichotomy** |

### 3.2 Verified Prior Work Capabilities (Phase 17.2 Audit)

| Tool/Paper | Cross-Hop Constraint Accumulation | Typed Scope Semantics | Probabilistic Ranking | Admissibility Proof |
|------------|----------------------------------|----------------------|----------------------|---------------------|
| **Zelkova (FMCAD 2018)** | ❌ Single policy only | Single request scope | No | ACL2 proofs for SMT |
| **IAM-MultiPolicyAnalyzer (FMCAD 2025)** | ❌ Single decision | Single decision | No | Not published |
| **PMapper v1.1.5** | ❌ No cross-hop accumulation | ❌ No scope differentiation | Binary reachability only | No formal proof |
| **AWS Security Hub Attack Path** | Unknown (proprietary) | Unknown | Heuristic | No public spec |
| **CCPF (Implemented)** | ✅ PathConstraintStore with typed scopes | ✅ 4 typed scopes (R/S/P/C) | ✅ Bayesian q8 product | **OPEN (conditional)** |

**Key Finding from Phase 17.2 PMapper Source Code Audit (commit 91d2e60):**
- PMapper v1.1.5 evaluates conditions only at the destination principal of a query
- No cross-hop constraint accumulation; conditions are a single global query input
- Graph edges store no condition metadata; `edges.py` has no constraint attributes
- Session policies are discarded at `sts:AssumeRole` pivots (explicit in `query_interface.py`)
- No scope differentiation (request/session/principal/config) in graph edges
- Unsupported operators silently match (`True`) in `local_policy_simulation.py`

---

## 4. Novelty Assessment

### 4.1 Defensible Research Gap (The "Narrow" Contribution)

**Gap 1: Multi-Hop Typed-Scope IAM Constraint Propagation**
No published work or audited open-source tool implements typed-scope (Request/Session/Principal/Config) IAM condition constraint propagation across sequential graph transitions with contradiction detection. PMapper evaluates conditions only at the query destination; Zelkova and IAM-MultiPolicyAnalyzer evaluate single decisions; commercial tools are proprietary.

**Gap 2: Binary Feasibility Filter with Admissibility Preservation (Conditional)**
The integration of a `{0.0, 1.0}` feasibility filter into a Bayesian best-first search with q8 quantization is formally specified. The admissibility proof is **conditional** on:
1. `grouped_product_q8` rounding behavior (floor to 1, not 0, for small probabilities)
2. Explicit zero-score path pruning to prevent wasteful heap expansion
3. Zero-score paths correctly handled by the heap ordering

**Gap 3: Reproducible Open Fixture Suite**
The CE1–CE9 fixture suite with deterministic ground truth is a reproducible benchmark for context-conditioned IAM path feasibility. No comparable public suite exists (Zelkova has ACL2 proofs but no path fixtures; PMapper has no formal benchmark).

### 4.2 Claims That Are NOT Substantiated

| Claim | Status | Evidence |
|-------|--------|----------|
| "CCPF subsumes Zelkova" | ❌ False | CCPF uses pre-extracted condition metadata; Zelkova solves full policy SMT |
| "CCPF solves temporal feasibility" | ❌ Out of scope | Temporal expiration explicitly deferred (Phase 14.1) |
| "CCPF subsumes PMapper" | ❌ Different level | PMapper does reachability; CCPF adds probabilistic ranking + CSP filter |
| "CCPF subsumes commercial CNAPPs" | Unverifiable | Commercial internals proprietary; no public algorithms |
| "CCPF improves attack path ranking" | Unproven | Active pruning not implemented; only post-search annotation |
| "CCPF eliminates false positives" | Unmeasured | No ground-truth UNSAT labels exist (RQ4: UNMEASURED) |
| "CCPF is a general framework" | Overstated | Tightly coupled to ARF-RT v1.2 q8 scheme and ARF-RT schema |

### 4.3 Open Questions Requiring Resolution Before Publication

| Question | Status | Required Action |
|----------|--------|-----------------|
| Does `grouped_product_q8` floor to 1 (not 0) for small probabilities? | OPEN | Source inspection of `arf_rt/util/` |
| Does the engine correctly handle zero-score paths (no infinite expansion)? | OPEN | Source inspection of `arf_rt/engine/paths.py` |
| Does ARF-RT's Bayesian search have a published formal specification? | PARTIAL (SeRIM 2026 abstract) | Need full paper access |
| Does PMapper source code confirm no cross-hop accumulation? | ✅ VERIFIED (commit 91d2e60) | Documented in Phase 17.2 |
| Does IAM-MultiPolicyAnalyzer model sequential transitions? | UNRESOLVED | Full paper read required |
| Does AWS Security Hub apply constraint propagation? | UNKNOWN | Requires AWS internal access |

---

## 5. Defensible Contribution Statement

### Narrowest Defensible Claim (Engineering Contribution)

> **CCPF introduces a diagnostic post-search annotation layer for IAM attack-path search results that applies a formally specified, deterministic constraint evaluator (RDCE) to identify paths containing provable IAM condition contradictions under the static-origin assumption. The contribution is the first *documented integration* of hop-by-hop constraint propagation into a probabilistic multi-hop graph search engine for cloud identity attack-path inference, with a reproducible fixture suite (CE1–CE9) and formally specified typed-scope semantics.**

### What This Claim Does NOT Assert
- ❌ Does not claim to improve security outcomes or reduce attacker success probability
- ❌ Does not claim to improve path ranking or reduce false positives in production
- ❌ Does not claim to solve temporal feasibility or session expiration
- ❌ Does not claim superiority over Zelkova, PMapper, or commercial tools
- ❌ Does not claim a general reusable framework (tied to ARF-RT v1.2)

---

## 6. Limitations That Must Be Acknowledged in Any Paper

### L1 — Static-Origin Assumption (Strong, Potentially Unrealistic)
CCPF assumes the attacker's source IP and session context are fixed at path entry. This fails for:
- Cloud-internal pivots (Lambda invocations with VPC-internal IPs)
- Cross-region calls with different NAT gateways
- Credential rotation mid-path
- Attacker-controlled botnets with multiple egress IPs

**Required disclosure:** All experimental results are conditioned on this assumption.

### L2 — No Ground-Truth UNSAT Labels
No external labeled dataset of known-infeasible cloud attack paths exists. All UNSAT validation is against internally constructed counterexamples. UNSAT rate on operational graphs is unmeasured.

### L3 — Annotation ≠ Pruning
Current implementation is post-search diagnostic only. UNSAT paths are annotated but NOT pruned or re-ranked. Claims of "filtering" or "ranking improvement" are outside authorized scope.

### L4 — Coverage Unknown
The proportion of real-world paths receiving SAT/UNSAT vs. UNKNOWN is unmeasured. The RDCE covers only 4 constraint types; all other IAM condition keys yield UNKNOWN.

### L5 — Micro-Fixture Performance Gate UNMET
On micro-fixtures (0.36ms/2.77ms baselines), relative overhead is +45.71%/+34.33%. The <15% gate is mathematically infeasible on sub-millisecond baselines due to SQLite query floor (~80-120μs). Enterprise-scale evaluation (≥500 nodes, ≥50ms baseline) is required to demonstrate operational viability.

### L6 — Admissibility Proof Incomplete
The formal admissibility proof is conditional on:
1. `grouped_product_q8` flooring to 1 (not 0) for small probabilities
2. Explicit zero-score path pruning implementation
3. Verification that integer rounding doesn't misclassify small probabilities as UNSAT

---

## 7. Recommended Next Steps for Publication

### Prerequisites for Any Venue Submission
| Gate | Description | Status |
|------|-------------|--------|
| G1: Full Zelkova FMCAD 2018 paper read | Confirm no cross-hop context | OPEN |
| G2: PMapper source audit complete | Cross-hop accumulation absent | ✅ VERIFIED |
| G3: CCPF filter implemented + CE1–CE6 verified | D3 fixtures passing | ✅ COMPLETED |
| G4: CE5 baseline non-perturbation verified | Exact numerical comparison | ✅ COMPLETED (bitwise parity) |
| G5: `grouped_product_q8` rounding confirmed | Floor to 1, not 0 | OPEN |
| G6: Zero-score path pruning verified | Prevents infinite expansion | OPEN |
| G7: ARF-RT (Conklin SeRIM 2026) full paper accessed | Confirm algorithm scope | OPEN |

### Recommended Target Venues (Provisional)
| Tier | Venue | Condition |
|------|-------|-----------|
| Tier 1 (USENIX Security, IEEE S&P, CCS, FMCAD) | ❌ Blocked | All gates G1–G7 must PASS |
| Tier 2 (Workshop co-located: SeRIM, CCS Workshop, etc.) | ⚠️ Conditional | G3–G4 complete; G1–G2 verified; G5–G6 in progress |
| Tier 3 (SeRIM Workshop — where ARF-RT published) | ✅ Appropriate | Engineering contribution + partial evidence sufficient |

---

## 8. Final Recommendation

### Verdict: **MORE EVIDENCE REQUIRED** (with a strong engineering contribution)

The CCPF implementation is:
- ✅ **Correct**: All 184 research tests + 525 total functional tests pass
- ✅ **Contract-compliant**: RDCE implements formal contract exactly
- ✅ **Architecturally isolated**: Zero changes to baseline ARF-RT search behavior
- ✅ **Well-specified**: Formal contract, typed scopes, counterexample fixtures
- ⚠️ **Performance gate UNMET** on micro-fixtures (architecturally explained)
- ⚠️ **Novelty claim not yet fully substantiated**: Requires G1, G5, G6, G7 resolution

### Recommended Path Forward
1. **Complete G5, G6** (source code inspection of `arf_rt/util/` and `arf_rt/engine/paths.py`)
2. **Obtain full texts** for Zelkova (FMCAD 2018), IAM-MultiPolicyAnalyzer (FMCAD 2025), ARF-RT (SeRIM 2026)
3. **If G5/G6 resolve favorably**: Submit to SeRIM workshop or similar Tier-2 venue with narrow engineering contribution framing
4. **If G5/G6 reveal issues**: Fix before any submission; document limitations explicitly
5. **Do not submit to top-tier venues** until all G1–G7 gates pass

### Final Position Statement
> CCPF is a **correct, well-tested, formally specified engineering extension** to ARF-RT that adds a post-search diagnostic layer for multi-hop IAM constraint feasibility. The implementation is complete and correct. The **scientific novelty** of the integration is **plausible but not yet fully substantiated** due to open verification gates (G1, G5, G6, G7). The contribution is suitable for a **workshop or emerging results track** with narrow engineering framing, contingent on resolving the remaining open gates. A **main conference submission is premature**.

---

*Report generated 2026-10-22. Based on inspection of `temporal-context-dev` branch at HEAD `e95b443`. All tests passing (525/525 functional). No commits, no pushes, no production code changes.*