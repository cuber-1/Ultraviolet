# USDA crop-subtype yield atlas v1

Select neighborhood size, distance power, and history-reliability power on 2018-2020 only. Select neighbor-disagreement scaling only when it reduces development mean 90% width by at least 1%; stability still sets coverage scales. Leave-one-county-out transfer within 100 km then needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; paired-bootstrap rank-gain lower >0; positive rank gain and MAE reduction over one nearest county in development, stability, and locked final blocks; no rank or MAE regression versus the best development-selected distance-only candidate in any block. Regional interval multipliers selected on development/stability must reach 80%/90%; locked pooled coverage must be 75-90%/87-96%, and every region needs final N >=50, 80% coverage >=70%, 90% coverage 85-98%, and mean 90% width <=0.90.

| Crop subtype | Locked N | Transfer ρ | Δρ vs nearest (95% CI) | 80% coverage | 90% coverage | Decision |
|---|---:|---:|---:|---:|---:|---|
| silage corn | 585 | 0.511 | +0.077 (+0.018 to +0.139) | 80.7% | 90.1% | PROMOTE |
| spring wheat | 257 | 0.710 | +0.116 (+0.047 to +0.194) | 85.2% | 92.6% | PROMOTE |

Promotion gate: **PASS**. Atlas records: **690**.

Neighborhoods were selected on 2018-2020 development only; interval scales also had to hold on 2021-2022 stability. The 2023-2025 outcomes remained locked until final evaluation.

## History-reliability ablation

History-count weighting is retained only when the development-selected candidate does not regress rank or MAE against the best distance-only candidate in development, stability, or final blocks.

| Crop subtype | History power | Locked Δρ | 95% CI | Locked MAE reduction |
|---|---:|---:|---:|---:|
| silage corn | 1.0 | +0.0079 | -0.0097 to +0.0266 | +0.0008 |
| spring wheat | 0.0 | +0.0000 | +0.0000 to +0.0000 | +0.0000 |

## Disagreement-scaled uncertainty

Neighbor-disagreement scaling is selected only after at least a 1% development-width reduction; stability years still determine coverage scales.

| Crop subtype | Selected α | Development width reduction | Locked 90% coverage | Locked mean 90% width | α=0 width |
|---|---:|---:|---:|---:|---:|
| silage corn | 0.0 | 0.0% | 90.1% | 0.746 | 0.746 |
| spring wheat | 5.0 | 8.0% | 92.6% | 0.617 | 0.665 |

## Region-safe uncertainty

Only crop-region pairs with at least 50 examples in development, stability, and final blocks are published. Multipliers were selected before opening the final block.

| Crop subtype | Region | 80% scale | 90% scale | Locked N | 80% coverage | 90% coverage | Mean 90% width |
|---|---|---:|---:|---:|---:|---:|---:|
| silage corn | Midwest | 1.05× | 1.10× | 402 | 84.1% | 91.8% | 0.747 |
| silage corn | Northeast | 1.00× | 1.00× | 183 | 73.2% | 86.3% | 0.744 |
| spring wheat | Midwest | 1.00× | 1.05× | 163 | 87.1% | 94.5% | 0.622 |
| spring wheat | West | 1.15× | 1.05× | 94 | 81.9% | 89.4% | 0.608 |

> Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.
