# USDA crop-subtype yield atlas v1

Select neighborhood size and distance power on 2018-2020 only. Leave-one-county-out transfer within 100 km then needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; paired-bootstrap rank-gain lower >0; positive rank gain and MAE reduction over one nearest county in development, stability, and locked final blocks; pre-final development/stability coverage >=78%/88%; locked 2023-2025 coverage 75-90%/87-96%; mean final 90% width <=0.80.

| Crop subtype | Locked N | Transfer ρ | Δρ vs nearest (95% CI) | 80% coverage | 90% coverage | Decision |
|---|---:|---:|---:|---:|---:|---|
| silage corn | 585 | 0.503 | +0.069 (+0.014 to +0.126) | 78.6% | 90.1% | PROMOTE |
| spring wheat | 257 | 0.710 | +0.116 (+0.047 to +0.194) | 83.7% | 90.3% | PROMOTE |

Promotion gate: **PASS**. Atlas records: **721**.

Neighborhoods were selected on 2018-2020 development only; interval scales also had to hold on 2021-2022 stability. The 2023-2025 outcomes remained locked until final evaluation.

> Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.
