# Contributing to ARF-RT Temporal Context Research

This repository is a research artifact. Contributions follow a strict research-engineering
discipline to maintain scientific reproducibility.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable documentation and verification mirror |
| `temporal-context-dev` | Active research workspace |

## Pre-Contribution Requirements

Before any code contribution to `arf_rt/`:

1. Run the full baseline verification campaign using `verification/run_full_suites.py`
2. Confirm Gate B status (911/912 tests pass; sole failure is host-performance only)
3. Obtain explicit researcher authorization
4. Document all changes in `docs/` before implementing

## Commit Style

Commits must follow this format:
```
<scope>: <short description>

<body explaining what, why, and evidence>
```

Scopes: `arf_rt`, `docs`, `verification`, `tests`, `research`

## Scientific Integrity Rules

- Do NOT modify `arf_rt/` without a prior formal design document in `docs/`
- Do NOT change test assertions or timing thresholds to make tests pass
- Do NOT commit without running the full test suite first
- All claims in docs must be supported by reproducible log evidence

## Research Contact

Researcher: Sneharsha001
Repository: temporal-context-aware-cloud-identity-attack-paths
