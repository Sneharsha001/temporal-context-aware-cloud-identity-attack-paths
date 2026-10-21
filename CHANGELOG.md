# Changelog

All notable changes to the ARF-RT project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **Temporal Context Module** (`arf_rt.temporal`) — time-aware path feasibility post-filter:
  - `TemporalHint` frozen dataclass carrying per-edge CloudTrail timestamp metadata.
  - `TemporalConfig` with `strict()` and `permissive()` factory presets.
  - `TemporalVerdict` / `VerdictKind` with FEASIBLE / INFEASIBLE / UNKNOWN outcomes.
  - `TemporalEvaluator` implementing TC-1 (Causal Order), TC-2 (Session Validity),
    TC-3 (Minimum Velocity), TC-4 (Stale Credential), TC-5 (Concurrent Session).
  - `cloudtrail_parser` — extracts `TemporalHint` objects from raw AssumeRole events.
  - `window_analyzer` — detects impossible concurrency, burst patterns, and cross-account reuse.
  - `sts_metadata` — `SessionSpec` and causal session-chain validation helpers.
- **134 new tests**: 126 unit tests + 8 golden tests locking evaluator verdicts.
- `scripts/analyze_cloudtrail.py` — CLI for temporal anomaly detection in CloudTrail exports.
- `docs/TEMPORAL_CONTEXT_DESIGN.md` — constraint model, integration design, and proof obligations.
- `docs/TEMPORAL_CONTEXT_FAQ.md` — operational Q&A for configuration and CloudTrail integration.
- `docs/TEMPORAL_RESEARCH_STATUS.md` — per-component implementation and test coverage tracker.
- Utility module `arf_rt.util` with `retry`, `text`, and `structures` helpers.
- Unified test runner `scripts/run_tests.py` with multi-suite selection and coverage reporting.
- Performance benchmark harness `scripts/benchmark.py` with p95/p99 tracking.
- Static quality gate `scripts/lint_check.py` wrapping ruff, mypy, and bandit.
- Artifact report generator `scripts/generate_report.py`.
- Fixture schema validator `scripts/validate_fixtures.py`.
- Path-level integration design specification (`docs/CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md`).


## [1.0.0-prompt5a] - 2026-10-14
### Added
- Remediated 6 confirmed correctness defects (F1-F6) in RDCE constraint evaluator.
- Stage E counterexample regression test suite (128/128 research tests passing).
- Independent code review sign-off and verification checklist.

## [1.0.0-prompt4] - 2026-10-10
### Added
- Semantic validation test suite with 60 comprehensive scenarios across 10 failure modes.

## [1.0.0-prompt3] - 2026-10-08
### Added
- Initial Relational Deterministic Constraint Evaluator (RDCE) isolated implementation.
- 46 core acceptance tests verifying context constraint parsing and satisfaction.
