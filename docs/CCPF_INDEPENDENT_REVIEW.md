# Independent CCPF Code Review and Soundness Audit

**Document Version:** 1.0.0  
**Review Stage:** Prompt 5 — Independent Code Review & Soundness Audit  
**Target Mechanism:** Context-Conditioned Path Feasibility (CCPF)  
**Evaluator Implementation:** `research/ccpf/rdce.py` (`RestrictedDeterministicConstraintEvaluator`)  
**Evaluator Contract:** `docs/CCPF_EVALUATOR_CONTRACT.md` (v1.1.0)  
**Formal Design Gate:** `docs/CCPF_FORMAL_DESIGN_GATE.md`  
**Test Suites:** `tests/research/test_rdce.py` (46 tests), `tests/research/test_semantic_validation.py` (60 tests)  
**Review Date:** 2026-10-13  
**Reviewer Role:** Independent Senior Cloud-Security & Formal-Methods Reviewer  

---

## 1. Executive Summary and Final Determination

### Final Determination: **NOT READY — CORRECTNESS DEFECTS REMAIN**

While the isolated RDCE prototype demonstrates clean architectural decoupling from Bayesian Q8 probability arithmetic and passes all 106 existing research unit tests, an independent formal soundness audit reveals **multiple confirmed correctness defects** in constraint evaluation, witness generation, and transition modeling.

Specifically:
1. **False-UNSAT Defects:** Valid, feasible attack paths are incorrectly classified as `UNSAT` under vacuous boolean disjunctions (`Bool: ["true", "false"]`), across `sts:AssumeRole` transition boundaries, and in dual-stack IPv4/IPv6 comparisons. In an integrated search engine, these defects would cause **unsound path pruning** (false negatives).
2. **False-SAT Defects:** Provably contradictory constraints are incorrectly classified as `SAT` due to predicate evaluation order dependence (`Null` before `StringEquals`), complete partition denial in `NotIpAddress`, and silent dropping of non-principal `StringEquals` scopes.
3. **Witness Invalidation:** In several satisfiable scenarios with `NotIpAddress`, the evaluator generates a constructive witness IP that directly resides within the forbidden CIDR block, violating the contract requirement for witness satisfiability.
4. **Weak Test Assertions:** The existing 106 tests passed because several tests only asserted `status != UNSAT` rather than validating witness consistency, and did not test predicate permutation or disjunctive multi-value branches.

**Remediation Required:** These defects must be corrected in a dedicated remediation phase before proceeding to integration design (Prompt 6) or production search integration (Prompt 7).

---

## 2. Detailed Findings by Evidence Level

### Finding 1: False-SAT & Non-Satisfying Witness on `NotIpAddress` Exclusion
- **Classification:** Confirmed correctness defect.
- **Severity:** High / Critical for Soundness.
- **Affected Component:** `research/ccpf/rdce.py` lines 548–575.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Sections 2.2, 3.1 (`NotIpAddress`), 5.1 (`SAT` witness validity).
- **Description:**
  1. When an allowed CIDR is partially narrowed by `NotIpAddress` (e.g. `IpAddress: ["10.0.0.0/16"]` and `NotIpAddress: ["10.0.0.0/24"]`), the evaluator returns `SAT`. However, the witness generator blindly selects `first_net.hosts()[0]` (`10.0.0.1`), which resides directly inside the denied network `10.0.0.0/24`. The returned witness fails to satisfy the active policy.
  2. When an allowed CIDR is fully partitioned and covered by multiple denied CIDRs (e.g. `IpAddress: ["10.0.0.0/24"]` and `NotIpAddress: ["10.0.0.0/25", "10.0.0.128/25"]`), the path is mathematically `UNSAT` ($S_{\text{allow}} \setminus \bigcup S_{\text{deny}} = \emptyset$). Because `rdce.py` checks `all(any(a.subnet_of(d) for d in denied_list) for a in allowed_list)`, neither `/25` contains the `/24` as a subnet. The evaluator fails to detect the contradiction, returning `SAT` with an invalid witness (`10.0.0.1`).
- **Minimal Reproduction:**
  ```python
  hop = HopContextSpec(
      hop=1, edge_type="s3:GetObject", src_node_id="u", dst_node_id="b",
      required_context=[
          ContextPredicate(key="aws:SourceIp", operator="IpAddress", values=["10.0.0.0/24"], scope=ContextScope.REQUEST),
          ContextPredicate(key="aws:SourceIp", operator="NotIpAddress", values=["10.0.0.0/25", "10.0.0.128/25"], scope=ContextScope.REQUEST),
      ]
  )
  res = evaluator.evaluate(PathEvaluationInput(path_id="repro_not_ip", hops=[hop]))
  # Actual: res.status == SAT, witness['aws:SourceIp'] == '10.0.0.1' (IN FORBIDDEN SUBNET)
  # Expected: res.status == UNSAT
  ```
- **Impact on Research Claim:** Violates constructive witness validity and causes false SAT verdicts.

---

### Finding 2: False-UNSAT on Disjunctive Boolean Conditions (`["true", "false"]`)
- **Classification:** Confirmed correctness defect.
- **Severity:** High / Soundness Defect (False Pruning).
- **Affected Component:** `research/ccpf/rdce.py` lines 396–420.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Section 3.1 (`Bool` multi-value semantics).
- **Description:**
  AWS IAM and contract v1.1.0 define `Bool: ["true", "false"]` as a vacuous disjunction (satisfied by either boolean state). `rdce.py` inspects only `pred.values[0]`:
  ```python
  truth_str = pred.values[0].strip().lower() if pred.values else ""
  ```
  If `pred.values == ["true", "false"]`, it fixes `b_val = True`. When a subsequent predicate requires `Bool: ["false"]`, the evaluator compares `True != False` and declares `UNSAT`.
- **Minimal Reproduction:**
  ```python
  hop = HopContextSpec(
      hop=1, edge_type="s3:GetObject", src_node_id="u", dst_node_id="b",
      required_context=[
          ContextPredicate(key="aws:MultiFactorAuthPresent", operator="Bool", values=["true", "false"], scope=ContextScope.SESSION),
          ContextPredicate(key="aws:MultiFactorAuthPresent", operator="Bool", values=["false"], scope=ContextScope.SESSION),
      ]
  )
  res = evaluator.evaluate(PathEvaluationInput(path_id="repro_bool", hops=[hop]))
  # Actual: res.status == UNSAT (rationale: 'Active True clashes with required False')
  # Expected: res.status == SAT (with witness MFA=False)
  ```
- **Impact on Research Claim:** Causes false pruning of viable attack paths that traverse optional-MFA or non-MFA policies.

---

### Finding 3: Order-Dependent Soundness Flaw & False-SAT on `Null` and Positive Predicates
- **Classification:** Confirmed correctness defect.
- **Severity:** High / Soundness Defect.
- **Affected Component:** `research/ccpf/rdce.py` lines 365–385 and 434–452.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Section 3.1 (`Null` contradiction condition), Section 3.2 (Hop-level conjunction).
- **Description:**
  A declarative CSP requires commutativity of conjunction ($\phi_1 \land \phi_2 \iff \phi_2 \land \phi_1$). In `rdce.py`, `Null: ["true"]` only inspects previously populated `hop_principal_tags`. If `Null: ["true"]` appears *before* `StringEquals` in `required_context`:
  1. `Null` evaluates: `hop_principal_tags` is empty; passes cleanly.
  2. `StringEquals` evaluates: populates `hop_principal_tags[key] = {"Engineering"}`.
  3. No backwards check occurs. The evaluator outputs **`SAT`** with witness `{'key': 'Engineering'}`.
  Conversely, if `StringEquals` precedes `Null: ["true"]`, it outputs **`UNSAT`**.
- **Minimal Reproduction:**
  ```python
  # Order A: StringEquals, then Null(true) -> UNSAT
  # Order B: Null(true), then StringEquals -> SAT (INCORRECT)
  ```
- **Impact on Research Claim:** Predicate order in JSON policies alters evaluation outcomes; contradictory policies can evaluate to `SAT`.

---

### Finding 4: False-UNSAT Across AssumeRole Boundary Due to Misindexed Pivot Check
- **Classification:** Confirmed correctness defect.
- **Severity:** Medium-High / Soundness Defect.
- **Affected Component:** `research/ccpf/rdce.py` lines 205–216.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Section 4 (Principal Scope Lifecycle), Section 8 (CE6 Falsification Criteria).
- **Description:**
  Line 208 checks `is_identity_pivot = (hop.edge_type == "sts:AssumeRole")`.
  On Hop 2 (which calls an API using assumed-role credentials, e.g. `s3:GetObject`), `hop.edge_type` is `s3:GetObject`, not `sts:AssumeRole`.
  Thus, `is_identity_pivot` evaluates to `False` on Hop 2. The evaluator erroneously copies the caller's principal tags from Hop 1 to Hop 2. If the caller on Hop 1 had `Dept = Dev` and Hop 2 requires `Dept = Ops`, the evaluator declares `UNSAT`, incorrectly treating caller attributes as persistent across the role assumption boundary.
- **Impact on Research Claim:** In multi-hop attack graphs where AssumeRole hops are evaluated without explicit external transition annotations, valid paths are falsely pruned.

---

### Finding 5: Unsound UNSAT on Mixed IPv4/IPv6 Dual-Stack Comparisons
- **Classification:** Confirmed correctness defect.
- **Severity:** Medium.
- **Affected Component:** `research/ccpf/rdce.py` lines 135–144 and 534.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Section 3.1 (`IpAddress` Rejection to UNKNOWN).
- **Description:**
  `intersect_two_cidrs` returns `None` if `net1.version != net2.version`. Under `static_origin_assumption`, the empty intersection immediately triggers `UNSAT`.
  However, contract Section 3.1 explicitly mandates: "Rejection to UNKNOWN: mixed IPv4/IPv6 comparisons without explicit dual-stack semantics". A host operating in a dual-stack environment can communicate via both IPv4 and IPv6 without logical contradiction.
- **Impact on Research Claim:** Violates contract specification; falsely classifies mixed-IP environments as infeasible rather than conservative `UNKNOWN`.

---

### Finding 6: Silent Dropping of Non-Principal Scopes for `StringEquals`
- **Classification:** Confirmed correctness defect.
- **Severity:** Medium.
- **Affected Component:** `research/ccpf/rdce.py` lines 365–385.
- **Contract Reference:** `docs/CCPF_EVALUATOR_CONTRACT.md` Section 3.1 (`StringEquals` Scope: PRINCIPAL, SESSION, or CONFIG).
- **Description:**
  Lines 365–385 check `if scope == ContextScope.PRINCIPAL:` and `elif scope == ContextScope.CONFIG: pass`.
  If `scope == ContextScope.SESSION` (or any other scope), the condition is silently skipped with no evaluation and no error. Two directly contradictory session string constraints (`aws:userid = alice` and `aws:userid = bob`) evaluate to `SAT`.
- **Impact on Research Claim:** Unmodeled scopes fail open to `SAT` instead of falling back to `UNKNOWN` or tracking session strings.

---

### Finding 7: Weak Test Assertions Masking Soundness Defects
- **Classification:** Missing test coverage.
- **Severity:** Medium.
- **Affected Component:** `tests/research/test_semantic_validation.py` (FM6, FM7) and `tests/research/test_rdce.py`.
- **Description:**
  Tests such as `test_not_ipaddress_narrow_not_unsat` and `test_null_false_with_stringequals_not_unsat` assert only `assert r.status != FeasibilityStatus.UNSAT`. They do not assert `status == SAT` and do not verify that the returned witness actually satisfies all predicates. Consequently, invalid witnesses and unmodeled predicates passed the test suite without detection.
- **Impact on Research Claim:** 106 passed tests did not provide independent validation of correctness.

---

### Finding 8: Baseline Test History Clarification
- **Classification:** Documentation clarification.
- **Severity:** Informational.
- **Affected Component:** `verification/FINAL_BASELINE_VERIFICATION_REPORT.md` and `RESEARCH_STATUS.md`.
- **Clarification:**
  - In earlier verification runs, two specific results were recorded:
    1. Research Workspace (`ARF-RT-TEMPORAL`): **910 passed, 2 failed** out of 912 total tests.
    2. Baseline Mirror (`ARF-RT-BASELINE`): **911 passed, 1 failed** out of 912 total tests.
  - Both failures were **performance/timing assertion failures** (`assert runtime < 1.0` in `test_stage1.py` and `assert runtime < 0.5` in `test_stage1b.py`), caused by Windows scheduler load.
  - Neither failure was a process timeout, unhandled exception, or functional logic regression. Functional test parity is 100% (625/625 unit tests, 250/250 golden tests, and 175/175 focused tests pass identical bit-for-bit).

---

## 3. Scope of Claims and Academic Posture

In accordance with rigorous academic and formal-methods standards, the following boundaries are reaffirmed:
- **No Full AWS IAM Semantics Claimed:** CCPF models only a restricted, domain-specific fragment. Operators like wildcards, complex condition blocks, resource policies, and evaluation logic across SCPs remain outside the current scope.
- **No Temporal Expiry Engine:** The evaluator does not model clock-based token expiration or lease durations; temporal context is represented purely through transition invariants and static persistence assumptions.
- **No Search Pruning Theorem Without Evaluator Soundness:** Top-$K$ search pruning cannot be claimed or implemented while false-UNSAT and false-SAT defects exist in the evaluator.
- **Isolated UNKNOWN vs Integrated Behavior:** Isolated fallback on unannotated fixtures (CE5) does not prove integrated Top-$K$ ranking non-perturbation, which requires empirical baseline comparison after integration.

---

## 4. Remediation Roadmap Prior to Prompt 6

Before integration design (Prompt 6) can be initiated, the following remediation tasks must be completed in a dedicated fix phase:
1. **Refactor `rdce.py` IP constraint solver:** Implement explicit interval subtraction for `NotIpAddress` and ensure witness generation picks an IP in $S_{\text{allow}} \setminus \bigcup S_{\text{deny}}$.
2. **Support full `Bool` multi-value disjunction:** Correctly handle `["true", "false"]` as vacuous without fixing truth to `True`.
3. **Enforce commutative conjunction:** Separate predicate parsing from constraint checking, or maintain an explicit state store where `Null` assertions and positive assertions cross-check regardless of order.
4. **Fix AssumeRole boundary indexing:** Check previous hop edge type (`input_data.hops[hop_idx - 2].edge_type == "sts:AssumeRole"`) to reset caller session and principal scopes on the subsequent hop.
5. **Handle mixed IP versions:** Reject mixed IPv4/IPv6 comparisons under static origin to `UNKNOWN` per contract Section 3.1.
6. **Support or reject session `StringEquals`:** Explicitly handle `ContextScope.SESSION` for `StringEquals` or reject to `UNKNOWN`.
7. **Strengthen test assertions:** Add tests verifying witness validity against `NotIpAddress`, predicate order invariance, and disjunctive boolean cases.


---

## 5. Remediation Disposition and Verification Results (Prompt 5A)

**Remediation Date:** 2026-10-13  
**Remediation Target:** `research/ccpf/rdce.py` (`RestrictedDeterministicConstraintEvaluator`)  
**Test Suite Extensions:** `tests/research/test_semantic_validation.py` (Stage E, 22 new counterexamples; strengthened FM6/FM7 assertions)  
**Verification Outcome:** **ALL 6 CONFIRMED DEFECTS RESOLVED**; full research suite: **128 passed / 128 total** in 0.57s.  

### Disposition Table

| Finding ID | Classification | Severity | Summary Description | Remediation Disposition | Evidence & Verification Result |
|---|---|---|---|---|---|
| **F1** | Correctness Defect | High / Soundness | `NotIpAddress` witness invalidity & partition denial failure | **FIXED** | Implemented interval subtraction `subtract_cidr_lists` using prefix decomposition; returns `UNSAT` on full partition denial (`/24` covered by two `/25` subnets); selects witness IP in $S_{\text{allow}} \setminus \bigcup S_{\text{deny}}$. Verified by `TestRemediationF1` (4 tests) and strengthened FM6 test. |
| **F2** | Correctness Defect | High / False Pruning | False-UNSAT on disjunctive `Bool: ["true", "false"]` | **FIXED** | Modeled boolean domains as sets (`hop_session_bool_domains`); vacuous disjunction `["true", "false"]` maintains `{True, False}` domain without fixing truth; subsequent `false` or `true` predicates intersect soundly. Verified by `TestRemediationF2` (4 tests). |
| **F3** | Correctness Defect | High / Soundness | Order-dependent non-commutative conjunction (`Null` vs positive predicates) | **FIXED** | Maintained hop-level `hop_null_assertions`; enforced bidirectional cross-checks between `Null` and positive predicates across all scopes; verified that all predicate permutations yield identical `UNSAT` or `SAT` verdicts. Verified by `TestRemediationF3` (4 tests). |
| **F4** | Correctness Defect | Medium-High / Soundness | Misindexed AssumeRole pivot check causing caller tag leakage | **FIXED** | Transition boundary check inspects predecessor hop (`prev_hop.edge_type == "sts:AssumeRole"` or explicit transition); resets caller session and principal scopes entering target role hop; preconditions evaluated before postconditions so target role attached tags apply to subsequent hops. Verified by `TestRemediationF4` (3 tests). |
| **F5** | Correctness Defect | Medium / Contract | Unsound UNSAT on mixed IPv4/IPv6 comparisons | **FIXED** | Enforced contract Section 3.1 conservative fallback: mixed address families within predicates, across static origin hops, or in CIDR set operations explicitly return `UNKNOWN(unknown_rationale="UNSUPPORTED_MIXED_IP_VERSIONS: ...")` instead of false UNSAT. Verified by `TestRemediationF5` (3 tests). |
| **F6** | Correctness Defect | Medium / Soundness | Silent dropping of non-principal `StringEquals` scopes | **FIXED** | Added full support for all four contract scopes: `PRINCIPAL`, `SESSION`, `CONFIG`, and `REQUEST`. Provided distinct scope isolation stores, cross-hop persistence for session strings across standard actions, and explicit scope diagnostics. Verified by `TestRemediationF6` (4 tests). |
| **F7** | Missing Coverage | Medium / Validation | Weak test assertions masking evaluator soundness defects | **FIXED** | Replaced all `assert r.status != UNSAT` checks in FM6 and FM7 with strict `assert r.status == SAT`, concrete witness IP range checks, and key presence/absence checks. Added 22 targeted counterexample tests across Stage E. |
| **F8** | Documentation | Informational | Baseline test history clarification | **DOCUMENTED** | Reconciled that baseline mirror and research workspace functional parity is 100% (625 unit, 250 golden, 175 focused pass bit-for-bit); the 2 failures were timing threshold assertions under Windows scheduler load. |

---

## 6. Revised Evaluator Determination

### Status: **READY FOR INDEPENDENT RE-REVIEW**

The isolated RDCE implementation has resolved all six identified correctness defects and strengthened all weak test assertions. The research suite now contains **128 deterministic unit and counterexample tests** (46 acceptance tests in `test_rdce.py` + 82 semantic and counterexample tests in `test_semantic_validation.py`), all passing 100%.

The implementation remains strictly decoupled from production Best-First search (`arf_rt/engine/paths.py`), Bayesian Q8 probability scores, and the original baseline mirror (`ARF-RT-BASELINE`).
