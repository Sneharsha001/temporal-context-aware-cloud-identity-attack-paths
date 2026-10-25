# Changelog

All notable changes to the ARF-RT project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] — 2026-10-26
### Added
- **`CredentialAlertEngine`** (`arf_rt.temporal.credential_alert_engine`): Evaluates risk scores against configurable threshold rules, emitting deduplicated structured `Alert` events across 4 severity tiers (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **`TemporalDriftDetector`** (`arf_rt.temporal.temporal_drift_detector`): Compares baseline and current snapshots of temporal metadata to detect new credentials, removed access, window shrinkage, and staleness regression.
- **`PolicyWindowValidator`** (`arf_rt.temporal.policy_window_validator`): Enforces organizational credential lifetime constraints, validating session durations, rotation intervals, and TTL thresholds.
- **`CoverageReporter`** (`arf_rt.temporal.coverage_reporter`): Quantifies temporal metadata coverage across privilege graphs with per-field statistics and gap reporting.
- **`TemporalDashboard`** (`arf_rt.temporal.temporal_dashboard`): Synthesizes scoring, alerts, policy validation, coverage, and drift into a formatted multi-section ASCII console dashboard.
- **`TemporalHint.to_dict` / `from_dict`** (`arf_rt.temporal.hints`): Roundtrip dictionary and ISO string serialization for temporal hints.
- **`scripts/validate_policy_windows.py`**: CLI tool for credential TTL, session duration, and rotation compliance enforcement.
- **`scripts/detect_temporal_drift.py`**: CLI tool for snapshot-based credential window drift detection.
- **`scripts/report_temporal_coverage.py`**: CLI tool for analyzing temporal metadata coverage across graph scenarios.
- **`scripts/run_temporal_dashboard.py`**: CLI tool for unified terminal security dashboard generation.
### Tests
- Added 120+ unit and CLI integration tests across the new analytical components. Full test suite now passes with **443 tests**.

## [0.6.0] — 2026-10-24
### Added
- **`TemporalGraphAnnotator`** (`arf_rt.temporal.graph_annotator`): Decorates privilege-graph edges with expiry windows, staleness flags, and Graphviz styling attributes.
- **`PathFeasibilityPruner`** (`arf_rt.temporal.pruner`): Early search-expansion pruner that discards graph branches violating temporal constraints before full evaluation.
- **`SessionRevocationSimulator`** (`arf_rt.temporal.revocation_simulator`): Computes blast-radius impact for credential revocation events, counting affected and eliminated attack paths.
- **`CloudTrailSyntheticGenerator`** (`arf_rt.temporal.synthetic_generator`): Generates realistic AWS CloudTrail benchmark logs with configurable anomaly injection for stress-testing.
- **`TemporalVerdictCache`** (`arf_rt.util.temporal_cache`): Bounded LRU memoization cache for path feasibility verdicts with hit/miss/eviction metrics.
- **`CredentialScorer`** (`arf_rt.temporal.credential_scorer`): Risk-scores credential edges 0–1 using TTL expiry, rotation staleness, and churn factors with configurable weights and tier labelling (MINIMAL → CRITICAL).
- **`TemporalExporter`** (`arf_rt.temporal.temporal_exporter`): Multi-format serialiser for `TemporalHint` and `CredentialRiskScore` collections (JSON, NDJSON, CSV, combined summary).
- **`scripts/score_credentials.py`**: CLI wrapping `CredentialScorer` + `TemporalExporter`; reads CloudTrail logs, scores all credential edges, outputs table/JSON/NDJSON/CSV with top-N filtering.
- **`scripts/simulate_revocation.py`**: CLI for interactive revocation blast-radius evaluation.
- **`scripts/generate_synthetic_cloudtrail.py`**: CLI for benchmark data generation and pipeline stress testing.
### Tests
- Unit tests for all six new modules (graph annotator, pruner, revocation simulator, synthetic generator, verdict cache, credential scorer, temporal exporter): **117 tests added**.

### Added
- **Temporal Context Module** (`arf_rt.temporal`) — time-aware path feasibility post-filter:
  - `TemporalHint` frozen dataclass carrying per-edge CloudTrail timestamp metadata.
  - `TemporalConfig` with `strict()` and `permissive()` factory presets.
  - `TemporalVerdict` / `VerdictKind` with FEASIBLE / INFEASIBLE / UNKNOWN outcomes.
  - `TemporalEvaluator` implementing TC-1 (Causal Order), TC-2 (Session Validity),
    TC-3 (Minimum Velocity), TC-4 (Stale Credential), TC-5 (Concurrent Session).
  - `TemporalPathFilter` wrapping evaluator and window analyzer into high-level filter API.
  - `TemporalAuditLog` structured decision logging with JSONL persistence and verdict filtering.
  - `TemporalMetrics` elimination rate collector, constraint violation tallies, and path histograms.
  - `TemporalSummaryReporter` executive summary and detailed constraint breakdown formatter.
  - `CredentialTimelineBuilder` chronological event extractor and ASCII Gantt chart generator.
  - `AnomalyClassifier` mapping temporal violations and window findings to standardized severity tiers (CRITICAL, HIGH, MEDIUM, LOW).
  - `PathFeasibilityBatchRunner` executing multi-scenario feasibility batches with ranking tables.
  - `scenario_enricher` bridging edge IDs to CloudTrail `TemporalHint` metadata with coverage reporting.
  - `cloudtrail_parser` — extracts `TemporalHint` objects from raw AssumeRole events.
  - `window_analyzer` — detects impossible concurrency, burst patterns, and cross-account reuse.
  - `sts_metadata` — `SessionSpec` and causal session-chain validation helpers.
  - `export` module — exports metrics and audit logs to CSV, JSON, and Markdown summary tables.
- **Statistical Utilities** (`arf_rt.util.temporal_stats`):
  - Inter-arrival time calculations, duration statistics, and z-score timing outlier detection.
- **CLI Tools**:
  - `scripts/visualize_path_timeline.py` — CLI for ASCII Gantt and chronological event visualization.
  - `scripts/run_temporal_diagnostics.py` — Operational diagnostic and health verification suite.
  - `scripts/filter_paths_temporal.py` — CLI for batch candidate path feasibility filtering.
  - `scripts/temporal_report.py` — CLI generating Markdown audit reports from JSONL logs.
  - `scripts/analyze_cloudtrail.py` — CLI for temporal anomaly detection in CloudTrail exports.
- **Documentation**:
  - `docs/TEMPORAL_ANOMALY_GUIDE.md` — Anomaly classification matrix and incident response playbooks.
  - `docs/CREDENTIAL_LIFECYCLE_ANALYSIS.md` — Mathematical chaining bounds and timeline reconstruction.
  - `docs/CCPF_NOVELTY_ASSESSMENT_REPORT.md` — Literature review and empirical novelty evaluation.
  - `docs/CCPF_D2_BENCHMARK_PRE_REGISTRATION.md` — D2 enterprise-scale benchmark pre-registration protocol.
  - `docs/TEMPORAL_CONTEXT_DESIGN.md` — Constraint model, integration design, and proof obligations.
  - `docs/TEMPORAL_CONTEXT_FAQ.md` — Operational Q&A for configuration and CloudTrail integration.
  - `docs/TEMPORAL_RESEARCH_STATUS.md` — Per-component implementation and test coverage tracker.
- **Automated Tests**: 226+ comprehensive tests spanning unit, golden, and end-to-end integration suites.
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
