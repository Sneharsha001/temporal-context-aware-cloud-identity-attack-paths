# Changelog

All notable changes to the ARF-RT project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
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
