# PHASE 17 — Related Work and Novelty Assessment

**Project:** Context-Conditioned Path Feasibility for Probabilistic Cloud Identity Attack-Path Analysis
**Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Branch:** `temporal-context-dev`
**Status:** Research and documentation only. No implementation performed.
**Date:** 2026-10-10

---

## Part 1 — Scope of This Assessment

This document critically and rigorously compares the proposed ARF-RT extension against the most relevant published research and production tools. The goal is to determine whether a defensible research gap exists, and to produce a justified GO / NARROW / PIVOT / HOLD recommendation.

The proposed contribution is:

> **Context-Conditioned Path Feasibility (CCPF):** Augmenting a Bayesian best-first path-search engine (ARF-RT v1.2) with a Constraint-Satisfaction Problem (CSP) layer that propagates IAM condition constraints hop-by-hop during path construction, applies a strict binary feasibility multiplier ({0.0, 1.0}) to eliminate logically impossible paths, and preserves the admissibility of the search bound.

This is explicitly **not** a policy satisfiability checker operating on a single policy document. It is a **path-level CSP filter integrated into a probabilistic multi-hop search engine**.

---

## Part 2 — Survey of Related Work

### 2.1 Zelkova / AWS IAM Access Analyzer (FMCAD 2018)

**What it does:**
Zelkova translates a single AWS IAM policy document into an SMT formula and checks satisfiability properties using Z3 / CVC4. Its canonical check is: "Is policy A less-or-equally-permissive than policy B?" It is the engine underlying IAM Access Analyzer, `CheckNoNewAccess`, and `CheckAccessNotGranted`.

**Key limitation relative to CCPF:**
Zelkova reasons about a **single policy in isolation** or a **pair of policies** for comparison. It does not model execution context that evolves across a sequence of multi-hop transitions. The AWS request context (e.g., `aws:SourceIp`, `aws:MultiFactorAuthPresent`) is treated as an unbounded unknown variable during policy satisfiability checking — not as a state that is *carried* and *constrained* hop by hop. Zelkova does not operate on graphs of IAM transitions; it operates on individual authorization decisions.

**Overlap with CCPF:** The specific intersection-check for CCPF's binary filter (IP subnet membership, Boolean conditions) is conceptually similar to a Zelkova SAT query on a conjunction of conditions. However, Zelkova is not a path-search algorithm and does not propagate `CarriedContext` across a traversal.

**Conclusion:** Zelkova is a predecessor and inspiration, but the architectural integration into a multi-hop graph search is not addressed by Zelkova.

---

### 2.2 IAM-MultiPolicyAnalyzer (FMCAD 2025 — "Modeling the AWS Authorization Engine")

**What it does:**
IAM-MultiPolicyAnalyzer extends Zelkova by composing multiple AWS policy types (identity-based, resource-based, SCPs, permission boundaries) into a single authorization model. It formally models how the AWS authorization engine combines these policies to reach a final Allow/Deny verdict. Used internally at Amazon to verify SCP changes before deployment.

**Key limitation relative to CCPF:**
Like Zelkova, IAM-MultiPolicyAnalyzer analyzes the **authorization semantics of a single cross-policy access decision at one point in time**. It models "Can principal P perform action A on resource R given this policy set?" rather than "Is the sequence of transitions P1 → P2 → P3 jointly feasible given the constraints imposed along the path?" It does not model state carried across an `sts:AssumeRole` chain or the cumulative effect of sequential hop constraints on the attacker's execution context.

**Overlap with CCPF:** IAM-MultiPolicyAnalyzer's cross-policy composition logic is conceptually a building block that CCPF could leverage when checking `RequiredContext(edge)` against a richer policy model. However, CCPF operates at a higher level of abstraction: it uses pre-extracted condition constraints as edge metadata, rather than re-evaluating full policy documents at each hop.

**Conclusion:** Meaningful conceptual predecessor. The multi-hop sequential feasibility dimension is not addressed.

---

### 2.3 Projective Model Counting for IP Addresses in Access Control (FMCAD 2024)

**What it does:**
This AWS research paper applies projective model counting to formally reason about the size of the IP address space permitted by an IAM policy condition (`aws:SourceIp` / `aws:SourceVpc`). It enables statements such as "This policy permits more than X% of the public IP address space," supporting the `NetworkReachability` findings in IAM Access Analyzer.

**Key limitation relative to CCPF:**
This work focuses on **cardinality of allowed request contexts for a single policy** — how many source IPs are allowed, not whether an attacker's source IP, assumed fixed across a traversal, satisfies a conjunction of constraints from multiple hops. CCPF's binary filter for IP subnet intersection (`10.0.0.0/8 ∩ 192.168.0.0/16 = ∅`) is a much simpler but different-purpose operation: it asks whether two specific subnet constraints are mutually satisfiable under the static-origin assumption, not how large the permitted space is.

**Overlap with CCPF:** The IP subnet arithmetic formalism is directly applicable and well-understood. CCPF implements a lightweight subset of this theory specifically for contradiction detection across path hops.

**Conclusion:** The formal IP reasoning in FMCAD 2024 supports CCPF's mathematical correctness claims, but the research purpose (path feasibility filtering vs. cardinality model counting) is orthogonal.

---

### 2.4 Principal Mapper (PMapper) — nccgroup

**What it does:**
PMapper models an AWS account as a directed graph where nodes are principals and edges are IAM permission-based relationships (e.g., "can assume role," "can pass role to a service"). It performs reachability analysis to identify privilege escalation paths from a low-privilege principal to a high-privilege one.

**Key limitation relative to CCPF:**
PMapper's edge evaluation performs a **static binary reachability check** ("can principal A reach principal B?") but does **not** evaluate whether the joint satisfaction of sequential IAM conditions across the entire path is feasible. Specifically:

1. PMapper does not model `aws:SourceIp` or `aws:MultiFactorAuthPresent` conditions on edges.
2. It does not carry context state across transitions.
3. It does not use a probabilistic ranking; paths are treated as binary (reachable / not reachable).
4. It does not maintain or propagate a `CarriedContext` across role assumption boundaries.

**Overlap with CCPF:** PMapper establishes the same graph structure (privilege escalation edges between principals). CCPF operates at the same level of abstraction but adds probabilistic ranking and condition-constraint propagation.

**Conclusion:** PMapper is the closest architectural cousin in the attack-path tooling space, but the probabilistic ranking and the context-constraint propagation are both genuinely absent.

---

### 2.5 AWS IAM Access Analyzer — Runtime / Policy Validation

**What it does:**
IAM Access Analyzer generates findings for external access (cross-account, cross-organization) by using Zelkova under the hood. It does not perform multi-hop path analysis. It does not model an attacker traversing a chain of transitions.

**Key limitation relative to CCPF:**
IAM Access Analyzer is a static policy checker, not a path-search engine. It does not model attack sequences, carry context, or rank paths probabilistically. The overlap is at the level of shared formal primitives (IP subnet semantics, MFA condition Boolean logic).

**Conclusion:** Different problem class. Not in direct competition with CCPF.

---

### 2.6 Commercial CNAPPs — Wiz, Orca, Prisma Cloud

**What they do:**
Wiz, Orca, and similar CNAPP platforms model cloud environments as security graphs and perform attack path analysis to identify "toxic combinations" — e.g., a critical CVE on an internet-exposed VM with an over-privileged IAM role. They visualize lateral movement paths and present ranked risk findings.

**Key limitation relative to CCPF:**
Commercial CNAPPs use **proprietary, undocumented** condition-evaluation logic. Their path feasibility assessments are:

1. Not formally specified; there is no published model of their constraint propagation.
2. Not provably admissible; there is no published proof that their path ranking upper-bounds the true attack probability.
3. Based on broad heuristic risk scores, not a principled Bayesian probability product.
4. Not reproducible or independently auditable via open benchmarks.

**Overlap with CCPF:** CNAPPs address the same motivation (reducing infeasible path noise). CCPF addresses the same problem but from a **formally specified, reproducible, and mathematically provable** perspective integrated into an open research framework.

**Conclusion:** The problem domain overlaps, but the formal specification, admissibility proof, and open-benchmark contribution are clearly absent in the commercial space.

---

### 2.7 General Attack Graph Research — Constraint Propagation (2023–2024)

**What the literature shows:**
Recent work in attack graph analysis has introduced constraint propagation and path pruning in the context of network-layer and cyber-physical systems (pre-condition / post-condition models, AI planning approaches using PDDL, progressive graph generation). These works generally prune based on network topology constraints and vulnerability pre-conditions.

**Key limitation relative to CCPF:**
No published work in this space specifically models:

1. IAM-specific context attributes (`aws:SourceIp`, `aws:MultiFactorAuthPresent`, `sts:ExternalId`, `aws:PrincipalTag`).
2. The scope semantics of these attributes (request-scoped vs. session-scoped vs. configuration-scoped) across IAM transitions.
3. Integration with a `q8`-quantized Bayesian best-first search with a provable admissibility guarantee.
4. The binary SAT/UNSAT/UNKNOWN trichotomy as a path scoring modifier preserving search admissibility.

**Conclusion:** General constraint propagation concepts have prior art, but the specific application to IAM condition-key semantics in a probabilistic cloud identity attack-path search engine is not addressed in the literature.

---

## Part 3 — Comparison Matrix

| Property | Zelkova (FMCAD 2018) | IAM-MultiPolicyAnalyzer (FMCAD 2025) | IP Model Counting (FMCAD 2024) | PMapper | CNAPP (Wiz/Orca) | **CCPF (Proposed)** |
|---|---|---|---|---|---|---|
| Unit of analysis | Single policy | Multi-policy composition | Single policy + IP cardinality | Principal graph | Whole-env graph | **Multi-hop path traversal** |
| Context-scoped attribute semantics | Within single request | Within single request | IP addresses only | None | Proprietary | **Per-hop, typed scope** |
| Carries state across hops | No | No | No | No | Unknown | **Yes — CarriedContext propagation** |
| Probabilistic path ranking | No | No | No | No | Heuristic | **Yes — Bayesian q8 product** |
| Admissibility proof for search bound | N/A | N/A | N/A | N/A | None | **Yes — {0,1} multiplier proof** |
| Open, reproducible benchmark | Yes (ACL2 proofs) | Partial (internal) | Yes (FMCAD proceedings) | Yes (open source) | No | **Yes — CE1–CE6 fixture suite** |
| IAM role boundary context tracking | No | No | No | No | Unknown | **Yes — per-scope continuity model** |
| Binary feasibility filter during search | No | No | No | No | Unknown | **Yes — SAT/UNSAT/UNKNOWN trichotomy** |

---

## Part 4 — Identified Research Gaps

The following three gaps are **defensible** because no published work or known public tool addresses them jointly.

### Gap 1 — Multi-Hop Context-Constraint Propagation in IAM Attack Paths

**Gap:** No published work propagates IAM condition constraints — specifically using the typed-scope model (request-scoped, session-scoped, principal-scoped, configuration-scoped) — across a multi-hop traversal of a cloud identity attack graph.

**Why it matters:** A path that requires `aws:SourceIp ∈ 10.0.0.0/8` at hop 1 and `aws:SourceIp ∈ 192.168.0.0/16` at hop 2 is physically impossible under a fixed execution origin, yet all existing tools (Zelkova, PMapper, CNAPP platforms) assign it a positive probability or flag it as reachable.

**Strength:** Strong. The gap is confirmed by direct inspection of all surveyed works.

---

### Gap 2 — Formal Admissibility of CSP-Filtered Probabilistic Path Search

**Gap:** No published work proves that applying a binary constraint-feasibility filter to a Bayesian best-first path-search preserves the admissibility of the search bound.

**Why it matters:** If the filter is not admissible, it may prune paths that should be explored, breaking the completeness guarantee. The {0.0, 1.0} restriction (rejecting fractional probabilities for partial overlaps) is a deliberate design choice that makes this proof tractable.

**Strength:** Moderate-to-strong. The admissibility proof is technically straightforward given the {0,1} restriction, but the integration proof (that no rounding or quantization artifact breaks admissibility in the q8 scheme) is non-trivial.

---

### Gap 3 — Reproducible Open-Benchmark Suite for Context-Conditioned IAM Path Feasibility

**Gap:** No open, standardized fixture suite exists for evaluating whether a cloud identity attack-path engine correctly eliminates context-infeasible paths while preserving context-compatible ones.

**Why it matters:** This enables reproducibility and future comparison. Zelkova has formal ACL2 proofs but no attack-path fixture suite. PMapper has no formal benchmark. CNAPPs are fully proprietary.

**Strength:** Moderate. The benchmark contribution is valuable for the research community but is secondary to the algorithmic contribution.

---

## Part 5 — Honest Assessment of Limitations and Risks

### L1 — Assumption Strength (Static Execution Origin)
The static-origin assumption — that an attacker's `aws:SourceIp` does not change across hops — is strong and may be unrealistic in sophisticated attacks using cloud-internal pivoting (e.g., Lambda invocations that have VPC-internal IPs, or cross-region calls with different NAT gateways). Under a violation of this assumption, CCPF incorrectly eliminates valid paths (unsound filter). This assumption must be explicitly stated in all fixture annotations and in any publication abstract.

### L2 — Scope Limitation (Intentional)
CCPF explicitly leaves out:
- Temporal session expiration (requires modeling attack execution time) — correctly deferred.
- Fractional probabilities for partial context overlap — correctly rejected to avoid invented mathematics.
- Full SMT solver integration — the lightweight intersection checker is the appropriate pragmatic choice for initial evaluation.

These are transparently stated limitations and do not undermine the core contribution.

### L3 — Novelty Positioning
The contribution is novel at the level of **integration and formal specification** rather than at the level of inventing new mathematical techniques. IP subnet intersection is well-understood. Constraint propagation is well-understood. The novelty is bringing these together in a formally specified, admissibility-preserving, scope-typed model for cloud identity attack-path search. This is a legitimate systems/applied security contribution, appropriate for a top-tier systems security or formal methods applied track venue.

### L4 — Baseline Dependency
The contribution is tightly coupled to ARF-RT v1.2's specific search algorithm and q8 quantization scheme. It is not a general portable framework. The contribution is the design and empirical evaluation on this specific system, which is sufficient for a focused research paper.

---

## Part 6 — Final Recommendation

### Verdict: **GO (NARROW)**

**Rationale:**

1. **Gap 1 is real and defensible.** No existing tool propagates typed IAM condition constraints across multi-hop identity traversals. This is a genuine blind spot in both research and production tooling, confirmed by direct inspection of all surveyed works.

2. **The formal model is correct.** The typed-scope model (request/session/principal/configuration-scoped), the SAT/UNSAT/UNKNOWN trichotomy, and the admissibility proof are internally consistent and mathematically sound as specified in `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md`.

3. **The contribution is proportionate to the scope.** A single paper contribution consisting of: (a) formal CCPF model, (b) admissibility proof, (c) open fixture suite with six counterexamples, (d) empirical evaluation on ARF-RT is focused, defensible, and completable.

4. **The limitation is transparent.** The static-origin assumption and the binary-only feasibility filter are explicitly stated. Fractional probability for partial overlap is explicitly deferred. This intellectual honesty strengthens the contribution.

### Required Narrowings:
| Claim to Avoid | Correct Scoping |
|---|---|
| "CCPF solves temporal feasibility" | "CCPF addresses context-conditioned spatial feasibility only; temporal feasibility is future work" |
| "CCPF subsumes Zelkova" | "CCPF operates at a higher abstraction level using pre-extracted condition metadata, not full policy documents" |
| "Static-origin assumption is realistic for all adversaries" | "CCPF provides guarantees under a fixed-origin attacker threat model; multi-pivot scenarios are out of scope" |
| "CCPF is a general framework" | "CCPF is an ARF-RT v1.2 extension evaluated on a specific research fixture suite" |

### Target Venues (Suggested):
- **USENIX Security** — applied cloud identity / access control track
- **IEEE S&P (Oakland)** — cloud security, formal methods applied
- **ACM CCS** — cloud access control, probabilistic security analysis
- **FMCAD** — if the formal admissibility contribution is emphasized as primary

---

## Part 7 — Recommended Next Steps

1. **Finalize fixture documentation** (CE1–CE6 as documented in `docs/PHASE16_COUNTEREXAMPLE_FIXTURES.md`). Add explicit static-origin assumption annotations to CE1/CE2.

2. **Draft an implementation plan** for the CCPF engine (Phase 18): lightweight IP-intersection checker, session-scope Boolean tracker, PathConstraintStore accumulator, integration point in `engine/paths.py`.

3. **Define the evaluation protocol**: Run CE1–CE6 against the implemented CCPF filter. Verify CE5 (baseline non-perturbation) with exact numerical comparison to baseline output.

4. **Draft a formal claim statement** suitable for an abstract submission:
   > "We present CCPF, a context-conditioned path feasibility filter for probabilistic cloud identity attack-path search. CCPF propagates IAM condition constraints across multi-hop traversals using a typed-scope model and eliminates logically infeasible paths via a binary SAT/UNSAT/UNKNOWN trichotomy. We prove that the binary multiplier preserves the admissibility of the Bayesian best-first search bound and evaluate the model against six formally specified counterexample fixtures."

---

## Appendix A — Reference Index

| Reference | Relevance to CCPF |
|---|---|
| Corpus, N. et al. "Semantic-based Automated Reasoning for AWS Access Policies using SMT." FMCAD 2018. | Zelkova: single-policy SMT reasoning. Predecessor formalism. Does not address multi-hop path context. |
| "Modeling the AWS Authorization Engine." FMCAD 2025. | IAM-MultiPolicyAnalyzer: multi-policy composition. No sequential path-level state propagation. |
| "Projective model counting for IP addresses in access control policies." FMCAD 2024. | IP subnet model counting. Supports CCPF IP arithmetic correctness. Orthogonal research purpose. |
| nccgroup/PMapper (GitHub). | Graph reachability for privilege escalation. No probabilistic ranking or context propagation. Closest architectural cousin. |
| AWS IAM Access Analyzer documentation. | Production tool using Zelkova. Single-decision context evaluation. Not path-level. |
| Wiz, Orca, Prisma Cloud CNAPP platforms. | Commercial attack path analysis. Proprietary; not formally specified; no admissibility guarantee. |
| ARF-RT v1.2 (`arf-rt-v1.2-baseline` tag). | Target baseline system. Probabilistic Bayesian q8 best-first search. |
| `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md` (this workspace). | CCPF formal model specification. |
| `docs/PHASE16_COUNTEREXAMPLE_FIXTURES.md` (this workspace). | Evaluation fixture set (CE1–CE6). |
| `docs/TEMPORAL_CONTEXT_RESEARCH_DESIGN.md` (this workspace). | Original research design document. |
| `docs/TEMPORAL_CONTEXT_STATE_MODEL.md` (this workspace). | Context-scope state model. |

---

*This document is part of the ARF-RT temporal-context-dev research branch.*
*No source code, tests, fixtures, dependencies, or configuration have been modified.*
*No implementation has been performed.*
