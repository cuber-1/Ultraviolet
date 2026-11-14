# USDA county yield atlas v1 validation

The atlas stores each county's historical percentile within crop and year. The retrospective forward-year test predicts each year using only earlier years for that county.

| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |
|---:|---:|---:|---:|---:|---:|
| 2019 | 2,531 / 3,108 | 81.4% | 0.759 | 0.739 to 0.776 | 0.151 |
| 2020 | 3,469 / 4,054 | 85.6% | 0.819 | 0.805 to 0.831 | 0.126 |
| 2021 | 3,518 / 3,671 | 95.8% | 0.826 | 0.813 to 0.839 | 0.125 |
| 2022 | 3,627 / 3,724 | 97.4% | 0.832 | 0.819 to 0.843 | 0.121 |
| 2023 | 3,442 / 3,497 | 98.4% | 0.849 | 0.839 to 0.859 | 0.117 |
| 2024 | 2,412 / 2,443 | 98.7% | 0.810 | 0.793 to 0.826 | 0.128 |
| 2025 | 2,909 / 2,989 | 97.3% | 0.828 | 0.814 to 0.841 | 0.123 |

Pooled forward-year Spearman: **0.819** over 21,908 covered observations (95% interval 0.811 to 0.826).

The production atlas contains 4,878 county-crop records. It is a descriptive historical prior, not a trained yield forecast.

> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.
