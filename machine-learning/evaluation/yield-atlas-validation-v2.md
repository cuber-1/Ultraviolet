# USDA county yield atlas v2 validation

The atlas stores each county's historical percentile within crop and year. The retrospective forward-year test predicts each year using only earlier years for that county.

| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |
|---:|---:|---:|---:|---:|---:|
| 2011 | 3,905 / 4,292 | 91.0% | 0.745 | 0.727 to 0.761 | 0.154 |
| 2012 | 4,119 / 4,324 | 95.3% | 0.599 | 0.579 to 0.620 | 0.194 |
| 2013 | 3,875 / 3,979 | 97.4% | 0.696 | 0.678 to 0.713 | 0.166 |
| 2014 | 4,029 / 4,119 | 97.8% | 0.729 | 0.711 to 0.744 | 0.155 |
| 2015 | 3,722 / 3,771 | 98.7% | 0.810 | 0.796 to 0.822 | 0.129 |
| 2016 | 3,782 / 3,830 | 98.8% | 0.799 | 0.785 to 0.813 | 0.132 |
| 2017 | 3,650 / 3,680 | 99.2% | 0.835 | 0.823 to 0.846 | 0.122 |
| 2018 | 3,278 / 3,300 | 99.3% | 0.856 | 0.846 to 0.866 | 0.116 |
| 2019 | 3,090 / 3,108 | 99.4% | 0.818 | 0.803 to 0.831 | 0.127 |
| 2020 | 3,994 / 4,054 | 98.5% | 0.845 | 0.835 to 0.854 | 0.118 |
| 2021 | 3,639 / 3,671 | 99.1% | 0.855 | 0.844 to 0.865 | 0.115 |
| 2022 | 3,699 / 3,724 | 99.3% | 0.846 | 0.834 to 0.857 | 0.118 |
| 2023 | 3,484 / 3,497 | 99.6% | 0.835 | 0.824 to 0.845 | 0.124 |
| 2024 | 2,433 / 2,443 | 99.6% | 0.811 | 0.794 to 0.828 | 0.128 |
| 2025 | 2,972 / 2,989 | 99.4% | 0.830 | 0.817 to 0.843 | 0.123 |

Pooled forward-year Spearman: **0.787** over 53,671 covered observations (95% interval 0.779 to 0.794).

## Fixed-window comparison

On the same 21,908 2019–2025 county-year rows, extending history from 2018 back to 2010 changed Spearman from **0.819** to **0.841** and percentile MAE from **0.127** to **0.120**. Gate: **PASS**.

## Calibrated uncertainty

The interval calibrator uses only 2011–2017 forward errors. On 2018–2025, the nominal 80% interval covered **83.5%** and the nominal 90% interval covered **92.3%** of 26,589 later outcomes. Mean 90% interval width was 0.513 percentile units. Gate: **PASS**.

The production atlas contains 5,562 county-crop records. It is an observed historical prior with calibrated uncertainty, not a parcel yield forecast.

> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.
