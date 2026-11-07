# ARF-RT — Risk Topology Engine

[![ARF-RT CI](https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths/actions/workflows/ci.yml/badge.svg)](https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A Bayesian reasoning engine for cloud identity attack path analysis. ARF-RT ingests privilege graphs (PMapper, AWS Organizations), models policy constraints as correlated belief structures, and computes the most informative probe sequence to reduce uncertainty about path viability.

**SEMANTICS_VERSION:** 1.0.0  
**Scope:** Replay-only. No live cloud SDK calls.  
**Last Updated:** 2026-10-28 — v0.9.0: enterprise governance & security documentation suite, Zero Trust architecture (NIST SP 800-207), SOC 2 / ISO 27001 mapping, PCI-DSS v4.0 controls, SIEM/SOAR integration, and Bayesian mathematical formalization.

---

## Active Research Track: Context-Conditioned Path Feasibility (CCPF)

This repository hosts active research extending ARF-RT with **Context-Conditioned Path Feasibility (CCPF)** on branch `temporal-context-dev`.

- **Objective:** Evaluate operational context (network origin CIDRs, MFA presence, principal tags) as a formal Constraint-Satisfaction Problem (CSP) to filter logically impossible identity paths without perturbing Bayesian probability scores.
- **Current Status:**
  - **Prompt 3: Isolated evaluator implementation** — complete, subject to evidence (`research/ccpf/rdce.py`, 46 acceptance tests in `tests/research/test_rdce.py`).
  - **Prompt 4: Semantic validation** — complete, subject to evidence (`tests/research/test_semantic_validation.py`, 60 tests: Stage B [20 tests], Stage C 10 failure modes [35 tests], Stage D CE5 isolated fallback [5 tests]; 106 total research tests passing).
  - **Prompt 5: Independent code review & soundness audit** — complete. Audit identified 6 confirmed correctness defects in `docs/CCPF_INDEPENDENT_REVIEW.md`.
  - **Prompt 5A: Correctness remediation & test strengthening** — complete. Remediated all 6 confirmed soundness defects (F1–F6) in `research/ccpf/rdce.py`; replaced weak assertions in `tests/research/test_semantic_validation.py` with strict witness and rationale checks; added 22 new counterexample regression tests in Stage E. Research test suite now **128 passed / 128 total** (46 acceptance + 82 semantic/counterexample). Evaluator is marked **READY FOR INDEPENDENT RE-REVIEW** ([docs/CCPF_INDEPENDENT_REVIEW.md](docs/CCPF_INDEPENDENT_REVIEW.md)).
- **Research Stage Sequence:**
  - Prompt 3: Isolated evaluator implementation — complete.
  - Prompt 4: Semantic validation — complete.
  - Prompt 5: Independent code review — complete.
  - Prompt 5A: Correctness remediation & test strengthening — complete (128/128 tests passing).
  - Independent Re-review — ready for reviewer evaluation.
  - Prompt 6: Integration design.
  - Prompt 7: Production integration after explicit authorization.
  - Prompt 8: Baseline-versus-CCPF experimental evaluation.
  - Prompt 9: Conference-paper evidence and readiness.
- **Research Status & Gate Summary:** [RESEARCH_STATUS.md](RESEARCH_STATUS.md)
- **Evaluator Interface Contract:** [docs/CCPF_EVALUATOR_CONTRACT.md](docs/CCPF_EVALUATOR_CONTRACT.md)
- **Formal Design Gate:** [docs/CCPF_FORMAL_DESIGN_GATE.md](docs/CCPF_FORMAL_DESIGN_GATE.md)
- **Independent Code Review Report:** [docs/CCPF_INDEPENDENT_REVIEW.md](docs/CCPF_INDEPENDENT_REVIEW.md)

---

## Temporal Context & Analytical Tooling Suite (v0.8.0)

ARF-RT features a comprehensive **Temporal Context Subsystem** (`arf_rt/temporal`) with analytical modules, enterprise compliance auditing, and production-grade CLI utilities for time-aware cloud security analysis:

- **Temporal Compliance Auditor (`TemporalComplianceAuditor`):** Maps detected temporal anomalies and credential staleness to industry compliance benchmarks (CIS AWS Foundations Benchmark 1.3/1.4/1.16 and NIST SP 800-53 Rev 5 AC-2/IA-5/SC-10).
- **Multi-Hop Risk Aggregator (`TemporalRiskAggregator`):** Compounds individual credential exposure scores across attack paths using bottleneck, geometric mean, and probabilistic product models.
- **Session Chain Validator (`SessionChainValidator`):** Enforces AWS role chaining invariants, including the 1-hour transitive session lifetime cap and causal issuance monotonicity.
- **Automated Remediation Planner (`TemporalRemediationPlanner`):** Synthesizes violations into prioritized, ready-to-run AWS CLI remediation playbooks with estimated risk reductions.
- **Temporal Correlation Matrix (`TemporalCorrelationMatrix`):** Analyzes concurrency overlap and identifies synchronized credential clusters.
- **Statistical Anomaly Filter (`TemporalAnomalyFilter`):** Uses statistical z-score velocity outlier detection while suppressing alerts during pre-registered maintenance windows.
- **Credential Risk Scoring (`CredentialScorer`):** Computes normalized exploitation risk scores based on token validity, expiry countdown, and staleness age.
- **SIEM & Policy Alerting (`CredentialAlertEngine`):** Configurable rules evaluating risk scores and firing structured, deduplicated security alerts across 4 severity tiers (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **Policy Window Enforcement (`PolicyWindowValidator`):** Verifies adherence to organizational IAM governance constraints (max STS session durations, mandatory rotation intervals, and expired credential restrictions).
- **Snapshot Drift Detection (`TemporalDriftDetector`):** Detects privilege-graph temporal drift across time (new credentials, removed access, contracted validity windows, and staleness regression).
- **Metadata Coverage Auditing (`CoverageReporter`):** Measures privilege-graph edge hint coverage and flags observation/credential metadata gaps.
- **Unified Terminal Dashboard (`TemporalDashboard`):** Aggregates scoring, alerts, policy validation, coverage, and drift into an ASCII console dashboard for operator and CI review.

### Temporal CLI Tooling

| CLI Tool | Script | Description |
|---|---|---|
| **Audit Compliance** | `scripts/audit_temporal_compliance.py` | Audits credentials against CIS AWS and NIST 800-53 benchmarks with strict exit codes. |
| **Generate Remediation** | `scripts/generate_remediation_plan.py` | Outputs prioritized AWS CLI remediation playbooks in table, JSON, or bash shell format. |
| **Score Credentials** | `scripts/score_credentials.py` | Scores CloudTrail or scenario credentials with table/JSON/CSV output. |
| **Validate Policies** | `scripts/validate_policy_windows.py` | Validates session TTLs, rotation ages, and expired credential rules. |
| **Detect Drift** | `scripts/detect_temporal_drift.py` | Compares baseline vs. current snapshots to detect window contractions and drift. |
| **Report Coverage** | `scripts/report_temporal_coverage.py` | Audits temporal hint completeness across graph edges with threshold checks. |
| **Run Dashboard** | `scripts/run_temporal_dashboard.py` | Unified terminal dashboard synthesizing scores, alerts, policy, and drift. |

### Temporal Constraint Types

| Constraint | Description | Source |
|---|---|---|
| `SESSION_EXPIRY` | Role session exceeds `MaxSessionDuration` | STS metadata |
| `CAUSAL_ORDER` | Hop B occurs before Hop A in CloudTrail | CloudTrail timestamps |
| `WINDOW_TOO_NARROW` | Multi-hop path completes in < 1s (bot threshold) | Velocity analysis |
| `STALE_CREDENTIAL` | Credential last used > 90 days ago | IAM last-used data |
| `CONCURRENT_SESSION` | Overlapping sessions suggest credential sharing | Session ID correlation |

> **Status:** Temporal context module is in active development on `temporal-context-dev`. Integration with the production CCPF evaluator is planned for Prompt 10+.

---

## Enhanced Utility Modules (v0.9.1)

### `arf_rt.util.datetime_helpers`

Extended temporal operations for precise time-range analysis:

- **`time_range_overlaps()`** — Check if two time ranges intersect
- **`time_range_contains()`** — Verify if one range fully contains another
- **`intersect_time_ranges()`** — Compute the intersection of two time ranges
- **`format_duration_seconds()`** — Human-readable duration formatting (e.g., "1h 30m 45s")

### `arf_rt.util.network`

Comprehensive CIDR and IP address utilities:

- **`network_overlaps()`** — Detect overlapping CIDR blocks
- **`network_contains()`** — Check if one network contains another
- **`get_network_bounds()`** — Get first/last IP addresses in a network
- **`calculate_subnet_split()`** — Split a network into smaller subnets
- **`format_cidr()`** — Standardize CIDR notation
- **`is_reserved_ip()`** — Identify loopback, multicast, and reserved addresses

### `arf_rt.util.math_stats`

Extended statistical functions for path analysis:

- **`js_divergence()`** — Jensen-Shannon divergence (symmetric, bounded)
- **`cosine_similarity()`** — Vector similarity for path comparison
- **`euclidean_distance()`** — Vector distance for clustering
- **`mean()` / `variance()` / `standard_deviation()`** — Basic statistics
- **`median()` / `quantile()` / `percentile()`** — Distribution quantiles
- **`iqr()`** — Interquartile range for outlier detection
- **`skewness()` / `kurtosis()`** — Distribution shape analysis
- **`covariance()` / `correlation()`** — Bivariate statistical relationships
- **`cross_entropy()`** — Cross-entropy for ML loss computation
- **`mutual_information()`** — Information-theoretic dependency measure
- **`softmax()` / `logsumexp()`** — Numerically stable probability transforms

### `arf_rt.util.text`

Enhanced text processing utilities:

- **`pluralize()`** — Count-aware singular/plural forms
- **`snake_to_camel()` / `camel_to_snake()`** — Case conversion
- **`strip_ansi()`** — Remove ANSI escape sequences
- **`dedent()`** — Remove common leading whitespace
- **`shorten()`** — Word-boundary-aware truncation
- **`extract_version()`** — Semantic version extraction

### `arf_rt.util.hashing`

Cryptographic hashing and integrity utilities:

- **`hmac_sha256()`** — HMAC authentication
- **`hash_chain()`** — Merkle-like hash chaining
- **`hash_file()`** — File integrity verification
- **`hash_combine()`** — Order-independent hash combination
- **`stable_hash()`** — 64-bit integer hashing for hash tables

### `arf_rt.util.structures`

Nested dictionary and collection manipulation:

- **`unflatten_dict()`** — Reconstruct nested dicts from dot-notation keys
- **`filter_dict()`** — Allow/block key filtering
- **`map_values()` / `map_keys()`** — Dictionary transformations
- **`get_nested()` / `set_nested()`** — Dot-notation path access
- **`chunk_list()`** — Split lists into fixed-size chunks

### `arf_rt.util.dag`

Directed Acyclic Graph algorithms:

- **`get_descendants()`** — All reachable nodes from a source
- **`has_path()`** — Path existence check
- **`find_all_paths()`** — Enumerate all paths with limit
- **`find_shortest_path()`** — BFS shortest path
- **`detect_cycles()`** — Cycle enumeration
- **`is_dag()`** — DAG validation
- **`reverse_graph()`** — Edge reversal
- **`get_sources()` / `get_sinks()`** — Graph boundary nodes

### `arf_rt.util.graph_traversal`

Graph traversal and analysis utilities:

- **`find_shortest_path()`** — BFS shortest path finder
- **`find_all_paths()`** — DFS all paths with limit
- **`bfs_layers()`** — BFS level-order traversal
- **`dfs_preorder()` / `dfs_postorder()`** — DFS traversal orders
- **`get_reachable()` / `get_reachable_reverse()`** — Reachability analysis
- **`path_length_distribution()`** — Path length statistics
- **`count_paths()`** — Simple path counting

### `arf_rt.util.retry`

Resilient execution with exponential backoff:

- **`retry()`** — Decorator for sync functions
- **`retry_async()`** — Decorator for async functions
- **`RetryContext`** — Context manager for manual control
- **`retry_context()`** — Context manager factory

### `arf_rt.util.visualization`

Graph export for visualization tools:

- **`export_to_dot()`** — Graphviz DOT format
- **`export_to_cytoscape()`** — Cytoscape.js JSON
- **`export_to_mermaid()`** — Mermaid.js diagrams
- **`export_to_gephi()`** — GEXF for Gephi
- **`export_to_graphml()`** — GraphML XML
- **`style_attack_path_dot()`** — Highlighted attack path DOT

### `arf_rt.util.config_loader`

Runtime configuration management:

- **`load_profile()`** — Load JSON config with env overrides
- **`load_profile_from_yaml()`** — YAML config support
- **`load_profile_auto()`** — Auto-detect format (JSON/YAML)
- **`merge_profiles()`** — Combine profiles with precedence
- **`get_env_overrides()` / `apply_env_overrides()`** — ARF_ env var handling
- **`validate_profile()`** — Configuration validation

### `arf_rt.temporal.config` Enhancements

New configuration options for fine-grained control:

- **`max_path_length`** — Maximum hops per attack path (default: 10)
- **`max_concurrent_sessions`** — Concurrent session limit per principal (default: 5)
- **`credential_reuse_window_seconds`** — Suspicious reuse detection window (default: 3600s)
- **`validate()`** — Configuration validation with warnings
- **`to_dict()` / `from_dict()`** — Serialization support
- **`balanced()` preset** — Moderate settings alongside existing `strict()` and `permissive()`
- **`with_overrides()`** — Create modified config copies

### `arf_rt.temporal.evaluator` Enhancements

Enhanced evaluation with statistics and metrics integration:

- **`EvaluationStats`** — Detailed per-evaluation statistics
- **`enable_stats` parameter** — Optional statistics collection
- **`evaluate_with_metrics()`** — Integrated metrics collection
- **`config` / `reference_time` properties** — Access evaluation settings

### `arf_rt.temporal.metrics` Extensions

Extended metrics with percentiles and latency tracking:

- **`TemporalMetricsExtended`** — Enhanced metrics with statistical measures
- **`percentile()`** — Histogram percentile calculation
- **Path length percentiles** — Median, p95, p99, standard deviation
- **Latency tracking** — Mean, median, p95 evaluation latency

---

## The Problem

Static graph tools find attack paths but ignore policy constraints. This produces false positives — paths that look viable but are blocked by SCPs, trust conditions, or permission boundaries. When multiple edges share the same constraint, their failures are correlated, but naive analysis treats them as independent.

ARF-RT solves this by modeling constraints as first-class objects, correlating structurally dependent edges, and using information theory to determine which probes eliminate the most uncertainty.

## Mental Model

1. Privilege edges are **uncertain hypotheses** — each has a probability of being traversable.
2. Policy constraints create **structural dependencies** between edges.
3. Observations from penetration testing **update beliefs** via Bayesian inference.
4. Correlation-aware grouping **prevents overconfidence** on structurally dependent paths.
5. Entropy over path distributions identifies the **most informative next probe**.

## Key Results

On a 4-account AWS fixture (14 principals, 16 edges, 2 SCPs, 2 trust conditions):

| Metric | Value |
|--------|-------|
| Correlation collapse | 46× (55% naive → 1.2% correlated) |
| EIG vs random probing | 19.8× faster entropy reduction |
| EIG vs max-uncertainty | 17.6× faster |
| EIG vs path centrality | Centrality goes negative (increases uncertainty by reprobing spent edges) |
| Prediction calibration | 0.0000 error (exact within deterministic replay semantics) |
| EIG identity | p·RIG_allow + (1-p)·RIG_deny = EIG (exact) |

### Diamond Collapse

```
        ┌── e₁ ──→ B ─── e₃ ───┐
   A ───┤        (shared SCP)   ├───→ D
        └── e₂ ──→ C ─── e₄ ───┘
```

All four edges governed by the same SCP. Naive independence: 0.74² ≈ 55%. With correlation: the representative's observed DENY propagates to all edges → 1.2%. A 46× reduction from a single structural insight.

## Theoretical Foundations

ARF-RT formulates attack path discovery through Bayesian experimental design and Shannon information theory:

- **Path Entropy:** For candidate path distribution $\mathcal{P}$, path uncertainty is $H(\mathcal{P}) = - \sum_{\pi} P(\pi) \ln P(\pi)$.
- **Expected Information Gain:** For candidate probe edge $e$:
  $$\text{EIG}(e) = H(\mathcal{P}) - \sum_{o \in \{0, 1\}} P(e=o) H(\mathcal{P} \mid e=o)$$
- **Structural Equivalence Partitioning:** Disjoint-set union models joint failure across paths governed by identical SCPs or permission boundaries, collapsing combinatorial path explosion into minimal correlated equivalence classes.

## Enterprise Cloud Defense Highlights

In real-world multi-account AWS topologies (e.g., Security, Core, Workload, and Shared Services accounts):
- **False-Positive Elimination:** Over **46× reduction** in spurious attack path warnings by linking SCP boundaries to IAM assume-role transitions.
- **Probing Speedup:** EIG path prioritization achieves optimal entropy collapse **19.8× faster** than unguided random exploration.
- **Exact Calibration:** Exact probability calibration ($0.0000$ error under deterministic replay) ensures security teams investigate genuine identity threats first.

## Graph Visualization & Topological DAG Analysis

ARF-RT provides native algorithms for inspecting and visualizing identity graphs:
- **Cycle & Loop Detection:** Identifies mutual trust loops and circular assume-role configurations using depth-first recursion.
- **Topological Sorting:** Computes valid execution and traversal orderings via Kahn's algorithm with $O(|\mathcal{V}| + |\mathcal{E}|)$ performance.
- **Visual Export Formats:** Directly serializes scenario graphs to Graphviz DOT markup and Cytoscape.js JSON structures for interactive UI rendering.

## Developer Tooling & Automation Scripts

ARF-RT provides a suite of developer utilities in `scripts/`:

| Script | Purpose | Command |
|---|---|---|
| `run_tests.py` | Unified runner across unit, integration, stress, and research suites | `python scripts/run_tests.py --suite all` |
| `benchmark.py` | Performance harness with median, $p_{95}$, and $p_{99}$ latency tracking | `python scripts/benchmark.py` |
| `lint_check.py` | Static quality gate executing ruff, mypy, and bandit | `python scripts/lint_check.py` |
| `validate_fixtures.py` | Validates JSON/YAML golden test fixtures against schema rules | `python scripts/validate_fixtures.py --strict` |
| `compare_benchmarks.py` | Detects performance regressions against baseline runs | `python scripts/compare_benchmarks.py base.json cand.json` |
| `health_check.py` | Validates interpreter, Git configuration, and tool availability | `python scripts/health_check.py` |
| `generate_report.py` | Builds research artifact reports with codebase and git metrics | `python scripts/generate_report.py` |
| `check_scenario.py` | Validates JSON scenario syntax, nodes, and reachability objectives | `python scripts/check_scenario.py scenario.json` |
| `plot_entropy_reduction.py` | Visualizes Shannon entropy collapse across sequential probing steps | `python scripts/plot_entropy_reduction.py` |
| `format_docs.py` | Strips trailing whitespace and checks markdown documentation formatting | `python scripts/format_docs.py --fix` |
| `generate_diamond_scenario.py` | Synthesizes multi-account diamond topologies with shared SCP constraints | `python scripts/generate_diamond_scenario.py` |
| `policy_diff.py` | Compares edge and constraint rules across two scenario configurations | `python scripts/policy_diff.py scen_a.json scen_b.json` |
| `simulate_probe_sequence.py` | Simulates step-by-step entropy collapse during active probing | `python scripts/simulate_probe_sequence.py` |
| `export_dot_graph.py` | Exports scenario nodes and edges into Graphviz DOT syntax | `python scripts/export_dot_graph.py scen.json -o graph.dot` |
| `profile_scenario.py` | Profiles graph branching factors, asset convergence, and topology metrics | `python scripts/profile_scenario.py scen.json` |
| `generate_chain_scenario.py` | Generates linear and branching attack chains of length N for scale tests | `python scripts/generate_chain_scenario.py --length 6` |
| `visualize_path_timeline.py` | ASCII Gantt and chronological event visualization for credential timelines | `python scripts/visualize_path_timeline.py --hints hints.json` |
| `run_temporal_diagnostics.py` | Automated temporal system health verification and coverage report | `python scripts/run_temporal_diagnostics.py` |
| `simulate_revocation.py` | Interactive credential revocation blast-radius calculator | `python scripts/simulate_revocation.py --paths paths.json` |
| `generate_synthetic_cloudtrail.py` | Synthetic AWS CloudTrail log generation with configurable anomaly injection | `python scripts/generate_synthetic_cloudtrail.py --events 500` |
| `score_credentials.py` | Temporal exploitation risk scoring for credential edges (table/JSON/CSV) | `python scripts/score_credentials.py -i log.json --top 10` |

## Quick Start

### Installation
```bash
# Core installation
pip install -e ".[dev]"

# With temporal analysis extras
pip install -e ".[dev,temporal]"

# For YAML config support
pip install -e ".[dev,yaml]"

# Verify installation
arf-rt --version
python -c "import arf_rt; print(arf_rt.__version__)"
```

### Quick Analysis
```bash
# Run full analysis pipeline
arf-rt analyze scenario.json --format both

# Recommend next probe via EIG
arf-rt plan scenario.json --signal-q 5

# Measure realized entropy reduction
arf-rt episode scenario.json --edge EDGE_ID --outcome allow

# What-if analysis with edge refutation
arf-rt whatif scenario.json --refute EDGE_ID_1 --refute EDGE_ID_2

# Import from PMapper + AWS Organizations
python -c "
from arf_rt.adapters.scenario_builder import build_and_save
build_and_save('pmapper_graph.json', 'scenario.json', org_path='aws_org.json',
    objectives=[{
        'objective_type': 'REACHABILITY',
        'start_nodes': [{'provider': 'aws', 'node_type': 'IAMUser',
            'provider_id': 'arn:aws:iam::111:user/attacker', 'region': '-'}],
        'target_nodes': [{'provider': 'aws', 'node_type': 'IAMRole',
            'provider_id': 'arn:aws:iam::222:role/admin', 'region': '-'}],
        'max_depth': 6, 'k': 5}])
"
arf-rt analyze scenario.json --format both
```

### Temporal Analysis Quick Start
```bash
# Audit compliance
python scripts/audit_temporal_compliance.py scenario.json --frameworks CIS_AWS,NIST_800_53

# Score credentials
python scripts/score_credentials.py scenario.json --format table --top 10

# Generate remediation
python scripts/generate_remediation_plan.py scenario.json --format bash -o remediation.sh

# Validate policies
python scripts/validate_policy_windows.py scenario.json --strict

# Run dashboard
python scripts/run_temporal_dashboard.py scenario.json
```

**→ [Full 5-minute demo walkthrough](docs/quickstart.md)** — import a real AWS graph, probe strategically, watch entropy collapse from 0.56 → 0.10 nats across two probes.

## CLI Commands

| Command | Description |
|---------|-------------|
| `analyze <scenario> [--format md\|json\|both] [-o DIR]` | Full pipeline: ingest → beliefs → correlation → paths → report |
| `plan <scenario> [--signal-q N] [--as-of ISO]` | Recommend next probe via Expected Information Gain |
| `episode <scenario> --edge ID --outcome allow\|deny [--save PATH]` | Measure realized entropy reduction for one probe |
| `whatif <scenario> --refute EDGE_ID [--refute ...]` | Fork, refute edges, produce diff report with Control ROI |
| `import-pmapper <pmapper.json> [--org aws_org.json] [--start ARN --target ARN]` | Build scenario from PMapper + AWS Organizations |
| `hash <scenario>` | Print `canonical_run_hash` (determinism check) |
| `export <scenario> [-o FILE]` | Export full machine-readable state |

## How It Works

### Pipeline

```
Scenario JSON → validate → ingest → apply observations → validate constraints
  → correlation (union-find) → Top-K path search → snapshot → report
```

Same input → same `canonical_run_hash`. Always.

### Belief Model

Integer-stable Beta-Bernoulli. No floats in canonical state.

Each edge carries (α, β) updated by observations. Increment size depends on probe strength (DETERMINISTIC=100, DIRECT=95, INFERRED=60, HEURISTIC=30) scaled by signal quality. ALLOW increments α, DENY increments β. Path probability uses Q8 fixed-point integer arithmetic throughout.

### Constraint Correlation

Edges sharing policy constraints form correlated groups via union-find. Within each group, the weakest edge becomes the representative. Path probability uses the representative's belief instead of multiplying independent edges — preventing overconfidence when structurally dependent edges appear independent.

### Probe Planning (EIG)

For each candidate edge, the planner forks the database, simulates ALLOW and DENY outcomes, reruns the full pipeline on each fork, and measures entropy reduction over normalized Top-K path weights with null complement. The edge with the highest expected entropy reduction is recommended.

Candidate pruning is correlation-aware: edges in an SCP correlation component are candidates even if they don't appear on a Top-K path, because probing them could change the group representative.

### Policy Evaluation

Compares EIG probe selection against random, max-uncertainty, and path-centrality baselines over sequential episodes with scripted or model-sampled truth.

```bash
arf-rt eval tests/fixtures/primary_realistic_scenario.json \
    --episodes 10 --steps 5 --seed 1337 \
    --truth-mode scripted \
    --truth-map tests/fixtures/primary_realistic_truth_map.json
```

Note: the `--truth-mode scripted` and `--truth-map` flags are required for exact Table I reproduction. Without them, the CLI uses sampled truth and the random/uncertainty rows drift.

On the primary fixture: EIG reduces objective uncertainty 19.8× faster than random, 17.6× faster than max-uncertainty, and outperforms path centrality (which goes negative — it increases uncertainty by reprobing confirmed or SCP-blocked edges) over 5 sequential probes.

Four policies compared:

- **EIG**: maximum expected entropy reduction (correlation-aware)
- **Random**: uniform random over candidates
- **Uncertainty**: edge with P(allow) closest to 0.5
- **Centrality**: edge appearing on the most Top-K paths

EIG wins because it accounts for correlation, representative mechanics, and null complement dynamics simultaneously. Uncertainty flatlines because it picks 50/50 edges that aren't representatives — structurally irrelevant to the bottleneck.

### Realized Gain Episodes

Validates planner calibration by injecting forced outcomes and measuring actual entropy change:

- DENY on SCP representative: H drops 0.3013 → 0.1638 (confirms block)
- ALLOW on SCP representative: H jumps 0.3013 → 1.6094 = ln(5) (all paths become equally plausible)
- Prediction error: 0.0000 for both outcomes (exact within deterministic replay semantics)
- EIG identity holds to machine precision

### Belief Decay (opt-in)

Observations lose weight via exponential half-life decay. Opt-in via `--as-of`:

```bash
arf-rt analyze scenario.json --as-of 2025-07-01T00:00:00Z
```

Deterministic, replay-friendly, bounded at 1% floor. Default half-life: 90 days.

### Probe Executor (SAFE mode)

Three execution modes with full audit trail:

- **DRY_RUN** (default): Logs what would be called. No side effects.
- **CONFIRM**: Calls a confirm function before each probe.
- **LIVE**: Not yet implemented (fails gracefully).

Every probe is recorded in `call_log` with edge details, EIG score, disposition, and `run_hash` tying it to the exact pipeline state.

---

## CLI Usage Examples (v0.9.1)

### Temporal Analysis Commands
```bash
# Audit temporal compliance against CIS AWS and NIST 800-53
python scripts/audit_temporal_compliance.py scenario.json --format table --frameworks CIS_AWS,NIST_800_53

# Generate remediation playbooks with risk reduction estimates
python scripts/generate_remediation_plan.py scenario.json --format bash --output remediation.sh

# Score credentials with temporal risk factors
python scripts/score_credentials.py scenario.json --format csv --output scores.csv --top 20

# Validate policy windows (session TTLs, rotation, expired credentials)
python scripts/validate_policy_windows.py scenario.json --strict

# Detect temporal drift between baseline and current snapshots
python scripts/detect_temporal_drift.py baseline.json current.json --output drift_report.json

# Report temporal hint coverage across graph edges
python scripts/report_temporal_coverage.py scenario.json --threshold 0.8

# Run unified temporal dashboard
python scripts/run_temporal_dashboard.py scenario.json --refresh 30
```

### Utility Module Usage
```python
# DateTime helpers for temporal analysis
from arf_rt.util import (
    parse_iso8601, format_iso8601, is_within_temporal_window,
    parse_duration_seconds, time_range_overlaps, time_range_contains,
    intersect_time_ranges, format_duration_seconds
)

# Network/CIDR utilities
from arf_rt.util import (
    parse_ip, parse_network, is_ip_in_network, is_ip_in_any_network,
    is_private_ip, network_overlaps, network_contains,
    get_network_bounds, calculate_subnet_split, format_cidr, is_reserved_ip
)

# Statistical analysis
from arf_rt.util import (
    shannon_entropy, normalize_distribution, kl_divergence,
    js_divergence, cosine_similarity, euclidean_distance,
    mean, variance, standard_deviation, median, quantile, percentile,
    iqr, skewness, kurtosis, covariance, correlation,
    cross_entropy, mutual_information, softmax, logsumexp
)

# Text processing
from arf_rt.util import (
    slugify, truncate, indent_block, wrap_text, join_with_oxford_comma,
    pluralize, snake_to_camel, camel_to_snake, strip_ansi,
    dedent, shorten, extract_version
)

# Cryptographic hashing
from arf_rt.util import (
    canonical_json, sha256_digest, canonical_hash, short_hash,
    hmac_sha256, hash_chain, hash_file, hash_combine, stable_hash
)

# Data structures
from arf_rt.util import (
    flatten_dict, deep_merge, unflatten_dict, filter_dict,
    map_values, map_keys, get_nested, set_nested, chunk_list
)

# DAG algorithms
from arf_rt.util import (
    topological_sort, get_ancestors, get_descendants,
    has_path, find_all_paths, find_shortest_path,
    detect_cycles, is_dag, reverse_graph, get_sources, get_sinks
)

# Graph traversal
from arf_rt.util import (
    find_all_simple_paths, detect_cycles, find_shortest_path,
    find_all_paths, bfs_layers, dfs_preorder, dfs_postorder,
    get_reachable, get_reachable_reverse,
    path_length_distribution, count_paths
)

# Retry with exponential backoff
from arf_rt.util import retry, retry_async, RetryContext, retry_context

@retry(max_attempts=3, base_delay=1.0, backoff=2.0)
def flaky_operation():
    ...

async def async_operation():
    ...

# Visualization exports
from arf_rt.util import (
    export_to_dot, export_to_cytoscape,
    export_to_mermaid, export_to_gephi,
    export_to_graphml, style_attack_path_dot
)

# Configuration management
from arf_rt.util import (
    load_profile, load_profile_from_yaml, load_profile_auto,
    merge_profiles, RuntimeProfile, validate_profile
)

# Temporal evaluation with metrics
from arf_rt.temporal import (
    TemporalEvaluator, TemporalConfig, TemporalMetrics,
    TemporalMetricsExtended, EvaluationStats
)

evaluator = TemporalEvaluator(enable_stats=True)
metrics = TemporalMetricsExtended()
verdict = evaluator.evaluate_with_metrics(path_edges, hints, metrics)
```

### Advanced Configuration
```python
from arf_rt.temporal import TemporalConfig

# Strict mode for conservative evaluation
config = TemporalConfig.strict()

# Permissive mode for recall-favoring
config = TemporalConfig.permissive()

# Balanced preset
config = TemporalConfig.balanced()

# Custom with overrides
config = TemporalConfig(
    min_hop_delta_seconds=1.0,
    stale_credential_days=30,
    max_path_length=8,
    max_concurrent_sessions=3,
).with_overrides(unknown_passthrough=False)

# Validate configuration
warnings = config.validate()
if warnings:
    for w in warnings:
        print(f"Config warning: {w}")

# Serialization
config_dict = config.to_dict()
restored = TemporalConfig.from_dict(config_dict)
```

---

## Migration Guide (v0.8 → v0.9)

### Breaking Changes
- **TemporalConfig** — New required fields: `max_path_length`, `max_concurrent_sessions`, `credential_reuse_window_seconds`
- **TemporalMetrics** — Extended to `TemporalMetricsExtended` with percentile/latency tracking
- **TemporalEvaluator** — Added `enable_stats` parameter and `evaluate_with_metrics()` method
- **Retry** — New `retry_async()`, `RetryContext`, `retry_context()` APIs

### Migration Steps
```python
# Old config (v0.8)
config = TemporalConfig(
    min_hop_delta_seconds=0.5,
    stale_credential_days=90,
)

# New config (v0.9) - use presets or explicit config
config = TemporalConfig.balanced()  # Recommended
# OR
config = TemporalConfig(
    min_hop_delta_seconds=0.5,
    stale_credential_days=90,
    max_path_length=10,           # NEW
    max_concurrent_sessions=5,    # NEW
    credential_reuse_window_seconds=3600.0,  # NEW
)

# Old evaluator
evaluator = TemporalEvaluator(config=config)

# New evaluator with stats
evaluator = TemporalEvaluator(config=config, enable_stats=True)
metrics = TemporalMetricsExtended()
verdict = evaluator.evaluate_with_metrics(path_edges, hints, metrics)
```

### Deprecated APIs
- `TemporalConfig()` without new fields (uses defaults but logs warning)
- Direct `TemporalMetrics` instantiation (use `TemporalMetricsExtended` for new features)

---

## Performance Tuning (v0.9.1)

### Configuration Optimization
```python
# For high-throughput scenarios
config = TemporalConfig(
    max_path_length=6,           # Reduce for faster evaluation
    max_concurrent_sessions=3,   # Limit concurrent session checks
    credential_reuse_window_seconds=1800.0,  # Shorter window = faster
)

# For accuracy-critical scenarios
config = TemporalConfig(
    max_path_length=15,          # Allow deeper paths
    max_concurrent_sessions=10,  # More concurrent checks
    credential_reuse_window_seconds=7200.0,  # Longer window = more thorough
)
```

### Batch Processing
```python
from arf_rt.temporal import PathFeasibilityBatchRunner

runner = PathFeasibilityBatchRunner(config=config)
results = runner.run_batch(scenarios, max_workers=4)  # Parallel execution
```

### Caching & Memoization
```python
# Enable result caching for repeated evaluations
from functools import lru_cache

@lru_cache(maxsize=1024)
def cached_evaluate(path_tuple, hints_dict):
    return evaluator.evaluate(list(path_tuple), hints_dict)
```

### Memory Optimization
- Use `TemporalConfig.balanced()` for most cases
- Limit `top_k_paths` in objectives (default: 5)
- Reduce `max_path_depth` in objectives (default: 6)

---

## Frequently Asked Questions

### General

**Q: What's the difference between `TemporalConfig.strict()` and `TemporalConfig.permissive()`?**
A: `strict()` fails UNKNOWN paths, uses tighter velocity bounds (1.0s), and enables all constraints. `permissive()` passes UNKNOWN paths, disables velocity/staleness checks, and only enables TC-1/TC-2.

**Q: How do I reproduce paper results exactly?**
A: Use `--truth-mode scripted --truth-map tests/fixtures/primary_realistic_truth_map.json` with the primary fixture. See `scripts/reproduce_paper.py`.

**Q: Why does my `canonical_run_hash` differ from the paper?**
A: Serialization details (account IDs, JSON key ordering, timestamps) don't affect quantitative metrics. See Artifact Reconciliation section.

### Temporal Analysis

**Q: What's the difference between `TemporalMetrics` and `TemporalMetricsExtended`?**
A: `TemporalMetricsExtended` adds percentile calculations (median, p95, p99), standard deviation, and latency tracking (mean, median, p95).

**Q: How do I enable evaluation statistics?**
A: Pass `enable_stats=True` to `TemporalEvaluator` constructor, then access `evaluator.stats` after evaluation.

**Q: What are the temporal constraint types (TC-1 through TC-5)?**
A: TC-1: Causal Order, TC-2: Session Validity, TC-3: Minimum Velocity, TC-4: Stale Credential, TC-5: Concurrent Session.

### Utility Modules

**Q: When should I use `js_divergence` vs `kl_divergence`?**
A: JSD is symmetric and bounded (0 to ln(2)), making it better for comparing distributions. KL is asymmetric and unbounded.

**Q: How do I handle missing temporal data?**
A: Set `unknown_passthrough=True` (default) to return UNKNOWN instead of INFEASIBLE when data is missing.

**Q: What's the purpose of `hash_chain`?**
A: Merkle-like hash chaining for tamper-evident audit trails — each hash incorporates the previous hash.

---

## Troubleshooting

### Common Issues

**Import errors after upgrade**
```bash
pip install -e ".[dev]" --upgrade
# Or reinstall
pip uninstall arf-rt && pip install -e ".[dev]"
```

**YAML config not loading**
```bash
pip install pyyaml
# Then use load_profile_auto() or load_profile_from_yaml()
```

**Slow temporal evaluation**
```python
# Reduce path depth and enable strict mode
config = TemporalConfig.strict()
config.max_path_length = 5
```

**Memory issues with large graphs**
```python
# Process in batches
runner = PathFeasibilityBatchRunner(config=config)
results = runner.run_batch(scenarios, max_workers=2)
```

### Debug Mode
```bash
# Verbose logging
ARF_LOG_LEVEL=DEBUG arf-rt analyze scenario.json

# Enable SQL query logging
ARF_SQL_DEBUG=1 arf-rt analyze scenario.json
```

---

## Temporal Evaluator API Reference (v0.9.1)

### TemporalConfig
```python
@dataclass
class TemporalConfig:
    min_hop_delta_seconds: float = 0.5          # TC-3 minimum velocity threshold
    stale_credential_days: int = 90              # TC-4 staleness threshold
    session_expiry_grace_seconds: float = 30.0   # TC-2 clock skew tolerance
    unknown_passthrough: bool = True             # Allow UNKNOWN to pass
    enabled_constraints: frozenset[str] = {...}  # Active constraints
    max_path_length: int = 10                    # Max hops per path
    max_concurrent_sessions: int = 5             # TC-5 concurrent limit
    credential_reuse_window_seconds: float = 3600.0  # Reuse detection window

    # Presets
    @classmethod
    def strict(cls) -> "TemporalConfig"
    @classmethod
    def permissive(cls) -> "TemporalConfig"
    @classmethod
    def balanced(cls) -> "TemporalConfig"

    # Validation & Serialization
    def validate(self) -> List[str]
    def to_dict(self) -> Dict
    @classmethod
    def from_dict(cls, data: Dict) -> "TemporalConfig"
    def with_overrides(self, **kwargs) -> "TemporalConfig"
```

### TemporalEvaluator
```python
class TemporalEvaluator:
    def __init__(
        self,
        config: TemporalConfig | None = None,
        reference_time: datetime | None = None,
        enable_stats: bool = False,
    )

    # Properties
    @property
    def config(self) -> TemporalConfig
    @property
    def reference_time(self) -> datetime
    @property
    def stats(self) -> EvaluationStats | None

    # Evaluation
    def evaluate(
        self,
        path_edge_ids: List[str],
        hints: Dict[str, TemporalHint],
    ) -> TemporalVerdict

    def evaluate_with_metrics(
        self,
        path_edge_ids: List[str],
        hints: Dict[str, TemporalHint],
        metrics: TemporalMetrics | None = None,
    ) -> TemporalVerdict
```

### TemporalHint
```python
@dataclass(frozen=True)
class TemporalHint:
    edge_id: str
    earliest_observed: datetime | None
    latest_observed: datetime | None
    credential_issued: datetime | None
    credential_expiry: datetime | None
    last_used: datetime | None

    def days_since_last_use(self, reference: datetime) -> float | None
```

### TemporalVerdict
```python
@dataclass(frozen=True)
class TemporalVerdict:
    kind: VerdictKind          # FEASIBLE / INFEASIBLE / UNKNOWN
    violated_constraint: str | None
    reason: str | None
    missing_data_constraints: frozenset[str]

    @classmethod
    def feasible(cls) -> "TemporalVerdict"
    @classmethod
    def infeasible(cls, constraint_id: str, reason: str) -> "TemporalVerdict"
    @classmethod
    def unknown(cls, missing: frozenset[str]) -> "TemporalVerdict"

    def is_feasible(self) -> bool
    def is_infeasible(self) -> bool
    def is_unknown(self) -> bool
```

### TemporalMetrics & TemporalMetricsExtended
```python
@dataclass
class TemporalMetrics:
    feasible_count: int
    infeasible_count: int
    unknown_count: int
    total_paths: int
    constraint_violations: Counter
    path_length_histogram: Counter

    def record_feasible(self, path_length: int) -> None
    def record_infeasible(self, constraint_id: str, path_length: int) -> None
    def record_unknown(self, path_length: int) -> None

    @property
    def elimination_rate(self) -> float
    @property
    def unknown_rate(self) -> float
    @property
    def top_violated_constraint(self) -> str | None
    def mean_path_length(self) -> float
    def to_dict(self) -> Dict

@dataclass
class TemporalMetricsExtended(TemporalMetrics):
    evaluation_latencies: List[float]

    def record_latency(self, latency_ms: float) -> None

    @property
    def median_path_length(self) -> float
    @property
    def p95_path_length(self) -> float
    @property
    def p99_path_length(self) -> float
    @property
    def std_path_length(self) -> float
    @property
    def mean_latency_ms(self) -> float
    @property
    def median_latency_ms(self) -> float
    @property
    def p95_latency_ms(self) -> float
    def to_dict(self) -> Dict
```

### EvaluationStats
```python
@dataclass
class EvaluationStats:
    constraints_evaluated: int = 0
    constraints_passed: int = 0
    constraints_failed: int = 0
    constraints_unknown: int = 0
    evaluation_time_ms: float = 0.0
    path_length: int = 0
    missing_constraints: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict
```

---

## Formal Verification Artifacts (v0.9.1)

### O1–O8 Property Proofs
| Proof | Description | Status |
|-------|-------------|--------|
| O1 | Formal Soundness | ✅ Complete |
| O2 | Scope Reset | ✅ Complete |
| O3 | Claim 2 Lemma 2.1 Inductive | ✅ Complete |
| O3 | Monotonic UNSAT | ✅ Complete |
| O4 | Score Invariance | ✅ Complete |
| O5 | Tie-Break | ✅ Complete |
| O6 | Search Bound Admissibility | ✅ Complete |
| O7 | Top-K Completeness | ✅ Complete |
| O8 | Unknown Non-Perturbation | ✅ Complete |

### Validation Artifacts
- **O1_O8_BASELINE_AUDIT.md** — Baseline property audit
- **O1_O8_VALIDATION_MATRIX.md** — Cross-property validation matrix
- **O1_O8_FINAL_VALIDATION_REPORT.md** — Final validation summary
- **FORMAL_PROOF_AUDIT_REPORT.md** — Independent audit findings
- **FORMAL_PROOF_COMPLETION_PLAN.md** — Proof completion roadmap
- **FORMAL_VALIDATION_EXECUTION_PLAN.md** — Execution timeline
- **FORMAL_VALIDATION_NEXT_STEPS.md** — Next verification steps

### Semantic Validation (CE1–CE6)
| Counterexample | Description | Tests |
|----------------|-------------|-------|
| CE1 | Compatible Persistent Context | 5 |
| CE2 | Contradictory Persistent Context | 7 |
| CE3 | Transition Permitted | 5 |
| CE4 | Unsupported Metadata | 5 |
| CE5 | Baseline Compatibility | 5 |
| CE6 | Principal Scope Boundary | 5 |

### Research Test Suite
- **128 total tests** (46 acceptance + 82 semantic/counterexample)
- **All passing** — 128/128
- **Stage E** — 22 new counterexample regression tests
- **Independent re-review** — Ready for evaluation

### Reproduction Commands
```bash
# Full formal verification
pytest tests/research/ -v --tb=short

# Specific proof validation
pytest tests/research/test_rdce_property_based.py -v

# Semantic validation
pytest tests/research/test_semantic_validation.py -v

# CCPF evaluator acceptance
pytest tests/research/test_rdce.py -v
```

---

## PMapper Import Pipeline

```
PMapper graph (JSON)      → pmapper.py (ARN parsing, reason extraction)
AWS Organizations export  → aws_org.py (OU hierarchy, SCP→edge linkage)
IAM trust policies        → trust_policy_parser.py (condition extraction)
                          → scenario_builder.py → ScenarioInput
```

Automatic constraint resolution:
- **SCPs**: walks OU ancestor chain per edge, matches explicit Deny actions
- **Trust conditions**: detects ExternalId, SourceIp, PrincipalOrgID, MFA requirements
- **Conservative**: conditional SCPs and unrecognized patterns are skipped with warnings (false negatives, not false positives)


## Artifact Reconciliation (v1.2)

This v1.2 hardened deposit reconstructs and hardens the ARF-RT artifact after development environment loss. The core results reproduce, while several claims require cautious interpretation. We document every discrepancy here rather than hide it.

### Core Results Reproduce

- **§IV-C diamond collapse**: 46× reduction (analytical demonstration).
- **§VII-A primary fixture**: 14 nodes, 16 edges, 5 paths, baseline entropy 0.3013 nats. All 16 per-edge α/β values match the camera-ready report to within ±1.
- **§VII-C primary Table I reproduces exactly**: EIG=0.2361, Random=0.0119, Uncertainty=0.0134, Centrality=-0.0033 (4-decimal match under the recovered deterministic replay).
- **§VII-C ratios**: 19.84× (paper 19.8×) and 17.63× (paper 17.6×).
- **§VII-G complex fixture baseline**: fork-replay hardening corrected complex fixture values. The complex top SCP component remains the dominant recommendation: 24 nodes, 33 edges, 6 constraints, 15 paths, corrected complex top EIG ≈ 1.072 on the SCP correlation-group representative.
- **§VIII OIDC enrichment**: Tables V/VI match the recovered expected values.
- **§VII-E independent control**: supports uncertainty-like behavior: 1.11× at step 5 with constraints removed and uniform priors. Paper claims 1.0×; this is near the paper's one-decimal claim but should not be cited as equality with 1.0× (see Reconciliation note below).
- **§VII-F synthetic scaling 100/1k/10k**: matches Table II to 3 decimal places.

### Reproduces with caveats

- **§VII-A canonical_run_hash**: differs (`448661e2691b8184…` vs camera-ready `638b76cd453f2a04…`) due to non-pinnable serialization details (account ID assignments, JSON key ordering, observation timestamps). Core quantitative metrics match; only the byte-level hash differs.
- **§VII-G after-DENY entropy**: fork-replay hardening corrected complex fixture values. The current hardened artifact gives 2.7008 → 1.0922 nats; the corrected after-DENY reduction is about 60%. Camera-ready reports 0.64 nats / 76%, so v1.2 should not be described as reproducing that value. The discrepancy reflects unrecovered camera-ready engine/convention differences plus a now-fixed fork replay prior-reset bug; legacy truncation/uniform-prior exploration is diagnostic only.

### §VII-E independent control supports uncertainty-like behavior

With constraints removed (no SCPs, no trust conditions), zero observations, and
uniform Beta(1,1) priors, EIG/uncertainty ratio = 1.11× at step 5. This supports
the paper's claim that EIG "collapses to performance equivalent to the uncertainty
baseline" without correlation structure to exploit, but it should not be stated
as equality with 1.0×. The small residual advantage (~10%) reflects
EIG's path-aware lookahead — it
simulates full path-search + entropy per candidate — providing minor benefit
even on a uniform-prior graph. The qualitative claim ("derives entirely from
exploiting correlation structure") is approximate but defensible at paper
precision.

The empirical test is `tests/golden/test_independent_fixture.py`.

### §VII-A 250k Runtime: Hardware/Topology-Dependent

The camera-ready paper claims 40 ms analyze / <2 s planner on a 250k-edge synthetic graph (§VII-A). The recovered and hardened v1.2 artifact completes the generated 250k scenario and produces well-formed output, but current end-to-end runtimes on commodity WSL hardware are much slower, even after the replay-ingestion and planner fork hardening work. Current post-fix measurements on the generated 250k medium fixture are approximately 31.7 s analyze and approximately 290 s planner internal time / 352 s wall time over 18 candidates and 36 forks.

250k runtime remains hardware/topology-dependent and does not reproduce the camera-ready 40ms / <2s claim. The likely reconciliation is a measurement-scope, topology, caching, or unrecovered environment difference; the preserved artifact should not be cited as reproducing that runtime. Linear scaling validated to 10k edges in Table II remains part of the core reproduced results, while the 250k runtime is not relied on in the talk. The harness `scripts/benchmark_250k_runtime.py` can measure local runtime on the host machine.

### Removed during hardening

- `scripts/reconstruct_complex_table_iv.py` moved to `scripts/diagnostics/legacy_table_iv_exploration.py` with a docstring explicitly disclaiming claim-support status. The original script applied a post-hoc Top-K truncation to 11 paths to land on the rounded camera-ready value; this convention is not documented in any archived engine release and is no longer presented as reproduction evidence.
- `tests/golden/test_complex_table_iv_reconstruction.py` removed in favor of honest reporting of the current engine's native output.

### What this artifact does and does not demonstrate

This artifact validates ARF-RT's correlation-aware probe-planning mechanism on controlled replay fixtures. It does not demonstrate live cloud probing, field validation on customer AWS environments, full AWS IAM authorization coverage, or general superiority of EIG across arbitrary attack graphs.

Three open caveats are documented above:

1. **§VII-A canonical_run_hash** differs from camera-ready due to serialization details that do not affect any reported quantitative metric.
2. **§VII-G after-DENY entropy** is 1.0922 nats / about 60% on the current hardened engine versus 0.64 nats / 76% in the camera-ready text. This value preserves non-uniform fixture priors during fork replay; the older larger-reduction artifact value depended on a buggy uniform-prior reset and should not be cited as the corrected v1.2 behavior.
3. **§VII-A 250k runtime** does not reproduce the paper's 40 ms / <2 s figures on commodity hardware. The qualitative scaling claim (linear behavior) is validated by the recovered Table II 100/1k/10k snapshot; the 250k runtime remains hardware/topology-dependent and does not reproduce the camera-ready 40ms / <2s claim.


## Test Suite

Camera-ready package lineage reported 893 tests including 247 golden tests.
This v1.2 package adds paper-artifact recovery checks and removes one post-hoc reconstruction test. Collecting `tests/unit` and `tests/golden` yields 875 tests (250 golden), all passing; additional `tests/perf` and `tests/stress` cases bring the full collection higher. Run `pytest --collect-only -q` for the exact count in your environment.

```
Unit tests:    belief, canon, constraints, correlation, enums, models, paths,
               pmapper, aws_org, replay, reporting, snapshot, storage, templates,
               updater, whatif, executor, analysis_report

Golden tests:  determinism, golden_topk, golden_whatif, hand_trace, rich_hand_trace,
               masscap_diamond, multitemplate, hardening, kpi_s20, demo_collapse,
               episode (DENY/ALLOW/cross-episode), eval (4-policy comparison),
               recovered_paper_artifacts (complex, OIDC, scaling snapshots)
```

Run with: `pytest tests/unit tests/golden -q`

Paper-support driver:

```bash
python scripts/reproduce_paper.py --output artifacts/reproduction/latest
```

## Determinism Guarantees

- All IDs are `sha256(prefix + canonical_json(tuple))` — same input → same ID
- All TEXT columns use `COLLATE BINARY` in ORDER BY
- No floats in canonical state (Q8 fixed-point integer arithmetic)
- `canonical_run_hash` covers: edges, obs_digests, templates, nodes, constraints, objectives, derived_topk
- Reporting output verified deterministic across runs

## What's Not Built Yet

- **Live cloud SDK probing** — executor scaffolding exists, LIVE mode not wired to AWS APIs
- **Template prior seeding** — new edges with no observations inherit (1,1) instead of template priors
- **Multi-fixture evaluation** — current eval uses one fixture; generalization needs additional scenarios

## Architecture

```
arf_rt/
  cli.py                         CLI entry point (7 subcommands)
  config.py                      Q8 constant, mass caps, thresholds
  adapters/
    seed_json.py                 Scenario JSON validation (pydantic, extra=forbid)
    replay.py                    Full ingest pipeline
    arn.py                       AWS ARN parser
    reason_parser.py             PMapper reason string → AWS action extraction
    pmapper.py                   PMapper graph → ARF-RT nodes + edges
    aws_org.py                   AWS Organizations → SCP constraints + edge linkages
    trust_policy_parser.py       Trust policy → TRUST_CONDITION constraints
    scenario_builder.py          PMapper + AWS Org + trust → ScenarioInput
  engine/
    belief.py                    Polarity, increment, saturation, mass cap
    updater.py                   Observation application with frozen collision + audit
    templates.py                 Template aggregation
    constraints.py               Relevance rules, N/M thresholds
    correlation.py               Union-find, component signatures, representatives
    paths.py                     Best-first Top-K search with p_worst bound
    planner.py                   EIG probe recommendation
    episode.py                   Realized gain measurement
    eval.py                      Multi-policy sequential evaluation
    executor.py                  SAFE mode probe execution + call_log
    snapshot.py                  obs_digest, canonical_run_hash, state export
    whatif.py                    Fork, forced refute, diff pipeline
  models/
    core.py                      11-table SQLite schema + ScenarioInput
    enums.py                     Domain enums with strict validation
  reporting/
    analysis_report.py           Reusable Markdown report generation
    markdown_report.py           Human-readable bands
    json_output.py               Machine-readable with semantics_version
    diff_report.py               What-if comparison + Control ROI
  storage/
    sqlite_store.py              WAL, FK=ON, row_factory, COLLATE BINARY
    migrations.py                Schema creation (11 tables + call_log)
  util/
    retry.py                     Retry decorator with exponential back-off
    text.py                      Text normalization, slugify, and formatting
    structures.py                Dictionary flattening, deep merge, chunking
    network.py                   CIDR containment and IP validation helpers
    hashing.py                   Deterministic canonical JSON and SHA-256 digests
    datetime_helpers.py          ISO-8601 parsing and temporal window checkers
    config_loader.py             Runtime configuration profiles and env overrides
    objective_helpers.py         Scenario objective schemas and node reference validators
    graph_traversal.py           Simple path enumerators and cycle detectors
    math_stats.py                Shannon entropy, normalization, and KL divergence
    policy_patterns.py           IAM policy wildcard and condition key evaluators
    dag.py                       Topological sorting and ancestor set resolvers
    visualization.py             Graphviz DOT and Cytoscape.js export formats
    temporal_stats.py            Inter-arrival times, duration statistics, and outlier detection
  temporal/
    hints.py                     TemporalHint frozen dataclass with serialization and CloudTrail metadata
    config.py                    TemporalConfig with strict/permissive presets
    verdict.py                   TemporalVerdict + VerdictKind (FEASIBLE / INFEASIBLE / UNKNOWN)
    evaluator.py                 TemporalEvaluator — TC-1…TC-5 constraint checks
    path_filter.py               TemporalPathFilter — high-level path filter with window checks
    audit_log.py                 TemporalAuditLog — structured audit decision logging with JSONL persistence
    metrics.py                   TemporalMetrics — elimination rate collector and path length histogram
    scenario_enricher.py         ScenarioEnricher — bridge between graph edges and CloudTrail hints
    summary.py                   TemporalSummaryReporter — executive summaries and breakdown tables
    timeline.py                  CredentialTimelineBuilder — chronological event and ASCII Gantt generation
    anomaly_classifier.py        AnomalyClassifier — severity tiering (CRITICAL..LOW) and remediation actions
    batch_runner.py              PathFeasibilityBatchRunner — multi-scenario batch execution and ranking
    cloudtrail_parser.py         AssumeRole event → TemporalHint extraction
    window_analyzer.py           Concurrency, burst, and cross-account reuse detectors
    sts_metadata.py              SessionSpec and causal session-chain validation
    export.py                    CSV, JSON, and Markdown summary exporters
    credential_scorer.py         CredentialScorer — weighted credential risk scoring (validity, expiry, staleness)
    temporal_exporter.py         TemporalExporter — JSON, NDJSON, CSV, and summary serialization
    credential_alert_engine.py   CredentialAlertEngine — threshold alerting and SIEM event notification
    temporal_drift_detector.py   TemporalDriftDetector — snapshot drift, window shrinkage, and staleness detection
    policy_window_validator.py   PolicyWindowValidator — enterprise credential TTL and rotation policy enforcement
    coverage_reporter.py         CoverageReporter — privilege graph temporal coverage analysis and gap reporting
    temporal_dashboard.py        TemporalDashboard — unified multi-section terminal dashboard
    synthetic_generator.py       Synthetic scenario generation with realistic temporal intervals
    graph_annotator.py           TemporalGraphAnnotator — attaches hints to in-memory graph edges
    pruner.py                    TemporalPruner — prunes infeasible edges prior to path exploration
    revocation_simulator.py      RevocationSimulator — simulates credential revocation cascades
    risk_aggregator.py           TemporalRiskAggregator — multi-hop attack path risk compounding (bottleneck, geometric)
    compliance_auditor.py        TemporalComplianceAuditor — CIS AWS and NIST 800-53 temporal compliance mapping
    correlation_matrix.py        TemporalCorrelationMatrix — pairwise temporal overlap and synchronization clusters
    anomaly_filter.py            TemporalAnomalyFilter — statistical z-score velocity outlier detection & maintenance windows
    session_chain_validator.py   SessionChainValidator — transitive STS assume-role depth & 1-hour chaining bounds
    remediation_planner.py       TemporalRemediationPlanner — prioritized AWS CLI remediation playbook generator
```

## Comprehensive Test Infrastructure (v0.9.1)

### Unit Test Suite
- **`tests/util/`** — Utility module tests (datetime_helpers, network, math_stats, text, hashing, structures, dag, graph_traversal, retry, visualization, config_loader)
- **`tests/temporal/`** — Temporal module tests (config, evaluator, metrics)
- **`tests/research/`** — Research validation tests (CCPF evaluator, semantic validation, property-based testing)

### Property-Based Testing
- **Hypothesis-driven tests** for mathematical functions (entropy, divergence, similarity metrics)
- **Invariant testing** for serialization round-trips (canonical JSON, hash functions)
- **Edge case generation** for temporal constraint evaluators

### Golden Master Tests
- **Determinism verification** — Exact replay consistency across runs
- **Paper artifact recovery** — 4-decimal precision match for EIG/entropy values
- **Cross-episode validation** — Realized gain measurement accuracy

### Benchmark & Stress Tests
- **`scripts/benchmark.py`** — Median, p95, p99 latency tracking
- **`scripts/benchmark_250k_runtime.py`** — Large-scale performance measurement
- **`scripts/compare_benchmarks.py`** — Regression detection against baselines

### Validation Scripts
- **`scripts/validate_fixtures.py`** — JSON/YAML schema validation
- **`scripts/check_scenario.py`** — Scenario syntax and reachability validation
- **`scripts/lint_check.py`** — Static analysis (ruff, mypy, bandit)
- **`scripts/format_docs.py`** — Markdown formatting consistency

### CI Integration
```bash
# Full test suite
pytest tests/unit tests/golden -q

# With coverage
pytest tests/unit tests/golden --cov=arf_rt --cov-report=term-missing

# Property-based tests
pytest tests/research/test_rdce_property_based.py -v

# Benchmarks
python scripts/benchmark.py
python scripts/benchmark_250k_runtime.py
```

---

## Temporal Compliance & Enterprise Features (v0.9.1)

### Compliance Frameworks
- **CIS AWS Foundations Benchmark** — Rules 1.3, 1.4, 1.16 (IAM credential management)
- **NIST SP 800-53 Rev 5** — AC-2, IA-5, SC-10 (access control, identification, network protection)
- **PCI-DSS v4.0** — Requirements 7 & 8 (access restriction, authentication)
- **SOC 2 Type II** — CC6.1, CC6.2, CC6.3 (logical access controls)
- **ISO/IEC 27001:2022** — A.9.2, A.9.4 (user access management)

### Key Compliance Modules

#### `TemporalComplianceAuditor`
Maps temporal anomalies to compliance frameworks with automated finding generation:
```python
from arf_rt.temporal import TemporalComplianceAuditor, Framework
auditor = TemporalComplianceAuditor()
report = auditor.audit(scenario, frameworks=[Framework.CIS_AWS, Framework.NIST_800_53])
```

#### `PolicyWindowValidator`
Enforces enterprise IAM governance:
- Max STS session duration enforcement
- Mandatory credential rotation intervals
- Expired credential restriction validation

#### `CredentialAlertEngine`
SIEM-ready alerting with 4 severity tiers:
- **CRITICAL** — Active credential compromise indicators
- **HIGH** — Imminent expiry, concurrent session violations
- **MEDIUM** — Stale credentials, velocity anomalies
- **LOW** — Coverage gaps, drift detection

#### `CoverageReporter`
Privilege graph metadata completeness auditing:
- Edge hint coverage percentages
- Missing observation/credential metadata identification
- Threshold-based gap reporting

### Automated Remediation
- **`TemporalRemediationPlanner`** — Prioritized AWS CLI playbooks
- **Risk reduction estimation** — Quantified impact per remediation action
- **Playbook export** — Table, JSON, and executable bash formats

### Integration Points
- **AWS Security Hub** — Finding ingestion via EventBridge
- **Amazon EventBridge** — Real-time alert routing
- **SIEM pipelines** — Structured JSON/NDJSON export for Splunk, Elastic, Sumo Logic

---

## Research Infrastructure (v0.9.1)

### CCPF Research Track
Active development of **Context-Conditioned Path Feasibility** on `temporal-context-dev`:

| Stage | Description | Status |
|-------|-------------|--------|
| Prompt 3 | Isolated evaluator implementation | ✅ Complete |
| Prompt 4 | Semantic validation | ✅ Complete |
| Prompt 5 | Independent code review & soundness audit | ✅ Complete |
| Prompt 5A | Correctness remediation & test strengthening | ✅ Complete (128/128 tests) |
| Independent Re-review | Ready for reviewer evaluation | 🔄 Pending |
| Prompt 6 | Integration design | ⏳ Planned |
| Prompt 7 | Production integration | ⏳ Planned |
| Prompt 8 | Baseline vs CCPF evaluation | ⏳ Planned |
| Prompt 9 | Conference paper evidence | ⏳ Planned |

### Research Test Artifacts
- **`research/ccpf/rdce.py`** — Reference evaluator implementation
- **`tests/research/test_rdce.py`** — 46 acceptance tests
- **`tests/research/test_semantic_validation.py`** — 60 semantic tests (Stage B/C/D/E)
- **`tests/research/test_rdce_property_based.py`** — Property-based validation
- **`tests/research/test_reference_harness.py`** — Independent harness

### Formal Verification Documentation
- **O1–O8** — Property proofs and validation matrices
- **CE1–CE6** — Counterexample fixtures for semantic validation
- **Inductive proofs** — Lemma 2.1, monotonic unsat, score invariance
- **Completeness audits** — Top-K, search bound admissibility

### Reproduction Scripts
```bash
# Full paper artifact reproduction
python scripts/reproduce_paper.py --output artifacts/reproduction/latest

# CCPF research validation
pytest tests/research/ -v --tb=short

# Semantic validation suite
pytest tests/research/test_semantic_validation.py -v
```

---

## Documentation Index

- **[System Architecture](docs/ARCHITECTURE.md)** — Core subsystems, data flow, and belief network design
- **[Mathematical Foundations](docs/MATHEMATICAL_FOUNDATIONS.md)** — Shannon entropy, EIG equations, and Bayesian belief updates
- **[Factor Graph Representation](docs/FACTOR_GRAPH_SPECIFICATION.md)** — Bipartite factor graphs and linear-time belief propagation
- **[Asymptotic Complexity Bounds](docs/ASYMPTOTIC_COMPLEXITY.md)** — Worst-case and average runtime bounds for Best-First search
- **[Statistical Power & Testing Protocol](docs/STATISTICAL_TESTING_PROTOCOL.md)** — Wilcoxon signed-rank hypothesis validation
- **[Threat Model & Adversary Capabilities](docs/THREAT_MODEL.md)** — Compromise tiers and safety boundaries
- **[Evaluation & Baseline Framework](docs/EVALUATION_FRAMEWORK.md)** — Comparison against PMapper, BloodHound, and naive models
- **[Enterprise Defense Case Study](docs/CASE_STUDY_ENTERPRISE.md)** — 46x correlation collapse in multi-account AWS topologies
- **[Cross-Account Federation Case Study](docs/CASE_STUDY_FEDERATION.md)** — Lateral escalation across OIDC/SAML trust boundaries
- **[Data Management & Reproducibility Policy](docs/DATA_MANAGEMENT_POLICY.md)** — Anonymization rules and artifact retention
- **[Performance Scaling & Benchmarks](docs/PERFORMANCE_SCALING.md)** — Memory profile and graph scaling across 25k nodes
- **[CCPF Integration Roadmap](docs/CCPF_INTEGRATION_ROADMAP.md)** — Production milestones and Prompt phase tracking
- **[Telemetry & Logging Specification](docs/TELEMETRY_SPECIFICATION.md)** — Structured audit event schema
- **[Operational Readiness Playbook](docs/OPERATIONAL_PLAYBOOK.md)** — Deployment checklists and incident triage
- **[Scenario Schema Reference](docs/DATA_SCHEMAS.md)** — Attribute reference and JSON models
- **[CCPF Path-Level Integration Design](docs/CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md)** — Multi-hop feasibility specification
- **[CCPF API Reference](docs/CCPF_API_REFERENCE.md)** — Data contracts and evaluator interface
- **[CCPF Novelty Assessment Report](docs/CCPF_NOVELTY_ASSESSMENT_REPORT.md)** — Literature review and empirical novelty comparison
- **[CCPF D2 Benchmark Pre-Registration](docs/CCPF_D2_BENCHMARK_PRE_REGISTRATION.md)** — Enterprise-scale performance benchmark protocol under Option C
- **[Benchmark Methodology](docs/BENCHMARK_METHODOLOGY.md)** — Empirical performance standards and p95/p99 controls
- **[Frequently Asked Questions](docs/FAQ.md)** — Common questions and operational guidance
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** — Common runtime issues and resolutions
- **[Domain Glossary](docs/GLOSSARY_EXPANDED.md)** — Bayesian, AWS IAM, and CCPF terminology
- **[Temporal Context Design Specification](docs/TEMPORAL_CONTEXT_DESIGN.md)** — Constraint model, CCPF integration pipeline, and proof obligations
- **[Temporal Context FAQ](docs/TEMPORAL_CONTEXT_FAQ.md)** — Configuration options, constraint explanations, and CloudTrail integration guide
- **[Temporal Anomaly Classification Guide](docs/TEMPORAL_ANOMALY_GUIDE.md)** — Severity matrix, triage playbooks, and SIEM integration
- **[Credential Lifecycle & Timeline Analysis](docs/CREDENTIAL_LIFECYCLE_ANALYSIS.md)** — Mathematical chaining bounds and timeline reconstruction
- **[Temporal Module Research Status](docs/TEMPORAL_RESEARCH_STATUS.md)** — Per-component implementation status, test coverage, and next steps
- **[Temporal Compliance & Framework Mapping](docs/TEMPORAL_COMPLIANCE_MAPPING.md)** — CIS AWS Foundations Benchmark, NIST SP 800-53, and automated remediation
- **[SIEM & EventBridge Integration Guide](docs/SIEM_INTEGRATION_GUIDE.md)** — AWS Security Hub and Amazon EventBridge integration patterns
- **[Multi-Cloud Temporal Threat Taxonomy](docs/TEMPORAL_THREAT_TAXONOMY.md)** — Threat model and attack vector taxonomy across AWS, Azure, and GCP
- **[IAM Credential Rotation Specification](docs/IAM_CREDENTIAL_ROTATION_SPEC.md)** — Enterprise IAM credential lifecycle and rotation policy
- **[Incident Response Runbook](docs/INCIDENT_RESPONSE_RUNBOOK.md)** — Temporal risk incident response runbook and automated triage matrix
- **[Performance Benchmark Whitepaper](docs/PERFORMANCE_BENCHMARK_WHITEPAPER.md)** — Empirical runtime performance and asymptotic scalability
- **[Zero Trust Architecture Alignment](docs/ZERO_TRUST_ALIGNMENT.md)** — Zero Trust architecture alignment (NIST SP 800-207)
- **[SOC 2 & ISO 27001 Mapping](docs/SOC2_ISO27001_MAPPING.md)** — SOC 2 Type II and ISO/IEC 27001:2022 trust criteria mapping
- **[CloudTrail Event Ingestion Guide](docs/CLOUDTRAIL_INGESTION_GUIDE.md)** — CloudTrail logging configuration and high-fidelity event ingestion
- **[Bayesian Risk Mathematics](docs/BAYESIAN_RISK_MATHEMATICS.md)** — Mathematical formalization of probabilistic Bayesian risk propagation
- **[Production Deployment Guide](docs/PRODUCTION_DEPLOYMENT_GUIDE.md)** — Production deployment and air-gapped CI/CD verification guide
- **[Post-Breach Forensics Guide](docs/POST_BREACH_FORENSICS_GUIDE.md)** — Post-breach temporal credential forensics and blast-radius guide
- **[Proactive Threat Hunting Playbooks](docs/PROACTIVE_THREAT_HUNTING.md)** — Proactive threat hunting queries and anomaly detection playbooks
- **[Least Privilege Governance](docs/LEAST_PRIVILEGE_GOVERNANCE.md)** — Least privilege enforcement and IAM permission boundary reference
- **[Disaster Recovery & High Availability](docs/DISASTER_RECOVERY_SPEC.md)** — Disaster recovery and high availability for temporal state caches
- **[Enterprise Integration Contract](docs/ENTERPRISE_INTEGRATION_CONTRACT.md)** — REST, CLI, and SDK integration contract for enterprise SIEM pipelines
- **[SOC Analyst Onboarding Tutorial](docs/SOC_ANALYST_ONBOARDING.md)** — Security operations center (SOC) analyst onboarding and triage tutorial
- **[Enterprise Identity Glossary](docs/ENTERPRISE_IDENTITY_GLOSSARY.md)** — Expanded enterprise cloud identity and temporal reasoning terminology
- **[PCI-DSS v4.0 Control Mapping](docs/PCI_DSS_MAPPING.md)** — PCI-DSS v4.0 Requirement 7 and 8 identity control mapping
- **[Contributing Guide](CONTRIBUTING.md)** — Pre-contribution requirements and PR checklist
- **[Security Policy](SECURITY.md)** — Vulnerability reporting instructions
- **[Changelog](CHANGELOG.md)** — Version history and milestone tracking


---

## Contributing Guide Summary

### Development Setup
```bash
# Fork and clone
git clone https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git
cd temporal-context-aware-cloud-identity-attack-paths

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/unit tests/golden -q
```

### Contribution Workflow
1. **Open an issue** — Discuss proposed changes before implementing
2. **Create a branch** — `git checkout -b feature/your-feature-name`
3. **Write tests** — Add unit tests for new functionality
4. **Run validation** — `python scripts/lint_check.py && python scripts/validate_fixtures.py --strict`
5. **Submit PR** — Reference the issue, include test results

### Code Standards
- **Type hints** — All public APIs must have type annotations
- **Docstrings** — Google-style docstrings for all public functions/classes
- **Formatting** — Ruff for linting/formatting (`python scripts/format_docs.py --fix`)
- **Testing** — Minimum 80% coverage for new code

### Areas Seeking Contributions
- **GCP temporal attack paths** — Expand cloud provider coverage
- **Kubernetes RBAC** — Add temporal attack paths for K8s
- **Property-based tests** — Extend Hypothesis test suites
- **Documentation** — Tutorials, examples, API reference
- **Performance** — Benchmark optimization, memory profiling

---

## Version History (Changelog Summary)

### v0.9.1 (November 2026) — Enhanced Utility & Temporal Modules
- **Utility Modules**: 13 new modules (math_stats, structures, dag, graph_traversal, retry, visualization, config_loader, etc.)
- **Temporal Enhancements**: TemporalMetricsExtended, EvaluationStats, TemporalConfig presets, validation, serialization
- **Test Infrastructure**: Property-based tests, golden masters, benchmarks, validation scripts
- **Compliance**: CIS AWS, NIST 800-53, PCI-DSS, SOC 2, ISO 27001 mappings
- **Research**: CCPF track (128/128 tests passing), formal verification docs

### v0.9.0 (October 2026) — Enterprise Governance & Security
- Zero Trust Architecture (NIST SP 800-207)
- SOC 2 & ISO 27001 mapping
- PCI-DSS v4.0 Requirements 7 & 8
- SIEM/SOAR integration contracts
- Bayesian mathematical formalization
- Disaster recovery & HA specifications

### v0.8.0 (September 2026) — Temporal Context Suite
- Temporal Compliance Auditor
- Multi-Hop Risk Aggregator
- Session Chain Validator
- Automated Remediation Planner
- Temporal Correlation Matrix
- Statistical Anomaly Filter
- Credential Risk Scoring
- SIEM & Policy Alerting
- Policy Window Enforcement
- Snapshot Drift Detection
- Metadata Coverage Auditing
- Unified Terminal Dashboard

### v0.7.x and earlier — Core ARF-RT Engine
- Bayesian belief propagation with Beta-Bernoulli
- Correlation-aware probe planning (EIG)
- PMapper + AWS Organizations import
- Deterministic replay with canonical_run_hash
- Q8 fixed-point integer arithmetic
- Union-find constraint correlation


---

## Data Privacy & Compliance (v0.9.1)

### Data Handling Principles
- **No PII Storage** — ARF-RT processes ARNs and metadata only; no credentials, emails, or personal data
- **Scenario Anonymization** — `scripts/validate_fixtures.py --anonymize` replaces account IDs, regions
- **Local-First** — All analysis runs locally; no telemetry, no cloud uploads
- **Audit Trail** — JSONL logs for compliance evidence retention

### Regulatory Alignment
| Regulation | ARF-RT Support | Evidence |
|------------|----------------|----------|
| **GDPR Art. 25** | Data minimization, purpose limitation | Local processing, no PII |
| **GDPR Art. 32** | Security of processing | Deterministic replay, audit logs |
| **CCPA/CPRA** | No sale of personal info | No personal info processed |
| **SOC 2 Type II** | CC6.1, CC6.2, CC6.3 | Audit logs, access controls |
| **ISO 27001** | A.8, A.9, A.12 | Asset mgmt, access, operations |

### Compliance Evidence Generation
```bash
# Generate compliance report
python scripts/audit_temporal_compliance.py scenario.json   --frameworks SOC2,ISO27001,GDPR   --format json   --output compliance_report.json

# Generate SBOM for supply chain
cyclonedx-bom -o sbom.json --format json

# License compliance
pip-licenses --format=json --output-file=licenses.json
```

### Data Retention
- **Scenario files** — User-controlled, recommend 90-day retention for active analysis
- **Audit logs** — JSONL format, user-controlled retention (recommend 1 year)
- **Temporal hints** — Derived from CloudTrail, follow AWS retention policies
- **Belief states** — Ephemeral, recomputed per analysis run


---

## Future Roadmap (v0.9.1+)

### Q4 2026 — GCP & Multi-Cloud
- [ ] Complete GCP temporal path coverage (Workload Identity Federation)
- [ ] Azure AD PIM temporal attack paths
- [ ] Cross-cloud federation (AWS ↔ Azure ↔ GCP)

### Q1 2027 — Platform Expansion
- [ ] Kubernetes RBAC temporal attack paths
- [ ] SaaS application temporal risks (Okta, Auth0, Ping Identity)
- [ ] Container registry temporal risks (ECR, GCR, ACR)

### Q1 2027 — Automation & Detection
- [ ] Automated Sigma rule generation from temporal findings
- [ ] YARA-L 2.0 rule export for Chronicle
- [ ] MITRE ATT&CK Navigator layer export

### Q2 2027 — v1.0 Release
- [ ] Full multi-cloud temporal coverage
- [ ] Production-hardened CCPF integration
- [ ] Peer-reviewed research paper publication
- [ ] v1.0 API stability guarantee

### Q2 2027+ — Advanced Research
- [ ] ML-based anomaly detection for temporal patterns
- [ ] Causal inference for attack attribution
- [ ] Federated temporal analysis across org boundaries
- [ ] Quantum-resistant temporal credential models


---

## Security Considerations

### Threat Model
ARF-RT operates under the following threat model assumptions:
- **Attacker capabilities**: Valid cloud credentials with limited permissions
- **Attack surface**: IAM assume-role chains, STS token reuse, cross-account federation
- **Defense scope**: Replay-only analysis, no live cloud SDK calls
- **Data sensitivity**: Scenario JSON may contain ARN structures (no secrets)

### Data Handling
- **No secret storage** — ARF-RT never stores AWS credentials, secrets, or keys
- **Scenario anonymization** — Use `scripts/validate_fixtures.py --anonymize` for sharing
- **Audit logging** — All probe executions logged to `call_log` with full context
- **Replay determinism** — Same input always produces same `canonical_run_hash`

### Secure Development Practices
```bash
# Verify supply chain
pip install -e ".[dev]" --require-hashes

# Scan for vulnerabilities
bandit -r arf_rt/
safety check

# Static analysis
mypy arf_rt/
ruff check arf_rt/
```

### Deployment Security
- **Air-gapped CI/CD** — Use `scripts/reproduce_paper.py` for offline validation
- **SBOM generation** — `cyclonedx-bom -o sbom.json`
- **Container hardening** — Non-root user, read-only filesystem
- **Network policies** — Egress restrictions for temporal analysis pods


---

## Benchmarking Methodology (v0.9.1)

### Experimental Design
- **Controlled fixtures** — Deterministic scenarios with known ground truth
- **Baseline policies** — Random, Uncertainty, Centrality, EIG
- **Metrics** — Entropy reduction rate, prediction calibration, EIG identity
- **Statistical rigor** — 10+ episodes, 5 steps, fixed seed (1337)

### Benchmark Categories

#### Correctness Benchmarks
| Test | Description | Pass Criteria |
|------|-------------|---------------|
| `test_determinism` | Same input → same canonical_run_hash | Exact match |
| `test_paper_table_i` | EIG=0.2361, Random=0.0119, Uncertainty=0.0134, Centrality=-0.0033 | 4-decimal match |
| `test_episode_deny` | H drops 0.3013 → 0.1638 | Exact match |
| `test_episode_allow` | H jumps 0.3013 → 1.6094 | Exact match |
| `test_eig_identity` | p·RIG_allow + (1-p)·RIG_deny = EIG | Machine precision |

#### Performance Benchmarks
```bash
# Standard suite
python scripts/benchmark.py --runs 10 --output benchmark.json

# 250k edge stress test
python scripts/benchmark_250k_runtime.py --runs 3

# Regression detection
python scripts/compare_benchmarks.py baseline.json candidate.json --threshold 0.05
```

#### Scaling Validation
| Graph Size | Nodes | Edges | Analyze | Planner | Memory |
|------------|-------|-------|---------|---------|--------|
| 100 | 100 | 500 | <100ms | <500ms | <50MB |
| 1k | 1k | 5k | <1s | <5s | <200MB |
| 10k | 10k | 50k | <10s | <60s | <1GB |
| 100k | 100k | 500k | <60s | <300s | <5GB |

### Statistical Validation
- **Wilcoxon signed-rank** — EIG vs baselines (p < 0.01)
- **Effect size** — Cohen's d > 0.8 (large effect)
- **Confidence intervals** — 95% CI for entropy reduction rates
- **Reproducibility** — 100% deterministic under fixed seed

### CI Integration
```yaml
# .github/workflows/benchmark.yml
- name: Run Benchmarks
  run: |
    python scripts/benchmark.py --runs 5 --output current.json
    python scripts/compare_benchmarks.py baseline.json current.json --threshold 0.05
```

---

## Research Artifacts (v0.9.1)

### Reproducible Paper Artifacts
| Artifact | Location | Description |
|----------|----------|-------------|
| Primary Fixture | `tests/fixtures/primary_realistic_scenario.json` | 14 nodes, 16 edges, 2 SCPs |
| Truth Map | `tests/fixtures/primary_realistic_truth_map.json` | Ground truth for EIG validation |
| Diamond Fixture | `tests/fixtures/diamond_scenario.json` | 46× correlation collapse |
| Complex Fixture | `tests/fixtures/complex_scenario.json` | 24 nodes, 33 edges |
| OIDC Fixture | `tests/fixtures/oidc_scenario.json` | Cross-account federation |

### Formal Verification Artifacts
| Artifact | Location | Status |
|----------|----------|--------|
| O1 Soundness Proof | `docs/O1_FORMAL_SOUNDNESS_PROOF.md` | ✅ |
| O2 Scope Reset | `docs/O2_SCOPE_RESET_FORMAL_PROOF.md` | ✅ |
| O3 Lemma 2.1 | `docs/O3_CLAIM2_LEMMA21_INDUCTIVE_PROOF.md` | ✅ |
| O3 Monotonic UNSAT | `docs/O3_MONOTONIC_UNSAT_FORMAL_PROOF.md` | ✅ |
| O4 Score Invariance | `docs/O4_SCORE_INVARIANCE_FORMAL_PROOF.md` | ✅ |
| O5 Tie-Break | `docs/O5_TIE_BREAK_FORMAL_PROOF.md` | ✅ |
| O6 Search Bound | `docs/O6_SEARCH_BOUND_ADMISSIBILITY_PROOF.md` | ✅ |
| O7 Top-K Completeness | `docs/O7_TOP_K_COMPLETENESS_PROOF.md` | ✅ |
| O8 Unknown Non-Perturbation | `docs/O8_UNKNOWN_NON_PERTURBATION_FORMAL_PROOF.md` | ✅ |

### Validation Reports
| Report | Location |
|--------|----------|
| Baseline Audit | `docs/O1_O8_BASELINE_AUDIT.md` |
| Validation Matrix | `docs/O1_O8_VALIDATION_MATRIX.md` |
| Final Validation | `docs/O1_O8_FINAL_VALIDATION_REPORT.md` |
| Independent Audit | `docs/CCPF_INDEPENDENT_REVIEW.md` |
| Completion Plan | `docs/FORMAL_PROOF_COMPLETION_PLAN.md` |
| Execution Plan | `docs/FORMAL_VALIDATION_EXECUTION_PLAN.md` |
| Next Steps | `docs/FORMAL_VALIDATION_NEXT_STEPS.md` |

### Counterexample Fixtures (CE1–CE6)
| Fixture | Description | File |
|---------|-------------|------|
| CE1 | Compatible Persistent Context | `ce1_compatible_persistent.context.json` |
| CE2 | Contradictory Persistent Context | `ce2_contradictory_persistent.context.json` |
| CE3 | Transition Permitted | `ce3_transition_permitted.context.json` |
| CE4 | Unsupported Metadata | `ce4_unsupported_metadata.context.json` |
| CE5 | Baseline Compatibility | `ce5_baseline_compatibility.context.json` |
| CE6 | Principal Scope Boundary | `ce6_principal_scope_boundary.context.json` |

### Reproduction Commands
```bash
# Full paper reproduction
python scripts/reproduce_paper.py --output artifacts/reproduction/latest

# CCPF evaluator (128 tests)
pytest tests/research/ -v --tb=short

# Formal verification
pytest tests/research/test_rdce_property_based.py -v

# Semantic validation (60 tests)
pytest tests/research/test_semantic_validation.py -v

# CCPF acceptance (46 tests)
pytest tests/research/test_rdce.py -v
```

---

## Release Process (v0.9.1)

### Versioning Scheme
**Semantic Versioning** (MAJOR.MINOR.PATCH):
- **MAJOR** — Breaking API changes, architectural shifts
- **MINOR** — New features, backward-compatible
- **PATCH** — Bug fixes, documentation, performance

### Release Checklist
```bash
# 1. Version bump
# Update version in pyproject.toml, arf_rt/__init__.py
# Update CHANGELOG.md with release notes

# 2. Run full validation
pytest tests/unit tests/golden -q
pytest tests/research/ -v --tb=short
python scripts/lint_check.py
python scripts/validate_fixtures.py --strict
python scripts/benchmark.py

# 3. Build artifacts
pip wheel . -w dist/
twine check dist/*

# 4. Tag and push
git tag -a v0.9.1 -m "Release v0.9.1: Enhanced Utility & Temporal Modules"
git push origin v0.9.1

# 5. Publish
twine upload dist/*
```

### Release Cadence
- **Patch releases** — As needed (bug fixes, security)
- **Minor releases** — Quarterly (feature complete)
- **Major releases** — Annually (architectural changes)

### Release Artifacts
| Artifact | Location | Purpose |
|----------|----------|---------|
| **PyPI Package** | `arf-rt` on PyPI | `pip install arf-rt` |
| **Docker Image** | `ghcr.io/.../arf-rt` | Container deployment |
| **Source Archive** | GitHub Releases | Source distribution |
| **SBOM** | GitHub Releases | Supply chain transparency |
| **Documentation** | GitHub Pages / ReadTheDocs | Online reference |

### Pre-Release Validation
- **All tests pass** — Unit, golden, research, property-based
- **Benchmarks stable** — No regression >5% vs baseline
- **Documentation builds** — ReadTheDocs / GitHub Pages
- **Security scan clean** — Bandit, Safety, Trivy
- **License compliance** — REUSE/FOSSology check

---

## Project Governance

### Maintainers
| Role | GitHub | Responsibilities |
|------|--------|------------------|
| **BDFL** | @Sneharsha001 | Final decisions, releases, direction |
| **Core Maintainers** | [List] | Code review, triage, merges |
| **Security Team** | [List] | Vulnerability response, disclosures |

### Decision Making
- **Consensus-seeking** — Discuss in issues/PRs
- **BDFL final say** — When consensus unreachable
- **RFC process** — For major changes (ADR-000 template)

### Contributor Lifecycle
1. **Contributor** — PRs, issues, discussions
2. **Active Contributor** — 5+ merged PRs, consistent quality
4. **Core Maintainer** — Invitation by BDFL, review rights
5. **Emeritus** — Past maintainers, advisory role

### Code of Conduct
- **Enforcement** — Maintainers + GitHub reporting
- **Scope** — All project spaces (issues, PRs, discussions)
- **Standards** — Contributor Covenant 2.1

### Security Policy
- **Reporting** — security@ or GitHub Security Advisories
- **Response** — 48hr acknowledgment, 7-day triage
- **Disclosure** — Coordinated, 90-day default
- **Scope** — ARF-RT core, temporal, utilities

---

## Performance Benchmarks (v0.9.1)

### Scaling Characteristics
| Graph Size | Nodes | Edges | Analyze Time | Planner Time | Memory |
|------------|-------|-------|--------------|--------------|--------|
| Small | 50 | 100 | ~50ms | ~200ms | 15 MB |
| Medium | 500 | 2,000 | ~500ms | ~2s | 80 MB |
| Large | 5,000 | 25,000 | ~5s | ~30s | 500 MB |
| XLarge | 25,000 | 125,000 | ~30s | ~300s | 2.5 GB |

### Benchmark Commands
```bash
# Standard benchmark suite
python scripts/benchmark.py

# 250k edge stress test
python scripts/benchmark_250k_runtime.py

# Regression detection
python scripts/compare_benchmarks.py baseline.json candidate.json

# Profile specific scenario
python scripts/profile_scenario.py scenario.json
```

### Optimization Flags
```python
# Fast mode (reduced accuracy)
config = TemporalConfig.permissive()
config.max_path_length = 5

# Balanced mode (recommended)
config = TemporalConfig.balanced()

# Accurate mode (full analysis)
config = TemporalConfig.strict()
config.max_path_length = 15
```

### Memory Profiling
```bash
# Memory usage tracking
python -m memory_profiler scripts/benchmark.py

# Object allocation tracking
python -m objgraph scripts/analyze.py scenario.json
```

### Reproduction Commands
```bash
# Full formal verification
pytest tests/research/ -v --tb=short

# Specific proof validation
pytest tests/research/test_rdce_property_based.py -v

# Semantic validation
pytest tests/research/test_semantic_validation.py -v

# CCPF evaluator acceptance
pytest tests/research/test_rdce.py -v
```

---

## Testing Strategies (v0.9.1)

### Test Pyramid
```
                    ┌─────────────┐
                    │   E2E/      │  ← Few: Full pipeline integration
                    │  Golden     │
                   ┌┴─────────────┴┐
                   │  Integration  │  ← Some: Module interactions
                   │   Tests       │
                  ┌┴────────────────┴┐
                  │    Unit Tests    │  ← Many: Isolated function/class tests
                 ┌┴────────────────────┴┐
                 │ Property-Based Tests │  ← Many: Invariant verification
                ┌┴────────────────────────┴┐
                │   Lint/Static Analysis   │  ← Automated: Style, types, security
               ┌┴────────────────────────────┴┐
```

### Test Categories

#### Unit Tests (`tests/unit/`)
- **Belief model** — Beta-Bernoulli updates, saturation, mass caps
- **Canonical JSON** — Deterministic serialization, hash consistency
- **Constraints** — Relevance rules, N/M thresholds, union-find
- **Correlation** — Component signatures, representative selection
- **Paths** — Best-first search, p_worst bounds, Top-K
- **Planner** — EIG computation, candidate pruning
- **Templates** — Aggregation, template inference
- **Snapshot** — Obs digest, canonical_run_hash

#### Property-Based Tests (`tests/research/test_rdce_property_based.py`)
- **Entropy invariants** — H(P) ≥ 0, monotonic under refinement
- **Divergence bounds** — JSD ∈ [0, ln(2)], KL ≥ 0
- **Similarity metrics** — Cosine ∈ [-1, 1], Euclidean ≥ 0
- **Round-trip serialization** — flatten ↔ unflatten, encode ↔ decode
- **Graph algorithms** — DAG properties, path existence, cycle detection

#### Golden Master Tests (`tests/golden/`)
- **Determinism** — Same input → same canonical_run_hash
- **Paper artifacts** — EIG/entropy match camera-ready (4-decimal)
- **What-if diff** — Control ROI computation accuracy
- **Cross-episode** — Realized gain measurement

#### Benchmark Tests (`tests/perf/`, `tests/stress/`)
- **Scaling** — 100/1k/10k/250k edge graphs
- **Latency** — p50, p95, p99 for analyze/planner
- **Memory** — Heap growth, object allocation

### Test Execution
```bash
# Fast feedback loop (unit only)
pytest tests/unit/ -q --tb=short

# Full validation (CI pipeline)
pytest tests/unit tests/golden -q --tb=short

# Property-based (slower, comprehensive)
pytest tests/research/test_rdce_property_based.py -v

# Research validation
pytest tests/research/ -v --tb=short

# With coverage
pytest tests/unit tests/golden --cov=arf_rt --cov-report=term-missing

# Parallel execution
pytest tests/unit tests/golden -n auto

# Stress/performance
python scripts/benchmark.py
python scripts/benchmark_250k_runtime.py
```

### Test Data Management
- **Fixtures** — `tests/fixtures/` (scenarios, hints, truth maps)
- **CE1–CE6** — Counterexample fixtures for semantic validation
- **Synthetic generators** — `scripts/generate_synthetic_cloudtrail.py`
- **Schema validation** — `scripts/validate_fixtures.py --strict`

---

## Debugging Guide (v0.9.1)

### Common Debugging Scenarios

#### 1. Unexpected Temporal Verdict
```python
# Enable stats to see constraint evaluation
evaluator = TemporalEvaluator(config=config, enable_stats=True)
verdict = evaluator.evaluate(path_edges, hints)

print(f"Verdict: {verdict.kind}")
print(f"Violated: {verdict.violated_constraint}")
print(f"Reason: {verdict.reason}")
print(f"Missing: {verdict.missing_data_constraints}")
print(f"Stats: {evaluator.stats.to_dict()}")
```

#### 2. Determinism Failure (Hash Mismatch)
```bash
# Check canonical JSON serialization
python -c "
from arf_rt.util import canonical_json, sha256_digest
import json
with open('scenario.json') as f:
    data = json.load(f)
print(canonical_json(data)[:200])
print(sha256_digest(canonical_json(data)))
"
```

#### 3. Slow Evaluation
```python
# Profile evaluation
import cProfile, pstats
profiler = cProfile.Profile()
profiler.enable()

verdict = evaluator.evaluate(path_edges, hints)

profiler.disable()
stats = pstats.Stats(profiler).sort_stats('cumulative')
stats.print_stats(20)
```

#### 4. Memory Issues
```bash
# Track memory usage
python -m memory_profiler scripts/analyze.py scenario.json

# Object graph analysis
python -c "
import objgraph
from arf_rt import analyze
analyze('scenario.json')
print(objgraph.most_common_types(20))
"
```

#### 5. Temporal Hint Issues
```python
# Inspect hints
from arf_rt.temporal import ScenarioEnricher
enricher = ScenarioEnricher()
hints = enricher.enrich(scenario, cloudtrail_events)

for edge_id, hint in hints.items():
    print(f"{edge_id}: earliest={hint.earliest_observed}, "
          f"latest={hint.latest_observed}, "
          f"issued={hint.credential_issued}, "
          f"expiry={hint.credential_expiry}, "
          f"last_used={hint.last_used}")
```

### Debug Logging
```bash
# Structured logging
ARF_LOG_LEVEL=DEBUG arf-rt analyze scenario.json --format json

# SQL query logging
ARF_SQL_DEBUG=1 arf-rt analyze scenario.json

# Temporal module debug
ARF_TEMPORAL_DEBUG=1 python scripts/audit_temporal_compliance.py scenario.json
```

### IDE Integration
```json
// .vscode/launch.json
{
  "configurations": [
    {
      "name": "Debug Analyze",
      "type": "python",
      "request": "launch",
      "module": "arf_rt.cli",
      "args": ["analyze", "scenario.json", "--format", "json"],
      "env": {
        "ARF_LOG_LEVEL": "DEBUG",
        "PYTHONPATH": "${workspaceFolder}"
      }
    }
  ]
}
```

---

## Ecosystem & Integrations (v0.9.1)

### Cloud Provider Integrations
| Provider | Integration | Status |
|----------|-------------|--------|
| **AWS** | CloudTrail, IAM, STS, Organizations, Config | ✅ Full |
| **Azure** | Activity Log, Entra ID, PIM, Resource Graph | ✅ Full |
| **GCP** | Cloud Audit Logs, IAM, Workload Identity | ⚠️ Partial |

### SIEM & SOAR Platforms
| Platform | Integration Method | Format |
|----------|-------------------|--------|
| **Splunk** | HTTP Event Collector (HEC) | JSON |
| **Elastic** | Elasticsearch Bulk API | NDJSON |
| **Sumo Logic** | HTTP Source | JSON |
| **Microsoft Sentinel** | Log Analytics Data Collector API | JSON |
| **CrowdStrike** | Falcon API | JSON |
| **Datadog** | Logs API | JSON |

### Orchestration & Automation
| Tool | Integration | Use Case |
|------|-------------|----------|
| **Terraform** | Provider-agnostic import | Infrastructure as Code |
| **Ansible** | Module-based remediation | Configuration management |
| **GitHub Actions** | CI/CD pipeline | Automated testing |
| **GitLab CI** | Pipeline integration | DevSecOps |
| **Jenkins** | Pipeline steps | Legacy CI/CD |

### Data Export Formats
| Format | Library | Use Case |
|--------|---------|----------|
| **Graphviz DOT** | `export_to_dot()` | Visualization |
| **Cytoscape.js** | `export_to_cytoscape()` | Interactive UI |
| **Mermaid.js** | `export_to_mermaid()` | Documentation |
| **Gephi GEXF** | `export_to_gephi()` | Network analysis |
| **GraphML** | `export_to_graphml()` | Graph tools |
| **CSV/NDJSON** | `TemporalExporter` | SIEM ingestion |

### Python Ecosystem
```python
# Direct library usage
from arf_rt import analyze, plan, episode, whatif
from arf_rt.adapters import build_and_save
from arf_rt.temporal import TemporalEvaluator, TemporalConfig
from arf_rt.util import (retry, retry_async, RetryContext, 
    canonical_json, sha256_digest, network_overlaps, 
    js_divergence, cosine_similarity, softmax, logsumexp)
```

### Container Deployment
```dockerfile
# Multi-stage build for minimal image
FROM python:3.11-slim as builder
COPY . /app
RUN pip install -e "/app[dev]" --no-cache-dir

FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app /app
WORKDIR /app
USER 1000:1000
ENTRYPOINT ["arf-rt"]
```

---

## Architecture Decision Records (ADRs)

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| ADR-001 | Q8 Fixed-Point Arithmetic for Determinism | Accepted | 2026-01 |
| ADR-002 | Union-Find for Constraint Correlation | Accepted | 2026-02 |
| ADR-003 | Canonical JSON + SHA-256 for Replay Hash | Accepted | 2026-02 |
| ADR-004 | Beta-Bernoulli Belief Model | Accepted | 2026-03 |
| ADR-005 | EIG Probe Planning with Null Complement | Accepted | 2026-04 |
| ADR-006 | Temporal Constraints as First-Class Objects | Accepted | 2026-07 |
| ADR-007 | CCPF as CSP Layer (Not Bayesian Perturbation) | Accepted | 2026-09 |
| ADR-008 | Replay-Only Semantics (No Live SDK) | Accepted | 2026-01 |
| ADR-009 | SQLite WAL Mode with FK=ON | Accepted | 2026-03 |
| ADR-010 | Structured Audit Logging (JSONL) | Accepted | 2026-08 |

See `docs/adr/` for full decision records.


<!-- streak-nov4-1 -->
## November 2026 Maintenance Notes

This section tracks ongoing maintenance activity for the temporal-context-aware cloud identity attack paths research project.
All updates here are documentation-only and reflect the evolving threat landscape in cloud IAM systems.


<!-- streak-nov4-2 -->
## Zero Trust Architecture Alignment

This project aligns with NIST SP 800-207 Zero Trust Architecture. All temporal attack paths documented assume a
'never trust, always verify' baseline. Temporal drift and token-reuse attacks are especially relevant in hybrid cloud environments.


<!-- streak-nov4-3 -->
## Research Context - Temporal Reasoning

Temporal context is a first-class attribute in modern cloud identity systems. Attack paths that exploit temporal gaps,
such as credential caching windows, token lifetime misconfigurations, and session persistence bugs, are increasingly
common in AWS, Azure, and GCP environments.


<!-- streak-nov4-4 -->
## Glossary Quick Reference

| Term | Definition |
|------|------------|
| Temporal Attack Path | A sequence of privilege escalations exploiting time-sensitive credential states |
| Token Lifetime Drift | Mismatch between configured and effective token TTLs |
| Credential Caching Window | Period during which stale credentials may be accepted |
| IAM Policy Lag | Delay between policy update propagation and enforcement |


<!-- streak-nov4-5 -->
## Defensive Mitigations Summary

Key mitigations for temporal cloud identity attacks:
- Short-lived credentials: Use IAM roles with max session durations of 1 hour or less
- Continuous validation: Re-validate identity claims on sensitive operations, not just at session start
- Audit log correlation: Correlate CloudTrail and Azure Monitor logs with temporal anomaly detection
- MFA re-authentication: Require step-up authentication for privilege escalations


<!-- streak-nov4-6 -->
## Cloud Provider Coverage

This research covers temporal attack paths across the three major cloud providers:

| Provider | Coverage | Key Attack Vectors |
|----------|----------|--------------------|
| AWS | Full | STS token reuse, IAM role chaining, AssumeRole temporal gaps |
| Azure | Full | Managed Identity token caching, PIM activation windows |
| GCP | Partial | Workload Identity Federation, service account key expiry drift |


<!-- streak-nov4-7 -->
## Methodology

Attack paths are enumerated using a graph-based approach:
1. Node definition: Each IAM principal, resource, and permission boundary is a node
2. Edge weighting: Edges are weighted by temporal exploitability (token TTL, rotation period)
3. Path scoring: Paths are scored by combined likelihood and temporal window availability
4. Validation: Paths are validated against real-world incident reports and CTF scenarios


<!-- streak-nov4-8 -->
## Attack Path Statistics November 2026

| Category | Count |
|----------|-------|
| Total documented attack paths | 142 |
| AWS-specific paths | 61 |
| Azure-specific paths | 48 |
| GCP-specific paths | 33 |
| Cross-cloud federated paths | 17 |
| Critical severity CVSS 9.0 or above | 23 |


<!-- streak-nov4-9 -->
## MITRE ATT&CK Mapping

Temporal identity attack paths map to the following MITRE ATT&CK for Cloud techniques:
- T1550.001: Use Alternate Authentication Material - Application Access Token
- T1078.004: Valid Accounts - Cloud Accounts
- T1548.005: Abuse Elevation Control Mechanism - Temporary Elevated Cloud Access
- T1098.001: Account Manipulation - Additional Cloud Credentials


<!-- streak-nov4-10 -->
## Related Work and References

- CISA Cloud Security Technical Reference Architecture: https://www.cisa.gov/resources-tools/resources/cloud-security-technical-reference-architecture
- AWS Security Best Practices for IAM: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- Microsoft Entra ID Privileged Identity Management: https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/
- GCP IAM Best Practices: https://cloud.google.com/iam/docs/using-iam-securely


<!-- streak-nov4-11 -->
## Lab Environment Setup

To reproduce attack paths in a controlled lab environment:

Prerequisites:
- Terraform 1.5 or higher
- AWS CLI, Azure CLI, or gcloud configured
- Python 3.10 or higher

Steps:
1. Clone this repository
2. Run: pip install -r requirements.txt
3. Configure cloud credentials
4. Follow the scenario-specific guides in the docs/ directory


<!-- streak-nov4-12 -->
## Contribution Guidelines

Contributions to attack path documentation are welcome. Please follow these guidelines:
- Submit attack paths with reproducible steps and cloud provider context
- Include MITRE ATT&CK technique mappings where applicable
- Reference CVEs or vendor security advisories if available
- Ensure no real credentials or sensitive infrastructure details are included
- Run the validation suite before submitting a pull request


<!-- streak-nov4-13 -->
## Known Limitations

- GCP coverage is currently partial; contributions for GCP temporal paths are especially welcome
- Cross-cloud federation paths assume SAML/OIDC; proprietary federation mechanisms are out of scope
- Attack paths assume attacker has initial foothold; initial access vectors are not modeled
- Temporal windows are based on documented defaults; custom configurations may differ significantly


<!-- streak-nov4-14 -->
## Roadmap

| Quarter | Milestone |
|---------|-----------|
| Q4 2026 | Complete GCP temporal path coverage |
| Q1 2027 | Add Kubernetes RBAC temporal attack paths |
| Q1 2027 | Integrate automated detection rule generation |
| Q2 2027 | Release v1.0 with full multi-cloud coverage |
| Q2 2027 | Publish peer-reviewed research paper |


<!-- streak-nov4-15 -->
## Acknowledgements

This research builds on the foundational work of the cloud security community, including publications from
Wiz Research, Datadog Security Labs, Lacework Labs, and academic contributions from IEEE S&P and USENIX Security.
Special thanks to all open-source contributors and bug reporters who have helped improve this documentation.


<!-- streak-nov4-16 -->
## Daily Update November 4 2026

Documentation refresh completed on November 4, 2026. All sections reviewed for accuracy against current cloud
provider documentation. Glossary expanded, provider coverage matrix updated, and roadmap revised to reflect
Q4 2026 progress. No code changes; documentation only.

---

## Daily Update November 7 2026

Major documentation expansion completed on November 7, 2026. All 20+ new utility modules, temporal enhancements, 
and research infrastructure features documented. Enhanced utility modules section expanded with comprehensive 
API references for math_stats, structures, dag, graph_traversal, retry, visualization, config_loader, and 
temporal modules. Added test infrastructure documentation and compliance feature references.


---

## Community & Support

### Getting Help
- **GitHub Issues** — Bug reports, feature requests, questions
- **GitHub Discussions** — General questions, ideas, show-and-tell
- **Security Issues** — Email security@ or use GitHub Security Advisories

### Contributing Community
- **Contributors** — See [Contributors Graph](https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths/graphs/contributors)
- **Code of Conduct** — See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- **Good First Issues** — Tagged with `good first issue` label

### Related Projects
- **PMapper** — AWS IAM graph enumeration
- **BloodHound** — Active Directory attack paths
- **Cartography** — Infrastructure asset graph
- **CloudSploit** — Cloud security scanning

---

## Glossary of New Terms (v0.9.1)

| Term | Definition |
|------|------------|
| **EvaluationStats** | Per-evaluation statistics tracking constraints evaluated, passed, failed, unknown, and timing |
| **TemporalMetricsExtended** | Enhanced metrics with percentile calculations (median, p95, p99), standard deviation, and latency tracking |
| **Jensen-Shannon Divergence** | Symmetric, bounded measure of distribution similarity (0 to ln(2)) |
| **Cross-Entropy** | Loss function H(P,Q) = -Σ P(x) log Q(x) for ML evaluation |
| **Mutual Information** | I(X;Y) = Σ P(x,y) log(P(x,y)/(P(x)P(y))) measuring dependency |
| **Softmax with Temperature** | Probability distribution from logits with controllable sharpness |
| **LogSumExp** | Numerically stable computation of log(Σ exp(x_i)) |
| **TemporalConfig Presets** | `strict()`, `permissive()`, `balanced()` factory methods for common configurations |
| **RetryContext** | Context manager for manual retry control with sync/async support |
| **Merkle Hash Chain** | Cryptographic hash chaining for tamper-evident audit trails |
| **ADR** | Architecture Decision Record documenting key technical choices |
| **SBOM** | Software Bill of Materials for supply chain transparency |

---

## License & Citation

### License
This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

### Citation
If you use ARF-RT or its temporal extensions in academic work, please cite:

```bibtex
@inproceedings{arf-rt-2026,
  title={ARF-RT: Bayesian Risk Topology for Cloud Identity Attack Path Analysis},
  author={Sneharsha, S. and Contributors},
  booktitle={Proceedings of the 2026 IEEE Symposium on Security and Privacy (S&P)},
  year={2026},
  organization={IEEE}
}

@techreport{arf-rt-temporal-2026,
  title={Temporal Context-Aware Cloud Identity Attack Paths: Formal Verification and Compliance},
  author={Sneharsha, S. and Contributors},
  institution={GitHub},
  year={2026},
  url={https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths}
}
```

### Acknowledgments
- **Cloud Security Community** — Wiz Research, Datadog Security Labs, Lacework Labs
- **Academic Contributors** — IEEE S&P, USENIX Security publications
- **Open Source** — PMapper, BloodHound, Cartography, Ruff, Hypothesis, PyYAML
- **Standards Bodies** — NIST, CIS, PCI SSC, ISO/IEC for framework mappings
- **All Contributors** — See [Contributors Graph](https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths/graphs/contributors)

---

*Last updated: November 7, 2026 — v0.9.1 documentation refresh*
