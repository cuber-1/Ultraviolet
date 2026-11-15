# CropFit log-linear validation

The candidate learns a multiplicative response from four transparent range-membership features. It receives no crop identity, coordinates, target score, or observed yield feature. Its structural match to the mechanistic teacher explains the near-zero fidelity error; this is not a claim of near-zero real-world crop error.

| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270510 | 0.01092 | 0.00000030 | 99.997% | 99.996% | 0.00000562 | 81.6% | 90.8% |
| confirmation | 20270511 | 0.01037 | 0.00000029 | 99.997% | 99.996% | 0.00000552 | 81.0% | 90.6% |
| confirmation | 20270512 | 0.01037 | 0.00000030 | 99.997% | 99.996% | 0.00000547 | 79.8% | 89.4% |
| confirmation | 20270513 | 0.01026 | 0.00000029 | 99.997% | 99.996% | 0.00000592 | 79.7% | 89.8% |
| confirmation | 20270514 | 0.01016 | 0.00000029 | 99.997% | 99.996% | 0.00000551 | 79.5% | 89.4% |
| final | 20270515 | 0.01035 | 0.00000028 | 99.997% | 99.996% | 0.00000544 | 81.7% | 90.5% |
| final | 20270516 | 0.01063 | 0.00000029 | 99.997% | 99.995% | 0.00000537 | 78.7% | 89.6% |
| final | 20270517 | 0.01043 | 0.00000029 | 99.997% | 99.996% | 0.00000559 | 78.8% | 90.3% |
| final | 20270518 | 0.00955 | 0.00000028 | 99.997% | 99.995% | 0.00000550 | 79.9% | 89.2% |
| final | 20270519 | 0.01125 | 0.00001303 | 99.884% | 99.799% | 0.00032692 | 83.9% | 89.7% |

Seed wins: **9/10**. Final-only gains are **99.975% MAE** and **99.956% p90**.

The regressor is **0.4 KB** versus **64.1 MB**, with **0.001x** batch latency.

## Independent shift

Fresh-shift gains are **99.999% raw MAE**, **99.999% raw p90**, and **99.999% deployed MAE**.

Active shifted coverage is **100.0% / 100.0%**.

Promotion gate: **NOT PASSED**.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
