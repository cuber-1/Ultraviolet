# Crop-region interval scaling validation

Select the smallest crop-region scale meeting nominal coverage in both development and stability; sparse groups retain v10. Require >=4% narrower pooled 90% bands, calibrated pooled/stability/final blocks, reliable crop and region slices, and no final region above 98% 90%-coverage.

The candidate reduces mean 90% width from **0.5113** to **0.4899** (4.2%) while pooled coverage remains 81.6% / 91.6%.

It is **not promoted**: locked West 90% coverage rises to **100.0%**, above the predeclared 98% upper bound. This is over-conservative rather than falsely narrow, but it fails calibration sharpness.

Promotion gate: **NOT PASSED**.

Decision: retain atlas v10 regional interval scales.

> Observed county-rank evidence; not parcel yield, revenue, or property value.
