# ARF-RT: 5-Minute Demo

**Goal:** Determine whether `user/arf-rt-attacker` can reach `role/arf-rt-CIRole`
in AWS account 516525145310.

We begin uncertain. We probe strategically. Our confidence updates. We converge on truth.

---

## Step 1 — Import the privilege graph

PMapper has already enumerated IAM principals and privilege edges.
Import the graph and declare a reachability objective:

```bash
python3 -m arf_rt.cli import-pmapper pmapper_consolidated.json \
  --start "arn:aws:iam::516525145310:user/arf-rt-attacker" \
  --target "arn:aws:iam::516525145310:role/arf-rt-CIRole" \
  -o scenario.json
```

```
Scenario saved to scenario.json
```

The scenario now contains 3 nodes, 2 edges, and 1 objective. No observations yet.

---

## Step 2 — Analyze the baseline

```bash
python3 -m arf_rt.cli analyze scenario.json --format both -o output/
```

```
canonical_run_hash: 5f0e2b5e66815633...

  Confidence: LOW
  Coverage:   0/2 edges (0%)
  Entropy:    0.5623 nats

  Path 1 (LOW):
    user/arf-rt-attacker →[sts:AssumeRole]→ role/arf-rt-DevRole  (HYPOTHESIZED)
    role/arf-rt-DevRole  →[sts:AssumeRole]→ role/arf-rt-CIRole   (HYPOTHESIZED)
```

Both edges are at prior beliefs — Beta(1,1), p=0.50.
Path probability is 0.50 × 0.50 = 0.25. The engine has no evidence. Everything is uncertain.

---

## Step 3 — Ask the planner what to probe

```bash
python3 -m arf_rt.cli plan scenario.json
```

```
Recommendation: probe 086780e1... (DevRole→CIRole)
  EIG = 0.1989
  p   = 0.50
  Reason: appears on a Top-K path, high uncertainty, never directly probed

Candidates:
  086780e1 (DevRole→CIRole)   EIG=0.1989  p=0.50
  2febbd6b (attacker→DevRole)  EIG=0.1989  p=0.50

Components: 2 × Uncorrelated (no SCPs in this account)
Runtime: 4 forks, 3ms
```

Both edges are equally uncertain — no correlation structure to exploit.
The planner picks DevRole→CIRole as the tiebreaker. We follow its recommendation.

---

## Step 4 — Execute the first probe

We test whether `role/arf-rt-DevRole` can assume `role/arf-rt-CIRole`.
The result: **ALLOW**.

```bash
python3 -m arf_rt.cli episode scenario.json \
  --edge 086780e1 --outcome allow \
  --save scenario_after_probe1.json
```

```
Episode: arf-rt-DevRole→arf-rt-CIRole → ALLOW

  H before:   0.5623
  H after:    0.6931
  RIG:       -0.1308
  EIG:        0.1996
  Pred error: 0.0000

Updated scenario saved to scenario_after_probe1.json
```

Entropy *increased* from 0.5623 to 0.6931 nats. RIG is negative.

This is correct. Before the probe, the system hedged toward "path probably doesn't work"
(the null outcome dominated the probability mass). Confirming that one edge *does* work
shifted mass toward viable paths, spreading the distribution more evenly.
More spread = higher entropy. The probe added information, but the information
made the outcome *less* certain, not more.

The planner predicted this H_after under deterministic replay (error = 0.0000).

---

## Step 5 — Observe the state change

```bash
python3 -m arf_rt.cli analyze scenario_after_probe1.json --format both -o output/
```

```
canonical_run_hash: f124c2ee6672fe37...

  Confidence: MEDIUM
  Coverage:   1/2 edges (50%)
  Entropy:    0.6931 nats

  Path 1 (MEDIUM):
    user/arf-rt-attacker →[sts:AssumeRole]→ role/arf-rt-DevRole  (HYPOTHESIZED)
    role/arf-rt-DevRole  →[sts:AssumeRole]→ role/arf-rt-CIRole   (CONFIRMED)
```

One edge is now CONFIRMED. Confidence upgraded from LOW to MEDIUM.
The hash changed — this is a different epistemic state.

The planner now concentrates all information value on the remaining edge:

```bash
python3 -m arf_rt.cli plan scenario_after_probe1.json
```

```
Recommendation: probe 2febbd6b... (attacker→DevRole)
  EIG = 0.6112
```

EIG jumped from 0.1989 to 0.6112. This is the only remaining source of uncertainty,
and resolving it will determine whether the full path is viable.

---

## Step 6 — Execute the second probe

We test whether `user/arf-rt-attacker` can assume `role/arf-rt-DevRole`.
The result: **ALLOW**.

```bash
python3 -m arf_rt.cli episode scenario_after_probe1.json \
  --edge 2febbd6b --outcome allow \
  --save scenario_after_probe2.json
```

```
Episode: arf-rt-attacker→arf-rt-DevRole → ALLOW

  H before:   0.6931
  H after:    0.1022
  RIG:       +0.5909
  EIG:        0.6136
  Pred error: 0.0000

Updated scenario saved to scenario_after_probe2.json
```

Entropy collapsed from 0.6931 to 0.1022 nats — an 85% reduction.
RIG is strongly positive (+0.5909). The system is now nearly certain.

---

## Step 7 — Confirm path viability

```bash
python3 -m arf_rt.cli analyze scenario_after_probe2.json --format both -o output/
```

```
canonical_run_hash: 056f18ef69a798c9...

  Confidence: VERY_HIGH
  Coverage:   2/2 edges (100%)
  Entropy:    0.1022 nats

  Path 1 (VERY_HIGH):
    user/arf-rt-attacker →[sts:AssumeRole]→ role/arf-rt-DevRole  (CONFIRMED)
    role/arf-rt-DevRole  →[sts:AssumeRole]→ role/arf-rt-CIRole   (CONFIRMED)
```

Both edges CONFIRMED. Full path viable at VERY_HIGH confidence.

---

## The epistemic trajectory

| Step | Entropy | Coverage | Confidence | Hash |
|------|---------|----------|------------|------|
| Baseline | 0.5623 | 0% | LOW | `5f0e2b5e...` |
| After probe 1 | 0.6931 | 50% | MEDIUM | `f124c2ee...` |
| After probe 2 | 0.1022 | 100% | VERY_HIGH | `056f18ef...` |

Three canonical hashes. Three distinct epistemic states.
Each probe changed the system's beliefs, and each belief change is
cryptographically committed and reproducible.

**Key observations:**

- **RIG can be negative.** The first probe (ALLOW on DevRole→CIRole) increased entropy
  because it made the path more plausible, spreading probability mass away from the null
  outcome. Information gain is not the same as uncertainty reduction.

- **EIG concentrates.** After the first probe, EIG on the remaining edge jumped 3×
  (0.1989 → 0.6112). The planner correctly identified it as the single bottleneck.

- **Prediction error was zero.** Both episode predictions matched the deterministic replay outcomes.
  The Bayesian machinery is deterministic given the model — no approximation error.

- **No SCPs in this account.** Both edges were uncorrelated singletons. In a multi-account
  environment with SCPs, correlation groups form, and a single probe can update
  beliefs across 6+ edges simultaneously. That is where EIG dominates random probing
  by 19.8× (see §6 of the workshop paper).

---

## What you just ran

ARF-RT is an epistemic control loop for red team operations:

1. **Import** a privilege graph from any enumerator (PMapper, Cartography, raw boto3).
2. **Analyze** the baseline to quantify uncertainty.
3. **Plan** the next probe using Expected Information Gain.
4. **Execute** the probe and record the outcome.
5. **Update** beliefs and repeat.

Each cycle is deterministic, auditable, and produces a cryptographic hash
that commits the entire epistemic state. The system doesn't tell you *how* to
exploit a path — it tells you *which path to investigate next* and *how confident
you should be* in the answer.
