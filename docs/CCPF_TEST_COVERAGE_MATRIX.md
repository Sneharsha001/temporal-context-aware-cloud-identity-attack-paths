# RDCE Test Coverage Matrix

**Document:** docs/CCPF_TEST_COVERAGE_MATRIX.md  
**Branch:** 	emporal-context-dev  
**Date:** 2026-10-13  
**Phase:** Post-Prompt-5A (128 tests passing)

---

## 1. Purpose

Maps every confirmed defect finding (F1–F7) and CE fixture to the specific
test cases that validate the fix. Serves as a traceability document for
the independent re-review.

---

## 2. Finding-to-test traceability

### F1 — NotIpAddress and witness soundness

| Test name | File | Validates |
|---|---|---|
| 	est_ip_allowed_cidr_sat | 	est_rdce.py | Basic IpAddress SAT + witness in CIDR |
| 	est_ip_forbidden_cidr_unsat | 	est_rdce.py | Forbidden /24 → UNSAT |
| 	est_not_ip_address_outside_range | 	est_semantic_validation.py | Witness outside denied range |
| 	est_two_quarter_subnets_cover_permitted | 	est_semantic_validation.py | Two /25 deny covers /24 → UNSAT |
| 	est_f1_witness_in_allowed_not_in_denied | 	est_semantic_validation.py | Witness membership assertion |
| 	est_f1_partition_denial_unsat | 	est_semantic_validation.py | Full partition denial |

### F2 — Boolean multivalue semantics

| Test name | File | Validates |
|---|---|---|
| 	est_bool_mfa_required_sat | 	est_rdce.py | Bool true SAT |
| 	est_bool_mfa_false_sat | 	est_rdce.py | Bool false SAT |
| 	est_bool_multivalue_both | 	est_semantic_validation.py | Bool ["true","false"] → domain {T,F} |
| 	est_f2_multivalue_does_not_contradict | 	est_semantic_validation.py | Subsequent narrowing ok |
| 	est_f2_multivalue_all_excluded_unsat | 	est_semantic_validation.py | Empty domain → UNSAT |

### F3 — Predicate-order invariance

| Test name | File | Validates |
|---|---|---|
| 	est_null_positive_predicate_sat_order1 | 	est_semantic_validation.py | Null-first then StringEquals |
| 	est_null_positive_predicate_sat_order2 | 	est_semantic_validation.py | StringEquals-first then Null |
| 	est_null_true_with_positive_unsat | 	est_semantic_validation.py | Null:true + StringEquals → UNSAT |
| 	est_f3_order_invariance_both_permutations | 	est_semantic_validation.py | All permutations agree |
| 	est_f3_contradiction_not_sat_by_order | 	est_semantic_validation.py | No false SAT from ordering |

### F4 — AssumeRole transition handling

| Test name | File | Validates |
|---|---|---|
| 	est_assume_role_scope_reset | 	est_rdce.py | Caller tags reset after AssumeRole |
| 	est_ce6_path_feasibility | 	est_rdce.py | Full CE6 3-hop path SAT |
| 	est_f4_caller_tags_do_not_survive | 	est_semantic_validation.py | Tag exclusion across boundary |
| 	est_f4_target_role_constraints_evaluated | 	est_semantic_validation.py | Target constraints under CE6 |

### F5 — Mixed IPv4/IPv6 handling

| Test name | File | Validates |
|---|---|---|
| 	est_mixed_ipv4_ipv6_unknown | 	est_semantic_validation.py | Mixed families → UNKNOWN |
| 	est_f5_mixed_not_unsat | 	est_semantic_validation.py | UNKNOWN, not false UNSAT |
| 	est_f5_mixed_not_sat | 	est_semantic_validation.py | UNKNOWN, not false SAT |
| 	est_f5_unknown_has_rationale | 	est_semantic_validation.py | UNKNOWN carries diagnostic |

### F6 — String constraints across scopes

| Test name | File | Validates |
|---|---|---|
| 	est_string_equals_principal_scope | 	est_semantic_validation.py | PRINCIPAL scope StringEquals |
| 	est_string_equals_session_scope | 	est_semantic_validation.py | SESSION scope StringEquals |
| 	est_string_equals_config_scope | 	est_semantic_validation.py | CONFIG scope StringEquals |
| 	est_string_equals_request_scope | 	est_semantic_validation.py | REQUEST scope StringEquals |
| 	est_f6_contradictory_session_strings_unsat | 	est_semantic_validation.py | Same key, different values → UNSAT |
| 	est_f6_scope_isolation | 	est_semantic_validation.py | Cross-scope values not merged |

### F7 — Strengthened test assertions

| Test name | File | Validates |
|---|---|---|
| Strengthened FM6 assertions | 	est_semantic_validation.py | SAT + exact witness check |
| Strengthened FM7 assertions | 	est_semantic_validation.py | UNKNOWN + rationale check |
| Stage E: 22 new counterexample tests | 	est_semantic_validation.py | All defects regression |

---

## 3. CE fixture coverage

| Fixture | Location | Expected | Verified |
|---|---|---|---|
| CE1 | 	ests/fixtures/research_context_feasibility/ce1_* | SAT | ✅ |
| CE2 | 	ests/fixtures/research_context_feasibility/ce2_* | UNSAT | ✅ |
| CE3 | 	ests/fixtures/research_context_feasibility/ce3_* | UNKNOWN | ✅ |
| CE4 | 	ests/fixtures/research_context_feasibility/ce4_* | SAT | ✅ |
| CE5 | 	ests/fixtures/research_context_feasibility/ce5_* | UNSAT | ✅ |
| CE6 | 	ests/fixtures/research_context_feasibility/ce6_* | SAT | ✅ |

All CE fixtures pass deterministic validation via alidate_research_fixtures.py.

---

## 4. Test count summary (post-Prompt-5A)

| File | Tests | Status |
|---|---|---|
| 	ests/research/test_rdce.py | 46 | All pass |
| 	ests/research/test_semantic_validation.py | 82 | All pass |
| **Total research suite** | **128** | **All pass** |

---

## 5. Gaps and deferred coverage

| Area | Status |
|---|---|
| DateGreaterThan / DateLessThan | No tests; operator unsupported → UNKNOWN |
| ArnLike / ArnEquals | No tests; operator unsupported → UNKNOWN |
| StringLike wildcards | No tests; operator unsupported → UNKNOWN |
| NumericEquals / comparisons | No tests; operator unsupported → UNKNOWN |
| Dual-stack IPv4+IPv6 soundness proof | Deferred; conservative fallback tested |

---

*Document created: 2026-10-13. Update when new tests are added.*
