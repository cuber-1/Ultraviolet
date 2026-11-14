# CropFit v0.5 range-relative feature validation

The candidate was compared with the v0.4 absolute-feature design on identical grouped splits. Entire crop profiles were held out.

| Seed | v0.4-style MAE | Candidate MAE | Improvement | Candidate R² | Candidate p90 |
|---:|---:|---:|---:|---:|---:|
| 20261110 | 5.2896 | 0.1496 | 97.17% | 0.9996 | 0.4092 |
| 20261111 | 5.5638 | 0.1588 | 97.15% | 0.9996 | 0.4310 |
| 20261112 | 5.3811 | 0.1543 | 97.13% | 0.9996 | 0.4297 |
| 20261113 | 5.3939 | 0.1536 | 97.15% | 0.9996 | 0.4386 |
| 20261114 | 5.3558 | 0.1519 | 97.16% | 0.9996 | 0.4443 |

Candidate wins: **5/5**. Mean MAE: **5.3968 → 0.1536** (97.15% lower).

These range-relative features encode where current conditions fall inside each crop's absolute and optimum ranges. They do not use crop identity or any held-out labels.

> This is surrogate fidelity to a mechanistic EcoCrop screening target, not validation against observed farm yield. The national observed-yield gate remains failed.
