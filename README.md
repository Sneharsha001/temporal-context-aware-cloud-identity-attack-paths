# ARF-RT — Risk Topology Engine

A Bayesian reasoning engine for cloud identity attack path analysis. ARF-RT ingests privilege graphs (PMapper, AWS Organizations), models policy constraints as correlated belief structures, and computes the most informative probe sequence to reduce uncertainty about path viability.

**SEMANTICS_VERSION:** 1.0.0  
**Scope:** Replay-only. No live cloud SDK calls.

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

## Quick Start

```bash
pip install -e ".[dev]"

# Run analysis
arf-rt analyze scenario.json --format both

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
```
