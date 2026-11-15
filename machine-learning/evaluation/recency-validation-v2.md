# USDA observed-prior recency validation v2

**Production gate: PASS**

The half-life and shrinkage weight were selected on 2018–2020 only. Selected: **3 years**, with **80% recency / 20% long-history**.

On the locked 2023–2025 test (8,889 rows), Spearman changed from **0.8269** to **0.8352** (delta +0.0083; grouped-bootstrap 95% interval +0.0061 to +0.0104). Percentile MAE changed by -0.0040.

| Crop | N | Baseline rho | Recency rho | Delta | MAE delta |
|---|---:|---:|---:|---:|---:|
| corn | 3,889 | 0.8362 | 0.8445 | +0.0083 | -0.0041 |
| soybean | 3,454 | 0.8215 | 0.8286 | +0.0071 | -0.0035 |
| wheat | 1,546 | 0.8221 | 0.8288 | +0.0067 | -0.0046 |

Gate rule: Confirmation must not regress rank or MAE. On the locked 2023–2025 test, pooled rank delta and grouped-bootstrap lower bound must be >0, MAE must not regress, and every crop and year rank delta must be non-negative.

> This tests county-level regional ordering only, not parcel yield or purchase returns.
