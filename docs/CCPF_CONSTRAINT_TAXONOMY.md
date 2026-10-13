# CCPF Constraint Class Taxonomy

**Document:** docs/CCPF_CONSTRAINT_TAXONOMY.md  
**Branch:** 	emporal-context-dev  
**Date:** 2026-10-13  
**Contract reference:** docs/CCPF_EVALUATOR_CONTRACT.md v1.1.0

---

## 1. Overview

This document provides a reference taxonomy of all constraint classes
evaluated by the RDCE. Each class is cross-referenced against the formal
contract, the relevant defect finding (F1–F7), and the test coverage
in 	ests/research/.

---

## 2. Constraint class registry

### 2.1 IP address constraints

| Class | IAM operator | Scope | RDCE support | Contract ref |
|---|---|---|---|---|
| IpAddress | IpAddress | REQUEST | Full | §3.1 |
| NotIpAddress | NotIpAddress | REQUEST | Full (F1 fix) | §3.1 |
| Mixed IPv4+IPv6 | Any IP operator | REQUEST | UNKNOWN fallback (F5) | §3.1 |

**Key invariants:**
- A generated SAT witness must lie inside every allowed CIDR.
- A generated SAT witness must lie outside every denied CIDR.
- If ∪(denied) covers ∩(allowed), the result is UNSAT.
- Mixed address-family combinations always return UNKNOWN (conservative).

---

### 2.2 Boolean constraints

| Class | IAM operator | Scope | RDCE support | Contract ref |
|---|---|---|---|---|
| Bool (single value) | Bool | SESSION | Full | §3.2 |
| Bool (multi-value list) | Bool | SESSION | Full (F2 fix) | §3.2 |

**Key invariants:**
- Multi-value Bool is disjunctive: ["true","false"] permits both.
- Domain intersection, not first-element selection, drives satisfiability.
- A Bool: ["true","false"] predicate followed by Bool: ["true"] yields
  domain {True}, not UNSAT.

---

### 2.3 Null / presence constraints

| Class | IAM operator | Scope | RDCE support | Contract ref |
|---|---|---|---|---|
| Null (key present) | Null: false | Any | Full (F3 fix) | §3.3 |
| Null (key absent) | Null: true | Any | Full (F3 fix) | §3.3 |

**Key invariants:**
- Null: false asserts the key exists (is not null).
- Null: true asserts the key is absent.
- Conjunction of Null: false and a positive predicate on the same key
  is SAT if a value satisfying the positive predicate exists.
- Conjunction of Null: true and a positive predicate on the same key
  is UNSAT (contradiction).
- Result must be invariant to predicate ordering (F3).

---

### 2.4 String constraints

| Class | IAM operator | Scope | RDCE support | Contract ref |
|---|---|---|---|---|
| StringEquals (exact) | StringEquals | PRINCIPAL | Full (F6 fix) | §3.4 |
| StringEquals (exact) | StringEquals | SESSION | Full (F6 fix) | §3.4 |
| StringEquals (exact) | StringEquals | CONFIG | Full (F6 fix) | §3.4 |
| StringEquals (exact) | StringEquals | REQUEST | Full (F6 fix) | §3.4 |
| StringLike (pattern) | StringLike | Any | UNKNOWN | §3.4 |
| StringNotEquals | StringNotEquals | Any | UNKNOWN | §3.4 |

**Key invariants:**
- Scope identity prevents cross-scope value merging.
- Contradictory session strings (two StringEquals on the same key,
  different values) yield UNSAT.
- Unknown operators return UNKNOWN with diagnostic.

---

### 2.5 AssumeRole / STS transition constraints

| Class | Context | RDCE support | Contract ref |
|---|---|---|---|
| sts:AssumeRole scope reset | Principal/session reset on role assumption | Full (F4 fix) | §3.5 (CE6) |
| Caller tag survival | Tags must not cross AssumeRole boundary | Full (F4 fix) | §3.5 |

**Key invariants:**
- Caller principal/session tags are reset when crossing an AssumeRole edge.
- Target-role constraints are evaluated under CE6 assumptions only.
- The CE6 rule is not generalised to all AssumeRole variants.

---

## 3. Unsupported / deferred constraint classes

| Class | Rationale | Expected result |
|---|---|---|
| DateGreaterThan / DateLessThan | Temporal expiration semantics unreviewed | UNKNOWN |
| StringLike | Glob/wildcard pattern semantics unreviewed | UNKNOWN |
| ArnLike / ArnEquals | ARN pattern matching unreviewed | UNKNOWN |
| StringNotEquals | Negation semantics unreviewed | UNKNOWN |
| Mixed IPv4+IPv6 | Dual-stack semantics unreviewed | UNKNOWN |
| NumericEquals / comparisons | Numeric range semantics unreviewed | UNKNOWN |

All unsupported classes return UNKNOWN with a diagnostic identifying the
unsupported operator or combination. UNKNOWN is never silently converted
to UNSAT.

---

## 4. Change log

| Date | Change |
|---|---|
| 2026-10-13 | Initial taxonomy created post-Prompt-5A remediation |

---

*Maintained by the CCPF research track. Any addition of a new supported
constraint class requires a formal contract review and update.*
