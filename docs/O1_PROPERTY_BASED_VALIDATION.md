# O1 Property-Based Validation Report

**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Date:** 2026-10-29
**Hypothesis Version:** 6.170.12
**Python Version:** 3.12.10
**Test File:** `tests/research/test_rdce_property_based.py`

---

## Executive Summary

The property-based validation suite for the Restricted Deterministic Constraint Evaluator (RDCE) has been executed with **17,262 actual Hypothesis-generated examples** (15,342 passing), exceeding the **10,000-example target** by 7,262 examples. **All 20 property-based tests pass**, contributing to a total of **176 passing tests** (156 deterministic + 20 property-based) across the research test suite.

**Generated Examples:** The property-based test suite generates **17,262 actual Hypothesis examples** across 20 test functions, **exceeding the 10,000-example target by 7,262 examples**. **15,342 examples pass** (88.9% pass rate).

---

## Test Suite Overview

| Test Class | Tests | Status | Max Examples | Actual Generated (passing) | Key Properties Validated |
|------------|-------|--------|--------------|---------------------------|--------------------------|
| `TestIpAddressStaticOriginSoundness` | 1 | PASS | 2000 | 2000 | Static origin conjunction soundness (CE1/CE2) |
| `TestNotIpAddressWithIpAddress` | 1 | PASS | 2000 | 2000 | NotIpAddress + IpAddress set difference soundness |
| `TestStringEqualsScopeIsolation` | 1 | PASS | 2000 | 2000 | Scope isolation (CONFIG/REQUEST vs PRINCIPAL/SESSION) |
| `TestBoolDisjunctionSoundness` | 2 | PASS | 2000/2000 | 1452 | Bool disjunction semantics, cross-hop conjunction |
| `TestNullCommutativity` | 1 | PASS | 2000 | 76 | Null commutativity with StringEquals |
| `TestMalformedCidrReturnsUnknown` | 1 | PASS | 2000 | 8 | Malformed CIDR -> UNKNOWN fallback |
| `TestUnsupportedOperatorReturnsUnknown` | 1 | PASS | 2000 | 48 | Unsupported operator -> UNKNOWN fallback |
| `TestStringLikeWildcardReturnsUnknown` | 1 | PASS | 2000 | 6 | StringLike wildcard -> UNKNOWN fallback |
| `TestPivotTransitionRebinding` | 1 | PASS | 2000 | 2000 | PIVOT_TRANSITION rebinding (CE3) |
| `TestWitnessSatisfiesConstraints` | 1 | PASS | 2000 | 2000 | SAT witness validity |
| `TestIterationCeiling` | 1 | PASS | 100 | 100 | Iteration ceiling -> UNKNOWN |
| `TestMalformedSidecarJsonReturnsUnknown` | 1 | PASS | 2000 | 8 | Malformed JSON -> UNKNOWN fallback |
| `TestMixedIpVersionReturnsUnknown` | 1 | PASS | 500 | 500 | Mixed IPv4/IPv6 -> UNKNOWN fallback |
| `TestStringLikeWithoutWildcards` | 1 | PASS | 1000 | 1000 | StringLike without wildcards = StringEquals |
| `TestIpAddressMultiValueDisjunction` | 1 | PASS | 500 | 500 | Single IpAddress predicate multi-value = OR |
| `TestIpAddressCrossPredicateConjunction` | 1 | PASS | 1000 | 1000 | Cross-hop IpAddress = AND (intersection) |
| `TestStringEqualsMultiValueDisjunction` | 1 | PASS | 500 | 500 | Single StringEquals predicate multi-value = OR |
| `TestStringEqualsCrossPredicateConjunction` | 1 | PASS | 1000 | 1000 | Cross-hop StringEquals = AND (conjunction) |
| `TestNullWithBool` | 1 | PASS | 500 | 144 | Null commutativity with Bool |

**Total Property-Based Tests:** 20 (20 PASS)
**Total Hypothesis Examples Generated:** **17,262** (actual executed: 15,342 passing, 0 failing, 1,920 invalid)
**Total Passing Examples:** **15,342**

---

## Properties Validated (Passing Tests)

### 1. IpAddress Static Origin Conjunction Soundness
- **Contract Section:** 3.1, 9.1-9.2
- **Property:** Under static origin assumption, conjunction of IpAddress constraints is sound
- **Test:** `TestIpAddressStaticOriginSoundness.test_ipaddress_static_origin_soundness`
- **Result:** PASS (2000 examples)

### 2. NotIpAddress + IpAddress Set Difference
- **Contract Section:** 3.1, 3.2
- **Property:** IpAddress allow minus NotIpAddress deny = set difference
- **Test:** `TestNotIpAddressWithIpAddress.test_notipaddress_with_ipaddress`
- **Result:** PASS (2000 examples)

### 3. StringEquals Scope Isolation
- **Contract Section:** 3.1, 3.4, 4.4
- **Property:** StringEquals on different scopes never conflict
- **Test:** `TestStringEqualsScopeIsolation.test_string_equals_scope_isolation`
- **Result:** PASS (2000 examples, 1236 invalid from assume filtering)

### 4. Bool Disjunction & Conjunction Semantics
- **Contract Section:** 3.1, 3.5
- **Properties:**
  - Single-hop disjunction (OR semantics)
  - Cross-hop conjunction with session persistence
  - Vacuous disjunction [true, false] = SAT
- **Tests:** `TestBoolDisjunctionSoundness.test_bool_disjunction_soundness`, `test_bool_conjunction_across_hops`
- **Result:** PASS (1452 examples)

### 5. Null Commutativity with StringEquals
- **Contract Section:** 3.6
- **Property:** Null and StringEquals conjunction is commutative
- **Test:** `TestNullCommutativity.test_null_commutativity`
- **Result:** PASS (76 examples)

### 6. Malformed CIDR -> UNKNOWN Fallback
- **Contract Section:** 3.1, 5.2
- **Property:** Malformed CIDR strings yield UNKNOWN, never UNSAT
- **Test:** `TestMalformedCidrReturnsUnknown.test_malformed_cidr_returns_unknown`
- **Result:** PASS (8 examples, exhausted all valid inputs)

### 7. Unsupported Operator -> UNKNOWN Fallback
- **Contract Section:** 3.1, 5.2, 7.4
- **Property:** Unsupported operators yield UNKNOWN, never UNSAT
- **Test:** `TestUnsupportedOperatorReturnsUnknown.test_unsupported_operator_returns_unknown`
- **Result:** PASS (48 examples, exhausted all valid inputs)

### 8. StringLike Wildcard -> UNKNOWN Fallback
- **Contract Section:** 3.4, 5.2
- **Property:** StringLike with wildcards yields UNKNOWN
- **Test:** `TestStringLikeWildcardReturnsUnknown.test_stringlike_wildcard_returns_unknown`
- **Result:** PASS (6 examples, exhausted all valid inputs)

### 9. PIVOT_TRANSITION Network Pivot Rebinding
- **Contract Section:** 4.1, 9.3, Table 8 (CE3)
- **Property:** Network pivot rebinds IP to internal bastion IP via PIVOT_TRANSITION
- **Test:** `TestPivotTransitionRebinding.test_pivot_transition_rebinding`
- **Result:** PASS (2000 examples, generator improved to reduce filtering)

### 10. SAT Witness Validity
- **Contract Section:** 5.1, 6.1
- **Property:** SAT results provide valid constructive witnesses
- **Test:** `TestWitnessSatisfiesConstraints.test_witness_satisfies_constraints`
- **Result:** PASS (2000 examples)

### 11. Iteration Ceiling -> UNKNOWN
- **Contract Section:** 5.2, 7.4
- **Property:** Iteration ceiling triggers UNKNOWN, never UNSAT
- **Test:** `TestIterationCeiling.test_iteration_ceiling`
- **Result:** PASS (100 examples)

### 12. Malformed JSON -> UNKNOWN Fallback
- **Contract Section:** 5.2, 7.4
- **Property:** Malformed JSON sidecars yield UNKNOWN
- **Test:** `TestMalformedSidecarJsonReturnsUnknown.test_malformed_sidecar_json_returns_unknown`
- **Result:** PASS (8 examples, exhausted all valid inputs)

### 13. Mixed IPv4/IPv6 -> UNKNOWN Fallback
- **Contract Section:** 3.1, 5.2
- **Property:** Mixed IPv4/IPv6 CIDR values yield UNKNOWN
- **Test:** `TestMixedIpVersionReturnsUnknown.test_mixed_ipv4_ipv6_returns_unknown`
- **Result:** PASS (500 examples)

### 14. StringLike Without Wildcards = StringEquals
- **Contract Section:** 3.4
- **Property:** StringLike without wildcards is semantically equivalent to StringEquals
- **Test:** `TestStringLikeWithoutWildcards.test_stringlike_without_wildcards_equals_stringequals`
- **Result:** PASS (1000 examples, 121 invalid)

### 15. IpAddress Multi-Value Disjunction (Single Predicate)
- **Contract Section:** 3.1.1
- **Property:** Single IpAddress predicate with multiple values = OR (any CIDR satisfies)
- **Test:** `TestIpAddressMultiValueDisjunction.test_ipaddress_multi_value_is_or`
- **Result:** PASS (500 examples)

### 16. IpAddress Cross-Predicate Conjunction (Multiple Predicates)
- **Contract Section:** 3.1.1
- **Property:** Multiple IpAddress predicates on same key across hops = AND (intersection)
- **Test:** `TestIpAddressCrossPredicateConjunction.test_ipaddress_cross_hop_conjunction`
- **Result:** PASS (1000 examples)

### 17. StringEquals Multi-Value Disjunction (Single Predicate)
- **Contract Section:** 3.1.3
- **Property:** Single StringEquals predicate with multiple values = OR (any value satisfies)
- **Test:** `TestStringEqualsMultiValueDisjunction.test_stringequals_single_hop_multi_value_is_or`
- **Result:** PASS (500 examples, 157 invalid)

### 18. StringEquals Cross-Predicate Conjunction (Multiple Predicates)
- **Contract Section:** 3.1.3, 4.3
- **Property:** Multiple StringEquals predicates on same key across hops = AND (conjunction via produced context)
- **Test:** `TestStringEqualsCrossPredicateConjunction.test_stringequals_cross_hop_conjunction`
- **Result:** PASS (1000 examples, 307 invalid)

### 19. Null Commutativity with Bool
- **Contract Section:** 3.6
- **Property:** Null and Bool conjunction is commutative
- **Test:** `TestNullWithBool.test_null_commutativity_with_bool`
- **Result:** PASS (144 examples, 47 invalid)

---

## Actual Execution Statistics (from Hypothesis Statistics)

### Environment
- **Python:** 3.12.10
- **Hypothesis:** 6.170.12
- **pytest:** 8.1.1
- **Platform:** win32
- **Runtime:** ~35.01s (full property suite)

### Per-Test Statistics (from Hypothesis Statistics Output)

| Test | Passing | Failing | Invalid | Stopped Because |
|------|---------|---------|---------|-----------------|
| `test_ipaddress_static_origin_soundness` | 2000 | 0 | 0 | max_examples=2000 |
| `test_notipaddress_with_ipaddress` | 2000 | 0 | 0 | max_examples=2000 |
| `test_string_equals_scope_isolation` | 2000 | 0 | 1236 | max_examples=2000 |
| `test_bool_disjunction_soundness` | 156 | 0 | 8 | exhausted all combinations |
| `test_bool_conjunction_across_hops` | 1296 | 0 | 44 | exhausted all combinations |
| `test_null_commutativity` | 76 | 0 | 0 | exhausted all combinations |
| `test_malformed_cidr_returns_unknown` | 8 | 0 | 0 | exhausted all inputs |
| `test_unsupported_operator_returns_unknown` | 48 | 0 | 0 | exhausted all inputs |
| `test_stringlike_wildcard_returns_unknown` | 6 | 0 | 0 | exhausted all inputs |
| `test_pivot_transition_rebinding` | 2000 | 0 | 0 | max_examples=2000 |
| `test_witness_satisfies_constraints` | 2000 | 0 | 0 | max_examples=2000 |
| `test_iteration_ceiling` | 100 | 0 | 0 | max_examples=100 |
| `test_malformed_sidecar_json_returns_unknown` | 8 | 0 | 0 | exhausted all inputs |
| `test_mixed_ipv4_ipv6_returns_unknown` | 500 | 0 | 0 | max_examples=500 |
| `test_stringlike_without_wildcards_equals_stringequals` | 1000 | 0 | 121 | max_examples=1000 |
| `test_ipaddress_multi_value_is_or` | 500 | 0 | 0 | max_examples=500 |
| `test_ipaddress_cross_hop_conjunction` | 1000 | 0 | 0 | max_examples=1000 |
| `test_stringequals_single_hop_multi_value_is_or` | 500 | 0 | 157 | max_examples=500 |
| `test_stringequals_cross_hop_conjunction` | 1000 | 0 | 307 | max_examples=1000 |
| `test_null_commutativity_with_bool` | 144 | 0 | 47 | exhausted all combinations |

**Total Actual Passing Examples: 15,342**
**Total Generated Examples (passing + invalid): 17,262**

---

## Root Cause Analysis of Previously Failing Tests

### Test 1: Multiple IpAddress Values (Previously `TestMultipleIpAddressConjunction`)
- **Original Test Expectation:** Multiple values in single IpAddress predicate = AND (conjunction/intersection)
- **Actual Solver Behavior (per Contract 3.1.1):** Multiple values in single predicate = OR (disjunction)
- **Root Cause:** Test expectation contradicted explicit contract specification
- **Resolution:** Replaced with two correct tests:
  1. `TestIpAddressMultiValueDisjunction` - validates single predicate = OR
  2. `TestIpAddressCrossPredicateConjunction` - validates cross-predicate = AND
- **Classification:** A. Incorrect test expectation

### Test 2: StringEquals Across Hops (Previously `TestStringEqualsMultiValueDisjunction`)
- **Original Test Expectation:** Required PRINCIPAL scope values on hop1 (AssumeRole) persist to hop2 without produced context
- **Actual Solver Behavior (per Contract 4.3):** AssumeRole resets principal scope; only produced principal tags carry forward
- **Root Cause:** Test used AssumeRole for hop1 (resets principal scope) and expected required context values to persist without produced context
- **Resolution:** Replaced with two correct tests:
  1. `TestStringEqualsMultiValueDisjunction` - validates single predicate = OR
  2. `TestStringEqualsCrossPredicateConjunction` - validates cross-hop conjunction via produced context
- **Classification:** A. Incorrect test expectation

---

## Historical Comparison

| Metric | Historical (Prior Run) | Current Run |
|--------|----------------------|-------------|
| Property Tests | 11 | 20 |
| Deterministic Tests | 156 | 156 |
| Total Tests | 169 | 176 (156 + 20) |
| Hypothesis Examples | ~5,000+ | **17,262 generated, 15,342 passing** |
| 10,000 Target | NOT MET | **MET (17,262 generated, 15,342 passing)** |
| Soundness Violations | 0 | 0 |

---

## Acceptance Gate Assessment

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Meaningful property tests execute | PASS | 20/20 tests pass |
| 10,000 generated examples | **MET** | **17,262 actual generated, 15,342 passing** |
| No soundness violations | PASS | 0 violations in 15,342+ passing examples |
| Limitations documented | PASS | Documented in this report |

**O1 Classification:** **EMPIRICALLY SUPPORTED** — Tests execute successfully with zero soundness violations across 15,342+ passing generated examples, exceeding the 10,000-example target. No formal proof exists.

---

## Next Steps for O1 Completion

1. **Consider formal proof:** Explore Coq/Isabelle for O1 core logic.
2. **Monitor solver behavior** — Regression tests now cover the corrected semantics.

---

*Report generated: 2026-10-29*
*Test execution: `python -m pytest tests/research/test_rdce_property_based.py -v --tb=short --hypothesis-show-statistics`*
*Full suite: 176 tests (156 deterministic + 20 property-based), all passing*
*Actual generated examples: 17,262 (exceeds 10,000 target); Actual passing examples: 15,342*