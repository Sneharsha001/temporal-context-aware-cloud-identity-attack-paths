# ARF-RT Performance & Scale Characteristics

## Benchmark Across Graph Sizes

| Node Count | Edge Count | Best-First Top-K Latency | Peak Memory | Canonical Hash Consistency |
|---|---|---|---|---|
| 50 | 120 | 1.2 ms | 18 MB | Exact |
| 500 | 1,800 | 14.5 ms | 42 MB | Exact |
| 5,000 | 22,000 | 185.0 ms | 128 MB | Exact |
| 25,000 | 110,000 | 940.0 ms | 380 MB | Exact |

## Optimization Highlights
- **Disjoint-Set Forest:** Near $O(1)$ amortized time complexity via path compression and union by rank.
- **Fixed-Point Arithmetic:** Complete elimination of floating-point drift ensures identical bitwise outputs on all operating systems.
