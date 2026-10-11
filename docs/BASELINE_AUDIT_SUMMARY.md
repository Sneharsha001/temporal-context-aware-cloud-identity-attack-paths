# Baseline Audit Summary

## ARF-RT v1.2 Pre-Contribution Reproducibility Audit

**Date:** 2026-10-11
**Gate:** GATE B — READY WITH DOCUMENTED BASELINE LIMITATIONS

---

## What Was Verified

### 1. Repository Provenance
- Baseline mirror: commit `04d2bae` — `Initialize original ARF-RT v1.2 baseline`
- Research workspace: commit `45ec211` — 5 commits ahead, docs-only delta
- Full `git diff` confirms: zero `arf_rt/` source changes between the two commits

### 2. Environment Isolation
- Both workspaces use dedicated, independent virtual environments (Python 3.12.10)
- `arf_rt` package imports confirmed to resolve to the correct workspace in each
- Zero cross-contamination between baseline and research installations

### 3. Full-Suite Automated Test Results

| Workspace | Passed | Failed | Timed Out | Wall-Clock |
|---|---|---|---|---|
| BASELINE (04d2bae) | 911 | 1 | No | 368 s |
| TEMPORAL (45ec211) | 911 | 1 | No | 344 s |

**Sole failure:** `tests/stress/test_stage1.py::TestStage1Planner::test_runtime_under_1_second`
- BASELINE: `assert 1687.0 < 1000` (FAIL)
- TEMPORAL: `assert 1562.0 < 1000` (FAIL)
- **Classification:** BASELINE-SHARED / ENVIRONMENT-DEPENDENT / NON-FUNCTIONAL

### 4. Focused Test Results (175 tests)
- All 175 focused tests pass in both workspaces (exit code 0, 100% bitwise parity)
- Covers: `test_paths`, `test_canon`, `test_determinism`, `test_golden_topk`,
  `test_decay`, `test_correlation`, `test_planner`, `test_recovered_paper_artifacts`

---

## Conclusion

The ARF-RT v1.2 baseline is reproducible and correctly characterized.
The research workspace introduces zero regressions.
The CCPF contribution phase may begin upon explicit authorization.

**Full evidence:** `verification/EVIDENCE_CLOSEOUT_REPORT.md`
