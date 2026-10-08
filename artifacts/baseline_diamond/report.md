# ARF-RT Analysis Report

## Summary

| Metric | Count |
|--------|-------|
| Nodes | 4 |
| Edges | 4 |
| Constraints | 1 |
| Objectives | 1 |
| Observations | 5 |

## Objective: REACHABILITY

**From:** A
**To:** D
**Max depth:** 4, **K:** 5

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | VERY_LOW | 2 | — |
| 2 | VERY_LOW | 2 | — |

**Path 1** (VERY_LOW):
  1. A →[sts:AssumeRole]→ B (REFUTED)
  2. B →[sts:AssumeRole]→ D (CONFIRMED)

**Path 2** (VERY_LOW):
  1. A →[sts:AssumeRole]→ C (CONFIRMED)
  2. C →[sts:AssumeRole]→ D (REFUTED)


## Evidence Coverage

**4** of **4** edges observed with DIRECT/DETERMINISTIC non-counterfactual evidence (**100%**).

## Constraint Validation

| Status | Count |
|--------|-------|
| VALIDATED | 1 |
