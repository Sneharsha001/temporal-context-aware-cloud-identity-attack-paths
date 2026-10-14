# CCPF Integration Design
## Prompt 6 — Design Only (No Production Code Modified)

**Document:** `docs/CCPF_INTEGRATION_DESIGN.md`
**Branch:** `temporal-context-dev`
**Date:** 2026-10-14
**HEAD at time of writing:** `9da2b29`
**Status:** DESIGN SPECIFICATION — implementation is gated on researcher authorization

> **STOP RULE:** This document records a design only. No production
> source under `arf_rt/` may be modified until this design is
> independently reviewed and explicitly approved. Prompt 6 ends here.

---

## 1. Purpose and Scope

This document specifies a technically defensible, minimal-risk integration
design for connecting the Restricted Deterministic Constraint Evaluator
(RDCE, `research/ccpf/rdce.py`) into the ARF-RT Best-First attack-path
search engine (`arf_rt/engine/paths.py`).

**Scope of this document:**
- Architecture inspection of actual source code (not assumed structure).
- Proposed data mapping from ARF-RT edge data to RDCE input structures.
- SAT / UNSAT / UNKNOWN handling contract.
- Probability isolation requirements.
- Top-K placement analysis and trade-offs.
- Staged experiment plan with measurable go/no-go criteria.
- Explicit non-goals and open proof obligations.

**Out of scope:**
- Implementation of any adapter, bridge, or integration code.
- Modification of `arf_rt/` production source files.
- Changes to probability scoring, Q8 arithmetic, or Top-K logic.
- Expansion of RDCE supported operator fragment.

---

## 2. Verified Baseline and Repository State

| Item | Value |
|---|---|
| Branch | `temporal-context-dev` |
| HEAD | `9da2b29` |
| Upstream sync | Matches `origin/temporal-context-dev` |
| Working tree | **Clean** |
| Prompt 5D verdict | **READY FOR INTEGRATION DESIGN** (`docs/CCPF_RE_REVIEW.md` Section 7) |
| Research test suite | 141 passed / 141 total |
| Fixture validation | 6/6 (CE1-CE6) OK |
| Baseline mirror | `ARF-RT-BASELINE` untouched |

---

## 3. Source-Supported Current Architecture and Call Flow

### 3.1 Core Data Model

**Nodes** (`nodes` table, `NodeInput` in `arf_rt/models/core.py`):
Fields: `node_id` (PK, typically an ARN), `provider`, `node_type`,
`provider_id`, `region`, `display_name`, `properties_json`.
`properties_json` is an opaque JSON blob with NO structured policy
condition fields in the current schema.

**Edges** (`edges` table, `EdgeInput` in `arf_rt/models/core.py`):
Fields: `edge_id`, `edge_type` (e.g. `"sts:AssumeRole"`), `src_node_id`,
`dst_node_id`, `region`, `template_id`, `alpha_i`, `beta_i`, `status`,
`frozen`, `flags_json`.
**No policy condition block field** exists on edges (confirmed in
`arf_rt/storage/migrations.py` v1 DDL).
Trust-condition information is extracted at ingest by
`arf_rt/adapters/trust_policy_parser.py` and stored as `constraints`
records linked via `edge_constraints`.

**Constraints** (`constraints` table, `ConstraintInput`):
Fields: `constraint_id`, `constraint_type` (SCP, PERMISSION_BOUNDARY,
TRUST_CONDITION, RESOURCE_POLICY, AZURE_CA, AZURE_PIM), `scope_type`,
`scope_id`, `region`, `properties` (dict), `status`, `validation_status`,
`confidence_q`. The `properties` dict holds `condition_key`,
`condition_operator`, `values` extracted by trust_policy_parser.

**EdgeConstraints** (`edge_constraints`): many-to-many edge_id <-> constraint_id.

### 3.2 Best-First Search Engine (`arf_rt/engine/paths.py`)

Entry point: `search_top_k(conn, objective_id, correlation) -> list[dict]`

Observed call flow (from direct source inspection):

```
search_top_k()
  Load objective (start_nodes, target_nodes, max_depth, k) from DB
  compute_correlation(conn)
    correlation.py: build_global_components -> compute_edge_groups
                    -> select_all_group_representatives
  Load all edges from DB:
    SELECT edge_id, src_node_id, dst_node_id, alpha_i, beta_i, flags_json
    (NOTE: edge_type NOT selected here -- Gap G1)
  Compute edge_probs[eid] = edge_p_q8(alpha_i, beta_i)
  Best-First heap loop:
    heap item: (-p_worst_q8, path_length, edge_id_seq_str,
                cur_node, visited, edge_list,
                pw_q8, pb_q8, worst_sigs, best_sigs)
    heappop -> if cur_node in target_nodes: record result, continue
    if plen >= max_depth: continue
    for (eid, dst) in adj[cur_node]:
      if dst in visited: skip
      compute new_pw_q8 via grouped_product_q8()
      compute new_pb_q8 via grouped_product_q8()
      heappush(...)
```

**Key observations (all source-verified):**
1. The engine loads edges WITHOUT constraint data. Constraints affect
   `correlation` grouping only, not per-edge expansion.
2. Heap state carries no feasibility or context state per path.
3. Priority key `(-p_worst_q8, path_length, edge_id_seq_str)` is
   independent of feasibility.
4. **No existing hook or callback interface for feasibility checking.**
5. `edge_type` is in the `edges` table (confirmed in migrations DDL)
   but is NOT loaded in the `paths.py` SELECT query (Gap G1).

### 3.3 Probability / Belief System

- Q8 = 100,000,000 (`arf_rt/config.py`, spec A§3.4).
- `edge_p_q8(alpha_i, beta_i)` = `floor(alpha_i * Q8 / (alpha_i + beta_i))`.
- `grouped_product_q8(pw, ep)` = `floor((pw * ep) / Q8)`.
- Score mutation: only via `arf_rt/engine/updater.py`. RDCE must not
  call updater or mutate beliefs.

### 3.4 RDCE Interface (`research/ccpf/rdce.py`)

Key public types (frozen dataclasses):

| Type | Purpose |
|---|---|
| `PathEvaluationInput` | `path_id`, `hops: List[HopContextSpec]`, `transition_constraints`, `scenario_assumptions` |
| `HopContextSpec` | `hop`, `edge_type`, `src_node_id`, `dst_node_id`, `required_context`, `produced_context` |
| `ContextPredicate` | `key`, `operator`, `values`, `scope: ContextScope`, `description` |
| `PathEvaluationResult` | `status: FeasibilityStatus`, `witness`, `contradiction_rationale`, `unknown_rationale`, `timeout_occurred`, `diagnostic_metadata` |
| `FeasibilityStatus` | `SAT`, `UNSAT`, `UNKNOWN` |

Supported safe fragment operators: `IpAddress`, `NotIpAddress`,
`StringEquals`, `StringLike` (no wildcards), `Bool`, `Null`.

Scopes: `REQUEST`, `SESSION`, `PRINCIPAL`, `CONFIG`, `UNKNOWN`.

AssumeRole detection: `edge_type == "sts:AssumeRole"` triggers scope reset.

**RDCE has zero imports from `arf_rt/`.** Fully isolated.

### 3.5 Constraint Data Available for Mapping

`trust_policy_parser.py` extracts and stores: `sts:ExternalId`,
`aws:SourceIp`, `aws:SourceVpc`, `aws:SourceVpce`, `aws:PrincipalOrgID`,
`aws:PrincipalOrgPaths`, `aws:MultiFactorAuthPresent`,
`aws:MultiFactorAuthAge`, `sts:RoleSessionName`, `aws:PrincipalTag/*`.

---

## 4. Proposed Integration Boundary and Data Mapping

### 4.1 Boundary Principle

The integration boundary is the narrowest possible interface that
supplies RDCE with required data without modifying heap state,
edge beliefs, correlation groups, or DB schema.

**Proposed boundary:** New module `arf_rt/ccpf_bridge.py` (not yet
created). Called from `paths.py` only when feature flag is set.

### 4.2 Required Adapter Inputs — Availability Analysis

| Required RDCE Field | ARF-RT Source | Available? |
|---|---|---|
| `HopContextSpec.hop` | Index in `edge_list` | YES |
| `HopContextSpec.edge_type` | `edge_data[eid]["edge_type"]` | GAP G1 (not loaded in SELECT) |
| `HopContextSpec.src_node_id` | `edge_data[eid]["src"]` | YES |
| `HopContextSpec.dst_node_id` | `edge_data[eid]["dst"]` | YES |
| `ContextPredicate.key` | `constraints.properties["condition_key"]` | In DB, not in search loop |
| `ContextPredicate.operator` | `constraints.properties["condition_operator"]` | In DB, not in search loop |
| `ContextPredicate.values` | `constraints.properties["values"]` | In DB, not in search loop |
| `ContextPredicate.scope` | Derived from `condition_key` | Must derive (no existing function) |
| `ProducedStateModification` | Sidecar `.context.json` (research-only) | NOT IN SCHEMA |
| `TransitionRelation` | Sidecar `.context.json` (research-only) | NOT IN SCHEMA |

**Identified data gaps:**

**G1** — `edge_type` not loaded by `paths.py`. One-line fix required
to add it to the SELECT query.

**G2** — Constraint predicate data not loaded into search loop. A
pre-search constraint index (edge_id -> list[ContextPredicate]) must
be built from `constraints` and `edge_constraints` tables before
the heap loop begins.

**G3** — `ProducedStateModification` and `TransitionRelation` have
no production schema equivalent. Initial integration uses
`produced_context=[]` and `transition_constraints=[]` only.

**G4** — Scope derivation function does not exist in production.
A new `infer_scope(condition_key) -> ContextScope` function is needed.

### 4.3 Proposed Scope Derivation Mapping

| Condition Key | Derived Scope |
|---|---|
| `aws:SourceIp` | `REQUEST` |
| `sts:ExternalId` | `CONFIG` |
| `aws:PrincipalTag/*` | `PRINCIPAL` |
| `aws:MultiFactorAuthPresent` | `SESSION` |
| `aws:MultiFactorAuthAge` | `SESSION` |
| `sts:RoleSessionName` | `SESSION` |
| `aws:PrincipalOrgID` | `PRINCIPAL` |
| `aws:SourceVpc` | `REQUEST` |
| `aws:SourceVpce` | `REQUEST` |
| Anything else | `UNKNOWN` (RDCE returns UNKNOWN safely) |

### 4.4 Missing Metadata Handling

- No constraints on edge: `required_context=[]`; RDCE returns UNKNOWN.
- Unsupported operator: RDCE returns UNKNOWN; path kept.
- Malformed values: RDCE returns UNKNOWN; path kept.
- Missing `edge_type` (empty): non-AssumeRole hop; no scope reset.

### 4.5 Feature Flag

```python
# Proposed addition to arf_rt/config.py
import os
CCPF_FEASIBILITY_GUARD: bool = os.environ.get("ARF_CCPF_GUARD", "0") == "1"
```

When `ARF_CCPF_GUARD=0` (default), `paths.py` must be bit-identical
to the pre-integration baseline.

### 4.6 Integration Point Options

**Option A — At neighbor generation (before heappush):**
- Prunes subtrees early; saves heap memory.
- Calls RDCE for every expanded candidate.
- Risk: false UNSAT prunes entire subtree.
- Requires O1+O3+O7 proof obligations.

**Option B — At heap pop (before target/depth check):**
- Calls RDCE only for competitive paths.
- No heap memory savings.
- Requires O1+O3 (O7 partially relaxed).

**Recommendation: Conservative Option A, single-hop evaluation only.**

Rationale: Conjunction monotonicity justifies prefix pruning IF RDCE
is sound (O1). Single-hop evaluation (evaluating only the new candidate
edge, not the full accumulated prefix) avoids needing O3/O6/O7 for
the full-prefix case and limits subtree pruning risk. This is the
smallest defensible starting point. Full-prefix evaluation is a
future option contingent on O3 verification.

---

## 5. SAT / UNSAT / UNKNOWN Handling Contract

### 5.1 SAT

RDCE found a satisfying assignment within the safe fragment.

Adapter behavior:
- Continue existing probability scoring unchanged.
- Do NOT modify `pw_q8`, `pb_q8`, `worst_sigs`, `best_sigs`.
- Do not alter heap priority key.
- Log witness at DEBUG level optionally.

Invariant: `p_worst_q8(path)` unchanged before vs after guard.

### 5.2 UNSAT

RDCE found a formal contradiction within the safe fragment.

Adapter behavior:
- Skip `heappush` (Option A) or `continue` (Option B).
- Log `contradiction_rationale` at INFO.
- Increment diagnostic counter `ccpf_unsat_pruned`.

Required preconditions before trusting UNSAT:
1. `timeout_occurred == False`.
2. `contradiction_rationale` is non-empty.
3. All evaluated predicates are from the safe fragment.
4. Constraint is VALIDATED (not UNVALIDATED or ASSUMED) with
   `confidence_q >= 500`.

Risks that must never be suppressed:
- UNSAT from UNVALIDATED constraint = incomplete evidence, not denial.
- `timeout_occurred=True` UNSAT must be treated as UNKNOWN.
- Q8 underflow (`p_worst_q8 = 0`) must NOT be converted to UNSAT.

### 5.3 UNKNOWN

RDCE could not reach a sound decision.

Adapter behavior:
- Treat identically to SAT — do not prune.
- Log `unknown_rationale` at DEBUG.
- Increment counter `ccpf_unknown_count`.

Invariants:
- UNKNOWN MUST NOT be converted to UNSAT.
- UNKNOWN MUST NOT cause a path to be dropped.
- UNKNOWN MUST NOT alter `p_worst_q8`.

Current ARF-RT fallback: with UNKNOWN treated as passthrough,
integrated behavior for UNKNOWN paths is identical to unintegrated
baseline. This is the correct conservative behavior.

### 5.4 Probability Isolation Invariants

| # | Invariant | How to verify |
|---|---|---|
| PI-1 | RDCE produces no probability value | `PathEvaluationResult` has no `probability`/`multiplier` field (verified) |
| PI-2 | SAT does not change `pw_q8` | Guard-off vs guard-on: identical `p_worst_q8` on same inputs |
| PI-3 | UNKNOWN does not change `pw_q8` | Same as PI-2 for UNKNOWN paths |
| PI-4 | UNSAT does not modify surviving paths' `pw_q8` | Surviving paths retain exact scores |
| PI-5 | RDCE does not import `arf_rt/` | Verified: zero `arf_rt` imports in `research/ccpf/rdce.py` |
| PI-6 | Correlation groups not mutated | `edge_groups`, `p_worst_reps`, `p_best_reps` read-only during guard |
| PI-7 | `updater.py` not called | Feasibility guard path never calls `updater.apply_observation` |

---

## 6. Top-K Placement Analysis and Trade-offs

### 6.1 Search Algorithm Characteristics (Source-Verified)

- Priority key: `(-p_worst_q8, path_length, edge_id_seq_str)`.
- Stopping: `len(results) == k` OR empty heap.
- Tie-breaking: deterministic by `COLLATE BINARY` on `edge_id_seq_str`.
- No explicit admissibility proof in source.

### 6.2 Placement Options Summary

| Position | Top-K Effect | UNKNOWN Safety | Completeness Risk |
|---|---|---|---|
| Before heappush (Option A) | UNSAT never enters heap | UNKNOWN enters normally | O1+O3+O7 must be proved |
| After heappop (Option B) | UNSAT popped and discarded | UNKNOWN scored normally | O1+O3 required; O7 relaxed |
| After target reached | All paths scored; filter at output | Safe | No pruning benefit |
| Never (disabled) | Baseline preserved | N/A | No risk; no benefit |

### 6.3 Proof Obligations (All From `CCPF_FORMAL_DESIGN_GATE.md §11`)

| Obligation | Status | Required Before |
|---|---|---|
| O1 Solver Soundness | OPEN | Any UNSAT-based pruning |
| O2 Scope Reset Invariance | OPEN | AssumeRole boundary detection |
| O3 Monotonic UNSAT Pruning | CONDITIONAL | Full-prefix Option A |
| O4 Score Invariance | OPEN | Integration regression |
| O5 Tie-Break Preservation | OPEN | Integration regression |
| O6 Search-Bound Admissibility | OPEN | Full-prefix Option A |
| O7 Exact Top-K Completeness | OPEN | Full-prefix Option A |
| O8 Non-Perturbation under UNKNOWN | OPEN | Integration regression |

Single-hop evaluation relaxes O3/O6/O7 requirement for initial prototype.
O1 and O4/O5/O8 still apply regardless.

### 6.4 Completeness and Tie-Break Risks

- **Underflow (O7):** If `k` is reached by zero-score non-pruned paths
  before positive-score paths fully expand, premature termination is
  possible. Must be verified empirically.
- **Tie-breaking:** UNSAT pruning changes which paths are in the heap
  but does not change priorities of surviving paths. Rank preservation
  holds only if no path ranking <= k is incorrectly pruned (O7).
- **Candidate generation:** No limits in `paths.py` beyond `max_depth`
  and `k`. Pruning reduces heap size but does not interact with
  `max_depth`.

---

## 7. Failure Modes, Assumptions, and Open Proof Obligations

### 7.1 Failure Modes

| Mode | Condition | Consequence | Mitigation |
|---|---|---|---|
| False UNSAT | RDCE soundness bug | Feasible path silently pruned | O1; disable on any reproducible false UNSAT |
| UNKNOWN to UNSAT | Bridge or error handler bug | Same as false UNSAT | PI-3; explicit tests for all UNKNOWN codes |
| Score mutation | Bridge calls updater or modifies belief | Corrupted ranking | PI-7; pre/post score comparison |
| Provenance error | UNVALIDATED constraint trusted | Premature pruning | Filter by `validation_status = 'VALIDATED'` |
| G1 gap unaddressed | `edge_type` missing from search | AssumeRole not detected | Must add `edge_type` to SELECT before integration |
| No produced context | No schema extension | Dynamic pivots not modeled | Leave `produced_context=[]`; document |

### 7.2 Explicit Assumptions

1. **Static attacker origin:** Source IP does not change across hops.
   Research-level assumption; not a general property of real attackers.
2. **Trust condition completeness:** Only conditions extracted by
   `trust_policy_parser.py` are evaluable. Others return UNKNOWN.
3. **Constraint validation provenance:** UNSAT only trustworthy on
   VALIDATED constraints. UNVALIDATED/ASSUMED constraints require
   UNKNOWN fallback.
4. **No temporal TTL:** RDCE does not model session expiry or
   time-based conditions. Such conditions return UNKNOWN.

---

## 8. Staged Experiment Plan and Reproducibility Requirements

### Stage 1 — RDCE Isolation Verification (COMPLETE)

Status: 141/141 tests pass. CE1-CE6 verified. Evidence in `tests/research/`.

### Stage 2 — Adapter Contract Tests (Pre-Implementation)

Proposed test file: `tests/integration/test_ccpf_bridge.py`

| Test | Scenario | Expected |
|---|---|---|
| B1 | VALIDATED SOURCE_IP TRUST_CONDITION -> IpAddress predicate | `ContextPredicate(key="aws:SourceIp", operator="IpAddress", scope=REQUEST)` |
| B2 | `edge_type="sts:AssumeRole"` | `HopContextSpec.edge_type == "sts:AssumeRole"` |
| B3 | UNVALIDATED constraint | Excluded from `required_context` |
| B4 | No constraints on edge | `required_context=[]`; RDCE returns UNKNOWN |
| B5 | Unsupported operator | RDCE returns UNKNOWN |
| B6 | Missing `edge_type` | No scope reset; treated as regular hop |
| B7 | Each known condition key | Correct `ContextScope` derived |
| B8 | Malformed CIDR | RDCE returns UNKNOWN; no exception |

Go/no-go: All B1-B8 pass before Stage 3.

### Stage 3 — Status Behavior Tests

Proposed test file: `tests/integration/test_ccpf_guard.py`

| Test | Scenario | Expected |
|---|---|---|
| S1 | SAT path: guard-off vs guard-on | Identical `p_worst_q8` and rank |
| S2 | UNKNOWN: guard-off vs guard-on | Identical results; path not pruned |
| S3 | UNSAT: VALIDATED SOURCE_IP disjoint CIDRs | Path excluded; counter increments |
| S4 | UNSAT with `timeout_occurred=True` | Treated as UNKNOWN; not pruned |
| S5 | UNSAT from UNVALIDATED constraint | Path not pruned |
| S6 | Empty fixture (no constraints) | Results identical to baseline |

Go/no-go: All S1-S6 pass. Failure in S1/S2/S4/S5/S6 is blocking.

### Stage 4 — Probability Invariance Tests

Method:
1. Run `search_top_k` guard-off; record `p_worst_q8` and `p_best_q8`.
2. Run guard-on on same fixture.
3. Assert scores identical for all surviving paths.

Go/no-go: Zero Q8 mutations. Any mutation blocks integration.

### Stage 5 — Top-K Comparison

Method:
1. Construct fixture with 3-5 known-infeasible paths and >=k feasible paths.
2. Guard-on: verify exactly k feasible paths returned.
3. Guard-off with k increased: verify infeasible paths appear.
4. Compare rank order of feasible paths.

Required: New fixture distinct from CE1-CE6.

Go/no-go: All k feasible paths present; infeasible absent; rank preserved.
Any feasible path missing = blocking defect.

### Stage 6 — Soundness Evaluation

Ground truth: `primary_realistic_truth_map.json` `result=ALLOW`.

Metrics:
- `false_unsat_rate = |incorrectly_pruned| / |total_unsat_pruned|`
- `true_unsat_rate = |correctly_pruned| / |total_unsat_pruned|`

Go/no-go: `false_unsat_rate == 0.0`. Any reproducible false UNSAT blocks.

### Stage 7 — Efficiency Measurement

Method:
1. Instrument bridge with `time.perf_counter()` per RDCE call.
2. Run on `stage1_large.json` and `primary_realistic_scenario.json`.
3. Minimum 10 runs; discard top-2 and bottom-2 outliers.
4. Report: median RDCE latency, RDCE time fraction of pipeline, slowdown factor.
5. One warm-up pass before measurement.

Note: The `< 35 us` figure in `CCPF_FORMAL_DESIGN_GATE.md` is a design
target, not an empirical result. No performance claims made here.

Go/no-go: RDCE time fraction < 5% of pipeline on `stage1_large.json`,
or researcher explicitly accepts overhead.

### Stage 8 — Reproducibility Requirements

Every experiment records:

| Item | Requirement |
|---|---|
| Git commit | Full SHA of `temporal-context-dev` |
| Python version | `python --version` |
| Package versions | `pip freeze` output |
| Fixture names and hashes | sha256 of each input |
| Command | Exact command line |
| Full output | Complete pytest or script output |
| Pass/fail | Explicit for each go/no-go criterion |

---

## 9. Acceptance Criteria for Future Implementation Phase

Implementation (Prompt 7+) is authorized only when ALL criteria pass:

| # | Criterion | Blocking |
|---|---|---|
| A1 | Architecture description verified against current source | YES |
| A2 | Gap G1 (edge_type) documented and accepted | YES |
| A3 | B1-B8 adapter contract tests pass | YES |
| A4 | S1-S6 status behavior tests pass | YES |
| A5 | PI-1 through PI-7 probability invariants verified | YES |
| A6 | Stage 5 Top-K comparison passes (no feasible path missing) | YES |
| A7 | Stage 6 `false_unsat_rate == 0.0` on all fixtures | YES |
| A8 | No UNKNOWN->UNSAT conversion reproducible | YES |
| A9 | No Q8 score mutation reproducible | YES |
| A10 | Stage 7 efficiency overhead acceptable | YES |
| A11 | O1 verified (informally, with exhaustive test coverage) | YES |
| A12 | Explicit researcher authorization | YES |

Blocking defects that immediately halt integration:
- Any reproducible false UNSAT.
- Any UNKNOWN silently converted to UNSAT.
- Any mutation of `p_worst_q8` or `p_best_q8` on surviving paths.
- Any regression in existing production test suite.

---

## 10. Files That Future Implementation Might Touch

| File | Change Type | Justification |
|---|---|---|
| `arf_rt/config.py` | Add `CCPF_FEASIBILITY_GUARD` env flag | Feature flag for opt-in activation |
| `arf_rt/engine/paths.py` | Minimal patch: (1) add `edge_type` to SELECT, (2) build constraint index, (3) guard call | Only place where per-path candidate expansion occurs |
| `arf_rt/ccpf_bridge.py` | New module | All CCPF translation logic; isolates `paths.py` changes |
| `tests/integration/test_ccpf_bridge.py` | New | B1-B8 adapter contract tests |
| `tests/integration/test_ccpf_guard.py` | New | S1-S6 end-to-end guard tests |
| `tests/integration/__init__.py` | New | Package init |

Files that MUST NOT be touched:
- `research/ccpf/rdce.py` (no operator extension in this phase)
- `arf_rt/engine/correlation.py`
- `arf_rt/engine/updater.py`
- `arf_rt/engine/belief.py`
- `arf_rt/models/core.py`
- `arf_rt/storage/migrations.py`
- `C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE`

---

## 11. Explicit Non-Goals and Limitations

1. No production integration implemented in Prompt 6.
2. Top-K completeness is NOT proven (O6, O7 open).
3. RDCE safe fragment is NOT extended.
4. No temporal conditions (TTL, expiry) modeled.
5. Full AWS IAM semantics not claimed.
6. `ProducedStateModification` and `TransitionRelation` not mapped
   (no production schema holds this data).
7. No performance claims. Figures are design targets only.
8. Multi-account / cross-region constraint correlation not addressed.

---

## 12. Final Design Recommendation and Evidential Basis

### Recommendation

Proceed to implementation via the following minimal path:

1. Create `arf_rt/ccpf_bridge.py` with:
   - `build_constraint_index(conn, validation_filter=True)` -> `dict[edge_id, list[ContextPredicate]]`
   - `infer_scope(condition_key) -> ContextScope`
   - `build_hop_spec(hop_index, eid, edge_data, constraint_index) -> HopContextSpec`
   - `evaluate_single_hop(eid, edge_data, constraint_index) -> PathEvaluationResult`

2. Patch `arf_rt/engine/paths.py` with exactly two additions:
   - Add `edge_type` to DB SELECT query (Gap G1, one-line change).
   - Behind `if CCPF_FEASIBILITY_GUARD:`, call `evaluate_single_hop`
     at neighbor-generation position (Option A, single-hop mode).

3. Create integration tests in Stages 2-6.

4. Run Stages 2-7 before claiming integration complete.

### Evidential Basis

| Claim | Source |
|---|---|
| RDCE sound within safe fragment | 141/141 tests; F1.1/F3.1 remediated; Prompt 5D review |
| Constraint data in DB | `trust_policy_parser.py` extracts 9+ condition key types |
| `edge_type` in DB but not loaded by search | `migrations.py` DDL vs `paths.py` SELECT |
| Feature flag preserves baseline | Disable flag = zero code path change |
| Single-hop is safest initial mode | Avoids O3/O6/O7 full-prefix obligations |
| Option A more memory-efficient | Option A avoids heappush for UNSAT; confirmed from source |
| UNKNOWN -> passthrough correct | `CCPF_EVALUATOR_CONTRACT.md §5` and `CCPF_FORMAL_DESIGN_GATE.md §11` O8 |
| No production file modified in Prompt 6 | Zero diffs to `arf_rt/` in this session |

### Unresolved Questions for Researcher

1. Should UNSAT pruning filter only VALIDATED constraints, or use a
   researcher-configurable confidence threshold?
2. Should the bridge log UNKNOWN rationales to a file or Python logger only?
3. What is the acceptable pipeline overhead for Stage 7?
4. Single-hop vs full-prefix evaluation for initial prototype?
   This document recommends single-hop; researcher confirmation required.

---

## Related Documents

- `docs/CCPF_EVALUATOR_CONTRACT.md` -- Formal RDCE interface contract
- `docs/CCPF_FORMAL_DESIGN_GATE.md` -- Open proof obligations O1-O8
- `docs/CCPF_RE_REVIEW.md` -- Independent reviews and READY verdict
- `docs/CCPF_PROMPT6_INTEGRATION_DESIGN.md` -- Earlier DRAFT (superseded)
- `RESEARCH_STATUS.md` -- Research phase log
- `research/ccpf/rdce.py` -- RDCE implementation
- `arf_rt/engine/paths.py` -- Best-First search engine

---

*Design authored on `temporal-context-dev` HEAD `9da2b29`.
Implementation gated on researcher review and explicit authorization.*
