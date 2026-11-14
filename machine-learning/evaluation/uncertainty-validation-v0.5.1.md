# CropFit uncertainty calibration v0.5.1

Calibration is fit only on validation crop profiles. This report compares methods on held-out crop-profile test splits; it measures fidelity to the EcoCrop screening teacher, not observed farm yield.

| Method | 80% coverage | 90% coverage | Mean 80% radius | Mean 90% radius |
|---|---:|---:|---:|---:|
| v0.5 disagreement bins | 95.7% | 97.7% | 0.226 | 0.308 |
| v0.5.1 normalized conformal | 80.0% | 89.8% | 0.005 | 0.125 |

The production-seed candidate reduces mean 90% radius by **59.5%** while bringing both marginal coverages to their nominal targets. Single-split gate: **PASS**.

## Frozen five-seed robustness

The method and gate were frozen before evaluating five new seeds (20261201–20261205). Every seed requires both coverages within three percentage points of nominal and a narrower mean 90% radius than v0.5.

| Seed | 80% coverage | 90% coverage | v0.5 radius90 | v0.5.1 radius90 | Reduction |
|---:|---:|---:|---:|---:|---:|
| 20261201 | 79.8% | 89.7% | 0.312 | 0.129 | 58.6% |
| 20261202 | 80.3% | 90.2% | 0.298 | 0.122 | 59.1% |
| 20261203 | 79.6% | 90.0% | 0.316 | 0.131 | 58.5% |
| 20261204 | 79.1% | 89.6% | 0.323 | 0.137 | 57.5% |
| 20261205 | 79.6% | 90.4% | 0.312 | 0.138 | 55.9% |

Robustness wins: **5/5**. Overall gate: **PASS**.

Intervals are marginal across unseen crop profiles. They are not per-species guarantees, yield intervals, or property-investment confidence.
