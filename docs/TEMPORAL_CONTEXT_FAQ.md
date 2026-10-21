# Temporal Context FAQ

This document answers common questions about the temporal context module
(`arf_rt.temporal`) and its integration with the CCPF evaluator.

---

## General

### What is the temporal context module?

The temporal context module adds time-aware feasibility checks to ARF-RT's
attack path analysis. It validates that the sequence of privilege hops in a
candidate path could have occurred in the observed order, with valid
credentials, and without violating session lifetime constraints.

### Does temporal evaluation change Bayesian probability scores?

**No.** The temporal evaluator is a pure post-filter. It can only *exclude*
paths from the candidate set. Paths that pass temporal evaluation enter the
Bayesian scorer with unmodified prior probabilities.

### What happens if CloudTrail data is unavailable?

Paths with insufficient timestamp data receive an `UNKNOWN` verdict. By
default (`unknown_passthrough=True`), these paths pass through to the
Bayesian layer. Set `unknown_passthrough=False` for conservative operation
(reduced recall, fewer false negatives).

---

## Constraints

### What is TC-1 (Causal Order)?

TC-1 checks that each hop in the path was observed *after* the preceding
hop. If CloudTrail timestamps show Hop B occurring before Hop A, the path
is temporally infeasible regardless of logical policy feasibility.

### What is TC-2 (Session Validity)?

TC-2 verifies that the STS session token obtained during Hop A had not
expired by the time Hop B was observed. This catches paths that require
reusing credentials beyond their `MaxSessionDuration`.

### What is TC-3 (Minimum Velocity)?

TC-3 flags paths where two consecutive hops are separated by less than
`min_hop_delta_seconds` (default: 0.5s). Such paths are likely API-driven
(scripted attacks) rather than human-operated.

### What is TC-4 (Stale Credential)?

TC-4 checks that the IAM credential involved in each hop was used within
the last `stale_credential_days` days (default: 90). Credentials unused for
longer are unlikely to still be in active attacker toolchains and may
indicate a reconstructed-but-stale path.

### What is TC-5 (Concurrent Session)?

TC-5 detects when two or more hops in the path share the same
`credential_issued` timestamp, which would indicate that the same STS
session token was used across multiple distinct privilege transitions
simultaneously — a pattern consistent with credential sharing or replay.

---

## Configuration

### How do I enable only causal ordering checks?

```python
from arf_rt.temporal.config import TemporalConfig

cfg = TemporalConfig(enabled_constraints=frozenset({"TC-1"}))
```

### What is the difference between strict and permissive presets?

| Setting | `strict()` | `permissive()` |
|---|---|---|
| `unknown_passthrough` | `False` | `True` |
| `min_hop_delta_seconds` | `1.0` | `0.0` |
| `stale_credential_days` | `30` | `365` |
| `session_expiry_grace_seconds` | `0.0` | `120.0` |
| Enabled constraints | All (TC-1…TC-5) | TC-1, TC-2 only |

Use `strict()` for investigations where you want maximum false-negative
reduction. Use `permissive()` for high-recall discovery passes.

---

## Integration

### At what stage does the temporal evaluator run?

```
Path Candidates
    → CCPF Evaluator (logical: CIDR, MFA, tags)
    → Temporal Evaluator (time: ordering, expiry, velocity)
    → Bayesian Scorer
    → Top-K Ranking
```

### How do I supply CloudTrail data to the evaluator?

```python
import json
from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.evaluator import TemporalEvaluator

with open("cloudtrail_events.json") as f:
    events = json.load(f)

hints = extract_hints_from_log(events)
ev = TemporalEvaluator()
verdict = ev.evaluate(["e1", "e2", "e3"], hints)
print(verdict)
```

### Can I run the temporal evaluator without CloudTrail data?

Yes. Pass an empty hints dict — all constraints will evaluate as UNKNOWN
and (with `unknown_passthrough=True`) all paths will pass through unchanged.
This is the zero-configuration safe default.
