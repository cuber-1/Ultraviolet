# CropFit compact-feature validation

The candidate keeps only six transparent, input-derived range and interaction features. Training density, estimator capacity, splits, and evaluation rows are unchanged from v0.10.

| Phase | Seed | v0.10 MAE | Compact MAE | MAE gain | p90 gain | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270110 | 0.01374 | 0.00998 | 27.37% | 34.65% | 80.6% | 91.0% |
| confirmation | 20270111 | 0.01352 | 0.01021 | 24.48% | 27.03% | 79.6% | 90.0% |
| confirmation | 20270112 | 0.01366 | 0.01013 | 25.84% | 34.95% | 81.7% | 91.5% |
| confirmation | 20270113 | 0.01462 | 0.01082 | 25.99% | 28.55% | 80.7% | 89.9% |
| confirmation | 20270114 | 0.01455 | 0.01020 | 29.90% | 35.10% | 80.1% | 89.6% |
| final | 20270115 | 0.01302 | 0.00995 | 23.58% | 26.92% | 81.2% | 90.4% |
| final | 20270116 | 0.01404 | 0.01049 | 25.28% | 26.14% | 81.5% | 91.1% |
| final | 20270117 | 0.01350 | 0.00990 | 26.67% | 31.32% | 81.5% | 90.3% |
| final | 20270118 | 0.01320 | 0.00986 | 25.30% | 28.81% | 81.2% | 90.9% |
| final | 20270119 | 0.01406 | 0.00973 | 30.80% | 34.03% | 81.3% | 91.4% |

Seed wins: **9/10**. Final-only gains are **26.33% MAE** and **29.44% p90**.

The forest is **63.8 MB** (3.8% smaller) with **0.94x** batch latency.

## Independent shift

Fresh-shift gains are **29.30% raw MAE**, **37.31% raw p90**, and **42.33% deployed MAE**.

Active shifted coverage is **80.7% / 89.7%**.

Promotion gate: **NOT PASSED**.

> The compact inputs are derived only from current conditions and published crop ranges; they contain no crop identity, held-out label, or observed yield.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
