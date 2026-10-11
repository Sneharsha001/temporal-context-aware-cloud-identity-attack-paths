# Verification Artifacts Index

Pre-contribution reproducibility audit for ARF-RT v1.2 — completed 2026-10-11.

## Files

| File | Description |
|---|---|
| `FINAL_BASELINE_VERIFICATION_REPORT.md` | Full narrative audit with environment setup, test breakdown, failure classification, and Gate B determination |
| `EVIDENCE_CLOSEOUT_REPORT.md` | Machine-confirmed final closeout resolving all pre-contribution evidence gaps |
| `execution_summary.json` | Structured JSON record of automated full-suite run (both workspaces, 912 tests each) |
| `run_full_suites.py` | Reproducible automation script used to generate the evidence logs |

## Gate Determination

**GATE B — READY WITH DOCUMENTED BASELINE LIMITATIONS**

| Item | Value |
|---|---|
| Baseline commit | 04d2bae12f600ff48b6054aa513878ea5dc72b16 |
| Research HEAD | 45ec211e3ca1f284e27e22d5bf4981166bf5880b |
| Test parity | 911/912 passed (identical in both workspaces) |
| Source diff | Zero `arf_rt/` changes between baseline and research workspace |
| Research regressions | 0 |
| Sole failure | `test_runtime_under_1_second` — BASELINE-SHARED / host performance |

## Reproducibility

To re-run the audit:
```bash
cd C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL
python verification/run_full_suites.py
```
