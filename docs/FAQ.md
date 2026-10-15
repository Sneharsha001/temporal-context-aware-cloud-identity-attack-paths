# Frequently Asked Questions (FAQ)

### Q1: What makes ARF-RT different from PMapper or BloodHound?
**A:** Traditional tools treat identity edges as independent Bernoulli variables. ARF-RT captures structural correlations (such as common SCPs and permission boundaries) and uses Shannon entropy over path probability distributions to determine the optimal next probe via Expected Information Gain (EIG).

### Q2: Does ARF-RT make live AWS API calls?
**A:** No. ARF-RT operates strictly in deterministic replay mode from offline JSON graph fixtures and policy artifacts. It never executes live network requests or modifies cloud infrastructure.

### Q3: What is the purpose of CCPF?
**A:** Context-Conditioned Path Feasibility evaluates operational prerequisites (such as source IP CIDRs, MFA device requirements, and temporary credential expiration) as a constraint satisfaction problem to eliminate logically impossible paths without modifying underlying Bayesian prior probabilities.

### Q4: How do I run the full test suite?
**A:** Use the unified test runner:
```bash
python scripts/run_tests.py --suite all
```
Or run baseline verification:
```bash
python verification/run_full_suites.py
```

### Q5: How do I run performance benchmarks?
**A:** Execute:
```bash
python scripts/benchmark.py
```
This measures cold-import, config loading, and path resolution latencies, providing min, median, p95, and p99 statistics.
