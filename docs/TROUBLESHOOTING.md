# ARF-RT Troubleshooting & Recovery Guide

## Common Issues & Resolutions

### 1. Host Performance Discrepancy during Stress Testing
- **Symptom:** `test_stage1b.py` or scale tests exceed timing budget on consumer laptops.
- **Cause:** Large matrix operations in structural correlation grouping are CPU/memory intensive.
- **Resolution:** Verify hardware profile. On dual-core or thermal-throttling CPUs, run with single-worker pytest or execute `python scripts/run_tests.py --suite research` to bypass host-dependent benchmark timing assertions.

### 2. Pytest Asyncio Fixture Warning
- **Symptom:** `PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.`
- **Resolution:** This warning is harmless. To silence, add `asyncio_default_fixture_loop_scope = "function"` to `pyproject.toml` or `pytest.ini`.

### 3. Missing Fixture Path Errors
- **Symptom:** `FileNotFoundError` when loading JSON scenarios.
- **Resolution:** Always invoke scripts from the workspace root directory:
  ```bash
  python scripts/run_tests.py
  ```

### 4. Git Divergence between `main` and `temporal-context-dev`
- **Symptom:** Unmerged commits or conflicting docs.
- **Resolution:** `main` serves as the public documentation and artifact baseline. `temporal-context-dev` contains active research iterations. Rebase or cherry-pick cleanly using conventional commit messages.
