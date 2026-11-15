# CropFit compact-feature validation

The candidate keeps only six transparent, input-derived range and interaction features. Training density, estimator capacity, splits, and evaluation rows are unchanged from v0.10.

| Phase | Seed | v0.10 MAE | Compact MAE | MAE gain | p90 gain | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270130 | 0.01364 | 0.01010 | 25.95% | 30.77% | 80.3% | 89.9% |
| confirmation | 20270131 | 0.01313 | 0.01003 | 23.61% | 25.98% | 80.3% | 91.5% |
| confirmation | 20270132 | 0.01448 | 0.00989 | 31.70% | 37.44% | 81.2% | 90.1% |
| confirmation | 20270133 | 0.01385 | 0.01059 | 23.54% | 28.84% | 81.3% | 89.8% |
| confirmation | 20270134 | 0.01331 | 0.01018 | 23.52% | 30.54% | 81.2% | 90.3% |
| final | 20270135 | 0.01457 | 0.01101 | 24.43% | 28.72% | 79.6% | 88.5% |
| final | 20270136 | 0.01470 | 0.01041 | 29.18% | 34.40% | 80.3% | 90.0% |
| final | 20270137 | 0.01396 | 0.01088 | 22.06% | 28.63% | 80.9% | 90.3% |
| final | 20270138 | 0.01409 | 0.01063 | 24.56% | 29.71% | 81.4% | 89.9% |
| final | 20270139 | 0.01256 | 0.01011 | 19.51% | 20.78% | 80.6% | 90.9% |

Seed wins: **10/10**. Final-only gains are **23.95% MAE** and **28.45% p90**.

The forest is **63.5 MB** (3.7% smaller) with **0.96x** batch latency.

## Independent shift

Fresh-shift gains are **22.19% raw MAE**, **24.81% raw p90**, and **32.92% deployed MAE**.

Active shifted coverage is **78.9% / 89.8%**.

Promotion gate: **PASS**.

> The compact inputs are derived only from current conditions and published crop ranges; they contain no crop identity, held-out label, or observed yield.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
