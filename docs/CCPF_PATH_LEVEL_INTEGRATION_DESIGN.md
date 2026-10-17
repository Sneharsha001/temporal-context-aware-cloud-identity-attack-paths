# CCPF Path-Level Integration Architecture Design & Independent Review Reconciliation

## Prompt 8 / 8A - Architecture Design Gate: Multi-Hop Prefix Feasibility for ARF-RT Best-First Search

**Document Version:** 1.4.0 (Prompt 9B Conformance, Reference Parity & Performance Gate Audit)
**Phase:** Prompt 9B -- CCPF Annotation Conformance, Reference Parity & Performance Gate Audit
**Branch:** `temporal-context-dev`
**Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Baseline Commit:** `c1a28f2` → Prompt 9 commit: see RESEARCH_STATUS.md
**Date:** 2026-10-17
**Status:** **AUDITED DESIGN SPECIFICATION -- Production source changes and active pruning strictly prohibited**

---

### Evidence & Confidence Legend
- **[VERIFIED]**: Directly confirmed from repository source code, schema, or test execution output.
- **[INFERRED]**: Formally derived or logically necessary consequence of verified baseline behavior.
- **[PROVEN]**: Supported by complete formal mathematical logic and codebase invariants.
- **[TESTED]**: Supported by a passing, named test suite fixture within its stated operational scope.
- **[OPEN]**: Unresolved design question, unverified empirical hypothesis, or incomplete proof obligation.
- **[BLOCKED]**: Strict technical impediment preventing implementation until prerequisite resolution.

---

## Document Revision & Correction Log (Prompt 8A Audit)

| Section | Nature of Correction / Reconciled Item | Impact on Architecture |
|---|---|---|
| **Preamble** | Promoted version to 1.1.0; documented starting commit `1d636f7`. | Formal alignment with Prompt 8A audit gate. |
| **Section 4.1 / 4.2** | **Disambiguated Prefix Tracking vs. Incremental Solving:** Clarified that RDCE has NO incremental solver API; Option B in its current form is a **Full-Prefix Reference Evaluator** (resubmitting accumulated prefix hops), NOT a true incremental solver. | Prevents unsupported claims of incremental efficiency. |
| **Section 4.2.3 / 5** | **Reconciled Heap Ordering Safety (PO-1):** Proved that the 11-element heap tuple is fragile (contains `frozenset` at positions 4, 8, 9 which raise `TypeError` if compared, and `PathContextSnapshot` lacks ordering). Formally mandated decoupling priority `(-pw, len, seq_str)` from state payload via `(priority_key, payload)`. | Resolves heap comparison blocker and guarantees tie-break safety. |
| **Section 4.2.2 / 6** | **Formal Limits on Absorbing UNSAT (PO-3):** Scoped absorbing-UNSAT strictly to monotonic conjunctive constraints. Proved that `UNKNOWN`, timeouts, and exceptions are **non-absorbing**. Explicitly bounded scoped resets and hop-local parameters. | Prevents false UNSAT propagation and diagnostic corruption. |
| **Section 5.1 / 7** | **Transition Rules Audit (TR-1 through TR-5):** Reconciled proposed vs. established RDCE behavior. Distinguished explicit fixture assumptions (`static_origin_assumption: True`) from dynamic multi-origin reality. Verified hop-locality of CONFIG (`sts:ExternalId`). | Eliminates semantic drift between formal model and code. |
| **Section 6 / 9** | **Reconciled Performance Plan & Complexity:** Reclassified speculative overhead claims (e.g., "5x cost") as unverified hypotheses. Clarified that the intermediate 20% milestone is an interim checkpoint, while `< 15%` remains the binding gate. Defined 4-tier benchmark matrix. | Aligns performance claims with authoritative governance targets. |
| **Section 7 / 8** | **Proof Obligations & Test Specifications Reconciled:** Reconciled PO-1 through PO-5 and T-B-01 through T-B-10 into strict evidence states (`PROVEN`, `TESTED`, `OPEN`, `BLOCKED`). Clarified that T-B-01 through T-B-10 are specifications, not yet implemented. | Resolves conflicting terminology and unsubstantiated verification claims. |
| **Section 10** | **Smallest Justified Next Implementation Step:** Compared Option A (post-search annotation), Option B (offline reference harness), and Option C (true incremental solver). Recommended a provably-safe two-step milestone (Test Reference Harness + Post-Search Annotation Layer). | Provides a defensible, non-disruptive implementation path. |
| **Prompt 8B / Harness** | **Offline Full-Prefix Reference Harness Built:** Implemented `tests/research/test_reference_harness.py` validating 15 test cases against RDCE. Formally verified multi-hop CIDR contradiction, non-inheritance without assumptions, hop-local ExternalId, AssumeRole boundaries, malformed context, and differential oracle. | Establishes authoritative offline correctness reference without touching production search. |

---

## 1. Primary Research Question

> **How can CCPF maintain sound path-prefix feasibility state across multi-hop attack paths
> without changing baseline Q8 scores, path ranking, or Top-K behavior, and without
> incurring unacceptable computational overhead?**

This document establishes the verified architectural foundation to answer this question by:
1. Reconciling the actual capabilities of the existing Restricted Deterministic Constraint Evaluator (RDCE) against search requirements.
2. Formally evaluating the distinction between full-prefix re-evaluation and true incremental constraint evaluation.
3. Establishing mathematically rigorous heap ordering and absorbing-UNSAT invariants.
4. Defining a provably safe, phased implementation roadmap adhering strictly to zero active pruning.

---

## 2. Background: Verified Findings from Prompts 7A / 7B / 7C

### 2.1 Current Architecture (Mode A -- Passive, Single-Hop)

**[VERIFIED]** `evaluate_candidate_hop()` in `arf_rt/ccpf_bridge.py` operates solely on the candidate edge:
```python
# arf_rt/ccpf_bridge.py (Mode A)
hop_spec = HopContextSpec(
    hop=1,
    edge_type=edge_type,
    src_node_id=src,
    dst_node_id=dst,
    required_context=required_context,
)
eval_input = PathEvaluationInput(
    path_id=eid,
    hops=[hop_spec],           # ALWAYS len == 1: candidate edge only
    scenario_assumptions=scenario_assumptions or {},
)
result = evaluator.evaluate(eval_input)
```

**[VERIFIED]** In `arf_rt/engine/paths.py` (lines 194-207), the passive audit hook passes only `eid` and single-edge metadata:
```python
if ccpf_guard and ccpf_evaluate_fn is not None:
    ccpf_evaluate_fn(
        eid=eid,
        edge_data=edge_data.get(eid, {}),
        constraint_index=ccpf_constraint_index,
        evaluator=ccpf_evaluator,
        audit_sink=ccpf_audit_sink,
    )
```
The accumulated `edge_list` is available in scope but is **never passed** to the bridge.

### 2.2 The Multi-Hop Limitation (Verified Counterexample -- Test 18)

**[VERIFIED from Test 18 in `tests/integration/test_ccpf_bridge.py`]**
Two consecutive edges with disjoint CIDR constraints:
- Hop 1 (`edge-ip-10`): requires `aws:SourceIp` in `10.0.0.0/24`
- Hop 2 (`edge-ip-192`): requires `aws:SourceIp` in `192.168.1.0/24`

Under `static_origin_assumption: True`, the joint conjunction is empty ($10.0.0.0/24 \cap 192.168.1.0/24 = \emptyset$). In a multi-hop evaluation, RDCE returns `UNSAT`. However, because Mode A evaluates each edge in isolation with `hops=[hop_spec]`, both edges independently evaluate to `SAT`. The multi-hop conflict is completely undetected during path search.

### 2.3 Performance Gate Status (UNMET)

**[VERIFIED]** Paired benchmark runs across 30 repetitions (commit `450d76b` / `86b2947`):
- `minimal_scenario`: **+30.8%** overhead (baseline 0.392 ms vs Mode A 0.513 ms)
- `complex_scenario`: **+27.9%** overhead (baseline 4.868 ms vs Mode A 6.226 ms)
- Authoritative Threshold: **< 15.0%** total pipeline overhead.
- Gate Status: **UNMET**. Absolute overhead is $+0.12$ ms to $+1.36$ ms.

---

## 3. Formal Problem Statement

### 3.1 Current Search Heap State

**[VERIFIED]** In `arf_rt/engine/paths.py`, the frontier priority queue is managed via `heapq`. The heap tuple currently consists of 10 elements:
```python
(
    -p_worst_q8,     # index 0: int, primary priority (min-heap simulates max-heap)
    path_length,     # index 1: int, secondary priority (shorter paths first)
    edge_seq_str,    # index 2: str, tie-breaker (canonical JSON of edge_list)
    cur_node,        # index 3: str, destination node of last hop
    visited,         # index 4: frozenset[str], cycle-prevention set
    edge_list,       # index 5: list[str], accumulated edge IDs from root
    pw_q8,           # index 6: int, positive p_worst_q8
    pb_q8,           # index 7: int, positive p_best_q8
    worst_sigs,      # index 8: frozenset[str], group signatures applied
    best_sigs,       # index 9: frozenset[str], group signatures applied
)
```

### 3.2 Non-Negotiable Correctness Invariants

| ID | Formal Invariant Statement | Enforcement Mechanism |
|---|---|---|
| **INV-1** | Baseline Q8 probability scores (`p_best_q8`, `p_worst_q8`) MUST NOT be altered by CCPF. | Mathematical identity: Q8 updates remain exclusively governed by `grouped_product_q8`. |
| **INV-2** | Frontier priority and tie-breaking order MUST NOT be altered by CCPF. | Structural heap separation or proved lexicographic non-participation. |
| **INV-3** | Returned Top-K path sequences MUST be bitwise identical to baseline under passive mode. | Assertional parity in baseline equivalence regression fixtures. |
| **INV-4** | Bridge and evaluator errors (exceptions, index misses, timeouts) MUST produce `UNKNOWN` feasibility and NEVER cause search termination or edge pruning. | Strict try/except boundaries with fallback `UNKNOWN` diagnostics. |
| **INV-5** | `CCPF_FEASIBILITY_GUARD=False` MUST invoke zero RDCE evaluations and add zero path-search logic. | Short-circuit guard checks prior to constraint loading and tracking. |
| **INV-6** | `UNSAT` verdicts MUST be recorded exclusively to the diagnostic audit sink. No candidate edge may be withheld from heap insertion. | Passive audit execution with zero conditional pruning branches. |

---

## 4. Architectural Analysis: Tracking Paradigms & Feasibility

### 4.1 Comparison of Core Evaluation Paradigms

Source code inspection of `research/ccpf/rdce.py` and `arf_rt/engine/paths.py` establishes a fundamental architectural distinction:

| Attribute | Full-Prefix Reference Evaluator (Current RDCE) | True Incremental Evaluator (Proposed / Target) |
|---|---|---|
| **Input Structure** | Reconstructs full `PathEvaluationInput` with all $k$ prefix hops | Receives single delta hop context specification |
| **Solver State** | Re-allocates fresh scope dictionaries on every call; re-evaluates hops $1..k$ from scratch | Retains solver state frame; appends delta constraints to existing state |
| **Time Complexity** | $O(k)$ per candidate extension; $O(L^2)$ along path of length $L$ | $O(1)$ delta evaluation per candidate extension; $O(L)$ along path |
| **Memory Footprint** | Allocates new `HopContextSpec` and `PathEvaluationInput` objects per candidate | Carries lightweight solver token or immutable constraint state reference |
| **Current RDCE Support** | **YES [VERIFIED].** Fully supported today by `RestrictedDeterministicConstraintEvaluator.evaluate()` | **NO [VERIFIED].** RDCE has no `push()`, `pop()`, or incremental state methods |

#### Detailed Answers to Prompt 8A Source Inquiries:

1. **Can RDCE extend an existing solver state by one hop?**
   **NO [VERIFIED].** `RestrictedDeterministicConstraintEvaluator.evaluate()` accepts a `PathEvaluationInput` and allocates fresh scope dictionaries (`hop_allowed_cidrs`, `hop_principal_strings`, etc.) at the start of every call. It provides no `push()`, `pop()`, or incremental state extension methods.

2. **Does the proposed `advance_tracker()` avoid re-evaluating existing prefix constraints?**
   **NO [VERIFIED].** In the Option B design, `advance_tracker()` accumulates `ContextPredicate` objects into a tuple and reconstructs a `PathEvaluationInput` containing all hops $1..k$. It resubmits the entire prefix to RDCE. It avoids re-evaluation **only** if the prefix status is already `UNSAT` (via short-circuit). For all `SAT` and `UNKNOWN` prefixes, it re-evaluates all prefix hops.

3. **What is the actual time and memory complexity per candidate extension?**
   **[INFERRED]**
   - **Time Complexity:** $O(k)$ per candidate edge, where $k$ is the current path depth. For a path of length $L$, cumulative evaluation time along the branch is $\sum_{i=1}^L O(i) = O(L^2)$.
   - **Memory Complexity:** $O(k)$ object allocations per candidate edge (`HopContextSpec`, tuple slicing, `PathEvaluationInput`), retaining $O(M \cdot \bar{k})$ memory in the frontier queue across $M$ active states.

4. **Which operations are implemented vs. requiring a new interface?**
   - **Implemented [VERIFIED]:** Full multi-hop batch evaluation in RDCE (`evaluate()`), static origin CIDR intersection, transition constraints (`TransitionRelation`), and produced state mutation.
   - **New Interface Required [VERIFIED]:** RDCE state-token / incremental solver interface (`push_hop()`, `pop_hop()`), bridge multi-hop accumulator, and search-engine tracker plumbing.

5. **Can the tracker remain sound under resets, rebinds, and hop-local variables?**
   **YES, but ONLY IF hop identity and sequential ordering are preserved [PROVEN].** Flat conjunctions of predicates (collapsing all hops into a single set) are mathematically unsound: a reset at hop 2 would not clear a constraint from hop 1, and hop-local `sts:ExternalId` parameters would incorrectly clash across hops. Sound tracking requires either full-prefix sequence retention or an explicit multi-scope environment frame.

---

### 4.2 Reconciled Option Analysis

#### Option A: Full-Prefix Batch Re-evaluation
- **Mechanism:** Reconstruct `PathEvaluationInput(hops=[h_1, ..., h_k])` for each neighbor candidate.
- **Feasibility:** Fully supported by existing RDCE code today.
- **Overhead Assessment:** **[OPEN - HYPOTHESIS]** Incurs $O(k)$ overhead per expansion. At average depth 5, overhead is hypothesized to scale significantly above current Mode A levels (+28-31%), failing the 15% performance gate.

#### Option B: Prefix-State Tracker with Full-Prefix Fallback (Refactored Option B)
- **Mechanism:** Carry a `PathContextSnapshot` along with search state. If `snapshot.prefix_status == "UNSAT"`, short-circuit immediately without calling RDCE. If `SAT` or `UNKNOWN`, reconstruct and evaluate the extended prefix.
- **Clarification:** This is a **Prefix-State Accumulator**, not an incremental solver.
- **Feasibility:** High architectural soundness; requires resolving heap tuple safety.

#### Option C: True Incremental Constraint Evaluator
- **Mechanism:** RDCE maintains an immutable solver state frame; candidate extension evaluates only the delta constraint against the inherited frame.
- **Feasibility:** **BLOCKED [VERIFIED].** Current RDCE has no incremental interface or constraint frame architecture. Requires substantial engine rewrites.

#### Option D: Post-Search Top-K Path-Level Feasibility Annotation (Transitional)
- **Mechanism:** Leave the inner search loop in Mode A (or pure baseline). Once `search_top_k()` returns the top $K$ paths, execute a single multi-hop RDCE evaluation on each of the $K$ completed paths.
- **Feasibility:** **100% Implemented & Safe [PROVEN].** Evaluates at most $K$ complete paths ($K \le 10$). Adds $< 1\%$ overhead. Eliminates all search-loop complexity while immediately providing full path-wide feasibility diagnostics on returned attack paths.

---

## 5. Heap Ordering Safety & State Immutability (PO-1 Reconciliation)

### 5.1 Vulnerability of the 11-Element Heap Tuple

**[VERIFIED from `arf_rt/engine/paths.py`]**
The proposed Option B design appended `PathContextSnapshot` at position 10 of the heap tuple:
```python
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list, pw_q8, pb_q8, worst_sigs, best_sigs, ccpf_snapshot)
```

Audit of tuple comparison mechanics in Python:
1. Python compares tuples lexicographically element-by-element: `t1 < t2` evaluates position 0, then position 1 on tie, then position 2, and so forth.
2. In the expansion loop, `edge_seq_str = canonical_json(new_edges)`. Because `new_edges` uniquely identifies the edge sequence for paths of length $>0$, position 2 is unique among expanded paths.
3. **CRITICAL DEFECT IDENTIFIED [VERIFIED]:** At the search root (length 0), **all start nodes share identical values for positions 0, 1, and 2**:
   `-p_worst_q8 == -Q8`, `path_length == 0`, `edge_seq_str == ""`
   Tie-breaking falls through position 2 to position 3 (`cur_node`). Because start nodes have distinct node IDs, position 3 breaks the tie.
4. **HAZARD IDENTIFIED [VERIFIED]:** Preceding positions in the tuple contain types for which Python defines **NO comparison operators**:
   - Position 4 (`visited`): `frozenset[str]`
   - Position 8 (`worst_sigs`): `frozenset[str]`
   - Position 9 (`best_sigs`): `frozenset[str]`
   In Python, attempting to compare two frozensets (`frozenset({'a'}) < frozenset({'b'})`) raises:
   `TypeError: '<' not supported between instances of 'frozenset' and 'frozenset'`!
5. Furthermore, `PathContextSnapshot` is a `@dataclass(frozen=True)` without `order=True`. If comparison ever reached position 10, Python would raise `TypeError: '<' not supported between instances of 'PathContextSnapshot'`.

### 5.2 Mandatory Structural Solution: Priority-Payload Decoupling

To formally prove PO-1 and guarantee that `PathContextSnapshot` can **NEVER** participate in heap comparison or crash search, the heap representation must separate comparison priority from state payload:

```python
# Recommended Structural Heap Representation
@dataclass(frozen=True, order=True)
class PathSearchPriority:
    """Immutable, strictly-ordered heap comparison key.

    Fields exactly match spec §15.2 frontier priority:
      1. -p_worst_q8 (highest probability first)
      2. path_length (shortest path length first)
      3. edge_seq_str (lexicographic edge_id_sequence COLLATE BINARY)
    """
    neg_p_worst_q8: int
    path_length: int
    edge_seq_str: str

@dataclass
class PathSearchPayload:
    """Search state payload carried by heap entry.

    Excluded entirely from priority queue comparisons.
    """
    cur_node: str
    visited: frozenset[str]
    edge_list: list[str]
    pw_q8: int
    pb_q8: int
    worst_sigs: frozenset[str]
    best_sigs: frozenset[str]
    ccpf_snapshot: Optional[Any] = None

# Heap entry is a 2-tuple: (PathSearchPriority, PathSearchPayload)
```

**Formal Proof of Ordering Invariant:**
Because `edge_seq_str` is unique for every path prefix of length $>0$, and start nodes have distinct `sn` identifiers (which can be incorporated into `edge_seq_str` or priority key at length 0), comparison strictly terminates at or before index 2 of `PathSearchPriority`. Comparison never accesses the payload or `ccpf_snapshot`.

---

## 6. Formal Limits on Absorbing-UNSAT (PO-3 Reconciliation)

### 6.1 Mathematical Formulation of the Invariant

Let a path prefix of length $k$ be denoted $\pi_k = (e_1, e_2, \dots, e_k)$ with associated constraints $C(\pi_k) = \bigwedge_{i=1}^k c(e_i)$ under scenario assumptions $A$ and transition relations $T$.

**Absorbing-UNSAT Statement:**
If $C(\pi_k) \land A \land T \models \bot$ (the prefix is unsatisfiable), then for any candidate edge extension $e_{k+1}$, the extended prefix $\pi_{k+1} = \pi_k \circ e_{k+1}$ satisfies:
$$C(\pi_{k+1}) \land A \land T \models \bot$$

### 6.2 Formal Scope and Boundary Conditions

The absorbing-UNSAT invariant holds strictly under the following proven conditions:

1. **Monotonic Conjunction Property [PROVEN]:**
   In classical first-order logic, conjunction is monotonic: $P \models \bot \implies (P \land Q) \models \bot$. Since path execution requires sequential feasibility of every hop, an infeasible prefix cannot become physically executable by appending further hops.

2. **Non-Absorbing Statuses [MANDATORY INVARIANT]:**
   - `FeasibilityStatus.UNKNOWN` is **NOT ABSORBING**. An unknown verdict indicates insufficient metadata or unhandled operators. It MUST NOT be short-circuited as `UNSAT`.
   - Evaluator timeouts and solver exceptions are **NOT ABSORBING**. They must be recorded as `UNKNOWN` and must not prevent subsequent hop evaluations.

3. **Protection Against False Contradictions across Variable Scopes [PROVEN]:**
   - **Hop-Local Parameters (CONFIG):** $e_1$ requiring `sts:ExternalId = "alpha"` and $e_2$ requiring `sts:ExternalId = "beta"` do NOT contradict, because `sts:ExternalId` is request-scoped to the specific call. Collapsing them into a single variable would generate false UNSAT.
   - **Identity Transitions (PRINCIPAL / SESSION):** When traversing an `sts:AssumeRole` boundary, caller principal tags and session tokens are reset. Earlier constraints bound to the caller identity do not constrain the assumed role identity.
   - **Witness Invalidation:** A satisfying assignment (SAT witness) $w_k \models C(\pi_k)$ is NOT necessarily a witness for $C(\pi_{k+1})$. SAT is NOT absorbing.

---

## 7. Audit of Transition Relations (TR-1 through TR-5)

| Rule ID | Context Scope | Current Implementation State | Authoritative Transition Semantics | Evidence State |
|---|---|---|---|---|
| **TR-1** | `REQUEST` (`aws:SourceIp`) | Implemented in `rdce.py` (lines 861-930) | **Conditional on Fixture Assumption:** If `static_origin_assumption: True`, source IP is inherited monotonically across hops ($IP_{hop1} = IP_{hop2}$). If assumption is `False`, origin is mutable per request and CIDRs are NOT intersected across hops. | **TESTED** (in RDCE suite) |
| **TR-2** | `SESSION` (`aws:MultiFactorAuthPresent`) | Implemented in `rdce.py` (lines 748-765) | Persists across normal action hops within an STS session. Upon traversing an `sts:AssumeRole` boundary, session state resets to fresh session (MFA presence cleared unless re-asserted). | **TESTED** (in RDCE suite) |
| **TR-3** | `CONFIG` (`sts:ExternalId`) | Implemented in `rdce.py` (lines 720-745) | **Strictly Hop-Local:** Parameter supplied in the specific API request. Never carried over to subsequent hops. Independent per hop. | **PROVEN & TESTED** |
| **TR-4** | `PRINCIPAL` (`aws:PrincipalTag/<k>`) | Implemented in `rdce.py` (lines 748-770) | Carried across action hops for the same identity. Upon `sts:AssumeRole`, caller principal tags reset; target role attached tags produced on the transition become the new principal tags. | **TESTED** (in RDCE suite) |
| **TR-5** | `UNKNOWN` Scope | Implemented in `rdce.py` (lines 780-795) | Non-inheritable. Evaluator immediately yields `FeasibilityStatus.UNKNOWN`. Never treated as SAT or UNSAT. | **PROVEN & TESTED** |

---

## 8. Proof Obligations & Test Specifications Reconciliation

### 8.1 Proof Obligations Status Matrix

| ID | Proof Obligation Statement | Target Milestone | Reconciled Status | Formal Evidence / Justification |
|---|---|---|---|---|
| **PO-1** | Prove `PathContextSnapshot` cannot alter Python tuple comparison or heap ordering. | Mode B Design | **BLOCKED on 11-tuple; PROVEN under Decoupled Representation** | 11-tuple contains `frozenset` at index 4, 8, 9 which crash on tie. Separation into `(PathSearchPriority, PathSearchPayload)` completely isolates payload from comparison. |
| **PO-2** | Prove `advance_tracker()` is a pure function without in-place mutations. | Mode B Implementation | **OPEN** | Specification defined in design; requires unit verification upon implementation. |
| **PO-3** | Prove Absorbing-UNSAT invariant soundness across multi-hop extensions. | Mode B Implementation | **PROVEN (Bounded)** | Monotonicity proven for conjunctive constraints under static origin; explicitly bounded: UNKNOWN/exceptions non-absorbing. |
| **PO-4** | Prove TR-1 through TR-5 transition invariants against RDCE semantics. | Mode B Implementation | **TESTED (Batch RDCE & Reference Harness) / OPEN (Tracker)** | Verified in RDCE research tests (`test_rdce.py`) and offline reference harness (`test_reference_harness.py`); tracker bridge integration not yet implemented. |
| **PO-5** | Prove observational equivalence between passive Mode B and disabled baseline (`ccpf_guard=False`). | Mode B Integration | **OPEN** | Requires passing baseline equivalence test `test_mode_b_baseline_equivalence`. |

### 8.2 Test Specifications Status Matrix (T-B-01 through T-B-10)

> **Clarification:** All T-B tests listed below are **design specifications** formulated in Prompt 8. None have been implemented or executed yet in the repository.

| Test ID | Target Component | Formal Verification Role | Current Status |
|---|---|---|---|
| **T-B-01** | `PathContextSnapshot.empty()` | Verifies initial root snapshot is SAT with hop_count=0. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-02** | `advance_tracker()` purity | Verifies unconstrained edge preserves SAT without in-place mutation. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-03** | Short-circuit evaluation | Verifies UNSAT prefix returns UNSAT snapshot with zero evaluator calls. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-04** | Disjoint IP multi-hop | Verifies Test 18 scenario produces UNSAT across 2 hops. | **TESTED (Offline Harness)** |
| **T-B-05** | Baseline equivalence | Verifies identical Top-K paths and Q8 scores vs `ccpf_guard=False`. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-06** | Exception isolation | Verifies evaluator crash produces UNKNOWN snapshot and does not abort search. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-07** | Disabled mode parity | Verifies `ccpf_guard=False` carries None snapshot with zero tracking overhead. | **OPEN (SPECIFICATION ONLY)** |
| **T-B-08** | Config scope isolation | Verifies `sts:ExternalId` constraints on consecutive hops do not clash. | **TESTED (Offline Harness)** |
| **T-B-09** | Request CIDR clash | Verifies CIDR contradiction detection under `static_origin_assumption: True`. | **TESTED (Offline Harness)** |
| **T-B-10** | Session MFA boundary | Verifies MFA persistence and reset across `sts:AssumeRole` transitions. | **TESTED (Offline Harness)** |

---

## 9. Performance Plan & Governance Gates

### 9.1 Binding Performance Threshold
- **Authoritative Gate:** Total pipeline search overhead **< 15.0%** increase relative to baseline (`ccpf_guard=False`).
- **Current Baseline Status:** Mode A overhead is currently **+27.9% to +30.8%** (UNMET).
- **Intermediate 20% Target Clarification:** The intermediate 20% milestone referenced in Prompt 8 is strictly an **internal engineering checkpoint** during prototype development; it is **NOT** an authorized final acceptance threshold. Full production integration remains strictly gated at `< 15.0%`.

### 9.2 Required 4-Tier Benchmark Suite

To prevent ungrounded complexity claims, all future performance claims must be measured against four standardized benchmarks:

```
Benchmark 1: Baseline Engine (ccpf_guard=False)
Benchmark 2: Mode A Passive Audit (Single-hop, current implementation)
Benchmark 3: Mode B-Ref (Full-prefix reference evaluator on every candidate extension)
Benchmark 4: Mode B-Inc (True incremental constraint tracker prototype, when available)
```

---

## 10. Smallest Justified Next Implementation Step

### 10.1 Evaluation of Candidate Next Steps

1. **Candidate 1: True Incremental Context Tracker (Full Search Integration)**
   - *Feasibility:* **BLOCKED.** RDCE has no incremental solver API; heap ordering requires restructuring; high risk of performance regressions.
2. **Candidate 2: Reference-Only Full-Prefix Evaluator (Test Harness Only)**
   - *Feasibility:* **HIGH.** Implementable as an offline test harness using existing `RestrictedDeterministicConstraintEvaluator.evaluate(PathEvaluationInput)`. Establishes differential testing ground truth without modifying `search_top_k()`.
3. **Candidate 3: Post-Search Top-K Feasibility Annotation Layer**
   - *Feasibility:* **HIGH & PROVABLY SAFE.** Evaluates only the returned Top-K completed paths ($K \le 10$) using RDCE after search finishes. Adds $< 1\%$ overhead; introduces zero changes to heap tuples; immediately provides full path-wide feasibility diagnostics.

### 10.2 Defensible Recommendation: Two-Step Gated Progression

```
+-----------------------------------------------------------------------------------------------+
| Recommended Next Implementation Milestone                                                     |
+-----------------------------------------------------------------------------------------------+
| Step 1 (Offline Verification):                                                                |
| Build an offline Full-Prefix Reference Test Harness to validate multi-hop feasibility against |
| counterexamples (CE1-CE6, Test 18) using the existing batch RDCE.                             |
|                                                                                               |
| Step 2 (Non-Intrusive Runtime Annotation):                                                    |
| Implement a Post-Search Top-K Feasibility Annotation Layer in search_and_store_top_k().         |
| Annotates derived_topk paths with multi-hop feasibility status at negligible overhead (< 1%).|
| Inner search loop, heap tuples, and Q8 rankings remain 100% untouched.                        |
+-----------------------------------------------------------------------------------------------+
```

---

## 11. Document Provenance & Verification

| Source Reference | Role in Audit & Verification |
|---|---|
| `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md` | Authoritative CSP definitions, scopes, continuity, and counterexamples CE1-CE6. |
| `docs/CCPF_EVALUATOR_CONTRACT.md` v1.1.0 | Tri-state output contract, isolation invariants, and failure signatures. |
| `arf_rt/engine/paths.py` (lines 144-246) | Source verification of heap tuple construction, frozenset presence, and tie-breakers. |
| `arf_rt/ccpf_bridge.py` | Source verification of `evaluate_candidate_hop()` single-hop parameter construction. |
| `research/ccpf/rdce.py` (lines 700-1000) | Source verification of batch evaluation loop, transition relations, and absence of incremental API. |
| `tests/integration/test_ccpf_bridge.py` | Anchor tests: Test 18 (multi-hop limitation), Test 19 (disabled-mode baseline). |

---

*Document audited and updated under Prompt 8A.*
*Zero production source code modified. Zero active pruning enabled.*
*All implementation work remains blocked pending researcher authorization.*


---

## Section 11 — Prompt 9 / 9B: Post-Search Top-K Feasibility Annotation & Audit

> **Status:** AUDITED & CONFORMANCE TESTED — `temporal-context-dev` branch.
> Post-search diagnostic layer integrated. Zero active pruning. Zero search interference.
> **Performance Gate Status:** **UNMET** (< 15.0% gate exceeded under controlled paired benchmark).

### 11.1 Implementation & Accessibility Contract

`annotate_paths_feasibility(paths, conn, ..., annotation_sink)` in `arf_rt/ccpf_bridge.py`:

**Ordering invariant:** Executed strictly after `search_top_k()` returns and `derived_topk`
rows are fully committed. Verified by `test_post_search_boundary_search_finishes_before_annotation`.

**Inputs consumed (read-only):**
- `paths`: List of path dicts with `edge_id_sequence` (JSON-encoded list of edge IDs).
- `conn`: SQLite connection for bulk edge metadata and constraint queries.
- `constraint_index`: Optional pre-built `ConstraintIndex` (built from `conn` if not supplied).
- `evaluator`: Optional `RestrictedDeterministicConstraintEvaluator` instance.
- `scenario_assumptions`: Explicit caller-supplied dict. Never silently defaulted.

**Outputs produced (non-mutating):**
- Returns `list[dict]`, one record per input path, in matching rank order.
- Each record: `{rank, edge_id_sequence, status, witness, contradiction_rationale,
  unknown_rationale, evaluated_hops, solver_duration_ms, timeout_occurred, diagnostic_metadata}`.
- Appends to `annotation_sink` if provided and appendable.
- **Does NOT mutate input path dicts, probability scores, rankings, or SQLite tables.**

**Caller Access Pattern & Sink Contract in `search_and_store_top_k()` (`arf_rt/engine/paths.py`):**
```python
def search_and_store_top_k(
    conn: sqlite3.Connection,
    ...,
    ccpf_post_search_annotation: bool = False,
    ccpf_annotation_sink: list[dict[str, Any]] | None = None,
    scenario_assumptions: dict[str, Any] | None = None,
) -> dict[str, list[dict]]:
    ...
    # 1. Normal search and derived_topk storage (strictly unchanged)
    ...
    conn.commit()

    # 2. Post-search annotation layer (Prompt 9 / 9B)
    if ccpf_post_search_annotation:
        if ccpf_annotation_sink is None or not hasattr(ccpf_annotation_sink, "append"):
            logger.warning(
                "ccpf_post_search_annotation is enabled but ccpf_annotation_sink is None or "
                "not appendable; skipping annotation to avoid computing discarded records. "
                "To receive annotation records, provide an appendable sink (e.g. list) to ccpf_annotation_sink."
            )
        else:
            try:
                from arf_rt.ccpf_bridge import annotate_paths_feasibility

                all_paths = [p for paths in all_results.values() for p in paths]
                annotate_paths_feasibility(
                    paths=all_paths,
                    conn=conn,
                    scenario_assumptions=scenario_assumptions,
                    annotation_sink=ccpf_annotation_sink,
                )
            except Exception as ex:
                logger.warning("CCPF post-search annotation layer encountered error: %s", ex)

    return all_results
```

**Sink Audit Verdicts (Prompt 9B):**
1. **Disabled (`ccpf_post_search_annotation=False`):** Zero RDCE evaluations, zero imports, sink is untouched.
2. **Enabled with valid sink:** Exactly one annotation record per returned path emitted to sink in matching order.
3. **Enabled without sink / non-appendable sink:** Explicitly skips computation and logs a warning. Zero records silently computed or discarded. Legacy search return shape strictly preserved.
4. **Faulty sink (sink raises on append):** Trapped and logged; search results and SQLite database rows remain uncorrupted.

### 11.2 Differential Reference-Evaluator Parity (Prompt 9B Audit)

Prompt 8B / 9 parity was rigorously audited via differential integration testing:
- **Disjoint CIDRs with `static_origin_assumption=True`:**
  Both integrated annotation and direct RDCE evaluate to `UNSAT` with identical contradiction rationale (`"disjoint"`).
- **Disjoint CIDRs with absent static origin (`scenario_assumptions={}` or `False`):**
  Both integrated annotation and direct RDCE evaluate to `SAT` with identical witness (reflecting per-hop origin independence).
  *Clarification:* The mention of "UNKNOWN without static origin" in the Prompt 9 conversational summary table was an errant report typo. Both the implementation and tests have consistently yielded `SAT`, confirming 100% exact parity with the reference RDCE.
- **Unsupported scope:** Both evaluate to `UNKNOWN`.
- **Zero silent assumptions:** No default assumptions are applied.

### 11.3 Controlled Paired Benchmark & Performance Gate Audit

**Methodology:**
- 50 paired trials, 5 warmup pairs, interleaved execution order (alternating disabled-first and enabled-first to eliminate thermal/GC bias).
- Database fixture construction occurred completely outside timed blocks.
- Measured complete calls: `search_and_store_top_k(conn, ccpf_guard=False, ccpf_post_search_annotation=False)` vs `search_and_store_top_k(conn, ccpf_guard=False, ccpf_post_search_annotation=True, ccpf_annotation_sink=sink)`.
- Standalone RDCE annotation measured separately and reported without substitution.

| Metric | Minimal Fixture (1 path, 2 edges) | Complex Fixture (15 paths, 33 edges) |
|---|---|---|
| Annotation Disabled Median | 0.543 ms (IQR 0.088 ms) | 4.175 ms (IQR 1.799 ms) |
| Annotation Enabled Median | 0.797 ms (IQR 0.128 ms) | 5.353 ms (IQR 1.548 ms) |
| Absolute Delta Median | +0.288 ms (IQR 0.172 ms) | +1.182 ms (IQR 1.487 ms) |
| **Per-Pair % Overhead (Median)** | **+57.85%** | **+27.25%** |
| Relative Median Overhead | +46.77% | +28.24% |
| Standalone RDCE Time | 0.0555 ms (0.0555 ms/path) | 0.5796 ms (0.0386 ms/path) |
| **Authoritative Gate (< 15.0%)** | **UNMET** (exceeded) | **UNMET** (exceeded) |

**Root Cause of Gate Exceedance:**
- Standalone RDCE solver evaluation is extremely fast (38 to 55 microseconds per path).
- However, the integrated post-search pipeline must query the SQLite `constraints` and `edge_constraints` tables, deserialize `properties_json`, query `edges` metadata, and build path context structures.
- Because ARF-RT's baseline search is exceptionally fast (~0.5 ms for minimal, ~4.2 ms for complex), the fixed ~0.29 ms to ~1.18 ms database querying and bridging overhead translates to +27% to +58% relative pipeline overhead.
- Under the strict Prompt 9B audit rule ("Do not use noise-floor pass as a substitute for an explicit decision rule"), the performance gate is formally recorded as **UNMET**.

### 11.4 Test Coverage Summary (16/16 Integration Tests Passing)

| Test Name | Category | Status |
|---|---|---|
| `test_post_search_boundary_search_finishes_before_annotation` | Boundary Isolation | PASS |
| `test_post_search_boundary_verdicts_do_not_affect_search` | Search Invariant | PASS |
| `test_baseline_equivalence_full_field_parity[minimal]` | Parity Invariant | PASS |
| `test_baseline_equivalence_full_field_parity[complex]` | Parity Invariant | PASS |
| `test_multihop_path_evaluation_disjoint_cidrs_with_and_without_static_origin` | Multi-hop Feasibility | PASS |
| `test_scope_transition_hop_local_external_id` | Scope Transition | PASS |
| `test_scope_transition_unsupported_scope_yields_unknown` | Scope Transition | PASS |
| `test_top_k_coverage_and_order_association` | Coverage & Ordering | PASS |
| `test_empty_results_handling` | Robustness | PASS |
| `test_annotation_failure_isolation` | Failure Isolation | PASS |
| `test_disabled_mode_zero_evaluations_and_empty_sink` | Disabled Invariant | PASS |
| `test_annotation_accessibility_enabled_with_valid_sink` | Accessibility (Prompt 9B) | PASS |
| `test_annotation_accessibility_enabled_without_sink_skips_computation_and_logs_warning` | Accessibility (Prompt 9B) | PASS |
| `test_annotation_accessibility_non_appendable_sink_skips_computation` | Accessibility (Prompt 9B) | PASS |
| `test_annotation_accessibility_faulty_sink_isolated_search_intact` | Accessibility (Prompt 9B) | PASS |
| `test_differential_reference_evaluator_parity_full_path` | Reference Parity (Prompt 9B) | PASS |

### 11.5 Audit Conclusion & Stop Rule

1. **Accessibility:** Solved and verified. No records are computed and silently discarded; return shape is intact.
2. **Reference Parity:** Proved 100% exact parity with direct RDCE reference evaluator across all assumption modes.
3. **Performance Gate:** Formally **UNMET** (+27.25% complex, +57.85% minimal vs < 15.0% threshold).
4. **Action:** Per Prompt 9B Stop Rule, implementation halted for researcher review. No active pruning, reranking, or speculative optimization introduced.
