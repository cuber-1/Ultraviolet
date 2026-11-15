# CropFit v0.10 independent density-shift validation

The v0.10 candidate was selected on frozen random development splits. This report tests it against v0.9.1 on a separately seeded Latin-hypercube scenario generator over the same held-out crop profiles.

| Metric | v0.9.1 | v0.10 | Gain |
|---|---:|---:|---:|
| Raw MAE | 0.01471 | 0.01400 | 4.83% |
| Raw p90 error | 0.04045 | 0.03667 | 9.34% |
| Deployed MAE | 0.00607 | 0.00613 | -0.99% |
| Deployed p90 error | 0.00064 | 0.00013 | 79.69% |

Active conditional coverage is **79.7% / 89.7%** on shifted scenarios and **79.8% / 90.1%** on frozen-random held-out scenarios.

Gate: **NOT PASSED**.

> This validates mechanistic-teacher fidelity under scenario shift. It does not validate observed yield, revenue, or property value.
