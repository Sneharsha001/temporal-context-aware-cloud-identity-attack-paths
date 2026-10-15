# Contributing to ARF-RT

Welcome to ARF-RT! This repository is a scientific research and engineering platform for Bayesian reasoning on cloud identity attack paths.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready codebase, verified documentation, and release baseline |
| `temporal-context-dev` | Active research workspace and experimental stage implementations |

## Pre-Contribution Checklist

Before submitting a Pull Request or pushing changes:
1. Ensure your Python environment is version 3.10 or higher.
2. Run the environment health check:
   ```bash
   python scripts/health_check.py
   ```
3. Run the code quality gate:
   ```bash
   python scripts/lint_check.py
   ```
4. Run the fixture validation script:
   ```bash
   python scripts/validate_fixtures.py
   ```
5. Ensure all commits adhere to Conventional Commits:
   - `feat(...)`: New capability or enhancement
   - `docs(...)`: Documentation additions or updates
   - `test(...)`: Test additions or regressions
   - `refactor(...)`: Code refactoring without behavior change
   - `ci(...)`: Automation or CI workflow updates

## Scientific Rigor & Reproducibility
- All performance benchmarks must follow the rules in `docs/BENCHMARK_METHODOLOGY.md`.
- No live cloud credentials or API calls are permitted; ARF-RT operates strictly against deterministic replays.
