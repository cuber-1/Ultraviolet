# USDA crop-subtype yield atlas v1

Select neighborhood size and distance power on 2018-2020 only. Leave-one-county-out transfer within 100 km then needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; paired-bootstrap rank-gain lower >0; positive rank gain and MAE reduction over one nearest county in development, stability, and locked final blocks. Regional interval multipliers selected on development/stability must reach 80%/90%; locked pooled coverage must be 75-90%/87-96%, and every region needs final N >=50, 80% coverage >=70%, 90% coverage 85-98%, and mean 90% width <=0.90.

| Crop subtype | Locked N | Transfer ρ | Δρ vs nearest (95% CI) | 80% coverage | 90% coverage | Decision |
|---|---:|---:|---:|---:|---:|---|
| silage corn | 585 | 0.503 | +0.069 (+0.014 to +0.126) | 82.4% | 90.6% | PROMOTE |
| spring wheat | 257 | 0.710 | +0.116 (+0.047 to +0.194) | 86.0% | 93.4% | PROMOTE |

Promotion gate: **PASS**. Atlas records: **690**.

Neighborhoods were selected on 2018-2020 development only; interval scales also had to hold on 2021-2022 stability. The 2023-2025 outcomes remained locked until final evaluation.

## Region-safe uncertainty

Only crop-region pairs with at least 50 examples in development, stability, and final blocks are published. Multipliers were selected before opening the final block.

| Crop subtype | Region | 80% scale | 90% scale | Locked N | 80% coverage | 90% coverage | Mean 90% width |
|---|---|---:|---:|---:|---:|---:|---:|
| silage corn | Midwest | 1.10× | 1.05× | 402 | 85.8% | 91.3% | 0.753 |
| silage corn | Northeast | 1.05× | 1.00× | 183 | 74.9% | 89.1% | 0.777 |
| spring wheat | Midwest | 1.00× | 1.00× | 163 | 90.2% | 96.9% | 0.644 |
| spring wheat | West | 1.33× | 1.33× | 94 | 78.7% | 87.2% | 0.702 |

> Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.
