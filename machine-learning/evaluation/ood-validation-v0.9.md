# CropFit seasonal-ceiling validation

The ML score is capped by the exact seasonal and establishment EcoCrop suitability already computed for limiting-factor explanations. The clamp only removes surrogate overestimation; it does not replace ML underestimation.

| Held-out path | MAE | p90 error | Maximum error |
|---|---:|---:|---:|
| Raw CropFit EcoCrop surrogate v0.9 | 0.0145 | 0.0407 | 3.337 |
| Deployed seasonal ceiling | 0.0063 | 0.0014 | 0.581 |

Existing p80/p90 radii remain conservative at **89.9% / 95.0%** coverage.

At exact solar and temperature absolute boundaries, the teacher score is zero. The raw ensemble can extrapolate nonzero values because continuous training samples almost never land exactly on a boundary; the ceiling reduces all tested boundary errors to zero.

Gate: **PASS**.

> This improves fidelity to EcoCrop constraints. It does not validate yield, revenue, or property value.
