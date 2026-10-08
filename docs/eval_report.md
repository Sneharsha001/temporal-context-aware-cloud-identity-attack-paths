# ARF-RT Policy Evaluation Report

**Policies**: eig, centrality, uncertainty, random
**Episodes per policy**: 10
**Steps per episode**: 5

## Cumulative RIG by Policy

| Policy | Median CumRIG@1 | Median CumRIG@2 | Median CumRIG@3 | Median CumRIG@5 |
|--------|-------:|-------:|-------:|-------:|
| eig | 0.1336 | 0.1827 | 0.2087 | 0.2361 |
| centrality | -0.0020 | -0.0025 | -0.0029 | -0.0033 |
| uncertainty | 0.0134 | 0.0134 | 0.0134 | 0.0134 |
| random | -0.0004 | 0.0128 | 0.0123 | 0.0119 |

## Mean CumRIG by Policy

| Policy | Mean CumRIG@1 | Mean CumRIG@2 | Mean CumRIG@3 | Mean CumRIG@5 |
|--------|-------:|-------:|-------:|-------:|
| eig | 0.1336 | 0.1827 | 0.2087 | 0.2361 |
| centrality | -0.0020 | -0.0025 | -0.0029 | -0.0033 |
| uncertainty | 0.0134 | 0.0134 | 0.0134 | 0.0134 |
| random | 0.0049 | 0.0087 | 0.0082 | 0.0533 |

*Note: Random policy shows mean/median divergence at step 5 (mean=0.0533, median=0.0119). A few lucky episodes pulled the mean up. Medians are the correct summary for skewed distributions.*

## EIG Advantage

- **CumRIG@1**: EIG median = 0.1336, Random median = -0.0004 (EIG wins, random at zero)
- **CumRIG@2**: EIG median = 0.1827, Random median = 0.0128 (ratio 14.29×)
- **CumRIG@3**: EIG median = 0.2087, Random median = 0.0123 (ratio 16.98×)
- **CumRIG@5**: EIG median = 0.2361, Random median = 0.0119 (ratio 19.84×)

- **CumRIG@1**: EIG median = 0.1336, Uncertainty median = 0.0134 (ratio 9.98×)
- **CumRIG@2**: EIG median = 0.1827, Uncertainty median = 0.0134 (ratio 13.64×)
- **CumRIG@3**: EIG median = 0.2087, Uncertainty median = 0.0134 (ratio 15.58×)
- **CumRIG@5**: EIG median = 0.2361, Uncertainty median = 0.0134 (ratio 17.63×)

### EIG vs Centrality

- **CumRIG@1**: EIG median = 0.1336, Centrality median = -0.0020 (EIG wins)
- **CumRIG@2**: EIG median = 0.1827, Centrality median = -0.0025 (EIG wins)
- **CumRIG@3**: EIG median = 0.2087, Centrality median = -0.0029 (EIG wins)
- **CumRIG@5**: EIG median = 0.2361, Centrality median = -0.0033 (EIG wins)

## Correlation Leverage (EIG policy)

- Avg RIG when probing representative: 0.0472
- Avg RIG when probing non-representative: 0.0000
- Rep flip rate: 0.0%

## Fixture

14 principals, 16 edges, 4 accounts, 2 SCPs, 2 trust conditions, 11 observations.
Scripted truth: 7 DENY edges (SCP-blocked), 9 ALLOW edges.
Baseline entropy: 0.3013 nats.

## Reproducibility

Baseline hash: `638b76cd453f2a04565cc40d4181adbd44a077102866cc1a209bcd21ea381d6b`. Base seed: 1337. Truth mode: scripted. Signal quality: 95.

## Headline

**On this realistic fixture, EIG reduces objective uncertainty faster than random (19.8×), max-uncertainty (17.6×) over the first 5 probes (median CumRIG@5: EIG=0.2361).**

EIG is not just picking "important" edges (centrality does that). It is not just picking uncertain edges (uncertainty does that). It is computing the expected entropy reduction from the full pipeline fork — which accounts for correlation, representative mechanics, and null complement dynamics simultaneously.