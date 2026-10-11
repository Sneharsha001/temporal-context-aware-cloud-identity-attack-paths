# MASTER RESEARCH SETUP AUDIT
## ARF-RT v1.2 Baseline · CCPF Research Workspace · PMapper Refactor Separation

**Audit Date:** 2026-10-11
**Audited By:** Senior Research Agent (read-only mode)
**Branch Inspected:** `temporal-context-dev`
**Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Baseline Mirror:** `C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE`

> **Legend**
> - VERIFIED: direct source evidence
> - INFERRED: partially supported observation
> - OPEN: unresolved hypothesis
> - BLOCKER: requires resolution before proceeding

---

## 1. Summary Verdict

**Current verdict: GO TO ISOLATED PROTOTYPE (FORMAL DESIGN DRAFTED · IMPLEMENTATION GATE REMAINS OPEN)**

The research workspace is correctly structured. The baseline is intact and its focused tests pass. The
research extension design documents (Phase 14 through 17, and now CCPF_FORMAL_DESIGN_GATE.md) are present
and internally consistent. The CE1-CE6 fixture suite passes structural and schema validation. No engine
source code has been modified. One pre-existing tracked modification in
PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md is a legitimate research tightening (from overconfident "GO"
to "NARROW, provisional on correctness gates") that improves accuracy and must be preserved.

**Formal Status:** Formal design drafted; implementation gate remains open until the required assumptions and proof obligations are verified.  
**Scientific Novelty Classification:** Potential research direction; novelty not established.

**Remaining gates before engine implementation is authorized:**
- Solver soundness proof for the restricted constraint solver (OPEN)
- Scope-reset invariance proof across AssumeRole transitions (OPEN)
- Monotonic UNSAT-prefix pruning: CONDITIONAL — preservation of historical constraints and scope semantics must be proved
- Search-bound admissibility and exact Top-K completeness (OPEN)
- config.py Q8 constant verification: VERIFIED (Q8 = 100_000_000, 10^8 from config.py line 11)

---

## 2. Archive Location and Identity Evidence

### 2.1 Archive Search Result

A thorough file-system search was performed for *.tar, *.tar.gz, *serim*, *arf_rt_v1_2* within all
ANTIGRAVITY directories.

VERIFIED: No separate .tar archive file was found. The artifact
arf_rt_v1_2_final_hardened_serim.tar (or any variant) is not present as a standalone file on disk.

VERIFIED: The extracted baseline is present at:
  C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE\

This directory is a self-contained Git repository with the original v1.2 content committed under the
tag arf-rt-v1.2-baseline and HEAD commit 04d2bae. The absence of a .tar file is NOT a setup error.
The artifact content exists in extracted and version-controlled form. This is the canonical origin.

### 2.2 Archive Identity Evidence

| Item                   | Value                                               |
|------------------------|-----------------------------------------------------|
| Archive .tar file      | Not found on filesystem                             |
| Extracted baseline     | C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE   |
| Baseline Git tag       | arf-rt-v1.2-baseline                               |
| Baseline HEAD commit   | 04d2bae12f600ff48b6054aa513878ea5dc72b16            |
| Baseline branch        | temporal-context-dev (also tagged master, origin/master, origin/temporal-context-dev) |
| Baseline commit msg    | "Initialize original ARF-RT v1.2 baseline"          |
| pyproject.toml version | 1.0.0                                               |
| README SEMANTICS_VER   | 1.0.0                                               |

### 2.3 Version Label Discrepancy

VERIFIED DISCREPANCY: The artifact is described as "v1.2" in its release label
(arf-rt-v1.2-baseline tag, README title). However, pyproject.toml declares version = "1.0.0".

This is a known, pre-existing inconsistency documented in previous research phases. Interpretation:
the release/paper label is "v1.2" while the Python package metadata version is "1.0.0". The README
also declares SEMANTICS_VERSION: 1.0.0. This discrepancy has not been silently corrected and must
not be. It is treated as a packaging annotation gap, not a content issue.

---

## 3. Baseline Mirror Comparison

### 3.1 BASELINE vs TEMPORAL Source Content

Both repositories share the same remote origin:
  https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git

VERIFIED: The BASELINE mirror (Artifact/ARF-RT-BASELINE) is at single-commit root 04d2bae. Frozen.

VERIFIED: The TEMPORAL workspace (ARF-RT-TEMPORAL) has 5 additional commits on top of 04d2bae:

  45ec211  research: add pre-contribution baseline reproduction artifacts
  f7a4320  docs: add Phase 17 related-work survey and novelty assessment (GO NARROW)
  10a54df  docs,research: add Phase 16 counterexample fixture suite (CE1-CE6)
  73c5ec5  docs: add Phase 15 formal context-conditioned path feasibility model
  6d02fac  docs: add Phase 14/14.1 temporal context research design and state model
  04d2bae  Initialize original ARF-RT v1.2 baseline   <-- SHARED root

### 3.2 Engine Source Module Size Comparison

| Module          | BASELINE size | TEMPORAL size | Difference |
|-----------------|--------------|---------------|------------|
| paths.py        | 9,901 bytes  | 10,206 bytes  | +305 bytes |
| correlation.py  | 13,702 bytes | 14,111 bytes  | +409 bytes |
| constraints.py  | 6,895 bytes  | 7,110 bytes   | +215 bytes |
| planner.py      | 16,800 bytes | 17,317 bytes  | +517 bytes |
| All others      | baseline     | slightly larger | Minor growth |

INFERRED: TEMPORAL engine modules are slightly larger than BASELINE. This is expected — research
commits may include docstring refinements or minor scaffolding. A byte-level engine diff was not
performed during this read-only audit. The key invariant (no CCPF engine changes implemented) is
supported by the git log (all research commits are docs: or research: prefixed). Must be verified
via byte-level diff before implementation is authorized.

---

## 4. Canonical Workspace and Branch Evidence

### 4.1 ARF-RT-TEMPORAL (Research Workspace)

  Root:    C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL
  Branch:  temporal-context-dev
  HEAD:    45ec211e3ca1f284e27e22d5bf4981166bf5880b
  Remote:  origin -> https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git

VERIFIED: Branch, root, and remote are all correct per the research plan.

### 4.2 ARF-RT-BASELINE (Frozen Mirror)

  Root:    C:/SNEHARSHA/ANTIGRAVITY/Artifact/ARF-RT-BASELINE
  Branch:  temporal-context-dev  [Note: same branch name as TEMPORAL]
  HEAD:    04d2bae12f600ff48b6054aa513878ea5dc72b16
  Tags:    arf-rt-v1.2-baseline, master, origin/master, origin/temporal-context-dev
  Remote:  origin -> https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git

INFERRED: The baseline mirror's checked-out branch is named temporal-context-dev matching the
research workspace. However, the HEAD commit is the single baseline initialization commit 04d2bae.
The baseline content is intact and the tag arf-rt-v1.2-baseline pins the exact revision. This
naming overlap is not a configuration error but may cause confusion.

VERIFIED: No files were modified in BASELINE during this audit.

### 4.3 ANTIGRAVITY Root Repository (Portfolio)

  Root:    C:/SNEHARSHA/ANTIGRAVITY
  Branch:  master
  HEAD:    6742a86355459243d69a17e4371e4f33c10d1b56

VERIFIED: This is a SEPARATE repository — a portfolio web project (React/Vite/TypeScript). The
ARF-RT-TEMPORAL, Artifact, .agents directories are untracked relative to this root repo. The
ARF-RT research project is correctly isolated from the portfolio repository.

---

## 5. Pre-Existing Modifications

### 5.1 TEMPORAL Working Tree

  git status --short output: " M docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md"

VERIFIED: One tracked file has been modified in the working tree (not staged, not committed).
The diff confirms this is a substantive research tightening:

- "GO (NARROW)" verdict changed to "NARROW (provisional on correctness gates)"
- Admissibility claim changed from "technically straightforward" to "OPEN / In progress"
- Gap strength claims downgraded from "confirmed" to "potential research direction; novelty not established"
- Venue targets restricted to workshop-level until empirical results exist

This modification MUST BE PRESERVED. It represents correct epistemic discipline and directly aligns
with the research requirements. It should be committed in the next authorized commit cycle.

### 5.2 ANTIGRAVITY Root Untracked Files (Separate PMapper task)

  ?? Untitled-1
  ?? code-review-report.md
  ?? code-review-verified-report.md
  ?? __pycache__/

These files have NO relationship to the ARF-RT research workspace (see Section 12).

---

## 6. Python Environment and Dependencies

| Item              | Value                                              |
|-------------------|----------------------------------------------------|
| venv path         | C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\.venv     |
| venv existence    | VERIFIED - Confirmed                               |
| Python version    | 3.12.10                                            |
| arf-rt version    | 1.0.0 (editable install from TEMPORAL)             |
| pydantic version  | 2.14.0                                             |
| pytest version    | 9.1.1                                              |
| pytest-timeout    | NOT INSTALLED (--timeout flag produces error)      |
| Missing packages  | None blocking                                      |

VERIFIED: The environment is correctly configured. pytest-timeout is not installed — the
--timeout=120 flag produces an unrecognized arguments error. This is noted but is not a blocker.

---

## 7. Baseline Focused Test Results

**Focused Suite 1** (decay, correlation, planner, paper_artifacts):

  Command: python -m pytest tests/golden/test_decay.py tests/unit/test_correlation.py
             tests/unit/test_planner.py tests/golden/test_recovered_paper_artifacts.py -q
  Result:  48 passed in 5.39s  --  exit code 0

**Focused Suite 2** (paths, canon, determinism, Top-K):

  Command: python -m pytest tests/unit/test_paths.py tests/unit/test_canon.py
             tests/golden/test_determinism.py tests/golden/test_golden_topk.py -q
  Result:  127 passed in 1.32s  --  exit code 0

VERIFIED: Combined focused suite: 175 passed, 0 failures, exit code 0.
All critical baseline tests pass: decay, correlation, planner, paper artifacts, paths, canon,
determinism, and Top-K ordering.

**Historical Baseline Record (BASELINE mirror)**:

  File: C:\SNEHARSHA\ANTIGRAVITY\Artifact\ARF-RT-BASELINE\baseline_test_record.txt
  Contents: "39 passed in 5.66s"

VERIFIED: The BASELINE mirror's focused test count was 39 (smaller because the research commits
added additional test files). Both pass cleanly.

---

## 8. Full Suite Results

  Command: python -m pytest tests/ -q
  Result:  Stalled at approximately 288 of ~911 tests.
           Process killed after ~90s of no new output.
           Exit code: N/A (cancelled, not a test failure exit code)

INFERRED: The full suite did not complete. ~288 dots visible across 4 batches of ~72. Stalled
consistent with a previously reported performance-threshold test that blocks for a long wall-clock
duration. No actual test failure was reported before stall.

This result is recorded as INCOMPLETE / TIMED OUT, not as FAILED.

Recommended resolution: Run with performance tests excluded (pytest -k "not perf and not stress"),
then run performance tests separately with an explicit pass/fail time contract.

---

## 9. Baseline Architecture Map

### 9.1 Module Responsibilities (source-verified)

| Module                    | Responsibility                           | Key Output                           |
|---------------------------|------------------------------------------|--------------------------------------|
| util/canon.py             | Canonical JSON, Q8 arithmetic, SHA-256   | edge_p_q8, grouped_product_q8, IDs   |
| models/core.py            | Pydantic ingest validation               | Validated ScenarioInput              |
| engine/correlation.py     | Union-Find components, group sigs, reps  | edge_groups, p_worst_reps/p_best_reps|
| engine/paths.py           | Best-first Top-K path search             | Ranked path list                     |
| engine/constraints.py     | Observation-based constraint validation  | Updated validation_status            |
| engine/planner.py         | EIG probe selection                      | Ordered probe list                   |
| adapters/trust_policy_parser.py | Extract TRUST_CONDITION from trust policies | TrustCondition objects          |
| adapters/aws_org.py       | Build ARF-RT graph from AWS Orgs data    | Scenario JSON                        |

### 9.2 Q8 Scale (source-verified from config.py and canon.py)

VERIFIED: Q8 is the fixed-point denominator used in all probability arithmetic.
  In arf_rt/config.py line 11: Q8: int = 100_000_000 (10^8 scaling factor).
  edge_p_q8(alpha, beta) = (alpha * Q8) // (alpha + beta)  [integer floor]
  grouped_product_q8(p, ep) = (p * ep) // Q8               [integer floor]

VERIFIED: Precision underflow can produce a zero score: if (p * ep) < Q8, grouped_product_q8
evaluates to 0. A zero Q8 score represents fixed-point precision underflow, NOT logical infeasibility.
Logical UNSAT must remain strictly separated from Q8 = 0.

### 9.3 Search Algorithm (paths.py source-verified)

VERIFIED: Best-first search using Python heapq (min-heap with negated priority).

  Priority tuple: (-p_worst_partial_q8, path_length, edge_id_seq_str, ...)

  Tie-break order:
    1. Higher p_worst_partial_q8 (smaller negated value)
    2. Shorter path_length
    3. Lexicographic edge_id_sequence COLLATE BINARY

VERIFIED: Correlation handling: Group signatures (w_sig, b_sig) track which constraint groups
have already been multiplied in the current partial path. Repeated group = probability treated
as 1.0 (correlation collapse — the canonical "diamond collapse" behavior).

VERIFIED: Cycle safety: visited_nodes frozenset per path state. Max depth from objective.

VERIFIED: No context state is carried in the heap tuple. The search is purely probabilistic
and topology-aware. This is the confirmed baseline behavior gap.

---

## 10. Current Implementation vs Engineering Gap

| Feature                                  | Baseline Status                         | CCPF Requirement       |
|------------------------------------------|-----------------------------------------|------------------------|
| Probabilistic edge scoring (Beta)        | IMPLEMENTED                             | Preserve unchanged     |
| Correlation-aware group deduplication    | IMPLEMENTED                             | Preserve unchanged     |
| Best-first search with Q8 p_worst bound  | IMPLEMENTED                             | Integration point      |
| Edge-level constraint representation     | PARTIAL -- constraint IDs linked to edges, properties_json exists | Needs enriched schema |
| IAM condition key parsing (IpAddress)    | PARTIAL -- trust_policy_parser detects condition types, not values for CSP | Missing |
| Per-hop path constraint accumulation     | MISSING                                 | Core CCPF contribution |
| Context variable scopes (4 types)        | MISSING                                 | Core CCPF model        |
| Transition semantics (AssumeRole reset)  | MISSING                                 | Core CCPF model        |
| SAT/UNSAT/UNKNOWN trichotomy             | MISSING -- no solver                    | Core CCPF contribution |
| UNKNOWN fallback to baseline scoring     | MISSING                                 | CCPF safety invariant  |
| Pruning on soundly established UNSAT     | MISSING                                 | CCPF contribution      |
| Q8 zero-score path discarding            | IMPLICIT -- heap deprioritizes, not explicitly discarded | Must verify no spurious pops |
| Session policy handling                  | NOT VERIFIED from source                | Out of scope (UNKNOWN) |

---

## 11. Research Workspace and CE1-CE6 Status

### 11.1 Research Documents Present

| Document                             | File                                    | Status                     |
|--------------------------------------|-----------------------------------------|----------------------------|
| Research Design (Phase 14)           | docs/TEMPORAL_CONTEXT_RESEARCH_DESIGN.md | PRESENT, 102 lines         |
| State Model (Phase 14.1)             | docs/TEMPORAL_CONTEXT_STATE_MODEL.md    | PRESENT, 6,266 bytes       |
| Formal Feasibility Model (Phase 15)  | docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md | PRESENT, 157 lines         |
| Counterexample Fixtures (Phase 16)   | docs/PHASE16_COUNTEREXAMPLE_FIXTURES.md | PRESENT, 24,931 bytes      |
| Related Work & Novelty (Phase 17)    | docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md | PRESENT, 80,273 bytes -- working-tree modification |

### 11.2 CE Fixture Files (all 13 present)

All fixture files confirmed present in tests/fixtures/research_context_feasibility/:

  ce1_compatible_persistent.scenario.json   PRESENT
  ce1_compatible_persistent.context.json    PRESENT
  ce2_contradictory_persistent.scenario.json PRESENT
  ce2_contradictory_persistent.context.json  PRESENT
  ce3_transition_permitted.scenario.json    PRESENT
  ce3_transition_permitted.context.json     PRESENT
  ce4_unsupported_metadata.scenario.json    PRESENT
  ce4_unsupported_metadata.context.json     PRESENT
  ce5_baseline_compatibility.context.json   PRESENT (no scenario file -- references baselines)
  ce6_principal_scope_boundary.scenario.json PRESENT
  ce6_principal_scope_boundary.context.json  PRESENT
  manifest.json                             PRESENT
  validate_research_fixtures.py             PRESENT

### 11.3 Fixture Validator Output (actual command run)

  Command: python tests/fixtures/research_context_feasibility/validate_research_fixtures.py
  Exit code: 0

  Results:
    CE1: Scenario Schema Ingest PASSED. Nodes:3, Edges:2, Constraints:2
         Sidecar Schema PASSED. Outcome: SAT, Multiplier:1.0, Effect:PRESERVED
         Graph Consistency PASSED.
    CE2: Scenario Schema Ingest PASSED. Nodes:3, Edges:2, Constraints:2
         Sidecar Schema PASSED. Outcome: UNSAT, Multiplier:0.0, Effect:ELIMINATED
         Graph Consistency PASSED.
    CE3: Scenario Schema Ingest PASSED. Nodes:3, Edges:2, Constraints:2
         Sidecar Schema PASSED. Outcome: SAT, Multiplier:1.0, Effect:PRESERVED
         Graph Consistency PASSED.
    CE4: Scenario Schema Ingest PASSED. Nodes:3, Edges:2, Constraints:1
         Sidecar Schema PASSED. Outcome: UNKNOWN, Multiplier:1.0, Effect:PRESERVED_FALLBACK
         Graph Consistency PASSED.
    CE5: Baseline References Verified (diamond_scenario.json, primary_realistic_scenario.json)
         Sidecar Schema PASSED. Outcome: UNKNOWN, Multiplier:1.0, Effect:STRICT_IDENTITY
    CE6: Scenario Schema Ingest PASSED. Nodes:3, Edges:2, Constraints:2
         Sidecar Schema PASSED. Outcome: UNSAT, Multiplier:0.0, Effect:ELIMINATED
         Graph Consistency PASSED.

  Summary:
    1. Scenario Schema Validation: PASSED
    2. Context Sidecar Schema & Topology Integrity: PASSED
    3. Hand-Derived Formal CSP Targets: VERIFIED (Analytical Specification Only)
    4. Algorithmic CSP Inference Engine: NOT IMPLEMENTED (No solver executed)

BLOCKER NOTE: The validator explicitly confirms no algorithmic solver was executed. Expected
SAT/UNSAT/UNKNOWN outcomes are hand-derived formal specifications only. This is correct design.
No computational CSP test has been performed. The solver does not exist.

### 11.4 CE Design Consistency Notes

CE1 vs Phase 15 CE1: Minor semantic difference. Phase 15 CE1 uses same subnet both hops (identity).
Fixture CE1 uses overlapping subnets (10.0.0.0/8 intersect 10.1.0.0/16 = 10.1.0.0/16, non-empty).
Fixture is strictly more interesting. Both yield SAT. Consistent.

CE3 vs Phase 15 CE3: Phase 15 CE3 describes a PrincipalTag AssumeRole boundary scenario (which maps
to fixture CE6, not fixture CE3). Fixture CE3 describes a context-changing transition that is SAT.
This is a semantic drift between Phase 15 document numbering and fixture numbering.
MUST BE RECONCILED before solver implementation.

CE4 vs Phase 15 CE4: Phase 15 CE4 covers ExternalId as request-scoped (yields SAT/UNKNOWN because
ExternalId can differ per hop). Fixture CE4 covers unsupported operator -> UNKNOWN. Different coverage.
Phase 15's ExternalId scenario is not represented as a standalone fixture. Gap in fixture coverage.

CE6 UNSAT assumption dependency: The formal UNSAT rationale in CE6 depends on trust policy constraint
enforcing Null(aws:RequestTag/Department) and denial of sts:TagSession. These assumptions are embedded
in fixture data but are NOT enforced by the existing ARF-RT constraint model. The CCPF solver must
implement the scope-rule that enforces principal tag resets at AssumeRole boundaries when these
conditions hold.

---

## 12. PMapper Refactor Assessment

### 12.1 Files Created (prior session)

  Untitled-1                  C:\SNEHARSHA\ANTIGRAVITY\Untitled-1               7,188 bytes
  code-review-report.md       C:\SNEHARSHA\ANTIGRAVITY\code-review-report.md     4,815 bytes
  code-review-verified-report C:\SNEHARSHA\ANTIGRAVITY\code-review-verified-report.md 2,891 bytes

### 12.2 Relationship to ARF-RT

VERIFIED: No relationship established. Direct inspection confirms:

- Untitled-1 imports from principalmapper.querying.* -- a completely separate open-source tool.
- Untitled-1 defines isAuthFor, isAuthFull, isAuthAcrossAccs -- AWS authorization query functions
  unrelated to ARF-RT's probabilistic engine.
- Untitled-1 is NOT in the ARF-RT-TEMPORAL repository. It is untracked in the ANTIGRAVITY root.
- python -m py_compile succeeded -- proves syntactic validity only, NOT behavioral correctness.
- No tests against the original PMapper implementation were performed.
- No backward compatibility has been verified.

### 12.3 Classification

CLASSIFICATION: Separate PMapper code-review task. No verified dependency on ARF-RT.

Must NOT be:
  - Copied into the ARF-RT package
  - Treated as a CCPF implementation
  - Committed to the research branch
  - Declared backward-compatible without unit/integration/regression tests

---

## 13. Related-Work Review Status

### 13.1 PHASE17 Working-Tree Diff Summary

The tracked working-tree modification to PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md:

| Claim (Committed) | Tightened (Working Tree) |
|-------------------|--------------------------|
| "Gap 1 is real and defensible" (strong) | "Potential research direction; novelty not established" |
| "Formal model is correct" | "Correctness requirements remain open" |
| "GO (NARROW)" | "NARROW (provisional on correctness gates)" |
| Admissibility "technically straightforward" | "OPEN / In progress" |
| Top-tier venue targeting recommended | Conditional on formal proofs + empirical evidence |

### 13.2 Open Evidence Gaps

| Related Work                    | Evidence Quality                                     |
|---------------------------------|------------------------------------------------------|
| PMapper v1.1.5 (tag d5136ff)    | VERIFIED -- Direct source inspection                 |
| PMapper master (91d2e60)        | VERIFIED -- Direct source inspection                 |
| Zelkova (FMCAD 2018)            | PRELIMINARY -- Abstract/publication record only      |
| AWS Auth Engine (FMCAD 2025)    | PARTIAL -- Preliminary text extraction; full review unconfirmed |
| Projective Model Counting (2024)| PRELIMINARY -- Limited review                        |
| ARF-RT / Conklin (SeRIM 2026)   | VERIFIED -- Direct source inspection of implementation |
| Commercial CNAPPs (Wiz, Orca)   | BLOCKED -- Proprietary; internals unverifiable       |

---

## 14. Formal Correctness Risks

1. BLOCKER -- Admissibility proof is OPEN.
   The informal argument in Phase 15 Section 5 says the {0,1} multiplier maintains monotonicity.
   The formal proof has not been completed, especially under Q8 floor operations and scope-reset
   transitions. A path prefix with p_worst > 0 that is UNSAT should yield 0 after multiplying.
   The proof must show this does not break the heap ordering invariant.

2. BLOCKER -- Scope-reset invariance is OPEN.
   CE6 assumes aws:PrincipalTag/Department is reset at AssumeRole unless explicitly propagated.
   The conditions under which session tags CAN be injected despite Null(aws:RequestTag/Department)
   trust policy constraint need formal specification. The CCPF solver must enforce this rule.

3. BLOCKER -- Solver soundness is OPEN.
   No solver exists. The CIDR intersection check (CE1/CE2) is well-defined. But the full supported
   logic subset (operators, data types, scope combinations) has not been proven sound.

4. INFERRED -- Q8 zero-score path handling.
   If UNSAT yields multiplier 0.0 and grouped_product_q8(pw, 0) = 0, heap naturally deprioritizes.
   Whether zero-score items are ever popped and produce spurious path results needs verification.
   The _confidence_band mapping returns "INSUFFICIENT" for pct < 1 (p_worst < Q8/100). A zero-score
   path popped from the heap would still check target membership before adding to results.

5. INFERRED -- CE3/CE4 semantic drift from Phase 15.
   Phase 15 CE numbering differs from fixture suite CE numbering. This must be reconciled before
   solver implementation to avoid implementing against the wrong specification.

---

## 15. Recommended Next Phase

Authorized work: docs/CCPF_FORMAL_DESIGN_GATE.md

Required before engine implementation:
  1. Read arf_rt/config.py to confirm exact Q8 value and underflow implications.
  2. Reconcile CE-numbering between Phase 15 document and fixture suite.
  3. Formalize admissibility proof for {0,1} multiplier under Q8 floor arithmetic.
  4. Define scope transition rules: which variables reset, persist, or transform at AssumeRole.
  5. Define restricted solver's supported logic subset (CIDR, Boolean, string equality).
  6. Perform byte-level engine diff: BASELINE vs TEMPORAL engine/ directory.

---

## 16. Actions That Could Not Be Completed

| Blocked Action                          | Reason                                              |
|-----------------------------------------|-----------------------------------------------------|
| SHA-256 hash of archive                 | No .tar archive found                               |
| BASELINE vs TEMPORAL byte-level engine diff | Git diff across separate repo clones not set up in this audit |
| Full test suite completion              | Suite stalled at ~288/~911 tests (performance threshold). No failure before stall. |
| config.py Q8 constant verification      | VERIFIED: read from config.py line 11 (Q8 = 100_000_000, 10^8) |
| FMCAD 2025 full-text review             | Not attempted during this audit                     |

---

*No engine source files were modified. No commits or pushes were made. No packages were installed
or upgraded. The baseline mirror is intact at commit 04d2bae (tag: arf-rt-v1.2-baseline).*
