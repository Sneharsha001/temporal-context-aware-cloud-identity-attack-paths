# CCPF D2 Benchmark Pre-Registration Protocol
## Enterprise-Scale Performance Benchmark for CCPF Under Option C

**Project:** Context-Conditioned Path Feasibility (CCPF) for Probabilistic Cloud Identity Attack-Path Analysis  
**Branch:** `temporal-context-dev`  
**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Document Version:** 1.0 (Pre-Registration)  
**Date:** 2026-10-22  
**Status:** PRE-REGISTRATION ONLY — Awaiting Researcher Authorization (D2)

---

## 1. Executive Summary

This document pre-registers the experimental protocol for **D2: Enterprise-Scale Performance Benchmark** under the accepted Option C operating stance (post-search diagnostic annotation, opt-in, disabled by default). 

The protocol addresses **RQ3b** (Performance at Operational Scale) from the CCPF Research Evaluation Plan:

> **RQ3b - Performance (Operational):** What is the relative overhead on realistic enterprise-scale graphs?
> **Hypothesis H3b (Operational Scale Gate):** On a synthetic enterprise-scale graph (>= 500 nodes, >= 2000 edges, realistic IAM condition distribution), the relative median overhead of post-search annotation enabled versus disabled will be strictly less than 15%.

**Current Status:** Gate G3b is **NOT YET AUTHORIZED** (Decision D2 pending). Historical micro-fixture overhead: +45.71% (minimal), +34.33% (complex). The 15% gate is UNMET on micro-fixtures due to SQLite query floor (~80-120 μs).

**This document is a PRE-REGISTRATION ONLY.** No benchmarks will be executed until explicit researcher authorization (Decision D2).

---

## 2. Workload Matrix

### 2.1 Synthetic Workload Sizes

| Size Class | Node Count | Edge Count | Path Count (Top-K=10) | Expected Baseline Latency | Rationale |
|------------|------------|------------|----------------------|---------------------------|-----------|
| **Small** | 10 | ~30 | ≤10 | ~1-5 ms | Unit correctness, fast iteration |
| **Medium** | 50 | ~200 | ≤10 | ~10-50 ms | Transition to operational scale |
| **Large** | 100 | ~500 | ≤10 | ~50-150 ms | Early enterprise scale |
| **X-Large** | 200 | ~1,000 | ≤10 | ~100-300 ms | Mid enterprise scale |
| **XX-Large** | 500 | ~2,500 | ≤10 | **50-500+ ms** | **Primary gate fixture** |
| **XXX-Large** | 1,000 | ~5,000 | ≤10 | 500+ ms | Stress / scaling limit |

**Primary Gate Fixture:** XX-Large (500 nodes, ~2,500 edges) — minimum for G3b gate evaluation.

### 2.2 Graph Topologies

| Topology | Description | Edge:Node Ratio | Rationale |
|----------|-------------|-----------------|-----------|
| **Tree** | Hierarchical IAM role chains | 1.0-1.5 | Baseline delegation chains |
| **DAG (Shallow)** | Cross-account role assumptions, fan-out ≤3 | 2-3 | Typical AWS org structure |
| **DAG (Deep)** | Long role-chaining paths (depth 10-20) | 1.5-2.5 | Max hop-path stress |
| **Mesh** | Dense cross-account permissions | 5-10 | Worst-case correlation density |
| **Hybrid (Primary)** | Tree backbone + cross-account edges + SCP boundaries | 3-5 | **Primary: realistic AWS org** |

**Primary Topology:** Hybrid (realistic AWS organization with SCPs, permission boundaries, cross-account roles).

### 2.3 Hop Counts (Path Lengths)

| Hop Count | Proportion | Rationale |
|-----------|------------|-----------|
| 1-2 hops | 30% | Direct permissions, single AssumeRole |
| 3-5 hops | 50% | Typical cross-account chains |
| 6-10 hops | 15% | Deep delegation chains |
| 11-20 hops | 5% | Maximum realistic depth |

Path lengths drawn from empirical distribution matching AWS customer data (per AWS documentation on role chaining limits).

### 2.4 Constraint Densities & Types

| Constraint Type | Proportion of Edges | Density (conditions/edge) | Supported by RDCE |
|----------------|---------------------|---------------------------|-------------------|
| **Boolean (MFA)** | 35% | 0.5-1.0 conditions/edge | ✅ Full |
| **IP Subnet (SourceIp)** | 25% | 0.5-2.0 CIDRs/edge | ✅ Full |
| **String Equality** | 20% | 0.5-3.0 values/edge | ✅ Full (exact/prefix) |
| **Temporal** | 10% | 0.2-1.0 windows/edge | ✅ Full |
| **Unsupported (UNKNOWN)** | 10% | 0.5-2.0 conditions/edge | ❌ Returns UNKNOWN |

**Condition Assignment:** Each edge receives 0-3 condition keys drawn from the above distribution. Contradiction rate: ~20% of constrained edges participate in at least one contradiction (under static-origin assumption).

---

## 3. Workload Generation (Deterministic)

### 3.1 Synthetic Graph Generator

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Random Seed** | `CCPF_SYNTH_SEED=42` (fixed) | Reproducibility |
| **Node Types** | IAMUser, IAMRole, S3Bucket, SecretsManager, DynamoDB, Lambda, SNS, SQS, SCP, PermissionBoundary | AWS resource taxonomy |
| **Edge Types** | `sts:AssumeRole`, `s3:GetObject`, `s3:PutObject`, `secretsmanager:GetSecretValue`, `lambda:InvokeFunction`, `dynamodb:GetItem`, `dynamodb:PutItem`, `sns:Publish`, `sqs:SendMessage` | AWS action taxonomy |
| **Regions** | `us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1` | Multi-region realism |
| **SCP Boundaries** | 5-20 per graph (OU hierarchy) | Organizational structure |

### 3.2 Deterministic Generation Procedure

1. **Seed PRNG** with `CCPF_SYNTH_SEED=42`
2. **Generate nodes** according to size class node count and type distribution
3. **Generate edges** using preferential attachment with topology-specific constraints
4. **Assign constraints** to edges per density/type distribution
5. **Inject contradictions** at controlled rate (20% of constrained edges)
6. **Assign observations** per Prompt 8B observation model (DIRECT/INFERRED/HEURISTIC)
6. **Serialize** to ARF-RT scenario JSON format
7. **Verify** fixture passes structural validation (connectivity, acyclicity for DAGs)

**Output:** Scenario JSON files + fixture manifests (`.scenario.json`, `.context.json` pairs for CE7/CE8/CE9 validation)

### 3.3 Fixed Seeds & Reproducibility

| Component | Seed | Purpose |
|-----------|------|---------|
| Graph topology | `CCPF_SYNTH_SEED=42` | Topology reproducibility |
| Constraint assignment | `CCPF_SYNTH_SEED=43` | Constraint reproducibility |
| Contradiction injection | `CCPF_SYNTH_SEED=44` | Contradiction reproducibility |
| Observation generation | `CCPF_SYNTH_SEED=45` | Observation reproducibility |
| Benchmark execution order | `CCPF_BENCH_SEED=42` | Run-order determinism |

---

## 4. Experimental Configurations

### 4.1 Configurations Under Test

| Config ID | Description | CCPF Annotation | CCPF Guard | Purpose |
|-----------|-------------|-----------------|------------|---------|
| **BASELINE** | `ccpf_post_search_annotation=False` | Disabled | N/A | Baseline performance |
| **ANNOTATED** | `ccpf_post_search_annotation=True`, `ccpf_annotation_sink=list` | Enabled | `CCPF_FEASIBILITY_GUARD=True` | Experimental |
| **DIRECT-RDCE** | Direct `RDCE.evaluate()` calls | N/A | N/A | Reference parity |

### 4.2 Configuration Matrix

| Size Class | Topology | Baseline Runs | Annotated Runs | Total Runs |
|------------|----------|---------------|----------------|------------|
| Small (10) | Hybrid | 50 | 50 | 100 |
| Medium (50) | Hybrid | 50 | 50 | 100 |
| Large (100) | Hybrid | 50 | 50 | 100 |
| X-Large (200) | Hybrid | 50 | 50 | 100 |
| **XX-Large (500)** | **Hybrid** | **50** | **50** | **100** |
| XXX-Large (1000) | Hybrid | 20 | 20 | 40 |

**Total Experimental Runs:** 540 paired trials (50 per size class × 2 conditions × 5 primary sizes + 20 for XXL)

---

## 5. Measurement Protocol

### 5.1 Pre-Registered Protocol (from Section 8.2)

| Parameter | Specified Value |
|-----------|----------------|
| Warm-up runs | 20 per condition |
| Measurement runs | 50 per condition |
| Execution order | Interleaved (alternating baseline / annotated) |
| Process isolation | Separate Python subprocess per measurement batch |
| Random seed | Fixed (`CCPF_BENCH_SEED=42`) |
| SQLite connection | Fresh per batch, not per trial |
| Reported metric | Median of measurement runs |
| Confidence interval | Bootstrapped 95% CI over 10,000 resamples |

### 5.2 Primary Metric

**Relative Median Overhead:**
```
Overhead = 100 * (Median(T_annotated) / Median(T_baseline) - 1)
```

**Only authorized gate metric.** Alternative metrics (mean, 95th percentile, absolute delta, per-pair median) reported as supplementary only.

### 5.3 Execution Procedure

For each size class × topology combination:

1. **Generate fixture** using deterministic generator (fixed seeds)
2. **Load into fresh SQLite DB** (fresh connection per batch)
3. **Warm-up phase:** 20 alternating runs (baseline → annotated → baseline → annotated...)
4. **Measurement phase:** 50 paired trials (alternating baseline/annotated)
5. **Record per-trial:** `T_baseline`, `T_annotated`, `path_count`, `verdict_distribution`, `p_worst_q8`, `p_best_q8`, `errors`
6. **Cool-down:** 5s delay between batches

### 5.4 Environment Capture

Per batch, record:
- Python version, interpreter flags
- SQLite version, compile options
- OS, CPU model, available RAM
- SQLite PRAGMA settings (page_size, cache_size, journal_mode)
- Process CPU affinity, priority
- Wall-clock vs CPU time

---

## 6. Metrics & Measurements

### 6.1 Primary Metrics

| Metric | Definition | Unit |
|--------|------------|------|
| **Relative Median Overhead** | `100 * (Median(T_annotated) / Median(T_baseline) - 1)` | % |
| **Absolute Median Overhead** | `Median(T_annotated) - Median(T_baseline)` | ms |
| **Per-Path Annotation Cost** | `Median(T_annotated - T_baseline) / Median(path_count)` | ms/path |

### 6.2 Secondary Metrics

| Metric | Definition |
|--------|------------|
| **Verdict Distribution** | Count/percentage of SAT / UNSAT / UNKNOWN per run |
| **UNSAT Detection Rate** | Paths with UNSAT / Total annotated paths |
| **Coverage Rate** | (SAT + UNSAT) / Total annotated paths |
| **Verdict Stability** | Identical verdicts on repeat evaluation / Total re-evaluations |
| **Annotation Failure Rate** | Failed annotations / Total annotation attempts |
| **Search Invariance** | Path ID sequence equality (baseline vs annotated) |

### 6.3 Correctness Metrics (RQ1, RQ2)

| Metric | Definition |
|--------|------------|
| **Fixture Verdict Accuracy** | Verdict matches ground truth for CE1-CE9 |
| **Reference Parity** | Integrated annotation verdict = Direct RDCE verdict |
| **Search Invariance** | Path IDs, scores, ordering identical (baseline vs annotated) |

---

## 7. Statistical Analysis

### 7.1 Primary Inference

- **Point Estimate:** Median relative overhead across 50 paired trials
- **Uncertainty:** Bootstrapped 95% CI (10,000 resamples)
- **Decision Rule:** Gate PASSES iff upper bound of 95% CI < 15%

### 7.2 Variability Reporting

| Statistic | Reported For |
|-----------|-------------|
| Median, IQR | Primary metric per size class |
| Mean, SD | Supplementary |
| 95% CI (bootstrap) | Primary metric |
| Min, Max | Outlier detection |
| Per-pair % change distribution | Supplementary |

### 7.3 Failed / Outlier Runs

| Condition | Handling |
|-----------|----------|
| Process crash / timeout | Record as failure; exclude from median; report count |
| SQLite error (locked, corrupt) | Record; retry once with fresh DB; exclude if persistent |
| RDCE exception (caught) | Record as `UNKNOWN` verdict; continue |
| RDCE exception (uncaught) | Record as failure; investigate |
| Verdict divergence (integrated vs direct) | **CRITICAL BLOCKER** — halt and investigate |

---

## 8. Acceptance Criteria (from Evaluation Plan)

### 8.1 Gate G3b - Performance Enterprise Scale

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| Relative median overhead < 15% on ≥500-node fixture | **< 15%** | **PENDING** |
| Measurement follows pre-registered protocol (Sec 8.2) | Full compliance | REQUIRED |
| Results reproducible on ≥2 platform configs | Required before claim | REQUIRED |

### 8.2 Gate G4 - Utility (RQ5)

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| Mean coverage rate ≥ 40% across size classes | ≥ 40% | PENDING |
| Verdict stability = 100% | 100% | PENDING |
| UNSAT detection rate ≥ 5% (20% contradictory edges) | ≥ 5% | PENDING |

### 8.3 Gate G2 - Search Invariance (Already PASSED)

- Path IDs identical (exact, ordered) ✅
- Scores identical (exact float equality) ✅
- Ordering identical ✅
- Derived_topk rows identical ✅

### 8.4 Gate G3 (Micro-Fixtures) — UNMET (Recorded)

| Fixture | Overhead | Gate |
|---------|----------|------|
| Minimal | +45.71% | UNMET |
| Complex | +34.33% | UNMET |

**Note:** Micro-fixture gate mathematically infeasible (SQLite floor ~80-120μs > 54μs budget). UNMET recorded transparently.

---

## 9. Unresolved Parameters Requiring Researcher Approval

| Parameter | Current Value | Options | Decision Required |
|-----------|---------------|---------|-------------------|
| **XX-Large node count** | 500 | 400 / 500 / 750 / 1000 | Confirm primary gate fixture size |
| **Edge:node ratio** | 5.0 (2500 edges) | 3.0 / 5.0 / 7.0 | Constraint density calibration |
| **Contradiction rate** | 20% | 10% / 20% / 30% | Contradiction injection rate |
| **Observation strength distribution** | DIRECT=60%, INFERRED=30%, HEURISTIC=10% | Various | Observation strength mix |
| **SCP boundary count** | 10 per 500 nodes | 5 / 10 / 20 | SCP density |
| **Dual-threshold gate** | <15% relative OR <1ms absolute | <15% only / dual / absolute only | Gate definition (Sec 8.3) |
| **Warm-up runs** | 20 | 10 / 20 / 30 | Warm-up sufficiency |
| **Measurement runs** | 50 | 30 / 50 / 100 | Statistical power |
| **Platform configurations** | 1 (current WSL) | 1 / 2 / 3 | G3b reproducibility requirement |

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SQLite query floor makes 15% gate impossible even at scale | Medium | High | Pre-register dual-threshold (relative OR absolute) |
| Synthetic graphs not representative of real AWS topologies | High | Medium | Validate topology against AWS Well-Architected patterns |
| SQLite connection overhead dominates at scale | Medium | Medium | Use connection pooling; measure connection overhead separately |
| Synthetic contradiction rate unrealistic | Medium | Medium | Calibrate against real AWS policy corpus (if authorized) |
| SQLite contention at high concurrency | Low | Medium | Single-threaded benchmark; no concurrency |
| Python interpreter variability (GC, JIT) | Medium | Low | Fixed seed, process isolation, warm-up |
| Zero-score path handling affects heap ordering | Low | Low | Documented in G6; verified under Option C |

---

## 10. Go/No-Go Checklist

| Item | Status | Notes |
|------|--------|-------|
| G1 (Zelkova) literature review | ✅ PASS (qualified) | Full paper read |
| G2 (Search Invariance) | ✅ PASSED | 7 tests pass |
| G3 (Micro-fixture) | ⚠️ UNMET | Documented; Option C accepted |
| G3b (Enterprise) | ⬜ PENDING | Requires D2 authorization |
| G4 (Utility) | ⬜ UNMEASURED | Requires D5 |
| G5 (Novelty) | ⚠️ BLOCKED | Requires G1, G5, G6, G7 |
| G6 (Active Pruning) | ⬜ BLOCKED | Requires G1-G5 |
| G7 (ARF-RT paper) | ⚠️ BLOCKED | Full paper not accessed |
| D1 (Option C) | ✅ ACCEPTED | 2026-10-22 |
| D2 (Enterprise benchmark) | ⬜ PENDING | **Awaiting authorization** |
| D3 (MUST-BE-ADDED fixtures) | ✅ COMPLETED | CE7, CE8, CE9 added |
| D4 (Search invariance tests) | ✅ COMPLETED | 7 tests pass |
| D5 (Utility experiment) | ⬜ PENDING | Requires D5 auth |
| D6 (Novelty review) | ⬜ PENDING | Requires D6 auth |

---

## 11. Authorization Request

**Requesting Authorization for D2: Enterprise-Scale Benchmark (Option D)**

- **Protocol:** This document (v1.0)
- **Workload Matrix:** 6 size classes × Hybrid topology × 50 paired trials
- **Primary Gate Fixture:** XX-Large (500 nodes, ~2500 edges)
- **Gate Threshold:** <15% relative median overhead (primary); dual-threshold option pending
- **Pre-registration:** Complete (this document)
- **Code Changes:** NONE (protocol only)
- **Runs on Authorization:** 540 paired trials (est. 2-4 hours wall time)

**Awaiting explicit researcher authorization (Decision D2) before execution.**

---

## 12. Appendix: Workload Generator Interface (Reference)

```python
# Reference interface for workload generator (not implementation)
from dataclasses import dataclass
from typing import Literal

@dataclass
class WorkloadConfig:
    size_class: Literal["small", "medium", "large", "xlarge", "xxlarge", "xxxlarge"]
    topology: Literal["tree", "dag_shallow", "dag_deep", "mesh", "hybrid"]
    node_count: int
    edge_count: int
    hop_distribution: dict[int, float]  # hop_count -> proportion
    constraint_density: float  # conditions per edge
    constraint_type_dist: dict[str, float]  # type -> proportion
    contradiction_rate: float
    seed: int
    topology_params: dict  # topology-specific params

def generate_workload(config: WorkloadConfig) -> Scenario:
    """Generate deterministic ARF-RT scenario from config."""
    ...
```

---

## 13. Final Notes

This pre-registration protocol is **complete and ready for researcher review**. 

**No benchmarks will be executed until explicit D2 authorization.**

The protocol adheres to:
- ✅ Option C diagnostic-only stance
- ✅ Performance gate UNMET (documented)
- ✅ G7 BLOCKED (no paper access)
- ✅ No active pruning / search modifications
- ✅ All seeds fixed, protocol pre-registered
- ✅ Dual-threshold gate option preserved for researcher decision
- ✅ All parameters explicit; unresolved items flagged for decision

**Awaiting Decision D2 authorization to proceed.**

---

*End of D2 Benchmark Pre-Registration Protocol v1.0*  
*Document path: docs/CCPF_D2_BENCHMARK_PRE_REGISTRATION.md*  
*Branch: temporal-context-dev @ e95b443*  
*Authored: 2026-10-22*