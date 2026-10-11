# CCPF — Context-Conditioned Path Feasibility

## Overview

**Context-Conditioned Path Feasibility (CCPF)** is the proposed research contribution
extending ARF-RT v1.2 toward a conference-quality paper.

## Problem Statement

Existing probabilistic attack-path frameworks (including ARF-RT) enumerate paths and
compute risk scores, but do not classify whether a given attack path is *feasible*
under a specific temporal access context.

A path may be highly ranked by EIG (Entropy-based Information Gain) yet infeasible
because:
- Required credentials have expired (decay curve crossed threshold)
- Correlated permissions were revoked after a prior step was detected
- Temporal access windows were closed by IAM policy rotation

## Proposed Contribution

CCPF adds a feasibility classification layer on top of the existing ARF-RT planner:

| Classification | Meaning |
|---|---|
| SAT | Path is feasible under the current temporal context |
| UNSAT | Path is infeasible — a hard temporal/permission constraint is violated |
| UNKNOWN | Feasibility cannot be determined with current evidence |

## Formal Basis

See `docs/CCPF_FORMAL_DESIGN_GATE.md` (on `temporal-context-dev`) for the complete
formal model including transition definitions, logical consistency review, and
correctness audit.

## Status

**Gated** — formal design complete, baseline verified, implementation not yet started.
Awaiting explicit researcher authorization to begin Phase C (implementation).

## Relationship to ARF-RT

CCPF will be implemented as an **isolated, additive module** that:
- Does NOT modify the EIG computation path
- Does NOT change existing tests or timing thresholds
- Adds a new `arf_rt/ccpf/` sub-package
- Is evaluated against the existing 912-test suite with zero regressions required
