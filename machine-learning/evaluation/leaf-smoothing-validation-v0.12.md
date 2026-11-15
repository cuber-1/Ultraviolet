# CropFit interaction-only compaction validation

The candidate retains all six v0.11 features and smooths leaves while increasing tree count. Training density and evaluation rows are unchanged from v0.11.

| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Max deployed error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270301 | 0.01055 | 0.00954 | 9.57% | 4.17% | 0.428 | 82.1% | 91.8% |
| confirmation | 20270302 | 0.01048 | 0.00905 | 13.65% | 9.82% | 0.651 | 81.8% | 90.5% |
| confirmation | 20270303 | 0.00993 | 0.00896 | 9.77% | -1.97% | 0.578 | 80.8% | 91.2% |
| confirmation | 20270304 | 0.01022 | 0.00922 | 9.78% | 6.81% | 0.412 | 80.1% | 90.7% |
| confirmation | 20270305 | 0.01017 | 0.00982 | 3.44% | -4.70% | 0.411 | 80.2% | 90.3% |
| final | 20270306 | 0.01026 | 0.00875 | 14.72% | 5.65% | 0.360 | 80.6% | 90.3% |
| final | 20270307 | 0.01007 | 0.00919 | 8.74% | 3.88% | 0.328 | 81.1% | 90.7% |
| final | 20270308 | 0.01041 | 0.00930 | 10.66% | 11.78% | 0.547 | 80.1% | 90.6% |
| final | 20270309 | 0.01084 | 0.00893 | 17.62% | 17.36% | 0.568 | 80.7% | 89.6% |
| final | 20270310 | 0.01000 | 0.00964 | 3.60% | -3.49% | 0.396 | 79.8% | 90.0% |

Seed wins: **4/10**. Final-only gains are **11.07% MAE** and **7.04% p90**.

The forest is **59.4 MB** (7.2% smaller) with **0.96x** batch latency.

## Independent shift

Fresh-shift gains are **11.70% raw MAE**, **1.93% raw p90**, and **9.23% deployed MAE**.

Active shifted coverage is **80.0% / 89.9%**.

Promotion gate: **NOT PASSED**.

> The retained inputs contain no crop identity, target score, held-out label, or observed yield.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
