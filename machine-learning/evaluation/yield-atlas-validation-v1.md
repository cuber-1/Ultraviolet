# USDA county yield atlas v1 validation

The atlas stores each county's historical percentile within crop and year. The retrospective forward-year test predicts each year using only earlier years for that county.

| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |
|---:|---:|---:|---:|---:|---:|
| 2019 | 2,531 / 3,108 | 81.4% | 0.759 | 0.739 to 0.776 | 0.151 |
| 2020 | 3,469 / 4,054 | 85.6% | 0.819 | 0.805 to 0.831 | 0.126 |
| 2021 | 3,518 / 3,671 | 95.8% | 0.826 | 0.813 to 0.839 | 0.125 |
| 2022 | 3,627 / 3,724 | 97.4% | 0.832 | 0.819 to 0.843 | 0.121 |

Pooled forward-year Spearman: **0.812** over 13,145 covered observations (95% interval 0.802 to 0.820).

The production atlas contains 4,712 county-crop records. It is a descriptive historical prior, not a trained yield forecast.

> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.
