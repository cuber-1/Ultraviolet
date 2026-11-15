# CropFit log-linear development screen

A four-feature log-linear regression learns the multiplicative EcoCrop response from fitting rows. It does not receive crop identity, coordinates, the target score, or observed yield as an input. The teacher is structurally log-linear in these memberships, which explains the near-zero fidelity error but does not imply near-zero real-world crop error.

| Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20270501 | 0.00944 | 0.00000028 | 99.997% | 99.995% | 0.00000569 | 80.0% | 90.3% |
| 20270502 | 0.01008 | 0.00000029 | 99.997% | 99.995% | 0.00000553 | 79.6% | 89.1% |
| 20270503 | 0.01005 | 0.00000029 | 99.997% | 99.995% | 0.00000551 | 80.4% | 90.7% |

Mean development gains: **99.997% MAE** and **99.995% p90**.

The candidate serializes to **0.4 KB** versus **64.1 MB**, with **0.001x** batch latency.

Development gate: **PASS**. Fresh confirmation, final, and shift seeds remain unopened.

> This measures fidelity to the declared mechanistic teacher, not observed yield, revenue, or property value.
