# CropFit interaction-only compaction validation

The candidate keeps only the two transparent interaction features and uses leaf smoothing to improve tail safety. Training density and evaluation rows are unchanged from v0.11.

| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Max deployed error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270210 | 0.00964 | 0.00588 | 39.00% | 31.59% | 0.305 | 81.0% | 90.8% |
| confirmation | 20270211 | 0.01000 | 0.00578 | 42.20% | 41.11% | 0.349 | 80.2% | 89.8% |
| confirmation | 20270212 | 0.01005 | 0.00606 | 39.70% | 33.89% | 0.369 | 80.2% | 90.1% |
| confirmation | 20270213 | 0.01012 | 0.00602 | 40.51% | 35.82% | 0.341 | 80.9% | 90.2% |
| confirmation | 20270214 | 0.01015 | 0.00577 | 43.15% | 36.52% | 0.421 | 80.5% | 90.1% |
| final | 20270215 | 0.00962 | 0.00561 | 41.68% | 34.63% | 0.235 | 81.6% | 90.4% |
| final | 20270216 | 0.00952 | 0.00569 | 40.23% | 33.83% | 0.326 | 81.5% | 90.6% |
| final | 20270217 | 0.00996 | 0.00616 | 38.15% | 34.15% | 0.260 | 80.6% | 90.8% |
| final | 20270218 | 0.00983 | 0.00591 | 39.88% | 35.21% | 0.456 | 79.8% | 88.9% |
| final | 20270219 | 0.01060 | 0.00589 | 44.43% | 39.29% | 0.303 | 80.1% | 89.4% |

Seed wins: **9/10**. Final-only gains are **40.87% MAE** and **35.42% p90**.

The forest is **38.4 MB** (40.2% smaller) with **0.92x** batch latency.

## Independent shift

Fresh-shift gains are **42.30% raw MAE**, **34.24% raw p90**, and **34.88% deployed MAE**.

Active shifted coverage is **80.7% / 90.3%**.

Promotion gate: **NOT PASSED**.

> The retained inputs contain no crop identity, target score, held-out label, or observed yield.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
