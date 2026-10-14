# CCPF Integration Design & Correctness Audit
## Prompt 6 / 6A -- Verified Integration Design & Soundness Specification

**Document:** `docs/CCPF_INTEGRATION_DESIGN.md`
**Branch:** `temporal-context-dev`
**Date:** 2026-10-14
**Audited Commit:** `6fb9ec0`
**Status:** DESIGN AUDIT & SOUNDNESS SPECIFICATION -- NOT READY FOR UNRESTRICTED PRODUCTION INTEGRATION

> **STOP RULE:** This document records an architectural design and correctness audit only.
> In strict compliance with research safety constraints, no production code under `arf_rt/` has
> been modified, no adapter implemented, and no scoring or search algorithms altered.
> Implementation is gated on explicit researcher authorization.

---

## 1. Purpose and Scope

This document provides a source-grounded correctness audit and revised integration design for connecting the isolated **Restricted Deterministic Constraint Evaluator (RDCE)** (`research/ccpf/rdce.py`) into the **ARF-RT Best-First search engine** (`arf_rt/engine/paths.py`).

Prompt 6A resolves contract inconsistencies, establishes policy-mapping soundness across IAM statement structures, corrects search-bound and Top-K claims, and defines the exact boundaries under which single-hop pruning is sound.

**Scope:**
1. Grounded inspection of real production source code, SQLite schemas, parsers, and RDCE contracts.
2. Reconciliation of the UNSAT contract, eliminating invented fields (`confidence_q` on result, `rationale` field naming) and removing unjustified numeric confidence thresholds.
3. Rigorous audit of IAM trust policy semantics: disjunctive statements, intra-statement conjunctions, multi-valued conditions, and missing statement identifiers (`Sid`).
4. Formal delineation of safe single-hop pruning vs multi-hop prefix feasibility.
5. Correction of Top-K search mechanics: distinguishing `max_depth` from search termination conditions (`len(results) < k`) and eliminating non-existent `max_expansions` references.
6. Staged validation plan with empirical go/no-go criteria.
7. Final readiness determination based on evidence.

---

## 2. Verified Baseline and Repository State

| Item | Verified Value | Ground-Truth Source |
|---|---|---|
| **Repository Path** | `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL` | Local workspace |
| **Active Branch** | `temporal-context-dev` | `git status --short --branch` |
| **Audited HEAD** | `6fb9ec0` | `git log -n 1 --oneline` |
| **Upstream Sync** | Synchronized with `origin/temporal-context-dev` | `git status` |
| **Working Tree** | Clean (untracked IDE `.agents/` preserved) | `git status` |
| **Protected Mirrors** | `main`, `master`, `ARF-RT-BASELINE` untouched | Repository safety rule |
| **Research Test Suite** | **141 passed / 141 total** (1.12s) | `tests/research/` |
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

1. **`confidence_q` Field Removed from Result:**
   - **Finding:** `confidence_q` does **not** exist in `PathEvaluationResult` or `rdce.py`. It exists solely in ARF-RT's SQLite `constraints` table as a Bayesian belief prior (e.g., 800 for auto-derived trust conditions).
   - **Correction:** The integration design must never look for or assert `confidence_q` on `PathEvaluationResult`.

2. **Removal of the `confidence_q >= 500` Rule:**
   - **Finding:** The Prompt 6 draft proposed: *"Constraint is VALIDATED with confidence_q >= 500 before trusting UNSAT."*
   - **Correction:** This rule is **removed**. A soft Bayesian probability score (500 = 0.50) cannot substitute for a formal proof of logical contradiction. RDCE is a deterministic, tri-state logical evaluator. If a constraint is formally proven UNSAT within the safe fragment, its mathematical infeasibility does not depend on a numerical prior. Conversely, if constraint provenance or policy structure is unverified, a high confidence score (800) does **not** prevent false UNSAT.

3. **Field Naming Correction:**
   - The generic field `rationale` referenced in Prompt 6 does not exist. The actual fields are `contradiction_rationale: Optional[str]` (populated on UNSAT) and `unknown_rationale: Optional[str]` (populated on UNKNOWN).

### 3.3 Strict Prerequisites for Trusting an UNSAT Result

An expansion may be pruned on `UNSAT` **only** when all of the following conditions are satisfied:
1. `result.status == FeasibilityStatus.UNSAT`
2. `result.timeout_occurred is False`
3. `result.contradiction_rationale is not None` and non-empty.
4. **All** evaluated predicates belong strictly to RDCE's supported operator fragment (`IpAddress`, `NotIpAddress`, `StringEquals`, `StringLike` without wildcards, `Bool`, `Null`).
5. **Semantic Conjunction Precondition:** The evaluated constraints are proven to form a pure logical **conjunction** (originating within a single policy statement), OR the complete disjunction of statements has been evaluated and proved unsatisfiable across all branches.
6. If any precondition fails, or if constraint grouping is ambiguous, the result **must** be conservatively demoted to `UNKNOWN` and **must not prune**.

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

3. **Explicit Deny Statements Ignored:**
   - Statements with `Effect == "Deny"` are skipped entirely by the parser. Any explicit Deny constraint (which should take precedence and render an attack path impossible) is absent from the graph.

4. **Multi-Valued Condition Keys:**
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

| Condition Key in DB | Scope | RDCE Operator | Value Representation | RDCE Supported? | Mapping Status / Limitations |
|---|---|---|---|---|---|
| `aws:sourceip` | `REQUEST` | `IpAddress`, `NotIpAddress` | CIDR string list | **YES** | Supported. Multi-CIDR is OR. |
| `aws:principaltag/<key>` | `PRINCIPAL` | `StringEquals`, `StringLike` (no wildcards) | String list | **YES** | Supported. Multi-value is OR. |
| `aws:multifactorauthpresent` | `SESSION` | `Bool` | `["true"]`, `["false"]`, `["0"]`, `["1"]` | **YES** | Supported. |
| `sts:externalid` | `CONFIG` | `StringEquals` | String list | **YES** | Supported hop-locally. |
| `aws:sourcevpc` | `REQUEST` | N/A | VPC ID list | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:sourcevpce` | `REQUEST` | N/A | VPCE ID list | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:principalorgid` | `PRINCIPAL` | N/A | Org ID string | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:principalorgpaths` | `PRINCIPAL` | N/A | Org path string | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `sts:rolesessionname` | `SESSION` | N/A | Session name | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:multifactorauthage` | `SESSION` | N/A | Numeric seconds | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:requesttag/<key>` | `REQUEST` | N/A | String list | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |
| `aws:tagkeys` | `REQUEST` | N/A | Tag key list | **NO** | Unsupported by RDCE. Must yield `UNKNOWN`. |

---

## 6. Scope of Safe Single-Hop Pruning

### 6.1 Sound Pruning Boundary

Given the architectural gap in `trust_policy_parser.py`, under what conditions is single-hop pruning mathematically sound?

**Soundness Theorem (Local Contradiction):**
Single-hop pruning of an edge expansion (u, v) is sound **if and only if**:
1. **Single-Statement Conjunction Guarantee:** The edge possesses either:
   - Exactly **one** active trust condition, OR
   - Multiple conditions proven to originate from the **same statement block** in the source policy.
2. **Supported Operator & Scope:** All conditions belong strictly to the supported fragment in Section 5.3.
3. **No Unmodeled Disjunction:** There are no alternative Allow statements for the role that lack conditions.
4. **Deterministic Clash:** RDCE returns `status = UNSAT` with `timeout_occurred == False` and a valid `contradiction_rationale` (e.g., self-contradictory CIDR restriction or contradiction with explicit scenario assumptions).

### 6.2 Pruning Policy When Metadata Is Incomplete

When an edge targets a role with:
- Multiple conditions whose statement grouping is unknown, OR
- Any unsupported condition key (`aws:SourceVpc`, `aws:PrincipalOrgID`, etc.), OR
- An unmodeled policy statement,
the adapter **MUST NOT PRUNE**. The verdict must be treated as **UNKNOWN (conservative passthrough)**.

---

## 7. Corrected Top-K Search Analysis

### 7.1 Search Mechanics & Invariants

ARF-RT's Top-K search is a Best-First search over path probabilities:
- **Priority Key:** `(-p_worst_q8, path_length, edge_id_seq_str)`
- **Candidate Eligibility:** Sound UNSAT pruning prevents logically impossible neighbor expansions from entering the heap.
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

### Stage 4: Top-K Replacement Verification
- In a scenario with M infeasible paths in baseline Top-K, verify that the guided search replaces exactly M infeasible paths with the next highest-scoring feasible candidates.

### Stage 5: Efficiency Benchmarking
- Measure per-hop RDCE evaluation latency.
- Measure total pipeline overhead on realistic graphs (target: < 15% increase).

---

## 9. Final Readiness Determination & Evidential Recommendation

### 9.1 Readiness Finding: NOT READY FOR UNRESTRICTED PRODUCTION INTEGRATION

The Prompt 6A correctness audit confirms:
1. **Blocking Architectural Gap:** `trust_policy_parser.py` flattens alternative IAM statements into a single unindexed constraint list, discarding `StatementId` and `Effect`. An unrestricted bridge evaluating all edge constraints as a conjunction would generate **false UNSAT** and discard valid attack paths.
2. **Missing Field Gaps:** `edge_type` is omitted from the search query in `paths.py` (Gap G1), and `ProducedStateModification` has no database representation (Gap G3).

### 9.2 Authorized Scopes for Prompt 7

Production integration is authorized **only under one of the following two safe operating modes**:

1. **Mode A (Passive / Audit Mode - Recommended):**
   - The bridge is implemented behind `ARF_CCPF_GUARD=1`.
   - RDCE evaluates candidate hops and logs verdicts (`SAT`, `UNSAT`, `UNKNOWN`) with diagnostic rationales.
   - **Zero pruning is performed.** Candidate expansion and heap operations proceed identically to baseline.
   - This validates bridge performance, data extraction, and logging without risking search truncation or false UNSAT.

2. **Mode B (Gated Single-Condition Active Pruning):**
   - Pruning is activated **strictly and exclusively** on edges that have **exactly one** attached trust condition from the supported safe fragment.
   - Edges with multiple conditions, missing statement IDs, or unsupported keys pass through as `UNKNOWN` without pruning.

Full unrestricted multi-condition pruning is deferred until `trust_policy_parser.py` and the SQLite schema are upgraded to preserve `StatementId` and disjunctive statement structure.

---

## Related Documents
- `docs/CCPF_EVALUATOR_CONTRACT.md` -- Formal RDCE interface contract
- `docs/CCPF_FORMAL_DESIGN_GATE.md` -- Open proof obligations
- `docs/CCPF_RE_REVIEW.md` -- Independent re-review report
- `arf_rt/adapters/trust_policy_parser.py` -- IAM trust condition extraction
- `arf_rt/engine/paths.py` -- Best-First Top-K path search engine
