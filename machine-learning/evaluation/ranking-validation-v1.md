# CropFit observed-ranking blend v1

**Blend gate: NOT PASSED**

The selected blend uses 90% observed county prior and 10% agroclimatic score. Candidate weight was selected on 2018–2020 only.

On untouched 2023–2025 outcomes (8,889 rows), Spearman changed from **0.8269** to **0.8286** (delta +0.0017; county-crop grouped-bootstrap 95% interval +0.0008 to +0.0027).

| Crop | N | Prior ρ | Hybrid ρ | Delta |
|---|---:|---:|---:|---:|
| corn | 3,889 | 0.8362 | 0.8385 | +0.0023 |
| soybean | 3,454 | 0.8215 | 0.8196 | -0.0019 |
| wheat | 1,546 | 0.8221 | 0.8291 | +0.0070 |

| Year | N | Prior ρ | Hybrid ρ | Delta |
|---:|---:|---:|---:|---:|
| 2023 | 3,484 | 0.8350 | 0.8387 | +0.0037 |
| 2024 | 2,433 | 0.8112 | 0.8121 | +0.0010 |
| 2025 | 2,972 | 0.8304 | 0.8306 | +0.0002 |

Blend gate rule: On untouched 2023–2025 rows: pooled rank delta and grouped-bootstrap lower bound > 0, every crop non-negative, and at least two of three years positive.

## Production ranking decision

On the same untouched rows, the observed prior scored **0.8269** versus **0.0299** for the current agroclimatic-only ranking (advantage +0.7970; grouped-bootstrap 95% interval +0.7691 to +0.8243). Production gate: **PASS**.

Use the observed prior only for supported crops in rural regional ranking; keep agroclimatic suitability for planting timing and unsupported crops. Do not promote the failed blend.

> This validates ordering counties for supported crops. It does not validate parcel yield, revenue, or purchase returns.
