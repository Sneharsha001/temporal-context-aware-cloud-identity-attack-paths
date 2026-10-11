# Verification Artifacts — ARF-RT Baseline Audit

This directory contains all machine-collected evidence from the **ARF-RT v1.2 pre-contribution
baseline verification campaign**, conducted prior to starting the CCPF research contribution.

## Campaign Summary

| Item | Value |
|---|---|
| **Audit Date** | 2026-10-11 |
| **Baseline Commit** | `04d2bae12f600ff48b6054aa513878ea5dc72b16` |
| **Research HEAD** | `45ec211e3ca1f284e27e22d5bf4981166bf5880b` |
| **Final Gate** | **GATE B — READY WITH DOCUMENTED BASELINE LIMITATIONS** |
| **CCPF Status** | Gated — awaiting explicit authorization |

## Test Results (Automated Full-Suite Runs)

| Workspace | Passed | Failed | Timed Out | Elapsed |
|---|---|---|---|---|
| BASELINE (04d2bae) | 911 | 1 | No | 368 s |
| TEMPORAL (45ec211) | 911 | 1 | No | 344 s |

**Sole failure (both):** 	ests/stress/test_stage1.py::TestStage1Planner::test_runtime_under_1_second
**Classification:** BASELINE-SHARED / ENVIRONMENT-DEPENDENT / NON-FUNCTIONAL

## Artifact Index

| File | Description |
|---|---|
| check_envs.py | Environment isolation verification script |
| run_full_suites.py | Automated bounded full-suite pytest runner |
| stage_a_git_state.txt | Initial git state for both workspaces |
| stage_b_env_and_deps.txt | Python environment and dependency inventories |
| commit_diff_04d2bae_45ec211.txt | Full git diff — baseline to research HEAD |
| stage_f_focused_tests.txt | Focused test runs — 175 tests x 2 workspaces |
| stage_g_git_comparison.txt | Post-audit git comparison (baseline 100% preserved) |
| full_suite_baseline.log | Full-suite log — BASELINE (1 failed, 911 passed) |
| full_suite_temporal.log | Full-suite log — TEMPORAL (1 failed, 911 passed) |
| execution_summary.json | Machine-readable summary (timestamps, exit codes) |
| FINAL_BASELINE_VERIFICATION_REPORT.md | Narrative gate report (v1.0.0) |
| EVIDENCE_CLOSEOUT_REPORT.md | Definitive closeout — GATE B CONFIRMED |

## Scientific Defensibility

All claims in this directory are supported by reproducible, timestamped, machine-collected
logs. No correctness claims are made beyond what the logs directly demonstrate.
The baseline mirror (ARF-RT-BASELINE) was never modified during this campaign.
