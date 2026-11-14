# USDA observed-prior recency validation v1

**Production gate: NOT PASSED**

The half-life was selected on 2018–2020 only. Selected: **3 years**.

On the locked 2023–2025 test (8,889 rows), Spearman changed from **0.8269** to **0.8346** (delta +0.0077; grouped-bootstrap 95% interval +0.0052 to +0.0102). Percentile MAE changed by -0.0041.

| Crop | N | Baseline rho | Recency rho | Delta | MAE delta |
|---|---:|---:|---:|---:|---:|
| corn | 3,889 | 0.8362 | 0.8439 | +0.0077 | -0.0043 |
| soybean | 3,454 | 0.8215 | 0.8277 | +0.0062 | -0.0035 |
| wheat | 1,546 | 0.8221 | 0.8283 | +0.0062 | -0.0049 |

Gate rule: Confirmation must not regress rank or MAE. On the locked 2023–2025 test, pooled rank delta and grouped-bootstrap lower bound must be >0, MAE must not regress, and every crop and year rank delta must be non-negative.

> This tests county-level regional ordering only, not parcel yield or purchase returns.
