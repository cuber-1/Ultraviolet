# CropFit density-refinement v3 validation

The candidate retains all six v0.11 features and increases fitting density while reducing tree count. Validation and held-out rows remain frozen.

| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Max deployed error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270320 | 0.01057 | 0.00964 | 8.80% | 9.89% | 0.611 | 80.5% | 90.2% |
| confirmation | 20270321 | 0.01055 | 0.00888 | 15.83% | 10.78% | 0.623 | 80.4% | 90.7% |
| confirmation | 20270322 | 0.01017 | 0.00956 | 6.00% | 5.40% | 0.746 | 81.3% | 90.9% |
| confirmation | 20270323 | 0.00988 | 0.00970 | 1.82% | 9.07% | 0.520 | 81.3% | 90.5% |
| confirmation | 20270324 | 0.01018 | 0.00861 | 15.42% | 14.66% | 0.641 | 81.5% | 90.8% |
| final | 20270325 | 0.00995 | 0.00938 | 5.73% | 5.98% | 0.514 | 80.4% | 89.3% |
| final | 20270326 | 0.01065 | 0.00993 | 6.76% | -1.52% | 0.561 | 81.0% | 89.7% |
| final | 20270327 | 0.01005 | 0.00935 | 6.97% | 5.43% | 0.543 | 80.6% | 91.2% |
| final | 20270328 | 0.00941 | 0.00901 | 4.25% | 3.51% | 0.634 | 79.9% | 89.5% |
| final | 20270329 | 0.01039 | 0.00958 | 7.80% | 10.71% | 0.422 | 79.7% | 89.5% |

Seed wins: **5/10**. Final-only gains are **6.30% MAE** and **4.82% p90**.

The forest is **66.9 MB** (4.2% larger) with **0.94x** batch latency.

## Independent shift

Fresh-shift gains are **8.06% raw MAE**, **9.43% raw p90**, and **-2.67% deployed MAE**.

Active shifted coverage is **79.5% / 89.2%**.

Promotion gate: **NOT PASSED**.

> The retained inputs contain no crop identity, target score, held-out label, or observed yield.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
