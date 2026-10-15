# CCPF Path-Level Integration Architecture Design

## Prompt 8 - Design Gate: Multi-Hop Prefix Feasibility for ARF-RT Best-First Search

**Document Version:** 1.0.0
**Phase:** Prompt 8 -- Architecture Design Gate (Design-Only; No Implementation)
**Branch:** `temporal-context-dev`
**Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Starting Commit:** `86b2947`
**Date:** 2026-10-15
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
4. Recommending a provably-safe integration pathway.
5. Defining open proof obligations and testability criteria that must be satisfied before
   implementation begins.

---

## 2. Background: Audit Findings from Prompts 7A / 7B / 7C

### 2.1 Current Architecture (Mode A -- Passive, Single-Hop)

**[VERIFIED]** `evaluate_candidate_hop()` in `arf_rt/ccpf_bridge.py` constructs a
`PathEvaluationInput` with exactly one `HopContextSpec`:

`python
# arf_rt/ccpf_bridge.py (current Mode A)
path_input = PathEvaluationInput(
    path_id=f"hop_audit:{eid}",
    hops=[hop_spec],           # len == 1: only the candidate edge, never the path prefix
    transition_constraints=[],
    scenario_assumptions=assumptions,
)
result = evaluator.evaluate(path_input)
`

**[VERIFIED]** In `arf_rt/engine/paths.py`, the passive audit hook is called with only the
current candidate edge identifier -- not the path prefix accumulated so far:

`python
# arf_rt/engine/paths.py (current Mode A hook)
ccpf_evaluate_fn(
    eid=eid,
    edge_data=edge_data.get(eid, {}),
    constraint_index=ccpf_constraint_index,
    evaluator=ccpf_evaluator,
    audit_sink=ccpf_audit_sink,
)
# The accumulated edge_list (path prefix) is present in scope but is NOT passed.
`

**[VERIFIED]** SAT, UNSAT, and UNKNOWN verdicts are completely discarded for all search
purposes. Zero edges are pruned. Heap priority and Q8 scores are not touched by the bridge.

### 2.2 The Multi-Hop Limitation (Counterexample -- Test 18)

**[VERIFIED from Test 18 in `tests/integration/test_ccpf_bridge.py`]**

Two consecutive hops with disjoint IP requirements:
- Hop 1 (`edge-ip-10`): requires `aws:SourceIp` in `10.0.0.0/24`
- Hop 2 (`edge-ip-192`): requires `aws:SourceIp` in `192.168.1.0/24`

Under `static_origin_assumption: True` (single attacker execution environment), the joint
constraint `10.0.0.0/24 intersect 192.168.1.0/24 = empty` is **UNSAT** in RDCE.

However, the current bridge evaluates each hop in isolation:
- Hop 1 evaluated alone: **SAT**
- Hop 2 evaluated alone: **SAT**

The joint infeasibility is **never detected**. The counterexample path is ranked normally,
indistinguishable from genuinely feasible paths.

### 2.3 Performance Gate (Currently UNMET)

**[VERIFIED]** Measured relative overhead from 30 paired trials:
- `minimal_scenario`: **+30.8%** (authorized target: `< 15%`)
- `complex_scenario`: **+27.9%** (authorized target: `< 15%`)

**Absolute overhead is small** (+0.12 ms to +1.36 ms). The gate is UNMET only on relative
overhead. The primary driver is the RDCE evaluation call per candidate edge, without any
path-prefix amortization.

---

## 3. Formal Problem Statement

### 3.1 Current Search State

**[VERIFIED]** The heap tuple in `search_top_k()` is:

`
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs)
`

The `edge_list` carries the full path prefix from the start node to `cur_node`.
This is sufficient to reconstruct the complete `PathEvaluationInput` for any extension.

### 3.2 Required Extension for Path-Wide Feasibility

To evaluate multi-hop joint constraint satisfiability, the bridge needs access to:

1. **The path prefix** `edge_list = [e1, e2, ..., ek]` -- **[VERIFIED: already in heap state]**
2. **Context predicates for each prefix edge** -- available from `ConstraintIndex`
3. **Transition relations** -- encoding which context variables persist across hops
4. **An incremental or prefix-aware solver** -- to avoid re-evaluating the full prefix from scratch

### 3.3 Correctness Invariants (Non-Negotiable)

| Invariant ID | Statement |
|---|---|
| **INV-1** | Baseline Q8 scores (`p_best_q8`, `p_worst_q8`) are not modified by CCPF. |
| **INV-2** | Heap ordering and tie-break mechanics are not modified by CCPF. |
| **INV-3** | Top-K path sets are identical between CCPF-enabled and baseline runs (until active pruning is authorized). |
| **INV-4** | CCPF errors (evaluator exceptions, constraint index failures) never alter path selection. |
| **INV-5** | `CCPF_FEASIBILITY_GUARD=False` preserves zero RDCE overhead (only the SQL `edge_type` column cost remains). |
| **INV-6** | UNSAT verdicts are recorded as diagnostics only and never used to discard edges during Mode A or Mode B passive tracking. |

---

## 4. Architectural Option Analysis

### Option A -- Full Prefix Re-evaluation at Every Hop

**Description:** At each candidate edge `eid` at depth `k`, reconstruct the full
`PathEvaluationInput` using the complete path prefix `[e1, ..., ek-1, eid]` (k hops).
Invoke RDCE on the full path for every neighbor expansion.

#### 4.1 Option A -- Complexity Analysis

| Metric | Analysis |
|---|---|
| Evaluator calls per path of depth d | O(d x branching_factor) total calls |
| Context objects per neighbor | O(k) HopContextSpec objects (full prefix rebuild) |
| Memory per evaluation | O(k) hop specs + transition relations |
| Overhead vs. Mode A | Significantly larger -- Mode A: O(1) per edge; Option A: O(k) per neighbor |

**[INFERRED]** For depth-10 search with branching factor 5: up to 250 RDCE invocations
per path (Mode A: 50). Option A is approx 5x more RDCE work, with Mode A already at +28-31%.

#### 4.2 Option A -- Assessment

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS |
| Path-wide feasibility accuracy | PASS |
| Implementation simplicity | PASS |
| Performance | **FAIL** -- significantly exceeds UNMET 15% gate |
| Incremental efficiency | **FAIL** -- full prefix rebuild per expansion |

**Verdict:** Architecturally correct but computationally infeasible as first integration step.

---

### Option B -- Incremental Path-Context Tracker (RECOMMENDED)

**Description:** Introduce a `PathContextTracker` maintaining the accumulated constraint
conjunction incrementally. At each hop, the tracker is extended by one edge rather than
re-evaluating from hop 1.

#### 5.1 Option B -- PathContextSnapshot Interface Specification

`python
from dataclasses import dataclass

@dataclass(frozen=True)
class PathContextSnapshot:
    """Immutable snapshot of accumulated path-prefix constraint state.

    Carried in the heap tuple at position index 10.
    All fields are immutable -- advance_tracker() returns a NEW snapshot.
    """
    prefix_predicates: tuple          # Accumulated ContextPredicates (hops 1..k)
    prefix_status: str                # "SAT" | "UNSAT" | "UNKNOWN"
    contradiction_rationale: str | None = None
    hop_count: int = 0

    @classmethod
    def empty(cls) -> "PathContextSnapshot":
        """Initial snapshot for a path with zero hops."""
        return cls(prefix_predicates=(), prefix_status="SAT", hop_count=0)
`

`advance_tracker()` Contract:

`python
def advance_tracker(
    snapshot: PathContextSnapshot,
    eid: str,
    constraint_index: ConstraintIndex,
    transition_constraints: list,
    scenario_assumptions: dict,
    evaluator,
) -> PathContextSnapshot:
    """Extend the tracker by one candidate edge and return a NEW snapshot.

    Invariants:
    - Pure function: snapshot is never mutated.
    - Absorbing UNSAT: if snapshot.prefix_status == "UNSAT", returns UNSAT
      immediately (short-circuit). UNSAT is an absorbing state.
    - Error isolation: evaluator exceptions produce prefix_status == "UNKNOWN",
      never "UNSAT". Exceptions never cause edge expansion to be skipped.
    - Zero pruning: returned snapshot is used ONLY for diagnostics.
      It NEVER gates edge expansion in the search engine.
    """
`

#### 5.2 Option B -- Heap Tuple Extension

`
# Current heap tuple (Mode A, 10 fields):
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs)

# Extended heap tuple (Mode B, 11 fields):
(-p_worst_q8, path_length, edge_seq_str, cur_node, visited, edge_list,
  p_worst_q8, p_best_q8, worst_sigs, best_sigs,
  ccpf_snapshot)   # PathContextSnapshot | None  (None when ccpf_guard is False)
`

**INV-1, INV-2 compliance:** Python tuple comparison is lexicographic. Position 0
(`-p_worst_q8`) determines heap order. Ties are broken by position 2 (`edge_seq_str`),
which is a canonical unique string per distinct path prefix. Positions 3+ (including
position 10 `ccpf_snapshot`) are never compared. The snapshot field does not participate
in heap ordering. **[INFERRED]**

#### 5.3 Option B -- Complexity Analysis

| Metric | Analysis |
|---|---|
| Evaluator calls per edge expansion | **1** (identical to Mode A) |
| Context objects constructed | O(k) predicates per snapshot, accumulated incrementally |
| Snapshot memory per heap entry | O(k) accumulated predicates |
| Total evaluator invocations | Same count as Mode A: one per candidate edge |
| RDCE input size per call | O(k) hops (vs. O(1) in Mode A) |

**[INFERRED]** Option B makes the same number of RDCE calls as Mode A, but each call
processes O(k) hops. For dense-constraint paths, overhead scales with average depth.
For sparse-constraint paths (most edges have no context predicates), RDCE short-circuits
and effective overhead approaches Mode A.

**[OPEN]** Actual overhead depends on constraint density. Requires empirical profiling.

#### 5.4 Option B -- Assessment

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS |
| Path-wide feasibility accuracy | PASS -- joint constraint evaluation across all prefix hops |
| Implementation complexity | MODERATE -- new PathContextSnapshot + heap extension |
| Performance | OPEN -- same call count as Mode A; profiling required |
| Incremental efficiency | PASS -- O(1) evaluator calls per expansion |
| Backward compatibility | PASS -- None snapshot when ccpf_guard=False; zero overhead path unchanged |

**Verdict: Option B is the Recommended Architecture.**

---

### Option C -- Deferred Prefix Evaluation (Post-Search Annotation)

**Description:** Preserve Mode A single-hop evaluation during search. After
`search_top_k()` returns Top-K paths, perform a second pass evaluating the full path
prefix for each result path for annotation.

#### 6.1 Option C -- Assessment

| Criterion | Result |
|---|---|
| Correctness (INV-1 through INV-6) | PASS -- post-search; never affects ranking |
| Path-wide feasibility accuracy | PARTIAL -- annotates only Top-K results; UNSAT prefix paths may still outrank SAT paths during search |
| Implementation simplicity | HIGH -- minimal changes to search_top_k() |
| Performance during search | PASS -- zero additional overhead during search |
| Research Validity | **FAIL** -- does not prevent UNSAT paths from occupying Top-K slots |

**Verdict:** Option C is appropriate as an immediate diagnostic transitional tool (Phase 1)
but does not solve the research problem of preventing infeasible path promotion during ranking.

---

## 5. Recommended Architecture: Option B Details

### 5.1 Transition Relations Specification

| Variable | Transition Semantics | Scope |
|---|---|---|
| `aws:SourceIp` | **EQUAL** under `static_origin_assumption: True` -- attacker network origin does not change unless reset by ProducedStateModification. | REQUEST |
| `aws:MultiFactorAuthPresent` | **SESSION** -- persists within STS token lifetime. Changes on role assumption if not re-asserted. | SESSION |
| `aws:PrincipalTag/<key>` | **PRINCIPAL** -- bound to active IAM entity. Changes on role assumption (pivot). | PRINCIPAL |
| `sts:ExternalId` | **CONFIG** -- hop-local parameter. Does not propagate across hops. | CONFIG |
| `active_principal` | **PIVOT_TRANSITION** -- changes on sts:AssumeRole. New principal is the role ARN. | PRINCIPAL |

### 5.2 Scope Transition Invariants

| ID | Statement |
|---|---|
| **TR-1** | REQUEST scope variables are inherited by the next hop if and only if `static_origin_assumption: True`. |
| **TR-2** | SESSION scope variables are inherited until a ProducedStateModification with `operation: "RESET"` is encountered. |
| **TR-3** | CONFIG scope variables are **never inherited**. Each hop evaluates its CONFIG predicates independently. |
| **TR-4** | PRINCIPAL scope variables are inherited until a PIVOT_TRANSITION ProducedStateModification resets `active_principal`. |
| **TR-5** | UNKNOWN scope variables are treated as non-inheritable. Each hop independently yields FeasibilityStatus.UNKNOWN. |

**[OPEN]** Transition relation logic must be implemented and tested for each ContextScope
type before Option B can be correctly implemented. Incorrect transition semantics cause
false UNSAT verdicts (over-pruning -- a correctness violation).

### 5.3 Baseline Equivalence Test Specification

**[OPEN -- Must be specified and implemented before Mode B implementation begins]**

`
Test: test_mode_b_baseline_equivalence
  Given: A fixed scenario fixture (e.g., complex_scenario.json)
  When:  search_top_k() run with ccpf_guard=False (baseline)
         AND search_top_k() run with ccpf_guard=True, Mode B tracker enabled
  Then:
    1. Top-K path lists are IDENTICAL (same edge sequences, same ranks).
    2. p_best_q8 and p_worst_q8 are IDENTICAL for every path.
    3. confidence_band values are IDENTICAL for every path.
    4. flags_json values are IDENTICAL for every path.
    5. audit_sink contains Mode B prefix_status annotations absent from baseline.
`

**[BLOCKER]** Implementation must not proceed until this test is formalized and passing.

---

## 6. Performance Analysis and Overhead Gate

### 6.1 Current Overhead (Mode A -- UNMET)

| Scenario | Baseline | Mode A | Relative Overhead | Gate |
|---|---|---|---|---|
| `minimal_scenario` | 0.392 ms | 0.513 ms | +30.8% | **UNMET** |
| `complex_scenario` | 4.868 ms | 6.226 ms | +27.9% | **UNMET** |

Authorized threshold: `< 15%` increase.

### 6.2 Overhead Reduction Strategies

| ID | Description | Risk |
|---|---|---|
| **S1: Sparse-constraint short-circuit** | RDCE skips evaluation for hops with zero constraints. Constraint density determines actual overhead. | **[OPEN]** Requires empirical measurement. |
| **S2: Predicate-only clash detection** | Lightweight CIDR intersection check for REQUEST scope only. Avoids full RDCE for non-conflicting hops. | Lower risk. |
| **S3: Prefix result memoization** | Cache PathContextSnapshot by canonical hash of accumulated predicate conjunction. | **[OPEN]** Cache invalidation requires formal proof. |

### 6.3 Recommended Phased Overhead Reduction

| Phase | Action | Expected Overhead |
|---|---|---|
| **Phase 1 (Immediate)** | Option C post-search annotation only | Zero search overhead |
| **Phase 2** | Option B PathContextSnapshot prototype; benchmark sparse-constraint fixtures | [OPEN -- measure] |
| **Phase 3** | Apply S2 lightweight clash detection; compare vs. full RDCE | Target: < 20% |
| **Phase 4** | If and only if measured overhead < 15%, advance to full tracker integration | < 15% gate |

**[BLOCKER]** Overhead gate must be re-measured empirically after implementing
PathContextSnapshot before enabling multi-hop evaluation in any environment.

---

## 7. Proof Obligations Before Implementation

| ID | Statement | Priority |
|---|---|---|
| **PO-1** | Prove PathContextSnapshot at heap tuple position 10 cannot affect Python tuple comparison ordering. Provide formal argument referencing lexicographic comparison semantics and uniqueness of `edge_seq_str`. | **[BLOCKER]** |
| **PO-2** | Prove `advance_tracker()` is a pure function with no side effects. Verify `snapshot.prefix_predicates` is never mutated in-place. | **[BLOCKER]** |
| **PO-3** | Prove UNSAT propagation (absorbing state) is sound: if path prefix is UNSAT, all extensions remain UNSAT under the same scenario assumptions and transition relations. | **[REQUIRED]** |
| **PO-4** | Prove transition invariants TR-1 through TR-5 against RDCE `static_origin_assumption` semantics. Demonstrate with counterexample tests that incorrect semantics produce false UNSAT or false SAT. | **[REQUIRED]** |
| **PO-5** | Prove that enabling Option B with all verdicts discarded (INV-6) is observationally equivalent to disabling Option B entirely, modulo audit sink entries. | **[REQUIRED]** |

---

## 8. Testability Criteria

### 8.1 Existing Tests (Mode A -- VERIFIED at commit 86b2947)

| Tests | Description |
|---|---|
| Tests 1-16 | Core bridge, constraint indexing, condition mapping, storage pipelines |
| Test 17 | Distinguishable diagnostic signatures for four edge states |
| Test 18 | Multi-hop counterexample proving joint-UNSAT detection gap in Mode A |
| Test 19 | Disabled-mode behavior (zero calls, +11.5 us SQL overhead) |

**Full suite:** 785 tests passing (625 unit, 141 research, 19 integration).

### 8.2 New Tests Required for Option B (Design-Only -- Not Yet Implemented)

| Test ID | Description | Validates |
|---|---|---|
| **T-B-01** | `PathContextSnapshot.empty()` yields SAT status with empty predicate tuple | advance_tracker() contract |
| **T-B-02** | `advance_tracker()` with unconstrained edge extends predicate tuple but preserves SAT | Pure function invariant |
| **T-B-03** | `advance_tracker()` with UNSAT prefix returns UNSAT immediately (absorbing state) | PO-3 |
| **T-B-04** | Multi-hop counterexample: two disjoint IP hops now produce UNSAT snapshot (Mode B corrects Test 18 gap) | Mode B accuracy |
| **T-B-05** | `search_top_k()` with Mode B tracker produces identical Top-K to baseline | INV-1, INV-2, INV-3 |
| **T-B-06** | `advance_tracker()` exception isolation: evaluator failure yields UNKNOWN, never UNSAT | INV-4 |
| **T-B-07** | `ccpf_guard=False` produces None snapshots in all heap entries | INV-5 |
| **T-B-08** | CONFIG scope predicates are NOT inherited across hops | TR-3 |
| **T-B-09** | REQUEST scope CIDR conflicts detected across hops under `static_origin_assumption: True` | TR-1 |
| **T-B-10** | SESSION scope `aws:MultiFactorAuthPresent` inherited until PIVOT_TRANSITION hop | TR-2, TR-4 |

---

## 9. Scope Transition: Mode A to Mode B Gating Criteria

| Gate Criterion | Current Status | Required for Transition |
|---|---|---|
| All Mode A tests passing (785 tests) | **VERIFIED (86b2947)** | No regression |
| PO-1 through PO-5 formally discharged | **[OPEN]** | All five obligations satisfied |
| T-B-01 through T-B-10 implemented and passing | **[OPEN]** | All ten tests green |
| Mode B benchmark overhead < 15% across all fixtures | **[OPEN]** | Empirical measurement required |
| Active pruning not introduced | **INVARIANT MAINTAINED** | Must continue -- active pruning is a separate future gated phase |

**Active pruning remains strictly prohibited in Phase B.** The PathContextSnapshot UNSAT
verdict is logged to the audit sink and carries diagnostic information. Edge expansion is
never skipped. Heap insertion is never withheld. This constraint is identical to Mode A
and must be explicitly preserved in all Mode B implementation code.

---

## 10. Glossary of Design Terms

| Term | Definition |
|---|---|
| `PathContextSnapshot` | Immutable dataclass carrying accumulated context predicate conjunction and feasibility status for path prefix (hops 1..k) |
| `advance_tracker()` | Pure function that extends a PathContextSnapshot by one edge; invokes RDCE on the extended prefix |
| **Absorbing UNSAT** | Invariant: once a path prefix evaluates to UNSAT, all extensions remain UNSAT under the same assumptions |
| **Mode A** | Current passive single-hop audit: zero path prefix tracking, zero pruning |
| **Mode B** | Target path-wide tracking: incremental prefix state, zero pruning, full joint-constraint evaluation |
| **Transition Relation** | Formal constraint specifying how a context variable is inherited, transformed, or reset across consecutive hops |
| **Sparse-constraint path** | A path where most edges carry no context predicates; Mode B overhead approaches Mode A in this case |

---

## 11. Document Provenance

| Source Document | Role in This Design |
|---|---|
| `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md` | Defines PathConstraintStore, RequiredContext, ProducedContext, CarriedContext |
| `docs/CCPF_EVALUATOR_CONTRACT.md` v1.1.0 | Defines RDCE interface, tri-state output, decoupling from Q8 scoring |
| `docs/CCPF_FORMAL_DESIGN_GATE.md` | Establishes infeasibility blindspot in purely probabilistic ranking |
| `docs/CCPF_INTEGRATION_DESIGN.md` Sec 13 | Gap analysis from Prompts 7A/7B/7C: single-hop limitation, overhead gate |
| `arf_rt/engine/paths.py` | Verified current heap tuple structure and Mode A hook placement |
| `arf_rt/ccpf_bridge.py` | Verified ConstraintIndex, evaluate_candidate_hop(), Mode A implementation |
| `research/ccpf/rdce.py` | Verified PathEvaluationInput, HopContextSpec, TransitionRelation, FeasibilityStatus |
| `tests/integration/test_ccpf_bridge.py` (Tests 18, 19) | Anchors Mode B design requirements |

---

*Document produced in Prompt 8 -- Design Gate. No source code has been modified.
No tracker has been implemented. Active pruning remains prohibited.
All items tagged [OPEN] or [BLOCKER] must be resolved before Phase B implementation begins.*