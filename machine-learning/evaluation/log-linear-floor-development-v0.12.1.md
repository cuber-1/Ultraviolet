# CropFit membership-floor log-linear development

The rejected v0.12 candidate logged positive memberships below the teacher's 1e-6 numerical floor, perturbing one fitted seed and making millionth-point calibration generator-dependent.

The follow-up uses the teacher's existing `1e-6` positive-membership floor; it was not selected from a parameter search.

| Phase | Seed | Candidate MAE | p90 | Maximum error | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|
| exposed-diagnostic | 20270519 | 0.00000030 | 0.00000122 | 0.00000646 | 80.5% | 90.1% |
| development | 20270521 | 0.00000029 | 0.00000119 | 0.00000552 | 80.0% | 89.6% |
| development | 20270522 | 0.00000030 | 0.00000125 | 0.00000581 | 78.6% | 88.8% |
| development | 20270523 | 0.00000029 | 0.00000121 | 0.00000563 | 80.5% | 90.8% |

On the exposed runtime-shaped shift, maximum raw error is **0.00000228** and all **23,872** served scores match the teacher at 0.1-point precision.

Development gate: **PASS**. New confirmation, final, and shift seeds remain sealed.

> This is mechanistic-teacher fidelity, not observed-yield accuracy.
