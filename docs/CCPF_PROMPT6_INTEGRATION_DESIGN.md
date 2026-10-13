# CCPF Prompt 6 — Integration Design Specification (DRAFT)

**Document:** docs/CCPF_PROMPT6_INTEGRATION_DESIGN.md  
**Branch:** 	emporal-context-dev  
**Date:** 2026-10-13  
**Status:** DRAFT — awaiting researcher sign-off before implementation

> **STOP RULE:** This document is a design specification only.
> No production code (rf_rt/) may be modified until this design is
> approved. Prompt 6 implementation is gated on Prompt 5A re-review passing.

---

## 1. Integration objective

Integrate the RDCE feasibility oracle into the existing Best-First
attack-path search engine (rf_rt/engine/paths.py) as a non-perturbing
**feasibility guard** that prunes logically infeasible path prefixes
before probability scoring.

The integration must:
- Not alter Bayesian Q8 probability scores for feasible paths.
- Not alter Union-Find correlation grouping for feasible paths.
- Not alter the ranked output order among feasible paths.
- Not add new external dependencies to the production engine.
- Remain fully opt-in behind a feature flag.

---

## 2. Proposed architecture

`
Best-First Search Loop (paths.py)
│
├── Expand next frontier node (existing logic)
│
├── For each candidate edge:
│   │
│   ├── [NEW] Build HopContextSpec from edge metadata
│   ├── [NEW] Call evaluate_path_feasibility(bundle)
│   │
│   ├── If SAT  → proceed with existing probability scoring
│   ├── If UNSAT → prune edge (do not add to frontier)
│   └── If UNKNOWN → treat as feasible (conservative; log diagnostic)
│
└── Continue existing Top-K selection and output
`

### 2.1 Feature flag

`python
CCPF_FEASIBILITY_GUARD = os.environ.get("ARF_CCPF_GUARD", "0") == "1"
`

When disabled, the engine behaves identically to the Prompt 3 baseline.

### 2.2 Edge metadata → HopContextSpec mapping

The following edge attributes (already present in the graph model) map
directly to RDCE inputs:

| Edge attribute | RDCE field |
|---|---|
| edge.src_node.arn | HopContextSpec.src_node_id |
| edge.dst_node.arn | HopContextSpec.dst_node_id |
| edge.action | HopContextSpec.edge_type |
| edge.condition_block | HopContextSpec.required_context (parsed) |
| Hop index in path | HopContextSpec.hop |

A new translation function 	ranslate_edge_to_hop_spec(edge, hop_index)
will be added to a new module rf_rt/ccpf_bridge.py. This keeps all
CCPF-specific logic outside the core engine.

### 2.3 Scope of changes

| File | Change type | Description |
|---|---|---|
| rf_rt/ccpf_bridge.py | **New** | Edge→HopContextSpec translator; isolated bridge |
| rf_rt/engine/paths.py | **Minimal patch** | Add guard call behind feature flag |
| 	ests/integration/test_ccpf_bridge.py | **New** | Bridge unit tests |
| 	ests/integration/test_ccpf_guard.py | **New** | End-to-end guard tests against baseline |

No other production files are modified.

---

## 3. Invariants that must be preserved

1. **Feasibility is independent of Q8 scores.** The guard runs before
   probability arithmetic. An UNSAT path is discarded before scoring.
2. **UNKNOWN is conservative.** An UNKNOWN result from the RDCE never
   causes a path to be pruned; it is logged and the path proceeds.
3. **Baseline parity.** With the guard disabled, ranked output must be
   bit-identical to the Prompt 3 baseline for every existing fixture.
4. **No RDCE state shared between paths.** Each call to
   evaluate_path_feasibility receives a fresh PathContextBundle.
5. **No production test regressions.** The full production test suite
   must continue to pass with the guard enabled on all existing fixtures
   (since no existing fixture path is UNSAT by construction).

---

## 4. Open design questions (for researcher review)

1. **Condition-block parser:** How should raw IAM JSON condition blocks
   from edge metadata be parsed into ContextPredicate objects? A new
   parser is needed; its scope must be agreed before Prompt 6 begins.
2. **AssumeRole boundary detection:** The engine currently tracks hop
   types. Confirm that edge.action == "sts:AssumeRole" is the correct
   signal for triggering the F4 scope reset in the bridge.
3. **UNKNOWN logging level:** Should UNKNOWN diagnostics go to the
   standard logger at DEBUG or WARNING? Researcher preference needed.
4. **Performance budget:** The RDCE adds < 35 µs per 3-hop path. Is
   this acceptable for the production query latency budget?

---

## 5. Acceptance criteria for Prompt 6

- [ ] rf_rt/ccpf_bridge.py exists and is tested.
- [ ] Feature flag correctly enables/disables guard.
- [ ] Baseline parity test passes (guard disabled = identical output).
- [ ] All 128 RDCE research tests continue to pass.
- [ ] Full production test suite passes.
- [ ] Integration design approved by researcher.

---

*Draft created: 2026-10-13. Implementation blocked on Prompt 5A re-review.*
