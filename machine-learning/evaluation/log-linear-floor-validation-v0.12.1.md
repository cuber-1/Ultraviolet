# CropFit membership-floor log-linear validation

The candidate aligns its positive-membership floor with the pre-existing mechanistic teacher and retains float64 precision only while fitting four learned elasticities.

| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20270530 | 0.01001 | 0.00000028 | 99.997% | 99.995% | 0.00000526 | 80.0% | 90.0% |
| confirmation | 20270531 | 0.01074 | 0.00000030 | 99.997% | 99.996% | 0.00000551 | 80.2% | 90.8% |
| confirmation | 20270532 | 0.01048 | 0.00000028 | 99.997% | 99.996% | 0.00000562 | 79.5% | 89.5% |
| confirmation | 20270533 | 0.01001 | 0.00000029 | 99.997% | 99.995% | 0.00000554 | 78.4% | 89.9% |
| confirmation | 20270534 | 0.01019 | 0.00000029 | 99.997% | 99.996% | 0.00000586 | 80.9% | 90.2% |
| final | 20270535 | 0.01032 | 0.00000029 | 99.997% | 99.996% | 0.00000550 | 81.1% | 90.7% |
| final | 20270536 | 0.00885 | 0.00000027 | 99.997% | 99.995% | 0.00000585 | 79.3% | 89.8% |
| final | 20270537 | 0.01061 | 0.00000029 | 99.997% | 99.996% | 0.00000525 | 80.3% | 90.6% |
| final | 20270538 | 0.00963 | 0.00000029 | 99.997% | 99.995% | 0.00000539 | 80.0% | 90.3% |
| final | 20270539 | 0.01003 | 0.00000028 | 99.997% | 99.996% | 0.00000532 | 79.3% | 89.7% |

Seed wins: **10/10**. Final-only gains are **99.997% MAE** and **99.995% p90**.

The regressor is **0.4 KB** versus **63.8 MB**, with **0.001x** batch latency.

## Independent runtime-shaped shift

Raw maximum error is **0.00000243**; serialized error radii are **0.001 / 0.001**; served-score mismatches: **0 / 23,872**.

Promotion gate: **PASS**.

> This validates fidelity to the mechanistic teacher at the API's reporting precision, not observed-yield accuracy.
