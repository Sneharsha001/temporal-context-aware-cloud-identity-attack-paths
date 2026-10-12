# CCPF Counterexample Testing Specification & Failure Mode Analysis

**Phase:** Prompt 4 Stages C & D — Counterexample / Negative Testing  
**Evaluator Implementation:** RestrictedDeterministicConstraintEvaluator (research/ccpf/rdce.py)  
**Test Suite:** tests/research/test_semantic_validation.py (Stage C: 35 tests, Stage D: 5 tests)  
**Date:** 2026-10-12  

---

## 1. Scope & Objective

This specification details the 10 formal failure modes (FM1 through FM10) and the CE5 isolated fallback evaluation designed to stress-test the soundness, robustness, and determinism of the RDCE solver.

A total of 40 targeted tests in tests/research/test_semantic_validation.py cover these behaviors:
- Stage C: 35 tests across FM1–FM10.
- Stage D: 5 tests across CE5 isolated fallback and scope distinction.

---

## 2. Failure Mode Summary (FM1–FM10)

| Mode | Semantic Target | Tests | Status | Key Soundness Finding |
|:---|:---|:---:|:---:|:---|
| **FM1** | Disjoint CIDRs require explicit coupling | 2 | **PASS** | Uncoupled disjoint CIDRs across hops do not produce spurious UNSAT. Explicit static origin coupling correctly triggers UNSAT. |
| **FM2** | Compatible CIDR witness validity | 2 | **PASS** | Witness IPv4 address is structurally validated to reside strictly in the intersection of both CIDR blocks. |
| **FM3** | Pivot context rebind | 2 | **PASS** | Pre-pivot IP does not erroneously carry over to post-pivot hop. Network pivot rebinds request scope soundly. |
| **FM4** | Unsupported operators yield UNKNOWN | 9 | **PASS** | Unsupported operators (ArnLike, ArnNotEquals, NumericLessThan, DateGreaterThan, BinaryEquals, IpAddressIfExists) and malformed inputs fail open to UNKNOWN. |
| **FM5** | Scope resets only on explicit declaration | 2 | **PASS** | Principal tag and session context persist without explicit AssumeRole / pivot boundary. |
| **FM6** | Multi-value combined predicates | 3 | **PASS** | Disjunctive OR for IpAddress and conjunctive AND NOT for NotIpAddress evaluate correctly under combined predicates. |
| **FM7** | Null presence constraints | 2 | **PASS** | Null: true / false assertions evaluate soundly without unhandled exceptions. |
| **FM8** | Q8 underflow decoupling | 3 | **PASS** | Integer probability underflow (p_worst_q8 = 0) is decoupled from feasibility and never triggers false UNSAT. |
| **FM9** | Exception fail-open safety | 3 | **PASS** | Empty hops, invalid CIDRs, and malformed JSON are trapped and return UNKNOWN (never false UNSAT). |
| **FM10**| Solver determinism | 7 | **PASS** | Multi-run outputs across all 6 fixtures and inline tests produce bit-for-bit identical results. |

---

## 3. Stage D — CE5 Isolated Fallback & Scope Distinction

1. **Isolated Evaluator Behavior:**
   - CE5 contains no context conditions in its constraints.
   - The isolated RDCE evaluator returns UNKNOWN with unknown_rationale: NO_CONTEXT_CONSTRAINTS_DEFINED.
   - Evaluated hops = 0, solver runtime = 0.003ms.
   - It does NOT report false UNSAT for that isolated input.

2. **Scope Boundary vs. Integrated Top-K Search:**
   - This isolated result is strictly distinct from integrated Top-K path search behavior.
   - CCPF has not been integrated into production search, and properties such as Top-K non-perturbation or search completeness have not been evaluated and are not claimed.
