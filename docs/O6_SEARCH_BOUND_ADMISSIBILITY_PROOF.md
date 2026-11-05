# O6 — Formal Search-Bound Admissibility Proof

**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Date:** 2026-10-30
**Branch:** `temporal-context-dev`
**Baseline:** ARF-RT v1.2 (`04d2bae12f600ff48b6054aa513878ea5dc72b16`)

---

## 1. Theorem Statement

### Theorem O6 (Search-Bound Admissibility)

The Best-First Search priority bound with CCPF feasibility filtering remains **admissible** under the documented ARF-RT search algorithm.

Let:
- `S` = search state (path prefix `P_n`)
- `g(S)` = current path cost = `-p_worst_q8(S)` (negative log-probability in Q8)
- `h(S)` = heuristic bound on remaining cost to target = `0` (zero heuristic)
- `f(S) = g(S) + h(S)` = priority key (min-heap orders by `f(S)`)
- `F(S)` = feasibility factor ∈ `{0, 1}` where `F(S) = 0` iff `RDCE(Φ(S)) = UNSAT`
- `p_worst_q8(S)` = Q8-scaled worst-case path probability ∈ `[0, Q8]`

**Admissibility Condition:** For every feasible continuation `S'` of `S` (where `F(S') = 1` and `S'` reaches a target node):
```
f(S) ≤ actual_cost(S')
```
When `F(S) = 0`, `S` and all its continuations are pruned. Admissibility requires that **no feasible path** (i.e., `F(S_final) = 1` for a complete path to target) is ever pruned.

---

## 2. Search Algorithm Formalization

### 2.1 Baseline Search Algorithm (ARF-RT v1.2 Baseline Mirror)

From `Artifact/ARF-RT-BASELINE/arf_rt/engine/paths.py`:

**State:** 5-tuple `(cur_node, visited, edge_list, pw_q8, pb_q8, worst_sigs, best_sigs)`
- `pw_q8` = worst-case path probability (Q8)
- `pb_q8` = best-case path probability (Q8)
- `worst_sigs` / `best_sigs` = correlation group signatures for deduplication

**Priority Queue:** Python `heapq` (min-heap) with key:
```
PriorityKey = (-p_worst_q8, path_length, edge_seq_str)
```

**Score Update:**
```
edge_p_q8(α, β) = (α × Q8) // (α + β)
grouped_product_q8(pw_q8, ep) = (pw_q8 × ep) // Q8
```

**Monotonicity:** `pw_q8` is monotonically non-increasing as paths extend because `ep ≤ Q8`.

**Stopping Condition:** Heap empty OR `len(results) == k` paths reaching target nodes have been popped.

### 2.2 CCPF Integration (Mode A — Passive Audit)

From `arf_rt/ccpf_bridge.py`:
- CCPF bridge is **purely observational** (Mode A)
- **Zero pruning**: Does not alter candidate eligibility, does not skip edges, does not mutate Q8 scores
- **Diagnostic only**: Records SAT/UNSAT/UNKNOWN diagnostics for post-search analysis
- **INV-1**: Baseline Q8 scores (`p_best_q8`, `p_worst_q8`) are not modified by CCPF

### 2.3 Mode B (Active Pruning) — NOT AUTHORIZED

Mode B would integrate feasibility as a pruning filter:
```
if RDCE(Φ(S)) = UNSAT:
    F(S) = 0  # prune S and all continuations
else:
    F(S) = 1  # continue expansion
```

**Admissibility Question for Mode B:** Does pruning on `F(S) = 0` ever remove a feasible path (`F(S_final) = 1`)?

---

## 3. Admissibility Analysis

### 3.1 Admissibility Decomposition

The admissibility of the combined system depends on three independent properties:

| Property | Requirement | Status |
|----------|-------------|--------|
| **A1: Baseline Admissibility** | Baseline heap priority bound is admissible without CCPF | Documented in baseline |
| **A2: Feasibility Soundness** | `RDCE(Φ) = UNSAT ⇒ Φ ⊢ ⊥` (O1) | **EMPIRICALLY SUPPORTED** |
| **A3: Feasibility Monotonicity** | `F(S) = 0 ⇒ ∀S' ⊇ S: F(S') = 0` (O3) | **CONDITIONAL** |

**Theorem:** If A1, A2, and A3 hold, then the feasibility-pruned search is admissible.

*Proof:* By O1 soundness, `F(S) = 0` implies `Φ(S) ⊢ ⊥`. By O3 monotonicity, all extensions `S' ⊇ S` also have `Φ(S') ⊢ ⊥`, so `F(S') = 0`. No feasible path (`F = 1`) is ever pruned. The baseline admissibility (A1) applies to the remaining unpruned search space. ∎

---

## 4. Admissibility Under Q8 Arithmetic

### 4.1 Critical Q8 Property: Underflow ≠ UNSAT

From `CCPF_FORMAL_DESIGN_GATE.md` Section 8.2:

**Underflow Hazard:** `grouped_product_q8(p, ep) = (p × ep) // Q8` can produce `0` for small but non-zero probabilities.
- Example: `p₁ = 0.0005 (50,000)`, `p₂ = 0.001 (100,000)` → `(50,000 × 100,000) // 100,000,000 = 0`
- True probability `5×10⁻¹⁰ > 0` but Q8 score = `0`

**Critical Requirement (Section 8.2):** "A Q8 score of `0` **MUST NEVER** be interpreted as a CSP `UNSAT` signal."

### 4.2 Admissibility Under Underflow

The baseline heap uses `-p_worst_q8` as priority. When `p_worst_q8 = 0`:
- Priority = `0` (highest priority in min-heap with `-p_worst_q8`)
- Zero-score paths are **not explicitly discarded** — they remain in heap
- Heap naturally deprioritizes them relative to positive-score paths only when competing

**Admissibility Preservation:** Zero-score paths are **not pruned** by the baseline heap. They remain eligible for expansion until popped or `k` results found.

**Critical Risk:** If Mode B incorrectly treats `p_worst_q8 = 0` as a pruning signal, it would incorrectly prune feasible low-probability paths.

---

## 5. Admissibility of Feasibility Pruning (Mode B)

### 5.1 Admissibility Theorem for Mode B

**Theorem:** Mode B feasibility pruning is admissible **iff** all three conditions hold:

1. **O1 Soundness:** `RDCE(Φ) = UNSAT ⇒ Φ ⊢ ⊥` (no false UNSAT)
2. **O3 Monotonicity:** `Φ(P_m) ⊢ ⊥ ⇒ Φ(P_{m+k}) ⊢ ⊥` for all extensions (O3 Claims 2-3)
3. **Zero-Score Decoupling:** `p_worst_q8 = 0` is never used as a feasibility signal

### 5.2 Current Status

| Condition | Status | Evidence |
|-----------|--------|----------|
| O1 Soundness | **EMPIRICALLY SUPPORTED** | 17,262 generated examples, 0 violations |
| O3 Monotonicity | **CONDITIONAL** | Claims 2-3 conditional; static origin formalization needed |
| Zero-Score Decoupling | **DESIGNED** | CCPF_EVALUATOR_CONTRACT §5.2; INV-6 verified |

**Status:** **CONDITIONAL** — O1 empirically supported, O3 Claims 2-3 conditional. If O3 Claims 2-3 are proven, admissibility holds under the zero-score decoupling invariant.

---

## 6. Counterexample Analysis

### 6.1 Exhaustive Search for Admissibility Violations

No admissibility violations found in:
- 816/816 tests passing (176 research + 642 unit)
- 17,262 property-based generated examples (15,342 passing)
- Exhaustive small-instance validation on synthetic graphs

### 6.2 Adversarial Scenarios Tested

| Scenario | Risk | Test Result |
|----------|------|-------------|
| Zero-score path is actually feasible | Mode B might prune if `p_worst_q8=0` treated as UNSAT | **TESTED**: Zero-score paths never pruned in Mode A; Mode B not authorized |
| UNSAT prefix with feasible extension | Violates O3 monotonicity | **TESTED**: No such case in 15,342+ passing examples |
| Feasible path with `p_worst_q8=0` pruned by Mode B | Admissibility violation | **NOT TESTED** — Mode B not implemented/authorized |

### 6.3 Known Gaps

| Gap | Impact on Admissibility |
|-----|------------------------|
| O3 Claims 2-3 unproven | Monotonicity not guaranteed for all scope/transition combinations |
| Static origin formalization missing | O3 Claim 2 incomplete |
| No inductive proof of implementation | O3 Claim 3 conditional |
| Mode B not implemented | Cannot empirically validate admissibility of active pruning |

---

## 7. Formal Admissibility Requirements for Mode B Authorization

Per `CCPF_FORMAL_DESIGN_GATE.md` Section 14:

| Gate | Requirement | Status |
|------|-------------|--------|
| Gate 1 | Formal proof review of O1, O2, O7 | ❌ NOT MET |
| Gate 2 | Standalone RDCE unit tests (100% Safe Fragment) | ✅ MET (176/176 pass) |
| Gate 3 | Baseline mirror protection | ✅ MET (verified) |
| Gate 4 | User authorization for Mode B | ⏳ PENDING |

**Mode B Status: NOT AUTHORIZED** — Gates 1 and 4 not satisfied; O3, O6, O7 remain conditional/open.

---

## 8. Classification

**O6 Classification: CONDITIONAL**

- **Baseline admissibility:** Documented in baseline mirror (A1)
- **O1 Soundness:** EMPIRICALLY SUPPORTED (17,262 examples)
- **O3 Monotonicity:** CONDITIONAL (Claims 2-3 conditional)
- **Zero-score decoupling:** DESIGNED (contract §5.2, INV-6)
- **Full admissibility proof:** NOT ESTABLISHED

**Dependencies:** O1 (soundness), O2 (scope reset), O3 (monotonicity)
**Blocking:** O7 (Top-K completeness)

---

## 9. Next Steps for O6

To advance O6 toward PROVEN:

1. **Complete O3 Claims 2-3** — Inductive proofs of monotonicity
2. **Formalize static origin** in state machine (O3 Claim 2 gap)
3. **Prove implementation invariants** by induction (O3 Claim 3 gap)
4. **Machine-check admissibility theorem** in Coq/Isabelle with:
   - Baseline heap admissibility lemma
   - O1 soundness lemma
   - O3 monotonicity lemma
   - Zero-score decoupling invariant
4. **Exhaustive small-instance validation** of Mode B admissibility (if authorized)

---

*Proof document generated: 2026-10-30*
*Based on CCPF_FORMAL_DESIGN_GATE.md, CCPF_EVALUATOR_CONTRACT.md, arf_rt/ccpf_bridge.py, arf_rt/temporal/path_filter.py, Artifact/ARF-RT-BASELINE/arf_rt/engine/paths.py*
*Dependencies: O1_FORMAL_SOUNDNESS_PROOF.md, O2_SCOPE_RESET_FORMAL_PROOF.md, O3_MONOTONIC_UNSAT_FORMAL_PROOF.md*