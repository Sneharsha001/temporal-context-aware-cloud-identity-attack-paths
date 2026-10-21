# Temporal Context Module — Research Status

**Last Updated:** 2026-10-21  
**Branch:** `temporal-context-dev` (development), `main` (stable artifacts)  
**Research Phase:** Active — Prompt 10 infrastructure

---

## Summary

The temporal context module introduces time-aware path feasibility checking
as a post-filter layer after the CCPF logical evaluator. This document tracks
the implementation status, test coverage, and outstanding research questions.

---

## Implementation Status

| Component | File | Status | Tests |
|---|---|---|---|
| `TemporalHint` dataclass | `arf_rt/temporal/hints.py` | ✅ Complete | 20 unit tests |
| `TemporalConfig` dataclass | `arf_rt/temporal/config.py` | ✅ Complete | 14 unit tests |
| `TemporalVerdict` + `VerdictKind` | `arf_rt/temporal/verdict.py` | ✅ Complete | 18 unit tests |
| `TemporalEvaluator` (TC-1…TC-5) | `arf_rt/temporal/evaluator.py` | ✅ Complete | 28 unit tests |
| CloudTrail event parser | `arf_rt/temporal/cloudtrail_parser.py` | ✅ Complete | 14 unit tests |
| Window analyzer | `arf_rt/temporal/window_analyzer.py` | ✅ Complete | 12 unit tests |
| STS metadata helpers | `arf_rt/temporal/sts_metadata.py` | ✅ Complete | 20 unit tests |
| Golden test suite | `tests/golden/test_temporal_golden.py` | ✅ Complete | 8 golden tests |
| analyze_cloudtrail CLI | `scripts/analyze_cloudtrail.py` | ✅ Complete | — |
| CCPF integration bridge | `arf_rt/temporal/ccpf_bridge.py` | 🔲 Planned | — |
| Temporal reporting | `arf_rt/reporting/temporal_report.py` | 🔲 Planned | — |

**Total temporal tests (committed to main):** 134 unit/golden

---

## Constraint Coverage

| Constraint | Implemented | Unit Tested | Golden Tested |
|---|---|---|---|
| TC-1 Causal Order | ✅ | ✅ | ✅ |
| TC-2 Session Validity | ✅ | ✅ | ✅ |
| TC-3 Minimum Velocity | ✅ | ✅ | ✅ |
| TC-4 Stale Credential | ✅ | ✅ | ✅ |
| TC-5 Concurrent Session | ✅ | ✅ | ✅ |

---

## Open Research Questions

1. **Timestamp Availability:** What fraction of real-world CloudTrail logs have
   sufficient timestamps for all five constraints? (Currently untested on real data.)

2. **Optimal δ_min (TC-3):** Is 0.5s the right bot-detection threshold? Needs
   empirical calibration against known automated attack tool latency data.

3. **Clock Skew Bounds:** AWS documentation suggests up to ±30s clock skew
   across accounts. Is the current 30s grace window (TC-2) sufficient?

4. **Integration with Bayesian Scorer:** The current design treats temporal
   evaluation as a binary gate (FEASIBLE/INFEASIBLE). A richer model could
   reduce edge probability as a function of temporal evidence quality.

5. **Retroactive Path Finding:** If a path was feasible at time T but
   credentials have since expired, should it still appear in the Top-K results
   as a "historical" finding?

---

## Next Steps (Prompt 10+)

- [ ] Implement `ccpf_bridge.py` to wire temporal evaluator into the existing
      `PathContextTracker` interface.
- [ ] Add `TemporalVerdictRecord` to the SQLite schema for auditability.
- [ ] Run evaluator on real CloudTrail exports from the test fixture and
      measure false-positive reduction relative to CCPF-only baseline.
- [ ] Write `docs/TEMPORAL_EVALUATION_REPORT.md` with empirical results.
- [ ] Integrate temporal constraint violations into the Markdown analysis report.

---

## References

- [Temporal Context Design Specification](docs/TEMPORAL_CONTEXT_DESIGN.md)
- [Temporal Context FAQ](docs/TEMPORAL_CONTEXT_FAQ.md)
- [CCPF Path-Level Integration Design](docs/CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md)
- [CCPF API Reference](docs/CCPF_API_REFERENCE.md)
