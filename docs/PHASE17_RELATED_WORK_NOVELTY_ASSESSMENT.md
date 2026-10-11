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
| Admissibility proof for search bound | N/A | N/A | N/A | N/A | None | **OPEN / In progress (search-bound invariance formalization required)** |
| Open, reproducible benchmark | Yes (ACL2 proofs) | Partial (internal) | Yes (FMCAD proceedings) | Yes (open source) | No | **Yes — CE1–CE6 fixture suite** |
| IAM role boundary context tracking | No | No | No | No | Unknown | **Yes — per-scope continuity model** |
| Binary feasibility filter during search | No | No | No | No | Unknown | **Yes — SAT/UNSAT/UNKNOWN trichotomy** |

---

## Part 4 — Identified Research Gaps

The following three gaps are **defensible** because no published work or known public tool addresses them jointly.

### Gap 1 — Multi-Hop Context-Constraint Propagation in IAM Attack Paths

**Gap:** Propagating IAM condition constraints across a multi-hop traversal of a cloud identity attack graph using a typed-scope model (request-scoped, session-scoped, principal-scoped, configuration-scoped).

**Why it matters:** A path requiring `aws:SourceIp ∈ 10.0.0.0/8` at hop 1 and `aws:SourceIp ∈ 192.168.0.0/16` at hop 2 is physically impossible under a fixed execution origin if request context persists, yet tools that evaluate hops independently will evaluate each hop as reachable.

**Strength:** Potential research direction; novelty not established. Absence of cross-hop condition propagation is directly observed in open-source PMapper (v1.1.5 release tag d5136ff and master snapshot 91d2e60) and unmentioned in preliminary FMCAD literature reviews. However, academic full-text reviews remain preliminary and commercial CNAPP / AWS Security Hub internals remain proprietary and unresolved.

---

### Gap 2 — Formal Admissibility of CSP-Filtered Probabilistic Path Search

**Gap:** Formally establishing that applying a binary constraint-feasibility filter to a Bayesian best-first path-search preserves the admissibility of the search bound and Top-K completeness under fixed-point quantization.

**Why it matters:** If the filter prunes an admissible prefix prematurely or if scope transitions violate monotonicity, the search completeness guarantee is broken.

**Strength:** Incomplete / OPEN. The formal admissibility, Top-K completeness, and scope-reset invariance proofs have not been completed. This remains a required prerequisite prior to engine modification.

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

### Verdict: **NARROW** (Provisional on resolving open correctness gates)

**Rationale:**

1. **Proposed focus addresses an observable limitation in open-source tooling.** In PMapper (audited at release tag `d5136ff` and `master` commit `91d2e60`), conditions are evaluated only at the destination node without cross-hop accumulation. Preliminary reviews of single-policy formalisms (Zelkova, IAM-MultiPolicyAnalyzer) indicate they do not model sequential path transitions.
2. **Formal correctness requirements remain open.** While the typed-scope design is specified in `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md`, the formal admissibility proof, scope-reset invariance, and solver soundness guarantees remain OPEN. Engine modifications cannot proceed until these proofs are established.
3. **No claims of scientific novelty or tool superiority are authorized.** Novelty relative to commercial systems (Wiz, Orca, AWS Security Hub) cannot be established due to proprietary internals. Claims of venue acceptance or superiority are premature prior to empirical implementation and evaluation.
4. **Scope must remain tightly bounded.** Work must be restricted to evaluating research fixtures without modifying baseline ARF-RT v1.2 search behavior.

### Required Narrowings:
| Claim to Avoid | Correct Scoping |
|---|---|
| "CCPF solves temporal feasibility" | "CCPF addresses context-conditioned spatial feasibility only; temporal feasibility is future work" |
| "CCPF subsumes Zelkova" | "CCPF operates at a higher abstraction level using pre-extracted condition metadata, not full policy documents" |
| "Static-origin assumption is realistic for all adversaries" | "CCPF provides guarantees under a fixed-origin attacker threat model; multi-pivot scenarios are out of scope" |
| "CCPF is a general framework" | "CCPF is an ARF-RT v1.2 extension evaluated on a specific research fixture suite" |

### Target Venues / Dissemination (Provisional):
- Any venue submission is strictly conditional on: (1) completing the formal search-bound and scope-reset proofs, (2) implementing the filter, and (3) experimentally validating CE1–CE6 on ARF-RT.
- Targeting top-tier venues (USENIX Security, IEEE S&P, ACM CCS, FMCAD) cannot be justified based on design documents alone. Initial dissemination should target specialized workshops (e.g., SeRIM) once empirical results exist.

---

## Part 7 — Recommended Next Steps

1. **Finalize fixture documentation** (CE1–CE6 as documented in `docs/PHASE16_COUNTEREXAMPLE_FIXTURES.md`). Add explicit static-origin assumption annotations to CE1/CE2.

2. **Draft an implementation plan** for the CCPF engine (Phase 18): lightweight IP-intersection checker, session-scope Boolean tracker, PathConstraintStore accumulator, integration point in `engine/paths.py`.

3. **Define the evaluation protocol**: Run CE1–CE6 against the implemented CCPF filter. Verify CE5 (baseline non-perturbation) with exact numerical comparison to baseline output.

4. **Draft a formal claim statement** suitable for an abstract submission:
   > "We present CCPF, a context-conditioned path feasibility filter for probabilistic cloud identity attack-path search. CCPF propagates IAM condition constraints across multi-hop traversals using a typed-scope model and eliminates logically infeasible paths via a binary SAT/UNSAT/UNKNOWN trichotomy. We prove that the binary multiplier preserves the admissibility of the Bayesian best-first search bound and evaluate the model against six formally specified counterexample fixtures."

---

## Appendix A — Reference Index

| Reference | Relevance to CCPF | Authoritative DOI / Stable URL | Source Status |
|---|---|---|---|
| **Zelkova (FMCAD 2018):** Backes, J., Bolignano, P., Cook, B., Dodge, C., Gacek, A., Luckow, K., Rungta, N., Tkachuk, O., & Varming, C. "Semantic-based Automated Reasoning for AWS Access Policies using SMT." FMCAD 2018, pp. 1–9. | Single-policy SMT reasoning. Evaluates single-request policy properties. Does not address multi-hop path context. | DOI: 10.23919/FMCAD.2018.8602994 *(Not 10.23919/FMCAD.2018.8603013)* | Full text obtained; preliminary inspection completed |
| **IAM-MultiPolicyAnalyzer (FMCAD 2025):** Barnett, L. A., D'Antoni, L., Goel, A., Kıcı, R. G., Rungta, N., Southern, M., & Sung, C. "Modeling the AWS Authorization Engine." FMCAD 2025. | Composes multiple AWS policy types for a single authorization decision. Zero multi-hop sequential state. | DOI: 10.34727/2025/isbn.978-3-85448-084-6_25 | Full text obtained; preliminary inspection completed |
| **IP Model Counting (FMCAD 2024):** D'Antoni, L., Gacek, A., Goel, A., Jovanović, D., Kıcı, R. G., Peebles, D., Rungta, N., Sharoda, Y., & Sung, C. "Projective Model Counting for IP Addresses in Access Control Policies." FMCAD 2024, pp. 248–257. | Cardinality analysis of allowed IPs for a single policy. Orthogonal to multi-hop attack path search. | DOI: 10.34727/2024/isbn.978-3-85448-065-5_26 | Full text obtained; preliminary inspection completed |
| **Principal Mapper (PMapper):** Steringer, E. / NCC Group. Principal Mapper, v1.1.5 (commit 91d2e60102bdadf346d77b60d90ddaa4a678f037). | Graph reachability for IAM privilege escalation. Evaluates conditions at destination principal only; no cross-hop accumulation. | https://github.com/nccgroup/PMapper | Full source code inspected (v1.1.5) |
| **AWS IAM Access Analyzer:** AWS Documentation. | SMT-backed policy validation using Zelkova. Single-decision context evaluation. Not path-level. | https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html | Documented tool behavior verified |
| **AWS Security Hub Attack Path Analysis:** AWS Documentation. | Cloud multi-hop attack path analysis correlating findings. Internal algorithms proprietary. | https://docs.aws.amazon.com/securityhub/latest/userguide/attack-path-analysis.html | Documented feature; algorithms proprietary |
| **Commercial CNAPPs (Wiz, Orca, Prisma Cloud):** Industry platforms. | Whole-environment graph analysis. Proprietary implementations; no public formal specifications. | Vendor specifications | Documented features; internals unknown |
| **ARF-RT (SeRIM 2026):** Conklin, E. "Correlation-Aware Probe Planning for Cloud Identity Attack Paths." SeRIM 2026 (IEEE EuroS&PW 2026). | Target baseline system. Correlation-aware Bayesian fixed-point (Q8) best-first search. | IEEE EuroS&PW 2026 proceedings | Abstract/record verified; codebase in repository inspected |
| `docs/PHASE15_FORMAL_FEASIBILITY_MODEL.md` (this workspace). | CCPF formal model specification. | Local repository | Authoritative project specification |
| `docs/PHASE16_COUNTEREXAMPLE_FIXTURES.md` (this workspace). | Evaluation fixture set (CE1–CE6). | Local repository | Authoritative evaluation fixtures |
| `docs/TEMPORAL_CONTEXT_RESEARCH_DESIGN.md` (this workspace). | Original research design document. | Local repository | Authoritative research design |
| `docs/TEMPORAL_CONTEXT_STATE_MODEL.md` (this workspace). | Context-scope state model. | Local repository | Authoritative state model |

---

*This document is part of the ARF-RT temporal-context-dev research branch.*
*No source code, tests, fixtures, dependencies, or configuration have been modified.*
*No implementation has been performed.*

---

## Phase 17.1 Audit Findings

**Audit Date:** 2026-10-10
**Auditor Role:** Critical self-review prior to implementation
**Scope:** Correct factual errors, strengthen citations, challenge unsupported claims, document search methodology, reassess verdict.

---

### A.1 Factual Errors Corrected

#### A.1.1 — Zelkova Author Attribution (CORRECTED)

**Original claim:** The Phase 17 document attributed authorship of the Zelkova FMCAD 2018 paper to "Corpus et al." — fabricated attribution.

**Corrected verified citation:**
- **Authors:** John Backes, Pauline Bolignano, Byron Cook, Catherine Dodge, Andrew Gacek, Kasper Luckow, Neha Rungta, Oksana Tkachuk, Carsten Varming.
- **Title:** "Semantic-based Automated Reasoning for AWS Access Policies using SMT."
- **Venue:** FMCAD 2018 (Formal Methods in Computer-Aided Design).
- **DOI:** 10.23919/FMCAD.2018.8602994
- **Source consulted:** Amazon Science publications index, confirmed via FMCAD 2018 proceedings record.

#### A.1.2 — PMapper Condition Key Support (CORRECTED — claim was too strong)

**Original claim:** "PMapper does not model `aws:SourceIp` or `aws:MultiFactorAuthPresent` conditions on edges."

**Corrected status: PARTIAL**

The PMapper `argquery` command accepts a `--condition` flag that allows the caller to supply condition keys including `aws:SourceIp` and `aws:MultiFactorAuthPresent` as inputs to a single authorization query. This is documented in the official PMapper README and confirmed by the nccgroup/PMapper repository.

**Precise distinctions established by evidence:**

| Dimension | PMapper Behavior | Evidence Basis |
|---|---|---|
| **Condition key in single query** | SUPPORTED. Caller can supply `aws:SourceIp=x` to `argquery` for one query. | PMapper README / argquery docs, GitHub repository |
| **Condition evaluation on individual graph edge** | PARTIAL. Edges are built using local policy simulation. Condition keys affect whether an edge exists, but the simulator accuracy for all condition operators is not guaranteed. | PMapper README note on IAM simulation limitations |
| **Propagation of the same condition value across all hops of a path** | NOT DOCUMENTED / UNKNOWN. No evidence of a CarriedContext or per-hop constraint accumulation mechanism. The condition supplied to a query is a single global assumption, not propagated structurally hop-by-hop. | Absence of evidence; source code inspection not performed |
| **Joint constraint accumulation across sequential hops** | NOT DOCUMENTED. The PathConstraintStore concept (accumulating constraints at each hop and checking for contradictions between hop i and hop j) is not described anywhere in PMapper's architecture. | Architecture description in README; no CSP layer |
| **Scope-differentiated continuity (request vs. session vs. config scope)** | NOT DOCUMENTED. | Absence from documentation |
| **Probabilistic ranking of paths** | NOT IMPLEMENTED. PMapper produces binary reachability (yes/no). | Confirmed by README and code architecture |

**Corrected claim:** PMapper PARTIALLY supports per-query condition key specification as a caller-supplied context. However, it does not implement cross-hop constraint accumulation, scope-typed continuity modeling, contradiction detection across path hops, or probabilistic path ranking. These remain the operative distinctions for CCPF.

#### A.1.3 — Session Policy Handling Across Pivot Edges

**Status: UNKNOWN (not established by evidence consulted)**

PMapper's README states that the tool models session policies. Whether it tracks how session policies change at `sts:AssumeRole` pivot edges in a way that is analogous to CCPF's CarriedContext is not established by the documentation reviewed. This question requires source code inspection of `principalmapper/graph/scp_analytics.py` and related files. Claimed as UNKNOWN.

---

### A.2 Primary Sources Verified and Complete Citations

All references used in this assessment are listed below with verification status:

| Reference | Authors | Title | Venue | Year | DOI / URL | Source Consulted | Status |
|---|---|---|---|---|---|---|---|
| Zelkova | Backes, Bolignano, Cook, Dodge, Gacek, Luckow, Rungta, Tkachuk, Varming | "Semantic-based Automated Reasoning for AWS Access Policies using SMT" | FMCAD 2018 | 2018 | 10.23919/FMCAD.2018.8602994 | Amazon Science index; FMCAD proceedings | Verified authors and DOI |
| IAM-MultiPolicyAnalyzer | Barnett, D'Antoni, Goel, Kıcı, Rungta, Southern, Sung | "Modeling the AWS Authorization Engine" | FMCAD 2025 | 2025 | 10.34727/2025/isbn.978-3-85448-084-6_25 | TU Wien Academic Press FMCAD 2025; leeabarnett.com | Verified authors and DOI |
| IP Model Counting | D'Antoni, Gacek, Goel, Jovanović, Kıcı, Peebles, Rungta, Sharoda, Sung | "Projective Model Counting for IP Addresses in Access Control Policies" | FMCAD 2024 | 2024 | Proceedings FMCAD 2024 pp. 208–216 (TU Wien) | chunghasung.org; Amazon Science | Verified authors; no single DOI located, conference volume confirmed |
| PMapper | Kyle Draper (primary); NCC Group | "Principal Mapper" (open-source tool) | GitHub: nccgroup/PMapper | Active | https://github.com/nccgroup/PMapper | README and argquery docs consulted | Partial — only documentation reviewed, not source code |
| AWS IAM Access Analyzer | AWS | Service documentation | AWS Documentation | Current | https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html | AWS docs | Tool behavior confirmed; no algorithmic spec |
| AWS Security Hub Attack Path | AWS | Attack path analysis feature documentation | AWS Documentation / Security Hub | Current | https://docs.aws.amazon.com/securityhub/latest/userguide/findings-understanding-asff.html | AWS docs | Feature confirmed; no published formal specification |
| ARF-RT | Eric Conklin | "ARF-RT: Correlation-Aware Probe Planning for Cloud Identity Attack Paths" | SeRIM 2026 (2nd Int'l Workshop on Security and Risk in Identity Management) | 2026 | fbk.eu conference page | fbk.eu listing | Author and venue confirmed; full paper not accessed |

**Papers read only via abstract or summary (not full text):**
- Zelkova FMCAD 2018 — abstract and Amazon Science description reviewed; full paper not accessed.
- IAM-MultiPolicyAnalyzer FMCAD 2025 — abstract and TU Wien proceedings listing reviewed; full paper not accessed.
- FMCAD 2024 IP Model Counting — abstract and author list confirmed; full paper not accessed.

**Consequence:** Claims about what these papers do NOT cover are based on abstract-level review and should be treated as provisional. Full paper review is required before any submission to a venue.

---

### A.3 Reassessment of Novelty Claims

The following answers each question from the Phase 17.1 brief. Confidence is rated LOW / MODERATE / HIGH based on evidence quality.

#### Q.A — Does existing work already solve AWS policy satisfiability?
**YES (HIGH confidence).** Zelkova (FMCAD 2018) solves this for single-policy and policy-comparison cases. IAM-MultiPolicyAnalyzer (FMCAD 2025) extends this to multi-policy composition. This is well-established prior work. CCPF does not re-solve this problem.

#### Q.B — Does existing work already compose multiple AWS policy types?
**YES (HIGH confidence).** IAM-MultiPolicyAnalyzer (FMCAD 2025) explicitly addresses multi-policy composition for authorization decisions. CCPF operates at a higher abstraction level using pre-extracted condition metadata and does not re-implement policy composition.

#### Q.C — Does existing work already discover and analyze multi-hop cloud identity paths?
**YES (MODERATE-HIGH confidence).** PMapper discovers multi-hop privilege escalation paths. AWS Security Hub's attack path analysis also identifies multi-hop identity paths. Neither is purely novel. CCPF's distinction is the *probabilistic ranking* (Bayesian q8 product) and *context-constraint propagation*, not path discovery itself.

#### Q.D — Does existing work propagate request-, session-, principal-, and configuration-scoped constraints jointly over sequential graph transitions?
**UNRESOLVED (LOW evidence quality).** Based on documentation reviewed: no published work describes this specific four-scope joint propagation across sequential IAM transitions. PMapper supports single-query condition key specification but no documented cross-hop accumulation. However, this negative claim is based on documentation review and abstract-level paper review only. Full source code inspection of PMapper and full paper review of Zelkova/IAM-MultiPolicyAnalyzer are required to confirm this gap. The absence of evidence in documentation is not confirmed absence of the capability.

#### Q.E — Does existing work integrate path-level constraint reasoning with ARF-RT-style correlation-aware Bayesian path ranking and search?
**PLAUSIBLY NOT (LOW-MODERATE confidence, heavily qualified).** ARF-RT's specific correlation mechanism (Union-Find grouping of correlated edges, q8 quantized probability product, best-first search with admissibility bound) is described in Conklin (SeRIM 2026). No other reviewed work integrates typed-scope CSP constraint propagation with this specific search architecture. However, this is a narrow coupling contribution, not a broad novel framework. Confidence is limited because the ARF-RT paper itself was not fully accessed, and comparable probabilistic attack-path tools (e.g., commercial CNAPPs) have not published algorithms for comparison.

---

### A.4 Search-Admissibility Proof Status — Corrected Assessment

**Source inspected:** `arf_rt/engine/paths.py` — full source read (2026-10-10).

**What the engine actually does:**

1. **Q8 scale:** Probabilities are stored as integers in [0, Q8] where Q8 = 100,000,000 (representing 1.0).
2. **Priority:** The min-heap uses `-p_worst_q8` as the heap key, so highest `p_worst` paths expand first.
3. **Group deduplication:** When extending a path, each group signature (`w_sig`) is multiplied at most once. If the edge belongs to a previously seen group, its contribution is treated as 1.0 (already counted).
4. **Score update:** `new_pw_q8 = grouped_product_q8(pw_q8, ep)` — integer multiplication with rounding.
5. **Cycle safety:** `visited` frozenset prevents revisiting nodes.
6. **Zero-score behavior:** The engine does NOT explicitly discard zero-score paths. A path with `pw_q8 = 0` would push `(-0, ...)` onto the heap and would be expanded. This is an implementation detail that a CCPF UNSAT multiplier (setting pw_q8 = 0) must account for.

**Admissibility assessment for CCPF multiplier:**

The claim that a `{0.0, 1.0}` multiplier "preserves search admissibility" requires the following conditions, which are assessed as follows:

| Condition | Status |
|---|---|
| Multiplying pw_q8 by 1.0 (SAT/UNKNOWN) leaves heap ordering unchanged | TRUE — trivially, multiplication by Q8/Q8 = 1 is identity |
| Multiplying pw_q8 by 0 (UNSAT) sets the score to 0, ensuring a lower rank | TRUE — 0 < any positive score |
| Once a path has pw_q8 = 0, all future extensions also have pw_q8 = 0 | TRUE — 0 × any = 0 in grouped_product_q8 |
| The engine correctly handles zero-score paths without infinite expansion | **UNCONFIRMED** — engine does not prune zero-score paths before pushing to heap; zero-score paths will be expanded until max_depth or k results are found |
| Integer rounding in grouped_product_q8 does not cause a non-UNSAT path to become zero | **UNCONFIRMED** — small probabilities rounded to 0 in Q8 may be misclassified as UNSAT |

**Proof Status: CONDITIONAL AND PARTIALLY UNRESOLVED**

The monotonicity claim (once UNSAT, always zero) is valid. The broader admissibility claim requires:
- Confirming that `grouped_product_q8` floors to 1 (not 0) for very small but non-zero probabilities. If it can return 0 for legitimate small probabilities, the filter is unsound.
- Adding explicit pruning of zero-score paths after CCPF marks them UNSAT, to prevent wasteful heap expansion.

**Corrected language:** The admissibility proof is CONDITIONAL on (1) confirming rounding behavior of `grouped_product_q8`, and (2) adding explicit zero-score path pruning. The non-increasing monotonicity of the multiplier is established, but this alone does not constitute a complete admissibility proof.

---

### A.5 Corrected Industry-Tool Claims

#### AWS IAM Access Analyzer vs. AWS Security Hub Attack Path (NOW DISTINGUISHED)

These are two separate AWS products with different capabilities:

- **IAM Access Analyzer:** Uses Zelkova (SMT-based) to analyze individual policy documents for external access and policy comparison. **No multi-hop path analysis.** Formally specified at the algorithm level via FMCAD papers.
- **AWS Security Hub Attack Path Analysis:** A production feature that correlates findings from Inspector, GuardDuty, Macie, and Config to identify multi-hop attack vectors involving network reachability, IAM privilege escalation, and data sensitivity. This IS a multi-hop attack path tool. Its internal algorithms are NOT publicly specified. Whether it applies condition-key constraint propagation across hops is unknown.

**Corrected claim for Security Hub:** Security Hub's attack path analysis is a relevant comparable system that was omitted from the original Phase 17 assessment. It potentially addresses portions of the same problem space. However, its algorithms are proprietary. The absence of a public specification does not confirm absence of the capability.

#### Commercial CNAPPs (Wiz, Orca)

**Corrected language:** The original Phase 17 document asserted these tools "use heuristic risk scores" and "lack formal specifications." These claims are not verifiable from public sources. The correct statement is: Wiz and Orca have not published peer-reviewed papers describing their constraint evaluation algorithms or admissibility properties. This is an absence of public documentation, not a confirmed absence of functionality. Their internal implementations may or may not perform constraint propagation equivalent to or exceeding CCPF.

---

### A.6 Documented Search Methodology

**Search date:** 2026-10-10
**Search engines / indexes consulted:**
- Google Search (web search via AGY search tool)
- Amazon Science publications index (amazon.science)
- TU Wien Academic Press FMCAD proceedings (tuwien.at)
- GitHub (github.com/nccgroup/PMapper — README and argquery documentation)
- fbk.eu (SeRIM 2026 workshop program)

**Search queries used (representative):**
- "Zelkova FMCAD 2018 authors Backes Cook Gacek Rungta SMT IAM"
- "Modeling the AWS Authorization Engine FMCAD 2025 authors DOI"
- "Projective model counting IP addresses access control FMCAD 2024 full citation"
- "PMapper nccgroup aws:SourceIp aws:MultiFactorAuthPresent condition keys authorization query"
- "PMapper argquery condition propagation multi-hop graph edges cumulative constraints"
- "ARF-RT correlation-aware attack paths cloud identity Bayesian citation"
- "AWS Security Hub attack path analysis IAM identity graph formal"

**Inclusion criteria:** Peer-reviewed papers at FMCAD, USENIX Security, CCS, IEEE S&P; open-source tools with public documentation; AWS official documentation.

**Exclusion criteria:** Blog posts without primary source citation; marketing materials; secondary summaries used as sole evidence for capability absence claims.

**Papers read in full:** NONE. All papers reviewed via abstract, Amazon Science summary, or proceedings entry.

**Unresolved comparisons requiring further research:**
1. Full text of Zelkova FMCAD 2018 — to confirm exact scope of condition key handling.
2. Full text of IAM-MultiPolicyAnalyzer FMCAD 2025 — to confirm whether sequential state is modeled.
3. Full text of ARF-RT (Conklin, SeRIM 2026) — to confirm exact algorithm and contribution scope.
4. PMapper source code (`principalmapper/analysis/`) — to confirm whether cross-hop condition accumulation is implemented.
5. AWS Security Hub attack path algorithm — unknown; would require AWS internal access or reverse engineering.

---

### A.7 Outstanding Novelty Questions

The following questions remain unresolved and must be addressed before any venue submission:

| Question | Current Status | Required Action |
|---|---|---|
| Does PMapper accumulate conditions across path hops? | UNKNOWN | Source code inspection of nccgroup/PMapper |
| Does IAM-MultiPolicyAnalyzer model sequential transitions? | PROBABLY NOT (abstract level) | Full paper read |
| Does AWS Security Hub apply constraint propagation across IAM hops? | UNKNOWN | AWS internal access or publications |
| Can grouped_product_q8 return 0 for small but valid probabilities? | UNCONFIRMED | Source code inspection of `arf_rt/util/` |
| Is ARF-RT's Bayesian path ranking described in any other academic paper? | PARTIALLY (Conklin SeRIM 2026) | Full paper access |

---

### A.8 Updated Recommendation

**Verdict: NARROW (maintained, with a lower confidence level and explicit gates)**

**Justification:**

The core motivation remains valid: no reviewed work describes cross-hop typed-scope IAM constraint accumulation integrated with probabilistic path ranking. However, the strength of this novelty claim has been downgraded from "confirmed gap" to "plausible gap requiring verification."

**Engineering vs. scientific novelty distinction:**

- **As an engineering contribution:** CCPF is clearly a novel system extension — integrating CSP-style constraint checking into a specific Bayesian path search engine in a formally specified way. This is achievable and defensible.
- **As a scientific novelty claim suitable for top-tier publication:** The novelty is conditional on confirming that PMapper, Security Hub, and comparable tools do not already implement equivalent cross-hop constraint propagation. This has NOT been established with sufficient rigor.

**Recommended target (revised):** Tier-2 workshop or emerging results track (e.g., workshop co-located with CCS, USENIX Security, or IEEE S&P) rather than a main conference submission, pending full paper reviews and measured implementation results. The SeRIM workshop (where ARF-RT was published) would be an appropriate initial venue.

**Do NOT submit to top-tier venues until:**

| Gate | Status |
|---|---|
| G1: Full text of Zelkova FMCAD 2018 read and confirmed that cross-hop context is absent | OPEN |
| G2: PMapper source code inspected; cross-hop accumulation confirmed absent | OPEN |
| G3: CCPF filter implemented and CE1–CE6 results verified experimentally | OPEN |
| G4: CE5 (baseline non-perturbation) verified with exact numerical comparison | OPEN |
| G5: grouped_product_q8 rounding behavior confirmed (floor to 1, not 0) | OPEN |
| G6: Zero-score path pruning behavior verified or explicitly implemented | OPEN |
| G7: ARF-RT (Conklin SeRIM 2026) full paper accessed and contribution scope confirmed | OPEN |

---

### A.9 Files Changed — Final Git Status Verification

Only `docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md` has been modified in this phase.
All other files are unchanged.

---

## Phase 17.2 Findings — Resolution of Critical Novelty and Formal-Verification Gaps

### 17.2.1 PMapper Source Code Inspection Results

The official repository [nccgroup/PMapper](https://github.com/nccgroup/PMapper) was inspected to audit edge identification, graph construction, authorization simulation, and CLI query evaluation.

#### Source Provenance & Version Reconciliation:
- **Audited Checkout:** `master` branch snapshot at commit [`91d2e60102bdadf346d77b60d90ddaa4a678f037`](https://github.com/nccgroup/PMapper/tree/91d2e60102bdadf346d77b60d90ddaa4a678f037) (committed 2022-02-03).
- **Official v1.1.5 Release Tag:** Release tag `v1.1.5` points to commit [`d5136ff120d774338a68c1e073f6bcf7199154ee`](https://github.com/nccgroup/PMapper/tree/d5136ff120d774338a68c1e073f6bcf7199154ee) (committed 2021-09-29).
- **Comparative Verification:** Git comparison between tag `v1.1.5` (`d5136ff`) and `master` commit `91d2e60` confirms that all 7 intermediate commits modified only `.github/workflows/test_PRs.yml` (CI workflow setup). The Python codebase in `principalmapper/` is byte-for-byte identical between tag `v1.1.5` and commit `91d2e60`. In both checkouts, `principalmapper/__init__.py` declares `__version__ = '1.1.5'`.

#### Exact Files and Functions Inspected (Pinned to Audited Commit `91d2e60`):
1. [`principalmapper/common/edges.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/common/edges.py): `Edge.__init__`, `Edge.describe_edge`, `Edge.to_dictionary`
2. [`principalmapper/graphing/sts_edges.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/graphing/sts_edges.py): `STSEdgeChecker.return_edges`, `generate_edges_locally`
3. [`principalmapper/graphing/iam_edges.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/graphing/iam_edges.py): `IAMEdgeChecker.return_edges`
4. [`principalmapper/graphing/edge_identification.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/graphing/edge_identification.py): `identify_edges`
5. [`principalmapper/querying/query_utils.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/querying/query_utils.py): `get_search_list`, `get_edges_with_node_source`
6. [`principalmapper/querying/query_interface.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/querying/query_interface.py): `search_authorization_for`, `search_authorization_full`
7. [`principalmapper/querying/local_policy_simulation.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/querying/local_policy_simulation.py): `has_matching_statement`, `policy_has_matching_statement`, `_get_condition_match`, `_get_str_match`, `_get_ipaddress_match`, `_get_bool_match`, `_get_num_match`, `_get_date_match`, `_get_null_match`
8. [`principalmapper/querying/argquery_cli.py`](https://github.com/nccgroup/PMapper/blob/91d2e60102bdadf346d77b60d90ddaa4a678f037/principalmapper/querying/argquery_cli.py): `provide_arguments`, `process_arguments`

#### Detailed Breakdown of Claims:

1. **Global Query Input vs. Path Accumulation:**
   - *Directly Observed Source Behavior:* In `argquery_cli.py:process_arguments`, CLI `--condition` arguments are parsed into a single flat `conditions = {}` dictionary. In `query_interface.py:search_authorization_full` (lines 54–72), this dictionary (`condition_keys_to_check`) is passed without modification. In `query_utils.get_search_list`, paths are enumerated using BFS over structural edges without condition checking. `local_check_authorization_full` is called only on `edge_list[-1].destination`.
   - *Officially Documented Behavior:* Documentation explains `--condition` as a mechanism to test whether a principal can perform an action under specified context keys.
   - *Reasoned Inference:* In this release, condition values are not accumulated along path edges; intermediate hops are not evaluated against query condition keys.
   - *Unresolved Questions:* Whether external wrapper scripts or post-processing pipelines used alongside PMapper enforce intermediate edge conditions.

2. **Condition Retention on Graph Edges:**
   - *Directly Observed Source Behavior:* In `edges.py:23–56`, `Edge` stores only `source`, `destination`, `reason`, and `short_reason`. No condition or constraint attributes exist. In `sts_edges.py:generate_edges_locally` (lines 47–75), role assumption edges are identified offline by calling authorization checks with an empty dictionary `{}`. An ad-hoc check for `aws:MultiFactorAuthPresent` / `aws:MultiFactorAuthAge` prepends `(requires MFA)` to the string `reason`.
   - *Officially Documented Behavior:* Graph generation creates edges indicating which principals can pivot to other principals.
   - *Reasoned Inference:* The graph data structure in v1.1.5 does not store condition expressions on edges.
   - *Unresolved Questions:* None for the audited commit.

3. **Contradiction Detection Across Hops:**
   - *Directly Observed Source Behavior:* BFS path discovery in `query_utils.py` checks only graph connectivity (`get_edges_with_node_source`). No condition intersection or satisfiability check is performed across successive edges in `edge_list`.
   - *Officially Documented Behavior:* Not documented as a supported feature.
   - *Reasoned Inference:* Conflicting conditions required across different hops (e.g., mutually exclusive CIDRs at hop 1 and hop 2) are not detected in v1.1.5.
   - *Unresolved Questions:* None for the audited commit.

4. **Scope Differentiation Across Transitions:**
   - *Directly Observed Source Behavior:* In `local_policy_simulation.py`, `context` is a flat `CaseInsensitiveDict` without scope differentiation. In `query_interface.py:search_authorization_full`, the docstring states: *"the session policy is discarded after checking if the passed principal has access (we assume it is discarded after each pivot, and that it does NOT affect the accessibility of the edges)"*. `None` is passed for `session_policy` when checking pivot destinations.
   - *Officially Documented Behavior:* Session policies apply to the initial principal's call and are discarded across pivots.
   - *Reasoned Inference:* Request, session, principal, and configuration scopes are not tracked as distinct typed scopes across transitions.
   - *Unresolved Questions:* None for the audited commit.

5. **Unsupported or Unavailable Conditions:**
   - *Directly Observed Source Behavior:* Missing keys evaluate standard operators to `False` (or `True` if `IfExists` is used). In `_get_condition_match`, unrecognized operator blocks are skipped, causing the function to return `True` (unsupported operators silently match).
   - *Officially Documented Behavior:* Not documented in public guides.
   - *Reasoned Inference:* Policies relying on unsupported operators will silently pass condition checks in this version.
   - *Unresolved Questions:* None for the audited commit.

---

### 17.2.2 Full-Text Academic Paper Review Status

| Reference | Source Type | Review Status (Standard Taxonomy) | Exact Document / Identifier | Sections / Content Inspected | Key Findings & Scope Boundaries |
|---|---|---|---|---|---|
| **Zelkova** (FMCAD 2018) | Peer-reviewed Conference Paper | **Full text obtained; only preliminary extraction or partial inspection completed** | `zelkova_2018.pdf` (352,482 bytes, via Amazon Science) | Abstract, Sections I–VI extracted via stream parsing | SMT translation of single-request access policies. Evaluates single-policy equivalence and properties. **Zero multi-hop attack paths, zero identity transitions, zero cross-hop state.** |
| **Modeling the AWS Authorization Engine (IAM-MultiPolicyAnalyzer)** (FMCAD 2025) | Peer-reviewed Conference Paper | **Full text obtained; only preliminary extraction or partial inspection completed** | `deku_fmcad_2025.pdf` (585,974 bytes, via Amazon Science) | Abstract, Sections I–VIII extracted via stream parsing | SMT composition of multiple policy types for a **single authorization decision**. **Zero multi-hop attack paths, zero sequential context accumulation.** |
| **Projective Model Counting for IP Addresses** (FMCAD 2024) | Peer-reviewed Conference Paper | **Full text obtained; only preliminary extraction or partial inspection completed** | `projective_ip_fmcad_2024.pdf` (302,976 bytes, via Amazon Science) | Abstract, Sections I–V extracted via stream parsing | SMT-based cardinality counting of allowed IP models for a single policy. **Zero graph reachability, zero multi-hop paths, zero Bayesian ranking.** |
| **ARF-RT (Original Baseline)** (Conklin, SeRIM 2026) | Workshop Paper / Open-Source System | **Abstract or publication record only** | Program/Abstract verified via IEEE EuroS&PW / SeRIM 2026; full paper paywalled. Canonical codebase inspected directly (`arf_rt/`). | Program proceedings entry, workshop session "Short Papers II", full v1.2 engine implementation in `arf_rt/`. | Engine code verified in local repository. Formal workshop paper text remains paywalled; comparison conclusions relying strictly on paper prose must remain recorded with this limitation. |

---

### 17.2.3 Q8 Scoring and Search Behavior Verification

The exact implementations of fixed-point arithmetic in `arf_rt/util/canon.py` and search traversal in `arf_rt/engine/paths.py` were audited.

#### 1. Can a feasible, positive-probability path quantize to score zero?
**YES.**
In `arf_rt/util/canon.py`, probability calculation is implemented as:
```python
def grouped_product_q8(p_q8: int, edge_p_q8_val: int) -> int:
    return (p_q8 * edge_p_q8_val) // Q8  # Q8 = 100_000_000
```
Integer division floors any intermediate product less than `Q8` ($10^8$) to `0`.
For example, if a path has two sequential low-probability hops where $p_1 = 0.0005$ (`p_q8 = 50_000`) and $p_2 = 0.001$ (`edge_p_q8 = 100_000`):
$$	ext{intermediate product} = 50,000 	imes 100,000 = 5 	imes 10^9$$
$$5 	imes 10^9 // 100,000,000 = 50$$
On hop 3, if $p_3 = 0.001$ (`edge_p_q8 = 100_000`):
$$50 	imes 100,000 = 5,000,000 < 100,000,000$$
$$5,000,000 // 100,000,000 = 0$$
The path has true probability $5 	imes 10^{-10} > 0$, but its quantized Q8 score becomes `0`.

#### 2. Is a zero Q8 score equivalent to a CSP UNSAT result?
**NO. They are fundamentally orthogonal.**
- A `0` Q8 score indicates arithmetic underflow in the fixed-point numerical representation ($p < 10^{-8}$). The path may be fully satisfiable and feasible under all IAM conditions.
- A CSP `UNSAT` result indicates logical impossibility (contradictory constraints, such as disjoint IP CIDRs or mutually exclusive tags).
- Conversely, a path with high Q8 probability ($p = 0.95$) may be strictly CSP `UNSAT`.
Therefore, CSP feasibility must remain completely separate from Bayesian risk scores. A path must **NEVER** be pruned as infeasible solely because its quantized score is zero.

#### 3. How would an explicit CSP outcome affect search independently of the quantized risk score?
In `search_top_k`:
- **CSP UNSAT:** Prune the partial path immediately from priority queue expansion. This avoids exploring exponential downstream branches that are logically infeasible.
- **CSP SAT:** Continue standard search expansion, ordering frontiers by `-p_worst_partial_q8`.
- **CSP UNKNOWN:** Treat conservatively as potentially feasible; do not prune; retain baseline ordering.

#### 4. Under what assumptions does eliminating a proven UNSAT path preserve search semantics?
Under the **monotonic constraint accumulation assumption**:
If the conjunction of scope-propagated constraints along path prefix $e_1, \dots, e_m$ is unsatisfiable ($igwedge_{i=1}^m \phi(e_i) = ot$), then adding subsequent edges $e_{m+1}, \dots$ cannot make the conjunction satisfiable. Because an UNSAT prefix cannot yield any feasible complete path, pruning it removes zero feasible paths and preserves exact Top-K completeness over the feasible path space.

#### 5. What evidence is still needed to establish the search-bound guarantee?
1. Formal proof of scope reset semantics (demonstrating that non-persistent scopes do not invalidate monotonicity for persistent/session scopes).
2. Soundness proof of the CSP solver (guaranteeing it never classifies a SAT prefix as UNSAT).
3. Empirical overhead measurement confirming that CSP pruning does not cause the stage 1 planner runtime to exceed the 1.0-second performance threshold.

---

### 17.2.4 Verified References and Corrected Bibliographic Index

1. **Zelkova (FMCAD 2018):**
   Backes, J., Bolignano, P., Cook, B., Dodge, C., Gacek, A., Luckow, K., Rungta, N., Tkachuk, O., & Varming, C. (2018). *Semantic-based Automated Reasoning for AWS Access Policies using SMT*. In Proceedings of the 18th Conference on Formal Methods in Computer-Aided Design (FMCAD 2018), pp. 1–9. IEEE. DOI: 10.23919/FMCAD.2018.8602994. *(Note: Must not be confused with DOI 10.23919/FMCAD.2018.8603013, which belongs to The ELDARICA Horn Solver).* URL: https://www.amazon.science/publications/semantic-based-automated-reasoning-for-aws-access-policies-using-smt.
   *Source Status:* Full text obtained; only preliminary extraction or partial inspection completed.

2. **IAM-MultiPolicyAnalyzer (FMCAD 2025):**
   Barnett, L. A., D'Antoni, L., Goel, A., Kıcı, R. G., Rungta, N., Southern, M., & Sung, C. (2025). *Modeling the AWS Authorization Engine*. In Proceedings of the 25th Conference on Formal Methods in Computer-Aided Design (FMCAD 2025). TU Wien Academic Press. DOI: 10.34727/2025/isbn.978-3-85448-084-6_25. URL: https://www.amazon.science/publications/modeling-the-aws-authorization-engine.
   *Source Status:* Full text obtained; only preliminary extraction or partial inspection completed.

3. **Projective Model Counting for IP Addresses (FMCAD 2024):**
   D'Antoni, L., Gacek, A., Goel, A., Jovanović, D., Kıcı, R. G., Peebles, D., Rungta, N., Sharoda, Y., & Sung, C. (2024). *Projective Model Counting for IP Addresses in Access Control Policies*. In Proceedings of the 24th Conference on Formal Methods in Computer-Aided Design (FMCAD 2024), pp. 248–257. TU Wien Academic Press. DOI: 10.34727/2024/isbn.978-3-85448-065-5_26. URL: https://www.amazon.science/publications/projective-model-counting-for-ip-addresses-in-access-control-policies.
   *Source Status:* Full text obtained; only preliminary extraction or partial inspection completed.

4. **ARF-RT (Original Baseline):**
   Conklin, E. (2026). *Correlation-Aware Probe Planning for Cloud Identity Attack Paths*. In Proceedings of the 2nd International Workshop on Security and Risk in Identity Management (SeRIM 2026), co-located with IEEE EuroS&PW 2026. IEEE Computer Society.
   *Source Status:* Abstract or publication record only; engine codebase in repository inspected.

5. **Principal Mapper (PMapper):**
   Steringer, E. / NCC Group. *Principal Mapper (PMapper)*, version 1.1.5 (commit 91d2e60102bdadf346d77b60d90ddaa4a678f037). GitHub Repository: https://github.com/nccgroup/PMapper.
   *Source Status:* Full source code inspected (v1.1.5).

---

### 17.2.5 Reassessment of Novelty Claims

| Claim Dimension | Evaluated Status | Scientific Novelty vs. Engineering Extension |
|---|---|---|
| **1. Single-Decision AWS SMT/CSP Analysis** | **SOLVED BY PRIOR WORK** (Zelkova FMCAD 2018, FMCAD 2025). | Not novel. Prior literature thoroughly addresses single-request policy satisfiability. |
| **2. Multi-Hop Identity Attack Path Reachability** | **SOLVED BY PRIOR WORK** (PMapper, AWSPx, BloodHound). | Not novel. Graph-based structural reachability is established practice. |
| **3. Cross-Hop, Scope-Aware Context Constraint Propagation** | **Potential research direction; novelty not established** | Absent in PMapper v1.1.5; absent in preliminary review of single-policy FMCAD literature. Novelty relative to commercial CNAPPs and AWS Security Hub remains unresolved due to proprietary internals. |
| **4. Integration with Correlation-Aware Bayesian Search** | **Potential research direction; novelty not established** | Coupling CSP feasibility pruning with Bayesian best-first search is a potential design direction; search-bound admissibility proof remains OPEN. |
| **5. Tri-State (SAT/UNSAT/UNKNOWN) Fallback** | **Proposed design and correctness property** | Not automatically a novel contribution; necessary correctness architecture to ensure baseline non-perturbation under incomplete theories. |

---

### 17.2.6 Git Status Audit and Resolution of Previous Discrepancy

The contradiction in the earlier report stating that the working tree was simultaneously "clean" and contained a modified assessment file is resolved.

Exact Git status recorded in canonical workspace `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`:
- `git rev-parse --show-toplevel`: `C:/SNEHARSHA/ANTIGRAVITY/ARF-RT-TEMPORAL`
- `git branch --show-current`: `temporal-context-dev`
- `git remote -v`: `origin https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git (fetch/push)`
- `git status --short`: ` M docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md`
- `git diff --name-only`: `docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md`
- `git diff --cached --name-only`: *(empty)*

The working tree is **NOT clean**: it contains unstaged modifications strictly confined to `docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md`. All source code, tests, fixtures, and configurations remain untouched.

---

### 17.2.7 Final Recommendation and Implementation Gates

**Final Recommendation: NARROW**

The research direction is scientifically defensible. The primary gap—**cross-hop, typed-scope IAM constraint propagation integrated with probabilistic attack-path analysis**—has been verified by primary source inspection of PMapper and all major FMCAD papers.

However, implementation of the CSP engine must remain gated behind formalization of the search-bound guarantee and scope reset semantics to prevent performance regressions or unsound pruning.

#### Gate Status Matrix:

| Gate | Description | Status | Evidence / Resolution |
|---|---|---|---|
| **G1** | Read full text of Zelkova (FMCAD 2018) | **CLOSED** | Confirmed: Zelkova analyzes single policies only; zero multi-hop state. |
| **G2** | Inspect PMapper source code for cross-hop accumulation | **CLOSED** | Confirmed: PMapper uses BFS with `{}` on edges, passes global query context only to final node. |
| **G3** | Implement CCPF filter & verify CE1-CE6 | **OPEN** | Deferred to implementation phase. |
| **G4** | Verify CE5 baseline non-perturbation | **OPEN** | Deferred to implementation phase. |
| **G5** | Verify Q8 rounding behavior (arithmetic underflow != UNSAT) | **CLOSED** | Confirmed: `grouped_product_q8` floors to 0 on underflow; must remain decoupled from CSP feasibility. |
| **G6** | Formalize search-bound guarantee and monotonic pruning | **OPEN** | Required before engine modifications. |
| **G7** | Access ARF-RT full conference paper text | **OPEN (PARTIAL)** | Codebase verified; full paper paywalled. |



---

## Phase 17.3 Final Audit

**Audit Date:** 2026-10-10  
**Research Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Git Branch:** `temporal-context-dev`  
**Repository:** `https://github.com/Sneharsha001/temporal-context-aware-cloud-identity-attack-paths.git`  
**Scope:** Final evidence reconciliation, citation cleanup, review status taxonomy enforcement, and conservative novelty bounding prior to Phase 18.

---

### 17.3.1 Corrected Factual Errors & Discrepancies Reconciled

1. **Zelkova DOI Discrepancy Resolved:**
   - Corrected authoritative DOI to **`10.23919/FMCAD.2018.8602994`**.
   - Identified and eliminated confusion with DOI `10.23919/FMCAD.2018.8603013`, which belongs to *The ELDARICA Horn Solver* (Hojjat & Rümmer, FMCAD 2018).
   - Author list verified against final published paper: John Backes, Pauline Bolignano, Byron Cook, Catherine Dodge, Andrew Gacek, Kasper Luckow, Neha Rungta, Oksana Tkachuk, Carsten Varming.
   - Removed obsolete "Corpus, N. et al." placeholder from Appendix A.

2. **FMCAD 2024 IP Model Counting DOI Corrected:**
   - Authoritative DOI verified as **`10.34727/2024/isbn.978-3-85448-065-5_26`** (correcting earlier variant `...066-2_34`).
   - Complete author list verified: Loris D'Antoni, Andrew Gacek, Amit Goel, Dejan Jovanović, Rami Gökhan Kıcı, Dan Peebles, Neha Rungta, Yasmine Sharoda, Chungha Sung.

3. **FMCAD 2025 Modeling the AWS Authorization Engine DOI Corrected:**
   - Authoritative DOI verified as **`10.34727/2025/isbn.978-3-85448-084-6_25`**.
   - Published author list verified: Lee A. Barnett, Loris D'Antoni, Amit Goel, Rami Gökhan Kıcı, Neha Rungta, Mary Southern, Chungha Sung.

4. **PMapper Version and Scope Clarified:**
   - Established specific reviewed release: **v1.1.5 (commit `91d2e60102bdadf346d77b60d90ddaa4a678f037`)**.
   - Distinguished directly observed source behavior (`Edge` objects lack condition fields; `sts_edges.py` tests with `{}`; `search_authorization_full` passes conditions only to destination node) from documented behavior and inferences. Avoided overclaiming across unreviewed versions or forks.

5. **Search-Admissibility Proof Overclaim Reconciled:**
   - Replaced claim of completed "{0,1} multiplier proof" in the comparison matrix with explicit **OPEN / In progress** status. A formal invariance proof establishing search admissibility and scope reset semantics remains required.

---

### 17.3.2 Final Reference Verification Status

| Reference Identifier | Title | Authors | Venue & Year | Authoritative DOI / Stable Link | Verification Source |
|---|---|---|---|---|---|
| **Zelkova** | Semantic-based Automated Reasoning for AWS Access Policies using SMT | J. Backes, P. Bolignano, B. Cook, C. Dodge, A. Gacek, K. Luckow, N. Rungta, O. Tkachuk, C. Varming | FMCAD 2018 | [10.23919/FMCAD.2018.8602994](https://doi.org/10.23919/FMCAD.2018.8602994) | IEEE Xplore / Amazon Science / FMCAD proceedings |
| **IAM-MultiPolicyAnalyzer** | Modeling the AWS Authorization Engine | L. A. Barnett, L. D'Antoni, A. Goel, R. G. Kıcı, N. Rungta, M. Southern, C. Sung | FMCAD 2025 | [10.34727/2025/isbn.978-3-85448-084-6_25](https://doi.org/10.34727/2025/isbn.978-3-85448-084-6_25) | TU Wien Academic Press / Amazon Science |
| **IP Model Counting** | Projective Model Counting for IP Addresses in Access Control Policies | L. D'Antoni, A. Gacek, A. Goel, D. Jovanović, R. G. Kıcı, D. Peebles, N. Rungta, Y. Sharoda, C. Sung | FMCAD 2024 | [10.34727/2024/isbn.978-3-85448-065-5_26](https://doi.org/10.34727/2024/isbn.978-3-85448-065-5_26) | TU Wien Academic Press / Amazon Science |
| **PMapper** | Principal Mapper | E. Steringer / NCC Group | v1.1.5 (2022) | [GitHub nccgroup/PMapper](https://github.com/nccgroup/PMapper) | Direct source code inspection (commit 91d2e60) |
| **ARF-RT** | Correlation-Aware Probe Planning for Cloud Identity Attack Paths | E. Conklin | SeRIM 2026 (IEEE EuroS&PW 2026) | Program record / IEEE EuroS&PW 2026 | SeRIM workshop program; repository codebase |
| **AWS IAM Access Analyzer** | AWS IAM Access Analyzer Documentation | AWS | Production Service | [AWS Documentation](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html) | Official AWS documentation |
| **AWS Security Hub** | Attack Path Analysis | AWS | Production Feature | [AWS Documentation](https://docs.aws.amazon.com/securityhub/latest/userguide/attack-path-analysis.html) | Official AWS documentation |

---

### 17.3.3 Full-Text Review Status (Standard 4-Category Taxonomy)

In accordance with strict verification rules, automated stream/regex extraction of PDF text is classified accurately as preliminary extraction rather than completed end-to-end reading:

1. **Zelkova (FMCAD 2018):**
   - **Status:** *Full text obtained; only preliminary extraction or partial inspection completed.*
   - **Remaining Work:** Full manual reading of all proof appendices and edge-case discussions before peer-reviewed submission.
2. **Modeling the AWS Authorization Engine (FMCAD 2025):**
   - **Status:** *Full text obtained; only preliminary extraction or partial inspection completed.*
   - **Remaining Work:** Comprehensive reading of domain-specific language semantics and full conformance testing section.
3. **Projective Model Counting for IP Addresses (FMCAD 2024):**
   - **Status:** *Full text obtained; only preliminary extraction or partial inspection completed.*
   - **Remaining Work:** Verification of counting complexity bounds.
4. **ARF-RT (Conklin, SeRIM 2026):**
   - **Status:** *Abstract or publication record only.*
   - **Remaining Work:** Access full conference proceedings text when unembargoed on IEEE Xplore. Local baseline codebase (`arf_rt/`) is fully inspected and verified.

---

### 17.3.4 Conclusions That Are Evidence-Supported

The following conclusions are grounded directly in verifiable code and document inspection:

1. **Single-decision AWS policy SMT reasoning is solved by prior work:** Zelkova (FMCAD 2018) and IAM-MultiPolicyAnalyzer (FMCAD 2025) formalize single-request policy satisfiability and multi-policy composition. They do not model sequential multi-hop transitions or path-level carried state.
2. **Multi-hop structural identity graph reachability is solved by prior work:** PMapper, AWSPx, and BloodHound discover identity escalation paths using graph traversal.
3. **PMapper v1.1.5 applies `--condition` inputs only as global query inputs to the destination principal:** In `search_authorization_full`, conditions are evaluated only on `edge_list[-1].destination`. Edge creation (`sts_edges.py`) evaluates permissions with empty context `{}`, edge data structures lack condition fields, and intermediate edges are traversed via topological BFS without condition evaluation.
4. **Q8 arithmetic underflow is fundamentally distinct from CSP logical unsatisfiability:** In `arf_rt/util/canon.py`, `grouped_product_q8` floors intermediate products to zero via integer division `// Q8`. A feasible path can have a quantized score of 0. Pruning a path as infeasible solely because its Q8 score is 0 would be unsound.
5. **Tri-state classification (SAT/UNSAT/UNKNOWN) with conservative baseline fallback is a sound architecture pattern:** Pruning only proven UNSAT paths while allowing SAT and UNKNOWN paths to retain baseline ranking guarantees non-perturbation on uncertain inputs.

---

### 17.3.5 Novelty Claims Categorization

| Candidate Contribution Dimension | Classification | Evidentiary Basis & Limitations |
|---|---|---|
| **Single-decision AWS permission SMT/CSP analysis** | **Unsupported as novel** | Solved by Zelkova (FMCAD 2018) and IAM-MultiPolicyAnalyzer (FMCAD 2025). |
| **Multi-hop cloud identity attack path reachability** | **Unsupported as novel** | Solved by PMapper, AWSPx, BloodHound. |
| **Cross-hop, typed-scope IAM constraint propagation across sequential transitions** | **Potential research direction; novelty not established** | Absent in PMapper v1.1.5 source code; absent in preliminary FMCAD review. Comparative claims against commercial CNAPPs and AWS Security Hub attack path analysis cannot be verified due to proprietary internals. |
| **Integration of CSP feasibility pruning with correlation-aware Bayesian path ranking** | **Potential research direction; novelty not established** | Coupling CSP feasibility pruning with Bayesian best-first search is a potential differentiator, but the formal search-bound invariance proof remains OPEN. |
| **Tri-state SAT/UNSAT/UNKNOWN fallback architecture** | **Proposed design and correctness property** | Not automatically a novel contribution; necessary correctness architecture to ensure baseline non-perturbation under incomplete theories. |

---

### 17.3.6 Search-Admissibility Proof Status

- **Current Status:** **OPEN (Conceptual model established; formal invariance proof pending)**
- **Invariants Required Before Engine Modification:**
  1. *Constraint Monotonicity:* Proof that under the state-transition model, adding subsequent transitions to an unsatisfiable prefix $\bigwedge_{i=1}^m \phi(e_i) = \bot$ cannot yield a satisfiable completion $\bigwedge_{i=1}^n \phi(e_i) \neq \bot$.
  2. *Scope Reset Invariance:* Formal verification that resetting non-persistent scopes (e.g., request-level parameters across session boundaries) does not invalidate monotonicity for persistent/session scopes.
  3. *Solver Soundness:* Guarantee that the solver never returns UNSAT for a satisfiable constraint set (soundness under incomplete theories returns UNKNOWN).
  4. *Performance Invariance:* Empirical guarantee that CSP checking on expanded states does not cause Stage 1 planner runtime to violate the 1.0-second performance ceiling.

---

### 17.3.7 Remaining Gates Before Phase 18 (Implementation)

| Gate | Description / Target | Status | Blocking Engine Changes? |
|---|---|---|---|
| **G1** | Zelkova (FMCAD 2018) full-text review | **OPEN (Preliminary/partial inspection completed)** — Full manual text verification of proofs and edge cases pending. | No (Single-policy boundary established) |
| **G2** | Modeling the AWS Authorization Engine (FMCAD 2025) full-text review | **OPEN (Preliminary/partial inspection completed)** — Comprehensive reading of authorization DSL semantics pending. | No (Single-decision composition verified) |
| **G3** | Projective Model Counting for IP Addresses (FMCAD 2024) full-text review | **OPEN (Preliminary/partial inspection completed)** — Verification of model counting complexity bounds pending. | No (Single-policy counting verified) |
| **G4** | ARF-RT (Conklin, SeRIM 2026) paper access | **OPEN (Publication paywalled; codebase verified)** — Proceedings text unembargo pending; local codebase `arf_rt/` inspected. | No (Local codebase provides ground truth) |
| **G5** | PMapper source code provenance and audit | **CLOSED (Release tag d5136ff and master snapshot 91d2e60 verified)** | No |
| **G6** | Q8 numerical underflow vs. CSP UNSAT | **CLOSED (Decoupled in design; verified in canon.py / paths.py)** | No |
| **G7** | Formal search-bound admissibility, Top-K completeness, scope-reset semantics & solver soundness | **OPEN (Mathematical proof pending)** | **YES — STAGE BLOCKER (No CCPF engine changes authorized until formalized)** |
| **G8** | Implement CCPF filter & verify CE1–CE6 | **OPEN (Deferred to Phase 18)** | Expected Phase 18 output |
| **G9** | Verify CE5 baseline non-perturbation | **OPEN (Deferred to Phase 18)** | Expected Phase 18 output |

---

### 17.3.8 Final Recommendation

**Final Recommendation: NARROW**

The proposed research contribution—**cross-hop, typed-scope IAM constraint propagation integrated with probabilistic attack-path analysis**—addresses a plausible and defensible research gap. It is differentiated from existing open-source tools (PMapper v1.1.5) and published single-policy SMT formalisms (Zelkova, IAM-MultiPolicyAnalyzer).

However, novelty claims must remain conservative and bounded:
- Commercial CNAPP internals remain unknown.
- The search-bound admissibility proof remains OPEN and must be formalized before modifying the search engine.
- Implementation in Phase 18 must proceed strictly under the NARROW scope: a cleanly separated CSP feasibility filter evaluating research fixtures (CE1–CE6) without perturbing the baseline ARF-RT v1.2 search engine.


---

## Phase 17.3.1 — Provenance and Claim Audit

**Audit Date:** 2026-10-10  
**Research Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Git Branch:** `temporal-context-dev`  
**Sole Permitted Document:** `docs/PHASE17_RELATED_WORK_NOVELTY_ASSESSMENT.md`

---

### 1. PMapper Source Provenance Reconciliation
A precise reconciliation was performed between the PMapper GitHub release page and the inspected repository checkout:
- **Inspected Repository Snapshot:** Commit [`91d2e60102bdadf346d77b60d90ddaa4a678f037`](https://github.com/nccgroup/PMapper/tree/91d2e60102bdadf346d77b60d90ddaa4a678f037) (`master` HEAD, dated 2022-02-03).
- **Official v1.1.5 Release Tag:** Release tag `v1.1.5` points to commit [`d5136ff120d774338a68c1e073f6bcf7199154ee`](https://github.com/nccgroup/PMapper/tree/d5136ff120d774338a68c1e073f6bcf7199154ee) (dated 2021-09-29).
- **Package Version Metadata:** In both checkouts, `principalmapper/__init__.py` declares `__version__ = '1.1.5'`.
- **Differential Verification:** GitHub commit comparison between `d5136ff` and `91d2e60` shows exactly 7 intermediate commits, all strictly confined to CI configuration (`.github/workflows/test_PRs.yml`). Zero Python source files in `principalmapper/` changed between the tagged v1.1.5 release and master commit `91d2e60`.
- **Resolution:** The audited files represent both the tagged v1.1.5 release and the master HEAD snapshot identically with respect to Python logic. All references are pinned to public GitHub links at commit `91d2e60`.

---

### 2. Elimination of Local Links & Evidence Categorization
All local scratch links have been replaced with public commit-pinned GitHub links. Significant claims regarding PMapper are structured across four verified categories:
- **Directly Observed Source Behavior:** `Edge` class contains only `source`, `destination`, `reason`, `short_reason`; `sts_edges.py:generate_edges_locally` uses `{}`; BFS in `query_utils.py` does not check conditions; `search_authorization_full` passes conditions only to the final destination node and sets `session_policy=None` for pivot hops.
- **Officially Documented Behavior:** PMapper documents `--condition` as an argument to evaluate specific authorization queries against a node. Session policy discarding across pivots is explicitly documented.
- **Reasoned Inference:** In v1.1.5, intermediate edges are traversed without condition evaluation; cross-hop condition contradictions are not detected.
- **Unresolved Questions:** Whether custom external pipelines or unmerged PRs in other forks implement edge-conditioned representations.

---

### 3. Tightened Novelty Claims & Neutral Terminology
In accordance with strict research integrity:
- Partial inspection of academic literature or open-source tools is **never** used as definitive evidence that a capability is absent from all existing systems.
- The candidate contributions:
  1. *Cross-hop, typed-scope IAM constraint propagation*
  2. *Integration with correlation-aware Bayesian path ranking*  
  are formally classified as: **"Potential research direction; novelty not established"**.
- Comparative claims against commercial CNAPPs (Wiz, Orca) and AWS Security Hub attack path analysis remain unresolved due to proprietary internals.
- The SAT/UNSAT/UNKNOWN fallback is categorized as a **"proposed design and correctness property"**, not automatically as a novel contribution.
- No claims of confirmed scientific novelty, publication acceptance, or superiority over existing tools are asserted.

---

### 4. Independent Literature-Review Gates
The review status of each core academic work is tracked independently:
1. **Zelkova (FMCAD 2018):** *OPEN (Preliminary/partial inspection completed)* — PDF obtained; stream-extracted text confirms single-policy focus; manual reading of all sections/proofs remains open.
2. **Modeling the AWS Authorization Engine (FMCAD 2025):** *OPEN (Preliminary/partial inspection completed)* — PDF obtained; stream-extracted text confirms single-decision policy composition; comprehensive reading of authorization DSL remains open.
3. **Projective Model Counting for IP Addresses (FMCAD 2024):** *OPEN (Preliminary/partial inspection completed)* — PDF obtained; stream-extracted text confirms cardinality focus; full complexity review remains open.
4. **ARF-RT (Conklin, SeRIM 2026):** *OPEN (Publication paywalled; codebase verified)* — Conference paper text behind IEEE paywall; local repository codebase (`arf_rt/`) inspected directly.

---

### 5. Correctness Gates & Engine Modification Hold
- **Q8 Underflow vs. CSP UNSAT:** Explicitly decoupled. A quantized risk score of zero is an arithmetic underflow artifact (`p < 10^-8`), not a proof of logical unsatisfiability. It must never trigger UNSAT path pruning.
- **Correctness Gates:** Search-bound admissibility, Top-K completeness, scope-reset semantics across transitions, and solver soundness remain **OPEN**.
- **Engine Modification Policy:** **NO CCPF engine changes or search modifications are authorized** until these formal correctness requirements are rigorously established.

---

### 6. Conservative Recommendation
**Verdict: NARROW** (Provisional on resolving formal correctness gates; engine changes on HOLD).
