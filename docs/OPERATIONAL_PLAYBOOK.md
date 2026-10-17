# ARF-RT Operational Readiness Playbook

## 1. Deployment Requirements
- Python 3.10, 3.11, or 3.12 (64-bit).
- Minimum 8 GB RAM for processing graphs up to 50,000 nodes.
- Local SQLite database engine with WAL (Write-Ahead Logging) support.

## 2. Pre-Flight Verification
Run the complete health check and test runner:
```bash
python scripts/health_check.py
python scripts/run_tests.py --suite all
```

## 3. Incident Triage Steps
1. **Benchmark Degradation:** Check CPU thermal throttling and run `scripts/compare_benchmarks.py`.
2. **Schema Incompatibility:** Run `scripts/validate_fixtures.py` on all scenario assets.
3. **Determinism Mismatch:** Verify `canonical_run_hash` against known golden snapshot.
