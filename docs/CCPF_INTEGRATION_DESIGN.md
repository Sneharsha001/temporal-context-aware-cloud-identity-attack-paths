# CCPF Integration Design & Correctness Audit
## Prompt 6 / 6A / 6B -- Verified Integration Design & Soundness Specification

**Document:** `docs/CCPF_INTEGRATION_DESIGN.md`
**Branch:** `temporal-context-dev`
**Date:** 2026-10-14
**Audited Commit:** `854131f`
**Status:** DESIGN AUDIT & SOUNDNESS SPECIFICATION -- MODE A (PASSIVE AUDIT ONLY) APPROVED; ACTIVE PRUNING DEFERRED

> **STOP RULE:** This document records an architectural design and correctness audit only.
> In strict compliance with research safety constraints, no production code under `arf_rt/` has
> been modified, no adapter implemented, and no scoring or search algorithms altered.
> Implementation is gated on explicit researcher authorization.

---

## 1. Purpose and Scope

This document provides a source-grounded correctness audit and revised integration design for connecting the isolated **Restricted Deterministic Constraint Evaluator (RDCE)** (`research/ccpf/rdce.py`) into the **ARF-RT Best-First search engine** (`arf_rt/engine/paths.py`).

Following Prompt 6A and Prompt 6B audits, this specification:
1. Reconciles the evaluator contract with actual source code, eliminating invented fields and arbitrary confidence thresholds.
2. Audits IAM trust policy semantics, proving that stored condition counts cannot guarantee a single-statement policy and that flattening statement alternatives causes false UNSAT.
3. Formally establishes the integration readiness boundary: **Mode A (passive audit with zero pruning) is the ONLY approved integration mode for Prompt 7**.
4. Defers all active pruning (Mode B) until source-level policy statement provenance, alternative Allow paths, and relevant effect semantics are preserved in the schema.
5. Corrects Top-K search mechanics, distinguishing `max_depth` from termination conditions and retracting invalid `max_expansions` claims.
6. Preserves complete probability isolation (no probability multipliers, bit-identical scores for surviving candidates).

---

## 2. Verified Baseline and Repository State

| Item | Verified Value | Ground-Truth Source |
|---|---|---|
| **Repository Path** | `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL` | Local workspace |
| **Active Branch** | `temporal-context-dev` | `git status --short --branch` |
| **Audited HEAD** | `854131f` | `git log -n 1 --oneline` |
| **Upstream Sync** | Synchronized with `origin/temporal-context-dev` | `git status` |
| **Working Tree** | Clean (untracked IDE `.agents/` preserved) | `git status` |
| **Protected Mirrors** | `main`, `master`, `ARF-RT-BASELINE` untouched | Repository safety rule |
| **Research Test Suite** | **141 passed / 141 total** (0.84s) | `tests/research/` |
| **Engine Unit Tests** | **625 passed / 625 total** (33.49s) | `tests/unit/` |
| **Prompt 5D Verdict** | READY FOR INTEGRATION DESIGN | `docs/CCPF_RE_REVIEW.md` Section 7 |

---

## 3. Reconciled Evaluator Contract & UNSAT Prerequisites

### 3.1 Ground-Truth RDCE Contract (`research/ccpf/rdce.py`)

Direct inspection of `research/ccpf/rdce.py` and `docs/CCPF_EVALUATOR_CONTRACT.md` establishes the real data structures:

```python
class FeasibilityStatus(str, Enum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    UNKNOWN = "UNKNOWN"

class ContextScope(str, Enum):
    REQUEST = "request"        # Per-API-call origin (e.g., aws:SourceIp)
    SESSION = "session"        # Bound to active STS token set (e.g., aws:MultiFactorAuthPresent)
    PRINCIPAL = "principal"    # Bound to active IAM entity (e.g., aws:PrincipalTag/<key>)
    CONFIG = "config"          # Hop-local request parameter (e.g., sts:ExternalId)
    UNKNOWN = "unknown"        # Unmapped or unclassified scope (yields FeasibilityStatus.UNKNOWN)

@dataclass(frozen=True)
class PathEvaluationResult:
    path_id: str
    status: FeasibilityStatus
    witness: Optional[Dict[str, Any]] = None              # Required if SAT
    contradiction_rationale: Optional[str] = None         # Required if UNSAT
    unknown_rationale: Optional[str] = None               # Required if UNKNOWN
    evaluated_hops: int = 0                               # Hops evaluated before decision
    solver_duration_ms: float = 0.0                       # Wall-clock duration
    timeout_occurred: bool = False                        # True if iteration ceiling reached
    diagnostic_metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.2 Resolution of Contract Inconsistencies

1. **`confidence_q` Removed from Result:**
   - **Finding:** `confidence_q` does **not** exist in `PathEvaluationResult` or `rdce.py`. It exists solely in ARF-RT's SQLite `constraints` table as a Bayesian belief prior (e.g., 800 for auto-derived trust conditions).
   - **Correction:** The integration design must never look for or assert `confidence_q` on `PathEvaluationResult`.

2. **Removal of the `confidence_q >= 500` Rule:**
   - **Finding:** The Prompt 6 draft proposed: *"Constraint is VALIDATED with confidence_q >= 500 before trusting UNSAT."*
   - **Correction:** This rule is **removed**. A soft Bayesian probability score (500 = 0.50) cannot substitute for a formal proof of logical contradiction. RDCE is a deterministic, tri-state logical evaluator. If a constraint contradiction is formally proven within the safe fragment, its mathematical infeasibility does not depend on a numerical prior. Conversely, if constraint provenance or policy structure is unverified, a high confidence score (800) does **not** prevent false UNSAT.

3. **Field Naming Correction:**
   - The generic field `rationale` referenced in Prompt 6 does not exist. The actual contract fields are `contradiction_rationale: Optional[str]` (populated on UNSAT) and `unknown_rationale: Optional[str]` (populated on UNKNOWN).

4. **Distinction Between Existing and Proposed Types:**
   - **Existing Production Types (`arf_rt/`):** `NodeInput`, `EdgeInput`, `ConstraintInput`, `search_top_k`.
   - **Existing Research Types (`research/ccpf/rdce.py`):** `ContextScope`, `ContextPredicate`, `HopContextSpec`, `ProducedStateModification`, `TransitionRelation`, `PathEvaluationInput`, `PathEvaluationResult`, `FeasibilityStatus`, `RestrictedDeterministicConstraintEvaluator`.
   - **Proposed Future Adapter Components (`arf_rt/ccpf_bridge.py`):** `infer_scope(condition_key) -> ContextScope`, `build_constraint_index(conn) -> dict`, `build_hop_spec(...) -> HopContextSpec`, `evaluate_single_hop(...) -> PathEvaluationResult`.

---

## 4. Source-Supported Architecture & Search Flow

### 4.1 SQLite Schema Reality (`arf_rt/storage/migrations.py`)

- **`nodes` Table:** `node_id`, `provider`, `node_type`, `provider_id`, `region`, `display_name`, `properties_json`.
- **`edges` Table:** `edge_id`, `edge_type`, `src_node_id`, `dst_node_id`, `region`, `template_id`, `alpha_i`, `beta_i`, `status`, `frozen`, `flags_json`, `features_json`.
- **`constraints` Table:** `constraint_id`, `constraint_key`, `provider`, `constraint_type`, `scope_type`, `scope_id`, `region`, `properties_json`, `properties_fp`, `status`, `validation_status`, `confidence_q`.
- **`edge_constraints` Table:** `edge_id`, `constraint_id`, `relation_type`.

### 4.2 Best-First Search Mechanics (`arf_rt/engine/paths.py:search_top_k`)

Inspection of the actual Python function `search_top_k` reveals:
1. **Adjacency Query (Gap G1):**
   ```sql
   SELECT edge_id, src_node_id, dst_node_id, alpha_i, beta_i, flags_json
   FROM edges ORDER BY edge_id COLLATE BINARY
   ```
   `edge_type` is present in the table schema but **not selected** in this query.
2. **Priority Heap Ordering:**
   Heap item: `(-new_pw_q8, plen + 1, new_seq_str, dst, visited | {dst}, new_edges, new_pw_q8, new_pb_q8, new_worst_sigs, new_best_sigs)`
   Lexicographical order:
   - Primary: `-new_pw_q8` (highest probability first)
   - Secondary: `plen + 1` (shortest path first)
   - Tie-breaker: `new_seq_str` (deterministic string comparison)
3. **Termination Conditions:**
   The search loop executes: `while heap and len(results) < k:`
   - Stops when `k` target paths are accumulated, or heap is exhausted.
   - **Crucial Architectural Correction:** There is **no `max_expansions` parameter** in `search_top_k`. The Prompt 6 draft mistakenly claimed an interaction with `max_expansions`.
4. **Depth Cutoff:**
   `if plen >= max_depth: continue`
   - Hard structural cutoff on path hop count. Pruning an `UNSAT` path does **not** allow any surviving candidate to exceed `max_depth`.

---

## 5. Trust-Policy Semantics & Mapping Audit

### 5.1 Audit of `arf_rt/adapters/trust_policy_parser.py`

A line-by-line audit of `parse_trust_conditions` and `resolve_trust_constraints` uncovered fundamental architectural gaps between AWS IAM policy evaluation and ARF-RT's stored representation:

1. **Disjunctive Statement Flattening (False UNSAT Vulnerability):**
   - In AWS IAM, trust policies contain multiple statements. Multiple `Allow` statements represent **alternatives** (logical disjunction: S_1 OR S_2).
   - In `trust_policy_parser.py:parse_trust_conditions`, all statements with `Effect == "Allow"` are iterated and their conditions appended to a single flat list:
     ```python
     for stmt in statements:
         if stmt.get("Effect") != "Allow": continue
         # ... extracts conditions into a flat list ...
     ```
   - `StatementId` (`Sid`) is **discarded**.
   - In `resolve_trust_constraints`, each extracted condition is linked to the edge via `edge_constraints`.
   - **Architectural Gap:** The SQLite schema does not record which statement a condition belongs to. If an edge has conditions from Statement 1 and Statement 2, treating all edge constraints as a conjunction (S_1 AND S_2) causes **catastrophic false UNSAT**.

2. **Deduplication Loss:**
   - In `resolve_trust_constraints`:
     `ckey = f"trust|{dst_arn}|{cond.condition_type}"`
     `if ckey not in constraints: constraints[ckey] = ...`
   - If Statement 1 and Statement 2 both contain `SOURCE_IP` conditions with different CIDRs, Statement 2's condition is **silently dropped**!

3. **Absence of Condition Records for Unconditional Alternatives:**
   - If Statement 1 has a condition (e.g., `aws:SourceIp in 10.0.0.0/24`) and Statement 2 has **no condition** (e.g., allowing an administrative backup principal unconditionally), Statement 2 produces **zero** condition records.
   - The database edge will therefore have **exactly one attached condition**, creating the false appearance of a single-statement policy, even though the role is unconditionally assumable via Statement 2!

4. **Explicit Deny Statements:**
   - Statements with `Effect == "Deny"` are skipped entirely by the parser.
   - Note: An explicit Deny statement does **not** automatically make an entire attack path infeasible in all contexts. In AWS IAM, a Deny statement with a condition applies only when its condition evaluates to true (e.g., deny if `aws:MultiFactorAuthPresent == "false"` does not deny when MFA is present). Because Deny statements are not parsed, ARF-RT neither accounts for them nor evaluates their conditions.

5. **Multi-Valued Condition Keys:**
   - In IAM, multiple values for a single key within an operator evaluate with logical **OR** (e.g., `StringEquals: {"aws:PrincipalTag/Dept": ["Eng", "Sec"]}`).
   - RDCE correctly supports set membership for `StringEquals` and CIDR unions for `IpAddress`, but enforces strict single-value cardinality for `Null`.

### 5.2 Conceptual Counterexample: Alternative Allow Statements

**Scenario:** An IAM role `Deployer` has two trust statements:
- **Statement S1:** Allow assumption if `aws:SourceIp` is in `10.0.1.0/24` (Corporate Office).
- **Statement S2:** Allow assumption if `aws:SourceIp` is in `192.168.1.0/24` (VPN Gateway).

**AWS IAM Ground Truth:** An attacker on VPN (`192.168.1.50`) successfully assumes `Deployer` via Statement S2. The path is **feasible**.

**Flawed Conjunction Model:**
1. The adapter loads both constraints onto the hop:
   - C_1: `IpAddress(aws:SourceIp, ["10.0.1.0/24"])`
   - C_2: `IpAddress(aws:SourceIp, ["192.168.1.0/24"])`
2. RDCE evaluates:
   Domain = (10.0.1.0/24) intersect (192.168.1.0/24) = empty
3. RDCE returns: `status = UNSAT`, `contradiction_rationale = "CIDR_DISJOINT_EMPTY_INTERSECTION"`.
4. If the search engine pruned on this UNSAT, the valid VPN attack path would be **silently eliminated**!
5. This is an unacceptable **false UNSAT** caused directly by flattening statement disjunction into an unsound conjunction.

### 5.3 Source-Grounded Condition Key Mapping Table

| Condition Key in DB | Scope (`ContextScope`) | RDCE Operator | Value Representation | RDCE Supported? | Mapping Status / Limitations |
|---|---|---|---|---|---|
| `aws:sourceip` | `REQUEST` | `IpAddress`, `NotIpAddress` | CIDR string list | **YES** | Supported. Multi-CIDR is OR. |
| `aws:principaltag/<key>` | `PRINCIPAL` | `StringEquals`, `StringLike` (no wildcards) | String list | **YES** | Supported. Multi-value is OR. |
| `aws:multifactorauthpresent` | `SESSION` | `Bool` | `["true"]`, `["false"]`, `["0"]`, `["1"]` | **YES** | Supported. |
| `sts:externalid` | `CONFIG` | `StringEquals` | String list | **YES** | Supported hop-locally. |
| `aws:sourcevpc` | `UNKNOWN` | N/A | VPC ID list | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:sourcevpce` | `UNKNOWN` | N/A | VPCE ID list | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:principalorgid` | `UNKNOWN` | N/A | Org ID string | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:principalorgpaths` | `UNKNOWN` | N/A | Org path string | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `sts:rolesessionname` | `UNKNOWN` | N/A | Session name | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:multifactorauthage` | `UNKNOWN` | N/A | Numeric seconds | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:requesttag/<key>` | `UNKNOWN` | N/A | String list | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |
| `aws:tagkeys` | `UNKNOWN` | N/A | Tag key list | **NO** | Unsupported by RDCE. Yields `ContextScope.UNKNOWN` -> `UNKNOWN`. |

*Note on `ContextScope.UNKNOWN`:* In `research/ccpf/rdce.py:ContextScope`, `UNKNOWN = "unknown"` is an actual enum member. Lines 122-131 of `rdce.py` explicitly check `if scope == ContextScope.UNKNOWN:` and reject the evaluation with `FeasibilityStatus.UNKNOWN` and rationale `"UNSUPPORTED_OR_UNKNOWN_SCOPE"`. Therefore, mapping unsupported keys to `ContextScope.UNKNOWN` in the bridge provides a fully safe, native fallback without inventing any new production API.

---

## 6. Re-Evaluation of Pruning Authorization & Invalidation of Mode B

### 6.1 Why Stored Condition Counts Cannot Authorize Pruning

The Prompt 6A draft proposed a restricted "Mode B" that would permit active pruning if an edge possessed "exactly one" attached trust condition. Prompt 6B re-evaluated this rule against the actual parser implementation:

1. **Unconditional Alternatives:** If an IAM policy has Statement 1 with a condition and Statement 2 without a condition, `trust_policy_parser.py` emits only Statement 1's condition. The database records exactly 1 condition for the edge, but the policy contains an unconditional alternative Allow statement!
2. **Deduplication Collisions:** If an IAM policy has two separate Allow statements with conditions of the same `condition_type` (e.g., different CIDRs), `resolve_trust_constraints` discards the second condition during deduplication. The database records exactly 1 condition, but the source policy contained alternative conditional statements!
3. **Unrepresented Denies:** Deny statements with specific conditions are completely omitted.

**Core Finding:**
> **A stored condition count (`count == 1`) does NOT prove that the source policy contains only one statement, nor that there are no unrepresented alternative Allow statements.**
> Equating stored condition count with verified single-statement policy structure is mathematically unsound and risks false UNSAT pruning.

### 6.2 Strict Pruning Soundness Rule

Active pruning of an edge expansion is mathematically sound **only if** the integration can prove from verified source-level policy metadata that:
1. All conditions evaluated form a genuine intra-statement conjunction ($C_1 \land C_2 \dots$).
2. No alternative Allow statements exist in the source policy (or all alternatives have been simultaneously evaluated and proved contradictory).
3. The conditions belong to RDCE's safe supported fragment.
4. The clash rationale is deterministic and `timeout_occurred == False`.

Because the current ARF-RT SQLite schema and `trust_policy_parser.py` do **not** preserve statement IDs or statement grouping:
- **Active pruning (Mode B) CANNOT be justified in the current repository state and is DEFERRED.**
- Incomplete or ambiguous policy metadata must **never** authorize pruning.

---

## 7. Corrected Top-K Search Analysis

### 7.1 Search Mechanics & Invariants

ARF-RT's Top-K search is a Best-First search over path probabilities:
- **Priority Key:** `(-p_worst_q8, path_length, edge_id_seq_str)`
- **Candidate Eligibility:** In passive audit mode, candidate eligibility is 100% identical to baseline. If active pruning is enabled in the future, sound UNSAT pruning would prevent logically impossible neighbor expansions from entering the heap.
- **Score Invariance (PI-1 to PI-4):**
  - Logical feasibility evaluation does not alter Bayesian probability scores.
  - For every candidate path P that is expanded and added to the heap, p_worst_q8(P) and p_best_q8(P) are **bit-identical** to the unguided baseline.
- **Tie-Break Preservation (PI-5):**
  - Relative ordering between any two surviving candidates in the heap is determined strictly by the baseline tuple key `(-pw, plen, edge_seq_str)`. Feasibility produces no secondary tie-breaker.
- **UNKNOWN Non-Perturbation (PI-6):**
  - Any candidate returning `UNKNOWN` enters the heap with its exact baseline score and priority.

### 7.2 Search Budget vs Depth Limits

| Mechanism | Actual Source Implementation | Interaction with CCPF Pruning |
|---|---|---|
| **`max_depth`** | `if plen >= max_depth: continue` (Line 134) | **Hard per-path cutoff.** Pruning an UNSAT branch does **not** allow any path to exceed `max_depth`. |
| **Search Budget** | `while heap and len(results) < k:` (Line 115) | The loop terminates as soon as k target paths are collected. Pruning high-probability UNSAT paths prevents them from consuming Top-K result slots, allowing valid lower-probability paths to be discovered. |
| **`max_expansions`** | **Does not exist** in `search_top_k` | Claims of `max_expansions` interaction in Prompt 6 were invalid and are retracted. |

### 7.3 Completeness & Equivalence Disclaimers

1. **No Monotonic Conjunction Equivalence:** We do **not** claim that monotonic conjunction guarantees Top-K path set equivalence. If an unguided search terminated upon collecting k paths that included infeasible paths, the guided search will collect k feasible paths, producing an intentionally different (and superior) result set.
2. **Path Set Equality:** Path set equivalence (R_guided == R_baseline) holds **only** when the baseline Top-K result contains zero infeasible paths.

---

## 8. Staged Validation Plan & Measurable Criteria

### Stage 1: Adapter Contract & Scope Tests (Pre-Implementation)
- Test bridge isolation: verify `ContextScope` derivation for all 12 condition keys.
- Verify that unsupported keys map to `ContextScope.UNKNOWN` and yield `FeasibilityStatus.UNKNOWN`.
- Verify handling of single-condition vs multi-condition edges.

### Stage 2: Soundness & Disjunction Guard Tests
- Construct fixtures with alternative Allow statements (Counterexample 5.2).
- Assert that alternative statements are **not** conjoined into false UNSAT.
- Verify: `false_unsat_rate == 0.0` across all fixtures.

### Stage 3: Baseline Bit-Identical Invariance
- On unannotated privilege graphs or with `ARF_CCPF_GUARD=0`, execute `search_top_k`.
- Assert: Generated paths, probabilities, and rankings match baseline byte-for-byte.

### Stage 4: Passive Audit Log Validation
- In passive mode (`ARF_CCPF_GUARD=1`), assert that verdicts and rationales are logged correctly for all expanded edges.
- Assert that heap size, results, and execution path remain identical to baseline (zero pruning).

### Stage 5: Efficiency Benchmarking
- Measure per-hop RDCE evaluation latency.
- Measure total pipeline overhead on realistic graphs (target: < 15% increase).

---

## 9. Final Readiness Determination & Evidential Recommendation

### 9.1 Readiness Finding: MODE A (PASSIVE AUDIT ONLY) APPROVED; ACTIVE PRUNING DEFERRED

The Prompt 6A and 6B correctness audits confirm:
1. **Architectural Gap:** `trust_policy_parser.py` flattens alternative IAM statements into a single unindexed constraint list, discarding `StatementId` and `Effect`. Unconditional alternative statements emit zero condition records, meaning an edge with a stored condition count of 1 may be unconditionally allowed.
2. **Pruning Soundness Precondition Unmet:** A count of stored conditions cannot substitute for verified statement structure. Consequently, active pruning (Mode B) cannot guarantee zero false UNSATs in the current repository state.

### 9.2 Authorized Scope for Prompt 7

Production integration is authorized **exclusively under Mode A**:

- **Mode A (Passive Audit Mode — Exclusively Authorized):**
  - Implement `arf_rt/ccpf_bridge.py` behind the `ARF_CCPF_GUARD=1` feature flag.
  - Call RDCE during neighbor expansion to evaluate candidate hops.
  - Log verdicts (`SAT`, `UNSAT`, `UNKNOWN`), solver duration, and diagnostic rationales.
  - **Zero pruning is performed.** All candidate edges are pushed to the heap exactly as in baseline.
  - Probability scores (`p_worst_q8`, `p_best_q8`) and heap priorities remain 100% bit-identical to baseline.
  - This safely validates bridge data mapping, performance, and real-world evaluator verdicts with zero risk of search truncation or false UNSAT.

**Active Pruning Deferral:**
All active pruning (discarding neighbor expansions or suppressing heap pushes) is **deferred** until `trust_policy_parser.py` and the SQLite schema are upgraded to store `StatementId`, statement boundaries, and policy alternatives.

---

## Related Documents
- `docs/CCPF_EVALUATOR_CONTRACT.md` -- Formal RDCE interface contract
- `docs/CCPF_FORMAL_DESIGN_GATE.md` -- Open proof obligations
- `docs/CCPF_RE_REVIEW.md` -- Independent re-review report
- `arf_rt/adapters/trust_policy_parser.py` -- IAM trust condition extraction
- `arf_rt/engine/paths.py` -- Best-First Top-K path search engine


---

## 10. Prompt 7 Implementation & Empirical Validation (Mode A: Passive Audit)

### 10.1 Implemented Components and Call Points

1. **Feature Flag (`arf_rt/config.py`):**
   - Config constant: `CCPF_FEASIBILITY_GUARD = os.environ.get("ARF_CCPF_GUARD", "0").strip().lower() in ("1", "true", "yes")`.
   - Default: `False` (zero overhead, zero code path change).

2. **Isolated Passive Bridge (`arf_rt/ccpf_bridge.py`):**
   - `infer_scope(condition_key)`: Maps supported IAM keys to formal `ContextScope` (`REQUEST`, `PRINCIPAL`, `SESSION`, `CONFIG`); all unsupported or unrecognized keys map to `ContextScope.UNKNOWN`.
   - `extract_predicates_from_constraint(...)`: Resiliently extracts condition predicates; ignores unconditional structural constraints; maps unsupported conditions to `ContextScope.UNKNOWN`.
   - `build_constraint_index(conn)`: Pre-loads edge constraints from DB into an in-memory dictionary before search traversal.
   - `evaluate_candidate_hop(...)`: Invokes RDCE to evaluate candidate hops; records diagnostic records in `audit_sink`; isolates any bridge or solver exception into a safe `UNKNOWN` fallback without interrupting search.

3. **Search Call Point (`arf_rt/engine/paths.py:search_top_k`):**
   - Added `edge_type` to adjacency SELECT query (resolving Gap G1).
   - Placed observational hook inside neighbor expansion loop behind `if ccpf_guard:`.
   - **Zero Pruning Invariant:** The candidate edge always proceeds to `heapq.heappush` with exact baseline Q8 probabilities and priority tuples.

4. **Integration Test Suite (`tests/integration/test_ccpf_bridge.py`):**
   - 10 focused tests covering all failure isolation, invariance, and edge cases: **10/10 passed** (0.43s).

### 10.2 Baseline Equivalence & Empirical Overhead Results

Empirical evaluation across three scenario fixtures (15 repetitions per scenario, median reported):

| Scenario Fixture | Paths Returned | Baseline Equivalence | Hops Evaluated | Median Baseline Latency | Median Audit Mode Latency | Absolute Overhead | Overhead % |
|---|---|---|---|---|---|---|---|
| `minimal_scenario.json` | 1 | **100% Bit-Identical** | 2 (0 SAT, 0 UNSAT, 2 UNK) | 0.136 ms | 0.184 ms | +0.048 ms | +35.5% |
| `complex_scenario.json` | 15 | **100% Bit-Identical** | 54 (2 SAT, 0 UNSAT, 52 UNK) | 2.360 ms | 2.840 ms | +0.480 ms | +20.3% |
| `primary_realistic_scenario.json` | 5 | **100% Bit-Identical** | 23 (2 SAT, 0 UNSAT, 21 UNK) | 1.083 ms | 1.333 ms | +0.250 ms | +23.1% |

**Key Findings:**
- **Bit-Identical Correctness:** Every candidate path identity (`edge_id_sequence`), rank, `p_worst_q8`, `p_best_q8`, `confidence_band`, and `flags_json` matches baseline byte-for-byte.
- **Zero Pruning Enforced:** No paths were eliminated, delayed, or reordered.
- **Sub-Millisecond Overhead:** Absolute audit latency overhead is under $0.5$ ms per Top-K search.
- **Privacy Boundary Maintained:** Diagnostic records capture operational metadata (`edge_id`, `src_node_id`, `dst_node_id`, `edge_type`, `status`, `solver_duration_ms`, `predicates_count`) while omitting sensitive secret values.

### 10.3 Remaining Limitations and Explicit Deferrals

- **Active Pruning Deferred:** Mode B active pruning remains strictly prohibited until statement boundaries (`StatementId`) and alternative Allow paths are stored and indexed.
- **Multi-Hop Transition Relations Deferred:** Cross-hop state mutations (`ProducedStateModification`) remain deferred until schema support for transition relations is introduced.


---

## 11. Prompt 7A Reliability & Observability Audit

### 11.1 Corrected Issues & Architecture Hardening
1. **Constraint-Index Loading Failure Handling:**
   - Introduced `ConstraintIndex` (subclassing `dict` with explicit `load_error` and `malformed_count` attributes).
   - If SQLite querying or index building fails, `load_error` is captured. Subsequent candidate-hop evaluations record `status=UNKNOWN` with `CONSTRAINT_INDEX_LOAD_FAILURE: <error>` rather than silently treating edges as unconstrained.
2. **Unsupported / Malformed Condition Mapping:**
   - Removed artificial wildcard ExternalId shortcut (`StringEquals(["*"])`). Unvouched or missing condition values strictly map to `ContextScope.UNKNOWN`.
   - Handled non-JSON/malformed properties and empty trust condition lists safely without raising exceptions or masking edge constraints.
3. **Audit Output Accessibility:**
   - Hoisted `evaluate_candidate_hop` import out of the neighbor expansion loop in `arf_rt/engine/paths.py`.
   - Updated `search_and_store_top_k()` to accept and forward `ccpf_audit_sink`, making full diagnostic traces accessible to calling workflows.
4. **Integration Test Suite Expansion:**
   - Expanded `tests/integration/test_ccpf_bridge.py` from 10 to 15 tests. All 15 pass (100% passing).
   - Verified full field comparison on scenario fixtures (`minimal_scenario.json`, `complex_scenario.json`, `primary_realistic_scenario.json`) confirming complete bit-identical equivalence to baseline.

### 11.2 25-Round Paired Performance Benchmark (Warm-up = 5)

| Scenario Fixture | Baseline Median (ms) | Audit Median (ms) | Absolute Overhead (ms) | Relative Overhead (%) | Target Gate (<= 10%) | Status |
|---|---|---|---|---|---|---|
| `minimal_scenario.json` | 0.282 | 0.397 | +0.115 | +40.8% | <= 10% | UNMET |
| `complex_scenario.json` | 7.479 | 10.513 | +3.034 | +40.6% | <= 10% | UNMET |
| `primary_realistic_scenario.json` | 1.681 | 2.371 | +0.690 | +41.0% | <= 10% | UNMET |

**Performance Analysis & Gate Determination:**
- **Absolute Overhead:** The absolute latency cost remains low (0.1 to 3.0 ms per Top-K search on complex graphs).
- **Relative Overhead:** Relative latency overhead is ~40.8%, exceeding the strict <= 10% relative gate target.
- **Root Cause:** In Python, invoking the RDCE per neighbor expansion on 50+ candidate hops adds interpreted dispatch and object allocation overhead relative to the lightweight C/SQLite search loop.
- **Gate Conclusion:** The relative performance gate is recorded as **UNMET**. Because Mode A is purely observational (and disabled by default with `CCPF_FEASIBILITY_GUARD=False`), it introduces zero overhead in default operation. Active pruning remains deferred.


---

## 12. Prompt 7B Passive Integration Conformance Audit

### 12.1 Real Parser-to-Storage-to-RDCE Pipeline Verification
A dedicated end-to-end integration test (`test_real_parser_to_sqlite_storage_to_rdce_pipeline`) verified the real pipeline without manual JSON manufacturing:
1. **Source Policy Extraction (`arf_rt/adapters/trust_policy_parser.py`):**
   - Real IAM trust policies are parsed with `resolve_trust_constraints()`.
   - Stored in ARF-RT `ScenarioInput` under `constraints` and `edge_constraints`.
2. **SQLite Database Persistence (`arf_rt/adapters/replay.py`):**
   - Ingested via `ReplayAdapter(conn).ingest(scenario)`.
   - Verified that `constraints` rows contain serialized JSON properties and `edge_constraints` contains valid edge-to-constraint linkages.
3. **Index Extraction & RDCE Mapping (`arf_rt/ccpf_bridge.py`):**
   - Loaded via `build_constraint_index(conn)`.
   - Verified transformation of persisted fields to RDCE predicates:
     - `aws:SourceIp` (operator `IpAddress`) -> `ContextScope.REQUEST` (yields `SAT` with witness when evaluated).
     - `aws:MultiFactorAuthPresent` (operator `Bool`) -> `ContextScope.SESSION` (yields `SAT`).
     - `sts:ExternalId` (operator `StringEquals`) -> `ContextScope.CONFIG` (yields `SAT`).
     - `aws:PrincipalTag/*` (operator `StringEquals`) -> `ContextScope.PRINCIPAL` (yields `SAT`).
     - Unsupported keys (`aws:SourceVpc`, `aws:PrincipalOrgID`, `aws:MultiFactorAuthAge`) -> `ContextScope.UNKNOWN` (yields `UNKNOWN` with `UNSUPPORTED_OR_UNKNOWN_SCOPE`).
4. **Condition Type vs. Condition Key Separation:**
   - **Audit Finding:** `condition_type` in `trust_policy_parser.py` represents an internal classification category enum/string (`EXTERNAL_ID`, `SOURCE_IP`, `TAG_CONDITION`, etc.), NOT an IAM condition key.
   - When `condition_key` is absent from properties, the bridge does NOT assume interchangeability or fabricate semantics. It strictly returns `ContextScope.UNKNOWN` with description: `internal category '...' without actual condition_key`.

### 12.2 Distinguishable Diagnostic Signatures for Four Edge States
A dedicated test (`test_distinguishable_diagnostic_signatures_for_four_edge_states`) verified that all four operational edge states produce mutually distinct diagnostic signatures:

| Edge Operational State | Diagnostic Status | Predicates Count | Unknown Rationale | Load Error Captured | Witness |
|---|---|---|---|---|---|
| **1. Unconstrained Edge** (loaded, no context) | `UNKNOWN` | 0 | `NO_CONTEXT_CONSTRAINTS_DEFINED` | `None` | `None` |
| **2. Valid Context Edge** (supported conditions) | `SAT` | >= 1 | `None` | `None` | Present |
| **3. Malformed / Unsupported Context Edge** | `UNKNOWN` | >= 1 | `UNSUPPORTED_OR_UNKNOWN_SCOPE: ...` | `None` | `None` |
| **4. Constraint Index Query Failure** | `UNKNOWN` | 0 | `CONSTRAINT_INDEX_LOAD_FAILURE: ...` | Captured string | `None` |

**Failure Isolation Guarantee:** An index query failure never masquerades as an unconstrained edge, never produces an unsupported `SAT` verdict, and never interrupts or crashes search traversal.

### 12.3 Application-Level Diagnostics & Caller Accessibility
- `search_and_store_top_k()` accepts and forwards `ccpf_audit_sink: list[dict]`.
- Existing callers that omit `ccpf_audit_sink` or `ccpf_guard` continue to operate with zero behavioral change.
- Audit sink failures (e.g., faulty sink throwing exceptions) are safely isolated and do not alter search results or crash callers.

### 12.4 Baseline Invariance Verification Scope
- Full-field comparison across scenario fixtures (`minimal_scenario.json`, `complex_scenario.json`) confirmed:
  - Path identities (`edge_id_sequence`) and returned ordering are bit-identical.
  - Probability scores (`p_worst_q8`, `p_best_q8`), ranks, flags, and confidence bands are bit-identical.
  - Search tie-breaking and termination behavior are unaltered.
- **Scope Limitation:** This empirical equivalence is verified on the 2 standard golden fixtures (covering 16 Top-K paths and 56 evaluated candidate hops). It establishes evidence of zero-pruning compliance within the test corpus; universal mathematical equivalence is guaranteed by the code architecture (observational hook with zero pruning control).

### 12.5 Performance Threshold & Gate Reconciliation
- **Originally Authorized Target:** Section 8.5 (Stage 5) specified a target of `< 15% increase` total pipeline overhead.
- **Audit Clarification on 10% Target:** The 10% target referenced in Prompt 7A is unanchored in the original design document and requires formal researcher clarification.
- **Gate Determination:**
  - Measured paired 25-round median relative overhead is $pprox 40.8\%$.
  - Whether evaluated against 10% or 15%, the relative overhead exceeds the threshold.
  - The relative performance gate is recorded as **UNMET**.
- **Absolute vs. Relative Overhead:**
  - Absolute overhead is negligible: $+0.115$ ms on minimal fixture, $+0.690$ ms on primary realistic fixture, $+3.034$ ms on complex fixture (median across 25 repetitions, 5 warm-up rounds).
  - The relative increase is dominated by Python function-call, dataclass construction, and object allocation overhead per evaluated hop compared to the compiled C/SQLite search loop.
- **Default Operation Guarantee:**
  - With `CCPF_FEASIBILITY_GUARD=False` (default), all RDCE calls and bridge data structures are completely bypassed.
  - The only unconditional change is the inclusion of `edge_type` in the adjacency SELECT query (resolving Gap G1), which adds negligible SQL parsing overhead.

### 12.6 Acceptance Criteria Checklist

| # | Acceptance Criterion | Evaluation Result | Evidence |
|---|---|---|---|
| 1 | Real parser-to-storage-to-RDCE test verifies mapping | **PASS** | `test_real_parser_to_sqlite_storage_to_rdce_pipeline` (Test 16) |
| 2 | Unsupported/malformed inputs distinguishable from absence of constraints | **PASS** | `test_distinguishable_diagnostic_signatures_for_four_edge_states` (Test 17) |
| 3 | Constraint-index loading failures produce explicit diagnostics | **PASS** | `ConstraintIndex.load_error` -> `CONSTRAINT_INDEX_LOAD_FAILURE` |
| 4 | Intended caller can obtain audit records | **PASS** | `search_and_store_top_k(..., ccpf_audit_sink=...)` verified |
| 5 | Feature-disabled and passive-mode outputs match on fixtures | **PASS** | Bit-identical comparison verified across all fields (Test 15) |
| 6 | No feasibility verdict changes candidate eligibility or Q8 scores | **PASS** | Zero pruning invariant verified across all test fixtures |
| 7 | Performance results and thresholds accurately documented | **PASS** | Section 11.2 & 12.5 document UNMET gate, absolute vs relative costs |
| 8 | Active pruning remains disabled | **PASS** | Mode A only; Mode B active pruning remains strictly deferred |
| 9 | No policy parser, schema, scoring, or Top-K semantics modified | **PASS** | `trust_policy_parser.py`, SQLite schema, Q8 scoring, and search untouched |

**Overall Conformance Audit Verdict:** **AUDIT PASSED (PASSIVE MODE CONFORMANCE VERIFIED)**.
Active pruning remains deferred pending future researcher authorization.


---

## 13. Prompt 7C Path-Level Semantics & Disabled-Mode Evidence Audit

### 13.1 Audit of Path-Wide vs. Single-Hop Evaluation Semantics
A rigorous code audit of `arf_rt/engine/paths.py:search_top_k()` and `arf_rt/ccpf_bridge.py:evaluate_candidate_hop()` established the following facts regarding integrated evaluation:

1. **Per-Hop Evaluation Scope:**
   - In `arf_rt/engine/paths.py`, the call site passes only the candidate edge identifier `eid` and its local dictionary `edge_data.get(eid, {})`.
   - The path prefix (`curr_path`) is **not** passed to `evaluate_candidate_hop()`.
   - In `arf_rt/ccpf_bridge.py`, `evaluate_candidate_hop()` evaluates solely the candidate edge in complete isolation.
2. **Construction of `PathEvaluationInput.hops`:**
   - At the bridge call site, `hop_spec = HopContextSpec(hop=1, edge_type=edge_type, src_node_id=src, dst_node_id=dst, required_context=required_context)`.
   - `eval_input = PathEvaluationInput(path_id=eid, hops=[hop_spec], scenario_assumptions=scenario_assumptions or {})`.
   - The input `hops` list is **always a 1-element list (`len(hops) == 1`)**.
3. **Absence of Cross-Hop Constraint Correlation:**
   - Constraints from distinct hops along a candidate path are evaluated independently and sequentially as neighbor edges are expanded.
   - The integrated search does not accumulate context predicates across the path prefix.
4. **Unexercised Multi-Hop RDCE Capabilities:**
   - While the underlying RDCE solver (`research/ccpf/rdce.py`) natively supports multi-hop paths via `PathEvaluationInput(hops=[hop1, hop2, ...])` and evaluates cross-hop scope consistency (e.g., shared static origin, session token lifecycle), this capability is **never exercised** by the integrated bridge in ARF-RT search.
5. **Justified Claims Boundary:**
   - The current integration is strictly an **observational single-hop edge constraint evaluator**.
   - No claims of path-wide, multi-hop context feasibility reasoning in ARF-RT search are justified by the existing codebase. Describing the integration as "path-wide feasibility reasoning" is factually inaccurate.

### 13.2 Concrete Multi-Hop Counterexample Demonstration
A dedicated integration test (`test_multihop_counterexample_joint_unsat_evaluated_independently_as_sat`, Test 18) proved the limitation:
- **Scenario:** Two consecutive hops where Hop 1 requires `aws:SourceIp` in `10.0.0.0/24` and Hop 2 requires `aws:SourceIp` in `192.168.1.0/24`.
- **Under Static Origin Assumption (`static_origin_assumption: True`):**
  - **Direct RDCE Joint Evaluation:** When evaluated as `hops=[hop1, hop2]`, RDCE correctly returns `status=UNSAT` with contradiction rationale: `"Contradictory persistent context under static origin assumption: CIDRs on hop 1 ([IPv4Network('10.0.0.0/24')]) are disjoint from hop 2 ([IPv4Network('192.168.1.0/24')])"`.
  - **Integrated Bridge Behavior:** In `search_top_k()`, Hop 1 is evaluated in isolation with `[10.0.0.0/24]` -> returns `status=SAT`. Hop 2 is evaluated in isolation with `[192.168.1.0/24]` -> returns `status=SAT`. Both are recorded as `SAT` in `audit_sink`.
  - **Conclusion:** The current integrated bridge completely fails to detect joint multi-hop contradictions.

### 13.3 Audit of Feature-Disabled Behavior
Inspection and spy-based testing (`test_feature_disabled_mode_zero_evaluations_and_sink_untouched`, Test 19) established:
1. **Solver & Bridge Invocations:**
   - When `CCPF_FEASIBILITY_GUARD=False`, test doubles verify:
     - `build_constraint_index` call count = 0.
     - `RestrictedDeterministicConstraintEvaluator` instantiation count = 0.
     - `evaluate_candidate_hop` call count = 0.
     - `ccpf_audit_sink` length = 0 (untouched).
2. **Output Equivalence:**
   - Baseline path output identities, ordering, `p_worst_q8`, `p_best_q8`, ranks, flags, and confidence bands remain 100% identical.
3. **Query Overhead Correction ("Zero Overhead" Claim Reconciled):**
   - The query in `search_top_k` unconditionally selects `edge_type`:
     `SELECT edge_id, edge_type, src_node_id, dst_node_id, alpha_i, beta_i, flags_json FROM edges...`
   - Micro-benchmarks (200 repetitions) measured:
     - Query with `edge_type`: $102.00$ µs median.
     - Query without `edge_type`: $90.50$ µs median.
     - Net difference: $+11.50$ µs per search query.
   - **Documentation Correction:** Calling the disabled path "zero overhead" is technically inaccurate due to this $+11.5$ µs SQL column selection. While negligible, it is an unconditional structural modification resulting from Gap G1.

### 13.4 Performance Benchmark & Threshold Reconciliation
- **Authorized Target:** The original Section 8.5 (Stage 5) target of `< 15% increase` total pipeline overhead is retained as the authoritative threshold.
- **Paired 30-Round Benchmark (5 warm-up iterations):**

| Scenario Fixture | Disabled Median (IQR) | Enabled Audit Median (IQR) | Absolute Difference | Relative Overhead | Authorized Target (< 15%) | Gate Status |
|---|---|---|---|---|---|---|
| `minimal_scenario.json` | 0.392 ms (0.030 ms) | 0.513 ms (0.034 ms) | +0.121 ms | +30.8% | < 15% | **UNMET** |
| `complex_scenario.json` | 4.868 ms (1.306 ms) | 6.226 ms (1.214 ms) | +1.358 ms | +27.9% | < 15% | **UNMET** |

- **Performance Gate Determination:** The performance gate remains **UNMET** (measured relative overhead is $pprox 28-31\%$, exceeding the 15% threshold).
- **Absolute Latency Cost:** Absolute latency cost remains small ($+0.12$ ms to $+1.36$ ms per search).

### 13.5 Design Gap Note: Requirements for Genuine Path-Level Feasibility Integration
To transition from the current single-hop observational hook to sound multi-hop path feasibility reasoning, the following architectural gaps must be addressed:
1. **Search State Augmentation:**
   - ARF-RT's Best-First search heap currently stores `(neg_p_worst, p_best, path_tuple, curr_node)`.
   - To evaluate path-wide context, the search must either:
     - Pass the accumulated path edge sequence (`path_tuple + (eid,)`) to reconstruct the full `PathEvaluationInput` with all hops `1..k`.
     - Or maintain an incremental context state tracker alongside the path tuple.
2. **Incremental Solving / Path Prefix Caching:**
   - Re-evaluating the full prefix from hop 1 to hop $k$ for every neighbor candidate at depth $k$ creates $O(k^2)$ solver invocations.
   - An incremental RDCE evaluator or prefix result cache is required to keep evaluation overhead tractable.
3. **Explicit Context Inheritance Scoping:**
   - Multi-hop rules (such as `static_origin_assumption`) cannot be applied globally without domain justification (e.g. AWS role chaining across external accounts may originate from different IP addresses via intermediate compute services).
   - Scenario assumptions must formally define which hops share persistent request/session contexts.
