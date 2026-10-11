# Temporal Context-Aware Cloud Identity Attack Paths

> **ARF-RT v1.2** — Attack-path Risk Framework with Reinforcement Training

A research artifact for probabilistic cloud identity attack-path analysis using
temporal context, entropy-guided exploration, and belief-state updates.

## Research Contribution

**Context-Conditioned Path Feasibility (CCPF)**

Extends ARF-RT toward a conference-quality contribution by adding formal feasibility
classification (SAT / UNSAT / UNKNOWN) conditioned on temporal access context, credential
decay curves, and correlated permission graphs in cloud IAM environments.

## Repository Structure

```
arf_rt/          # Core attack-path analysis library (ARF-RT v1.2)
docs/            # Research design, formal models, novelty assessment
verification/    # Pre-contribution baseline audit and test evidence
tests/           # Unit, golden, and stress test suites (912 tests)
```

## Test Status

| Suite | Tests | Status |
|---|---|---|
| Unit | 625 | All passing |
| Golden | 250 | All passing |
| Stress | 37 | 36 passing / 1 host-performance threshold |

## Research Gate

**Current:** GATE B — READY WITH DOCUMENTED BASELINE LIMITATIONS
**Next:** CCPF Implementation (gated — awaiting authorization)

## Key Documents

- [CCPF Formal Design Gate](docs/CCPF_FORMAL_DESIGN_GATE.md)
- [Phase 17 Novelty Assessment](docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md)
- [Evidence Closeout Report](verification/EVIDENCE_CLOSEOUT_REPORT.md)
- [Research Status](RESEARCH_STATUS.md)
