# CropFit uncertainty calibration v0.5.1

Calibration is fit only on validation crop profiles. This report compares methods on the untouched crop-profile test split; it measures fidelity to the EcoCrop screening teacher, not observed farm yield.

| Method | 80% coverage | 90% coverage | Mean 80% radius | Mean 90% radius |
|---|---:|---:|---:|---:|
| v0.5 disagreement bins | 95.7% | 97.7% | 0.226 | 0.308 |
| v0.5.1 normalized conformal | 80.0% | 89.8% | 0.005 | 0.125 |

The candidate reduces mean 90% radius by **59.5%** while bringing both marginal coverages to their nominal targets. Gate: **PASS**.

Intervals are marginal across unseen crop profiles. They are not per-species guarantees, yield intervals, or property-investment confidence.
