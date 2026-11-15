# USDA crop-subtype yield atlas v1

Select neighborhood size, distance power, and history-reliability power on 2018-2020 only. Promote a crop-specific temporal blend only after at least +0.005 development Spearman with lower MAE and no rank or MAE regression in 2021-2022 stability. Select neighbor-disagreement scaling and region-conditioned calibration only when each reduces development mean 90% width by at least 1%; regional calibration also needs at least 50 pre-2018 errors per region/history group, and stability still sets coverage scales. Leave-one-county-out transfer within 100 km then needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; paired-bootstrap rank-gain lower >0; positive rank gain and MAE reduction over one nearest county in development, stability, and locked final blocks; no rank or MAE regression versus the best development-selected distance-only candidate in any block. Regional interval multipliers selected on development/stability must reach 80%/90%; locked pooled coverage must be 75-90%/87-96%, and every region needs final N >=50, 80% coverage >=70%, 90% coverage 85-98%, and mean 90% width <=0.90.

| Crop subtype | Locked N | Transfer ρ | Δρ vs nearest (95% CI) | 80% coverage | 90% coverage | Decision |
|---|---:|---:|---:|---:|---:|---|
| silage corn | 585 | 0.522 | +0.079 (+0.020 to +0.141) | 82.2% | 89.9% | PROMOTE |
| spring wheat | 257 | 0.710 | +0.116 (+0.047 to +0.194) | 85.6% | 92.6% | PROMOTE |

Promotion gate: **PASS**. Atlas records: **690**.

Neighborhoods were selected on 2018-2020 development only; interval scales also had to hold on 2021-2022 stability. The 2023-2025 outcomes remained locked until final evaluation.

## History-reliability ablation

History-count weighting is retained only when the development-selected candidate does not regress rank or MAE against the best distance-only candidate in development, stability, or final blocks.

| Crop subtype | History power | Locked Δρ | 95% CI | Locked MAE reduction |
|---|---:|---:|---:|---:|
| silage corn | 1.0 | +0.0093 | -0.0091 to +0.0288 | +0.0010 |
| spring wheat | 0.0 | +0.0000 | +0.0000 to +0.0000 | +0.0000 |

## Crop-specific temporal memory

The generic 80% recency blend is replaced only after a meaningful development rank gain, lower development MAE, and rank/MAE confirmation in stability years.

| Crop subtype | Recency weight | Development Δρ | Stability Δρ | Locked Δρ (95% CI) | Locked MAE reduction |
|---|---:|---:|---:|---:|---:|
| silage corn | 0.25 | +0.0134 | +0.0139 | +0.0115 (+0.0006 to +0.0234) | +0.0018 |
| spring wheat | 0.80 | +0.0000 | +0.0000 | +0.0000 (+0.0000 to +0.0000) | +0.0000 |

## Disagreement-scaled uncertainty

Neighbor-disagreement scaling is selected only after at least a 1% development-width reduction; stability years still determine coverage scales.

| Crop subtype | Selected α | Development width reduction | Locked 90% coverage | Locked mean 90% width | α=0 width |
|---|---:|---:|---:|---:|---:|
| silage corn | 0.0 | 0.0% | 89.9% | 0.750 | 0.750 |
| spring wheat | 5.0 | 8.0% | 92.6% | 0.617 | 0.665 |

## Region-conditioned calibration

Regional conformal groups are retained only after at least a 1% development-width reduction and at least 50 pre-2018 errors per region/history group; pooled groups remain available as fallback.

| Crop subtype | Selected scope | Development width reduction | Locked 90% coverage | Locked mean 90% width | Pooled width |
|---|---|---:|---:|---:|---:|
| silage corn | pooled | 0.0% | 89.9% | 0.750 | 0.750 |
| spring wheat | region-conditioned | 1.2% | 92.6% | 0.608 | 0.617 |

## Region-safe uncertainty

Only crop-region pairs with at least 50 examples in development, stability, and final blocks are published. Multipliers were selected before opening the final block.

| Crop subtype | Region | 80% scale | 90% scale | Locked N | 80% coverage | 90% coverage | Mean 90% width |
|---|---|---:|---:|---:|---:|---:|---:|
| silage corn | Midwest | 1.10× | 1.10× | 402 | 86.3% | 91.0% | 0.751 |
| silage corn | Northeast | 1.00× | 1.00× | 183 | 73.2% | 87.4% | 0.746 |
| spring wheat | Midwest | 1.05× | 1.05× | 163 | 87.7% | 94.5% | 0.606 |
| spring wheat | West | 1.10× | 1.00× | 94 | 81.9% | 89.4% | 0.613 |

> Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.
