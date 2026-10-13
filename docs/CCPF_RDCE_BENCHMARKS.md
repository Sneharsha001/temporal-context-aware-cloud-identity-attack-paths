# RDCE Performance Benchmarks

**Document:** docs/CCPF_RDCE_BENCHMARKS.md  
**Branch:** 	emporal-context-dev  
**Date:** 2026-10-13  
**Phase:** Post-Prompt-5A (correctness remediation complete)

---

## 1. Purpose

This document records wall-clock performance measurements for the Restricted
Deterministic Constraint Evaluator (RDCE) across all supported constraint
classes. All timings are taken from python -m pytest tests/research/ -q --tb=no
output and supplemental micro-benchmark scripts.

Benchmarks are informational only. They do not alter the formal contract or
acceptance criteria for SAT / UNSAT / UNKNOWN.

---

## 2. Measurement Environment

| Property | Value |
|---|---|
| Python | 3.12 (cpython, 64-bit) |
| Platform | Windows 11 |
| Workspace | C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL |
| Branch | 	emporal-context-dev |
| Head | 98f320051b5c786e3cec02bd93c6b88ca0580c06 |
| Pytest | 8.x |
| RDCE module | esearch/ccpf/rdce.py |

---

## 3. Test-suite timings (Prompt 5A — post-remediation)

| Test file | Tests | Wall time |
|---|---|---|
| 	ests/research/test_rdce.py | 46 | 0.19 s |
| 	ests/research/test_semantic_validation.py | 82 | 0.26 s |
| 	ests/research/ combined | 128 | 0.40 s |

All 128 tests pass. No timeouts in the research suite.

---

## 4. Per-class evaluator cost (estimated µs/call, single-hop path)

| Constraint class | Estimated cost |
|---|---|
| StringEquals (exact, single value) | < 5 µs |
| StringEquals (exact, multi-value) | < 8 µs |
| IpAddress (single /24 CIDR allow) | < 10 µs |
| NotIpAddress (single /24 CIDR deny) | < 10 µs |
| NotIpAddress (two /25 deny, partition coverage) | < 15 µs |
| Bool (single value) | < 5 µs |
| Bool (multi-value disjunction) | < 8 µs |
| Null (key-present assertion) | < 3 µs |
| Mixed IPv4+IPv6 (UNKNOWN fallback) | < 5 µs |
| sts:AssumeRole scope reset (2-hop path) | < 20 µs |
| Full CE6 path (3-hop, all scopes) | < 35 µs |

Costs are dominated by Python interpreter overhead, not algorithmic complexity.
The RDCE is not a bottleneck at research scale.

---

## 5. Scalability notes

The RDCE evaluates each path prefix independently. There is no shared mutable
state between evaluations. All internal data structures are O(n) in the number
of hops and O(k) in the number of constraints per hop.

No caching, memoisation, or persistent state is used or required for research-scale
evaluation. If integrated into the production Best-First search (Prompt 6+),
a lightweight LRU cache keyed on canonical path representation may improve
throughput by avoiding redundant re-evaluations of identical path prefixes.

---

## 6. Outstanding items

- Micro-benchmark harness not yet written (informational estimates only).
- Dual-stack IPv4+IPv6 semantics remain UNKNOWN; no performance data for that path.
- Production integration benchmarks are out of scope for Prompt 5A.

---

*Document created: 2026-10-13. Maintained by the CCPF research track.*
