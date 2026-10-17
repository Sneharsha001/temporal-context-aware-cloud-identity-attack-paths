# CCPF Path-Level Integration Architecture Design

## Prompt 8 - Design Gate: Multi-Hop Prefix Feasibility for ARF-RT Best-First Search

**Document Version:** 1.0.0
**Phase:** Prompt 8 -- Architecture Design Gate (Design-Only; No Implementation)
**Branch:** `temporal-context-dev`
**Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Starting Commit:** `86b2947`
**Date:** 2026-10-17
**Status:** **DESIGN SPECIFICATION -- Implementation strictly blocked pending gate acceptance**

> **Evidence & Confidence Legend**
> - **[VERIFIED]**: Directly confirmed from repository source code, schema, or test output.
> - **[INFERRED]**: Formally derived or logically necessary consequence of verified baseline behavior.
> - **[OPEN]**: Unresolved design decision, hypothesis, or formal proof obligation.
> - **[BLOCKER]**: Unresolved correctness issue that strictly halts engine modification.

---

## 1. Primary Research Question

> **How can CCPF maintain sound path-prefix feasibility state across multi-hop attack paths
> without changing baseline Q8 scores, path ranking, or Top-K behavior, and without
> incurring unacceptable computational overhead?**

This document answers the question by:
1. Establishing the precise architectural gap between the current single-hop bridge (Mode A)
   and genuine path-wide feasibility reasoning (Mode B target).
2. Formally defining a `PathContextTracker` interface and its required invariants.
3. Evaluating three architectural options against safety, correctness, and complexity criteria.
4. Recommending a provably-safe integration pathway with a phased overhead reduction plan.
5. Defining formal proof obligations and testability criteria that must be satisfied before
   any implementation begins.

---

## 2. Background: Audit Findings from Prompts 7A / 7B / 7C

### 2.1 Current Architecture (Mode A -- Passive, Single-Hop)

**[VERIFIED]** `evaluate_candidate_hop()` in `arf_rt/ccpf_bridge.py` constructs a
`PathEvaluationInput` with exactly one `HopContextSpec`:

```python
# arf_rt/ccpf_bridge.py (current Mode A)
path_input = PathEvaluationInput(
    path_id=f"hop_audit:{eid}",
    hops=[hop_spec],           # len == 1: only the candidate edge, never the path prefix
    transition_constraints=[],
    scenario_assumptions=assumptions,
)
result = evaluator.evaluate(path_input)
```

**[VERIFIED]** In `arf_rt/engine/paths.py`, the passive audit hook receives only the
current candidate edge identifier -- not the path prefix accumulated so far:

```python
# arf_rt/engine/paths.py (current Mode A hook, lines ~194-207)
ccpf_evaluate_fn(
    eid=eid,
    edge_data=edge_data.get(eid, {}),
    constraint_index=ccpf_constraint_index,
    evaluator=ccpf_evaluator,
    audit_sink=ccpf_audit_sink,
)
# The accumulated edge_list (full path prefix) is present in scope but is NOT passed.
```

**[VERIFIED]** SAT, UNSAT, and UNKNOWN verdicts are completely discarded for all search
purposes. Zero edges are pruned. Heap priority and Q8 scores are not touched by the bridge.

### 2.2 The Multi-Hop Limitation (Counterexample -- Test 18)

**[VERIFIED from Test 18 in `tests/integration/test_ccpf_bridge.py`]**

Two consecutive hops with disjoint IP requirements:
- Hop 1 (`edge-ip-10`): requires `aws:SourceIp` in `10.0.0.0/24`
- Hop 2 (`edge-ip-192`): requires `aws:SourceIp` in `192.168.1.0/24`

Under `static_origin_assumption: True` (single attacker execution environment), the joint
constraint `10.0.0.0/24 intersect 192.168.1.0/24 = empty-set` is **UNSAT** in RDCE.

However, the current bridge evaluates each hop in isolation:
- Hop 1 evaluated alone: **SAT**
- Hop 2 evaluated alone: **SAT**

The joint infeasibility is **never detected**. The counterexample path is ranked normally,
indistinguishable from genuinely feasible paths.

### 2.3 Performance Gate (Currently UNMET)

**[VERIFIED]** Measured relative overhead from 30 paired trials:
- `minimal_scenario`: **+30.8%** (authorized target: `< 15%`)
- `complex_scenario`: **+27.9%** (authorized target: `< 15%`)

Absolute overhead is small (+0.12 ms to +1.36 ms). The gate is UNMET only on relative
overhead. The primary driver is one RDCE evaluation call per candidate edge, with no
path-prefix amortization.

---

## 3. Formal Problem Statement

### 3.1 Current Search Heap State

**[VERIFIED]** The heap tuple in `search_top_k()` (lines ~144-161 of `arf_rt/engine/paths.py`):

```
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs)
```

The `edge_list` carries the full path prefix from the start node to `cur_node`.
This is sufficient to reconstruct the complete `PathEvaluationInput` for any extension.
The field is **already present** in heap state; no new data collection is required.

### 3.2 Information Required for Path-Wide Feasibility

To evaluate multi-hop joint constraint satisfiability, the bridge needs:

1. **The path prefix** `edge_list = [e1, e2, ..., ek]` -- **[VERIFIED: already in heap]**
2. **Context predicates per prefix edge** -- available from `ConstraintIndex`
3. **Transition relations** -- encoding which context variables persist across hops
   (e.g., `aws:SourceIp` under `static_origin_assumption`)
4. **An incremental or prefix-aware solver** -- to avoid full O(k) prefix reconstruction
   per candidate neighbor expansion

### 3.3 Non-Negotiable Correctness Invariants

Any chosen architecture must maintain all six invariants:

| ID | Statement |
|---|---|
| **INV-1** | Baseline Q8 scores (`p_best_q8`, `p_worst_q8`) are not modified by CCPF. |
| **INV-2** | Heap ordering and tie-break mechanics are not modified by CCPF. |
| **INV-3** | Top-K path sets are identical between CCPF-enabled and baseline runs until active pruning is explicitly authorized as a separate gated phase. |
| **INV-4** | CCPF errors (evaluator exceptions, constraint index failures) never alter path selection. |
| **INV-5** | `CCPF_FEASIBILITY_GUARD=False` preserves zero RDCE overhead (only the SQL `edge_type` column cost of +11.5 us remains). |
| **INV-6** | UNSAT verdicts are recorded as diagnostics only. They never discard edges in Mode A or Mode B passive tracking. |

---

## 4. Architectural Option Analysis

Three candidate architectures are evaluated against the correctness invariants, accuracy,
and complexity requirements.

---

### 4.1 Option A -- Full Prefix Re-evaluation at Every Hop

**Description:** At each candidate edge `eid` at depth `k`, reconstruct the full
`PathEvaluationInput` using the complete path prefix `[e1, ..., ek-1, eid]`.
Invoke RDCE once per neighbor expansion on the full k-hop path.

**Complexity:**

| Metric | Analysis |
|---|---|
| Evaluator calls per edge expansion | 1 call, but with O(k) hop input |
| Context objects per call | O(k) HopContextSpec objects (full prefix rebuild each time) |
| Total evaluator invocations | O(E) calls (same count as Mode A), but each invocation is O(k) heavier |
| Overhead vs. Mode A (avg depth d) | Approximately d times Mode A overhead per call |

**[INFERRED]** For avg depth d=5, Option A overhead per search is approx 5x Mode A overhead.
Mode A already measures +28-31%. Option A would approach +140-155% overhead.

**Assessment:**

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS |
| Path-wide feasibility accuracy | PASS -- full joint evaluation |
| Performance | **FAIL** -- far exceeds the UNMET 15% gate |
| Incremental efficiency | **FAIL** -- O(k) object reconstruction per expansion |

**Verdict:** Architecturally correct but computationally infeasible as the first step.

---

### 4.2 Option B -- Incremental PathContextTracker (RECOMMENDED)

**Description:** Introduce a `PathContextSnapshot` that maintains the accumulated
constraint conjunction incrementally. At each hop, the snapshot is extended by exactly
one edge's constraints rather than re-evaluating from hop 1.

#### 4.2.1 PathContextSnapshot Interface

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PathContextSnapshot:
    """Immutable snapshot of accumulated path-prefix constraint state.

    Carried in the heap tuple at position index 10. All fields are immutable.
    advance_tracker() always returns a NEW snapshot without mutating self.

    Invariant: prefix_status reflects the joint satisfiability of all predicates
    accumulated across hops 1..hop_count under the active scenario assumptions
    and transition relations.
    """
    prefix_predicates: tuple          # Accumulated ContextPredicates (hops 1..k)
    prefix_status: str                # "SAT" | "UNSAT" | "UNKNOWN"
    contradiction_rationale: str | None = None
    hop_count: int = 0

    @classmethod
    def empty(cls) -> "PathContextSnapshot":
        """Initial snapshot for a path with zero hops. Always SAT."""
        return cls(prefix_predicates=(), prefix_status="SAT", hop_count=0)
```

#### 4.2.2 advance_tracker() Contract

```python
def advance_tracker(
    snapshot: PathContextSnapshot,
    eid: str,
    constraint_index: ConstraintIndex,
    transition_constraints: list,   # list[TransitionRelation]
    scenario_assumptions: dict,
    evaluator,                      # RestrictedDeterministicConstraintEvaluator
    audit_sink: list | None,
) -> PathContextSnapshot:
    """Extend the tracker by one candidate edge and return a NEW snapshot.

    Contract:
    [PURE] No side effects. snapshot is never mutated in-place.

    [ABSORBING UNSAT]
        If snapshot.prefix_status == "UNSAT", return UNSAT snapshot immediately
        without invoking the evaluator (short-circuit). UNSAT is an absorbing state:
        all extensions of an UNSAT prefix remain UNSAT.

    [ERROR ISOLATION]
        Any evaluator exception produces prefix_status == "UNKNOWN" in the returned
        snapshot. Exceptions NEVER produce an UNSAT verdict. The search engine is
        never affected.

    [ZERO PRUNING]
        The returned snapshot is used ONLY for diagnostics and audit sink recording.
        It NEVER gates edge expansion. Edges are never skipped based on snapshot status.

    [AUDIT SINK]
        If audit_sink is not None, append a diagnostic record with eid, hop_count,
        prefix_status, and contradiction_rationale.
    """
```

#### 4.2.3 Heap Tuple Extension

The heap tuple is extended by one field appended at position index 10:

```
# Current heap tuple -- Mode A (10 fields, positions 0-9):
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs)

# Extended heap tuple -- Mode B (11 fields, positions 0-10):
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs,
  ccpf_snapshot)    # PathContextSnapshot | None  (None when ccpf_guard=False)
```

**INV-1, INV-2 compliance argument:**

Python tuple comparison is lexicographic. Heap ordering is determined by position 0
(`-p_worst_q8`). Ties at position 0 fall to position 1 (`path_length`), then position 2
(`edge_seq_str`). The `edge_seq_str` field encodes the canonical JSON of the full
`edge_list` -- it is unique per distinct path prefix. Consequently positions 3-10 are
never compared during heap operations. **[INFERRED] The `ccpf_snapshot` field at position
10 cannot participate in heap ordering and does not affect path ranking.**

#### 4.2.4 Option B -- Complexity Analysis

| Metric | Analysis |
|---|---|
| Evaluator calls per edge expansion | **1** (same as Mode A) |
| Evaluator input size per call | O(k) hops (vs. O(1) in Mode A) |
| Snapshot memory per heap entry | O(k) accumulated ContextPredicates |
| Total evaluator invocations | Identical count to Mode A |
| Overhead vs Mode A | Scales with O(k) input size per RDCE call; depends on constraint density |

**[INFERRED]** For sparse-constraint paths (most edges have zero context predicates),
RDCE short-circuits. Effective overhead approaches Mode A. For dense-constraint paths,
overhead scales with average path depth. **[OPEN]** Requires empirical profiling.

#### 4.2.5 Option B -- Assessment

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS |
| Path-wide feasibility accuracy | PASS -- full joint evaluation across all prefix hops |
| Implementation complexity | MODERATE -- new PathContextSnapshot dataclass + heap field |
| Performance | OPEN -- same call count as Mode A; profiling required before enabling |
| Incremental efficiency | PASS -- O(1) evaluator calls per expansion (vs. O(k) in Option A) |
| Backward compatibility | PASS -- None snapshot when ccpf_guard=False; INV-5 preserved |

**Verdict: Option B is the Recommended Architecture.**

---

### 4.3 Option C -- Deferred Prefix Evaluation (Post-Search Annotation)

**Description:** Preserve Mode A single-hop evaluation unchanged during search.
After `search_top_k()` returns the Top-K path list, perform a second pass that evaluates
the full path prefix for each result path for diagnostic annotation.

#### 4.3.1 Option C -- Assessment

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS -- post-search; never affects ranking |
| Path-wide feasibility accuracy | PARTIAL -- annotates result paths only; UNSAT prefix paths may still outrank SAT paths during search and claim Top-K slots |
| Implementation simplicity | HIGH -- minimal change to search_top_k() |
| Search overhead | ZERO during path search |
| Research validity | **FAIL** -- does not prevent infeasible path promotion during ranking |

**Verdict:** Option C is appropriate as an **immediate transitional diagnostic layer**
(Phase 1) but does not solve the research problem. It must not be presented as a
multi-hop feasibility integration.

---

## 5. Recommended Architecture: Option B -- Detailed Design

### 5.1 Transition Relations Specification

The transition relation model defines which context variables persist across hops.
Correctness of multi-hop UNSAT detection depends directly on correct transition semantics.

| Variable | Transition Type | Scope | Semantics |
|---|---|---|---|
| `aws:SourceIp` | **EQUAL** | REQUEST | Inherited hop-to-hop when `static_origin_assumption: True`. Attacker network origin does not change between API calls unless explicitly reset by a ProducedStateModification. |
| `aws:MultiFactorAuthPresent` | **SESSION** | SESSION | Persists within STS token lifetime. Changes on role assumption if MFA is not re-asserted in the new session. |
| `aws:PrincipalTag/<key>` | **PRINCIPAL** | PRINCIPAL | Bound to the active IAM entity. Changes on role assumption (PIVOT_TRANSITION). |
| `sts:ExternalId` | **CONFIG** | CONFIG | Hop-local parameter only. Does not propagate to subsequent hops under any scenario assumption. |
| `active_principal` | **PIVOT_TRANSITION** | PRINCIPAL | Changes on sts:AssumeRole hop. New principal is the assumed role ARN. |

### 5.2 Scope Transition Invariants

| ID | Statement |
|---|---|
| **TR-1** | REQUEST scope variables are inherited to the next hop if and only if `static_origin_assumption: True`. |
| **TR-2** | SESSION scope variables are inherited until a ProducedStateModification with `operation: "RESET"` on the variable is encountered in the path. |
| **TR-3** | CONFIG scope variables are **never inherited**. Each hop evaluates its CONFIG predicates independently regardless of prior hops. |
| **TR-4** | PRINCIPAL scope variables are inherited until a `PIVOT_TRANSITION` ProducedStateModification resets `active_principal`. |
| **TR-5** | UNKNOWN scope variables are treated as non-inheritable. Each hop independently yields `FeasibilityStatus.UNKNOWN` for such predicates. |

**[OPEN]** These invariants must be implemented and tested before Option B can be
correctly coded. Incorrect transition semantics directly produce false UNSAT verdicts
(over-pruning -- a Mode A-equivalent correctness violation even in passive mode, because
the diagnostic record would be wrong).

### 5.3 Baseline Equivalence Test Specification

The baseline equivalence test is the critical correctness gate for Mode B:

```
Test ID: test_mode_b_baseline_equivalence
  Given: A fixed scenario fixture (e.g., complex_scenario.json)
  When:
    Run A: search_top_k() with ccpf_guard=False (pure baseline)
    Run B: search_top_k() with ccpf_guard=True and Mode B tracker enabled
  Then (asserting Run A == Run B on all ranking fields):
    1. Top-K path lists are IDENTICAL (same edge_id_sequence for every rank).
    2. p_best_q8 values are IDENTICAL for every path.
    3. p_worst_q8 values are IDENTICAL for every path.
    4. confidence_band values are IDENTICAL for every path.
    5. flags_json values are IDENTICAL for every path.
    6. Run B audit_sink contains prefix_status annotations absent from Run A.
```

**[BLOCKER]** Mode B implementation must not proceed until this test is formalized,
implemented, and passing.

---

## 6. Performance Analysis and Overhead Gate

### 6.1 Current Overhead Measurement (Mode A Baseline -- UNMET)

| Scenario | Baseline Median | Mode A Median | Absolute Delta | Relative Overhead | Gate |
|---|---|---|---|---|---|
| `minimal_scenario` | 0.392 ms | 0.513 ms | +0.121 ms | +30.8% | **UNMET** |
| `complex_scenario` | 4.868 ms | 6.226 ms | +1.358 ms | +27.9% | **UNMET** |

Authorized threshold: `< 15%` increase. Measurements: 30 paired trials, 5 warm-up iterations.

### 6.2 Overhead Reduction Strategies for Option B

| ID | Description | Expected Impact | Risk |
|---|---|---|---|
| **S1: Sparse-constraint short-circuit** | RDCE already skips evaluation for hops with zero constraints. If most edges carry no predicates, effective RDCE input size remains O(1) per call. | High if constraint density is low | **[OPEN]** Requires empirical measurement of fixture constraint density. |
| **S2: Predicate-only clash detection** | Replace full RDCE with a lightweight CIDR intersection check for REQUEST scope conflicts only. Avoids full RDCE for hops without conflicting predicates. | Moderate -- eliminates majority of RDCE calls | Lower risk -- no RDCE for non-conflicting hops. |
| **S3: Prefix result memoization** | Cache PathContextSnapshot results by canonical hash of the accumulated predicate conjunction. Identical path prefixes reuse cached snapshots. | High for common path prefixes | **[OPEN]** Cache key collision and invalidation semantics require formal proof. |

### 6.3 Recommended Phased Overhead Reduction Path

| Phase | Action | Overhead Target |
|---|---|---|
| **Phase 1 (Immediate)** | Option C post-search Top-K annotation for diagnostic reporting | Zero search overhead |
| **Phase 2** | Implement PathContextSnapshot + advance_tracker(); benchmark with sparse-constraint and dense-constraint fixtures | Empirical measurement |
| **Phase 3** | Apply S2 lightweight clash detection; re-benchmark and compare vs. full RDCE | Target: < 20% |
| **Phase 4** | If and only if measured overhead < 15% across all benchmark fixtures, advance tracker to full `search_top_k()` integration | < 15% gate (authorized) |

**[BLOCKER]** Overhead must be re-measured empirically after implementing PathContextSnapshot
before enabling multi-hop evaluation. The 15% gate is the authoritative threshold.

---

## 7. Formal Proof Obligations Before Implementation

All five obligations must be discharged before any Mode B implementation begins.

| ID | Statement | Priority |
|---|---|---|
| **PO-1** | Prove that `PathContextSnapshot` at heap tuple position 10 cannot affect Python tuple comparison ordering. Provide formal argument referencing lexicographic comparison semantics and uniqueness of `edge_seq_str`. | **[BLOCKER]** |
| **PO-2** | Prove that `advance_tracker()` is a pure function with no side effects. Specifically verify that `snapshot.prefix_predicates` is never mutated in-place and that all returned snapshots are newly allocated. | **[BLOCKER]** |
| **PO-3** | Prove that UNSAT propagation (absorbing state) is sound: if a path prefix is UNSAT, all extensions of that prefix under the same scenario assumptions and transition relations are also UNSAT. | **[REQUIRED]** |
| **PO-4** | Prove transition invariants TR-1 through TR-5 against RDCE `static_origin_assumption` semantics. Demonstrate with counterexample tests that incorrect transition semantics produce false UNSAT or false SAT verdicts. | **[REQUIRED]** |
| **PO-5** | Prove that enabling Option B with all verdicts discarded (INV-6) is observationally equivalent to disabling Option B entirely (`ccpf_guard=False`), modulo the audit sink entries. | **[REQUIRED]** |

---

## 8. Testability Criteria

### 8.1 Existing Tests (Mode A -- VERIFIED at commit 86b2947)

| Test IDs | Description |
|---|---|
| Tests 1-16 | Core bridge functionality: constraint indexing, condition mapping, storage pipelines, error isolation |
| Test 17 | Distinguishable diagnostic signatures for four edge states (unconstrained, valid, malformed, query failure) |
| Test 18 | Multi-hop counterexample proving Mode A joint-UNSAT detection gap |
| Test 19 | Disabled-mode verification (zero RDCE calls, +11.5 us SQL overhead when guard=False) |

**Full suite:** 785 tests passing (625 unit + 141 research + 19 integration), 100% pass rate.

### 8.2 New Tests Required for Option B (Design-Only -- Not Implemented)

| ID | Description | Validates |
|---|---|---|
| **T-B-01** | `PathContextSnapshot.empty()` yields SAT status with empty predicate tuple and hop_count=0 | advance_tracker() precondition |
| **T-B-02** | `advance_tracker()` with unconstrained edge extends predicate tuple but preserves SAT status | Pure function invariant; no false UNSAT |
| **T-B-03** | `advance_tracker()` with UNSAT prefix returns UNSAT snapshot immediately without evaluator call (absorbing state) | PO-3; evaluator call count |
| **T-B-04** | Multi-hop counterexample (Test 18 scenario): two disjoint IP hops now produce UNSAT snapshot in Mode B | Mode B accuracy; Test 18 gap resolved |
| **T-B-05** | `search_top_k()` with Mode B tracker enabled produces identical Top-K to `ccpf_guard=False` baseline | INV-1, INV-2, INV-3 |
| **T-B-06** | `advance_tracker()` exception isolation: evaluator failure yields UNKNOWN snapshot, never UNSAT, never skips expansion | INV-4 |
| **T-B-07** | `ccpf_guard=False` produces None at position 10 in all heap entries; no PathContextSnapshot objects allocated | INV-5 |
| **T-B-08** | CONFIG scope predicates (`sts:ExternalId`) NOT inherited across hops | TR-3 |
| **T-B-09** | REQUEST scope CIDR conflicts detected across consecutive hops under `static_origin_assumption: True` | TR-1 |
| **T-B-10** | SESSION scope `aws:MultiFactorAuthPresent` inherited across hops until a PIVOT_TRANSITION hop | TR-2, TR-4 |

---

## 9. Mode A to Mode B Scope Transition Gating

All five criteria must be met before implementation proceeds:

| Gate Criterion | Current Status | Required Condition |
|---|---|---|
| All Mode A tests passing (785 tests) | **VERIFIED at 86b2947** | No regression allowed |
| PO-1 through PO-5 formally discharged | **[OPEN]** | All five obligations satisfied |
| T-B-01 through T-B-10 implemented and passing | **[OPEN]** | All ten new tests green |
| Mode B benchmark overhead < 15% across all fixtures | **[OPEN]** | Empirical measurement required |
| Active pruning not introduced | **INVARIANT MAINTAINED** | Must continue -- active pruning is a separate future gated phase requiring explicit authorization |

**Active pruning remains strictly prohibited in Mode B.** The `PathContextSnapshot` UNSAT
verdict populates the audit sink for diagnostic analysis only. Edge expansion is never
conditional on snapshot status. Heap insertion is never withheld. This constraint is
identical to Mode A and must appear explicitly in all Mode B implementation code.

---

## 10. Glossary

| Term | Definition |
|---|---|
| `PathContextSnapshot` | Immutable dataclass carrying accumulated ContextPredicate conjunction and feasibility status for path prefix (hops 1..k) |
| `advance_tracker()` | Pure function that extends a PathContextSnapshot by one edge; invokes RDCE on the extended prefix |
| **Absorbing UNSAT** | Invariant: once a path prefix evaluates to UNSAT, all extensions remain UNSAT under the same assumptions and transition relations |
| **Mode A** | Current passive single-hop audit: zero path prefix tracking, zero pruning |
| **Mode B** | Target path-wide tracking: incremental prefix state, zero pruning, full joint-constraint evaluation |
| **Transition Relation** | Formal constraint specifying how a context variable is inherited, transformed, or reset across consecutive hops |
| **Sparse-constraint path** | A path where most edges carry no context predicates; Mode B overhead approaches Mode A in this case |
| **Dense-constraint path** | A path where many edges carry context predicates; Mode B overhead scales with average path depth |

---

## 11. Document Provenance

| Source Document | Role in This Design |
|---|---|
| `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md` | Defines PathConstraintStore, RequiredContext, ProducedContext, CarriedContext -- foundational CSP formulation |
| `docs/CCPF_EVALUATOR_CONTRACT.md` v1.1.0 | Defines RDCE interface, tri-state output contract, strict decoupling from Q8 probability scoring |
| `docs/CCPF_FORMAL_DESIGN_GATE.md` | Establishes the infeasibility blindspot in purely probabilistic attack-path ranking |
| `docs/CCPF_INTEGRATION_DESIGN.md` Section 13 | Gap analysis from Prompts 7A/7B/7C: single-hop limitation, overhead gate, design gap notes |
| `arf_rt/engine/paths.py` lines 144-246 | Verified current heap tuple structure, edge expansion loop, and Mode A hook placement |
| `arf_rt/ccpf_bridge.py` | Verified ConstraintIndex, evaluate_candidate_hop(), ConstraintPredicate extraction, Mode A implementation |
| `research/ccpf/rdce.py` | Verified PathEvaluationInput, HopContextSpec, TransitionRelation, FeasibilityStatus, static_origin_assumption |
| `tests/integration/test_ccpf_bridge.py` Tests 18, 19 | Anchors Mode B design requirements: gap evidence (Test 18) and disabled-mode baseline (Test 19) |

---

*Document produced in Prompt 8 -- Design Gate.*
*No source code has been modified. No PathContextTracker has been implemented.*
*Active pruning remains prohibited.*
*All items tagged [OPEN] or [BLOCKER] must be resolved before Mode B implementation begins.*