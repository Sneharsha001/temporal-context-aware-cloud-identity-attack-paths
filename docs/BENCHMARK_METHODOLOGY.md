# ARF-RT Benchmark Methodology & Statistical Controls

## 1. Principles
Performance characterization within ARF-RT follows rigorous empirical guidelines to eliminate thermal jitter, cold-start compilation variance, and garbage collection spikes.

## 2. Statistical Metrics
For each benchmark routine:
- **Warm-Up Iterations:** At least 5 unmeasured warmup invocations precede data collection.
- **Sample Distribution:** Minimum 100 iterations per benchmark target.
- **Percentiles:** Both 95th ($p_{95}$) and 99th ($p_{99}$) percentiles are computed from ordered sample slices.
- **Standard Deviation:** Calculated to verify normality and detect outliers.

## 3. Threshold Gates
- Any regression exceeding **15%** in median latency or **25%** in $p_{99}$ latency between releases triggers a CI gate failure.
- Cold-import time of core modules must not exceed **250ms** on baseline reference hardware.
