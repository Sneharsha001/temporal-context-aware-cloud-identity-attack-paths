# ARF-RT Research Data Management & Reproducibility Policy

## 1. Cloud Credential Hygiene
- **Zero-Live-Secret Policy:** No AWS secret access keys, session tokens, or private credentials may be committed or processed in plain text.
- **ARN Anonymization:** Production account identifiers (12-digit integers) must be replaced with canonical test IDs (`111111111111`, `222222222222`) before inclusion in fixtures.

## 2. Artifact Retention Standards
- Benchmark results and test execution logs must be stored in `artifacts/` with ISO-8601 timestamps.
- Golden fixtures in `tests/golden/` are immutable and require formal gate approval before modification.
