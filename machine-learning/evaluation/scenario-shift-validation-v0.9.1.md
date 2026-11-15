# CropFit v0.9.1 independent scenario-shift validation

Held-out crop profiles are evaluated with independently seeded Latin-hypercube scenarios rather than the random generator used for fitting and promotion. This measures EcoCrop-teacher fidelity, not observed-yield accuracy.

| Metric | v0.8 | v0.9 | Gain |
|---|---:|---:|---:|
| Raw MAE | 0.01782 | 0.01471 | 17.45% |
| Raw p90 | 0.04881 | 0.04045 | 17.13% |
| Deployed MAE | 0.00695 | 0.00607 | 12.66% |
| Deployed p90 | 0.00284 | 0.00064 | 77.46% |

| Active-case calibration | 80% coverage | 90% coverage |
|---|---:|---:|
| Old global method on shifted test | 7.8% | 55.0% |
| Conditional method on frozen-random test | 80.6% | 90.9% |
| Conditional method on shifted test | 81.4% | 91.4% |

The previous marginal intervals were dominated by deterministic hard-zero cases. v0.9.1 calibrates active growing conditions separately and assigns zero radius only when the deterministic ceiling fixes the deployed score at zero.

Gate: **PASS**.
