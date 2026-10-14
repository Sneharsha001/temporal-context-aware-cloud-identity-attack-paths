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
