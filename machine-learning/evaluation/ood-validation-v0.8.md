# CropFit seasonal-ceiling validation

The ML score is capped by the exact seasonal and establishment EcoCrop suitability already computed for limiting-factor explanations. The clamp only removes surrogate overestimation; it does not replace ML underestimation.

| Held-out path | MAE | p90 error | Maximum error |
|---|---:|---:|---:|
| Raw CropFit EcoCrop surrogate v0.8 | 0.0175 | 0.0491 | 4.136 |
| Deployed seasonal ceiling | 0.0068 | 0.0013 | 0.828 |

Existing p80/p90 radii remain conservative at **89.9% / 95.0%** coverage.

At exact solar and temperature absolute boundaries, the teacher score is zero. The raw ensemble can extrapolate nonzero values because continuous training samples almost never land exactly on a boundary; the ceiling reduces all tested boundary errors to zero.

Gate: **PASS**.

> This improves fidelity to EcoCrop constraints. It does not validate yield, revenue, or property value.
