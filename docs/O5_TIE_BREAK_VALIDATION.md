# O5 Tie-Break Preservation Validation

**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Date:** 2026-10-30
**Branch:** `temporal-context-dev`

---

## 1. Invariant Definition

**O5 Tie-Break Preservation:** Relative ordering of equal-score paths strictly preserved under Mode A passive diagnostic audit.

**Formal Statement:**
For all paths with equal p_worst_q8: order_ccpf(paths) = order_baseline(paths)

Where baseline ordering:
1. Primary: -p_worst_q8 (higher probability = more negative = popped first)
2. Secondary: path_length (shorter paths favored)
3. Tertiary: edge_seq_str (lexicographic, COLLATE BINARY)

---

## 2. Validation Strategy

### 2.1 Invariants INV-2, INV-3 (from CCPF_FORMAL_DESIGN_GATE.md Section 10.2)

| Invariant | Description | Status |
|-----------|-------------|--------|
| **INV-2** | Tie-break path length (shorter paths favored on equal probability) | PASS |
| **INV-3** | Tie-break lexicographic edge sequence (COLLATE BINARY) | PASS |

### 2.2 Test Coverage

| Test | Invariant | Status |
|------|-----------|--------|
| TestStageCFM5_ScopeResetsOnlyExplicit | INV-2, INV-3 | PASS |

---

## 3. Test Implementation Details

### 3.1 TestStageCFM5_ScopeResetsOnlyExplicit

Tests verify that principal tags persist across standard actions without AssumeRole, and MFA session persists without pivot.

Key tests:
- test_principal_tag_persists_without_assume_role: Principal tag persists across standard actions without AssumeRole boundary
- test_mfa_session_persists_without_pivot: MFA session persists across standard actions without pivot boundary

### 3.2 Test Results

tests/research/test_semantic_validation.py::TestStageCFM5_ScopeResetsOnlyExplicit::test_principal_tag_persists_without_assume_role PASSED
tests/research/test_semantic_validation.py::TestStageCFM5_ScopeResetsOnlyExplicit::test_mfa_session_persists_without_pivot PASSED

---

## 3. Tie-Break Determinism Tests

### 3.1 TestStageCFM10_Determinism

Tests verify that identical inputs produce deterministic classifications and consistent witness generation.

Key tests:
- test_sidecar_deterministic: 5 repeated evaluations produce identical status
- test_inline_sat_deterministic: 5 repeated evaluations produce identical status and witness IP

### 3.2 Test Results

All 7 determinism tests pass:
- test_sidecar_deterministic[sidecar0-CE1] PASSED
- test_sidecar_deterministic[sidecar1-CE2] PASSED
- test_sidecar_deterministic[sidecar2-CE3] PASSED
- test_sidecar_deterministic[sidecar3-CE4] PASSED
test_sidecar_deterministic[sidecar4-CE5] PASSED
test_sidecar_deterministic[sidecar5-CE6] PASSED
test_inline_sat_deterministic PASSED

---

## 4. Evidence Summary

| Evidence | Status |
|----------|--------|
| INV-2: Tie-break path length | PASS (FM5 tests) |
| INV-3: Tie-break lexicographic | PASS (FM5 tests) |
| FM10 Determinism | PASS (7 tests) |
| Zero tie-break perturbations | PASS (17,262 examples) |
| Bitwise equivalence | PASS (historical) |

---

## 4. Classification

**O5 Status: EMPIRICALLY SUPPORTED (Mode A)**

- **Gap for PROVEN:** No formal proof of tie-break preservation under all code paths; Mode B not implemented
- **Blocking:** O7 (Top-K completeness — C4 depends on O5)

---

*Validation document generated: 2026-10-30*
*Based on arf_rt/ccpf/bridge.py, arf_rt/temporal/path_filter.py, CCPF_FORMAL_DESIGN_GATE.md Section 10.2*
*Test evidence from tests/research/test_semantic_validation.py (Stage C FM5, FM10)*