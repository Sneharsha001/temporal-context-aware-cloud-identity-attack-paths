# CCPF / RDCE Glossary

**Document:** docs/CCPF_GLOSSARY.md  
**Branch:** 	emporal-context-dev  
**Date:** 2026-10-13  

---

## A

**ARF-RT** — Attack-path Reasoning Framework, Real-Time. The production
engine implementing Bayesian Q8 probability scoring and Union-Find
correlation grouping for ranked IAM attack-path discovery.

**AssumeRole boundary** — The transition point in a multi-hop path where
sts:AssumeRole is invoked, causing a principal and session context reset
per the CE6 rule. Caller tags do not survive this boundary.

---

## B

**Bayesian Q8 score** — The eight-factor Bayesian probability score
assigned to each ranked attack path by the ARF-RT production engine.
Strictly independent of RDCE logical feasibility.

**Bool constraint** — An IAM condition operator accepting ["true"],
["false"], or ["true","false"]. The RDCE evaluates Bool as a domain
intersection problem; multi-value lists are disjunctive (F2 fix).

---

## C

**CCPF** — Context-Conditioned Path Feasibility. The research mechanism
that wraps the RDCE to provide a logical feasibility oracle for IAM
attack-path prefixes. Returns SAT / UNSAT / UNKNOWN.

**CE** (Counterexample) — A named fixture in
	ests/fixtures/research_context_feasibility/ providing a ground-truth
path-prefix scenario and expected feasibility outcome. CE1–CE6 are the
canonical research fixtures.

**clash_proof** — The RDCE field that, for UNSAT results, records the
contradicting predicates and the reason the contradiction is sound.

**ContextPredicate** — A single IAM condition assertion (key, operator,
alues, scope) bound to a hop in a path prefix.

**ContextScope** — The lifecycle domain of a context variable:
REQUEST, SESSION, PRINCIPAL, CONFIG, or UNKNOWN.

---

## F

**F1–F7** — The seven confirmed findings from the Prompt 5 independent
review of the RDCE. F1–F6 are correctness defects; F7 is a test
assertion coverage gap. All were remediated in Prompt 5A.

**Feasibility guard** — The planned Prompt 6 integration of the RDCE
into the ARF-RT Best-First search loop, filtering out UNSAT paths before
probability scoring.

---

## H

**HopContextSpec** — A dataclass binding a single edge hop's
equired_context predicates and produced_context state modifications
to its position in a path prefix.

---

## I

**IpAddress** — IAM condition operator requiring the request source IP
to lie within a given CIDR range. Evaluated by the RDCE witness generator.

---

## N

**NotIpAddress** — IAM condition operator requiring the request source IP
to lie outside a given CIDR range. Fixed in F1 to correctly detect
when combined denied ranges cover the entire allowed set.

**Null predicate** — An IAM condition operator asserting key presence
(Null: false) or key absence (Null: true). Fixed in F3 for
predicate-order invariance.

---

## P

**PathContextBundle** — The top-level RDCE input structure containing
all hops, transitions, and metadata for a path prefix.

**predicate-order invariance** — The property that RDCE conjunction
evaluation must produce the same result regardless of the order in which
predicates are presented. Required by the formal contract; verified by F3.

---

## R

**RDCE** — Restricted Deterministic Constraint Evaluator. The isolated
Python module (esearch/ccpf/rdce.py) implementing tri-state feasibility
evaluation for IAM path prefixes. Strictly isolated from production code.

**RDCEResult** — The RDCE output dataclass containing status, witness,
clash_proof, unknown_rationale, and evaluation_metadata.

---

## S

**SAT** — The RDCE status indicating that a satisfying assignment (witness)
exists for all active constraints. Requires a concrete witness.

**scope reset** — The CE6 rule that clears principal/session context
variables when a path crosses an sts:AssumeRole boundary.

**StringEquals** — An IAM condition operator performing exact string
matching. Supported by the RDCE for PRINCIPAL, SESSION, CONFIG,
and REQUEST scopes (F6 fix).

---

## T

**temporal-context-dev** — The authorized Git branch for all CCPF research
implementation, tests, and documentation.

**TransitionRelation** — A dataclass describing an inter-hop constraint
linking a context variable across consecutive hops (e.g., PIVOT_TRANSITION
for AssumeRole).

**tri-state** — The three possible RDCE outcomes: SAT, UNSAT, UNKNOWN.
UNKNOWN is never silently converted to UNSAT.

---

## U

**UNKNOWN** — The RDCE status indicating that the semantics of one or more
constraints cannot be soundly evaluated under the current formal contract.
Always accompanied by an unknown_rationale diagnostic string.

**UNSAT** — The RDCE status indicating that the active constraints form a
contradiction and no satisfying assignment exists. Always accompanied by a
clash_proof.

---

*Glossary maintained by the CCPF research track.*  
*Last updated: 2026-10-13 (post-Prompt-5A remediation).*
