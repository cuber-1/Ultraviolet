# USDA county yield atlas v4 validation

The atlas stores each county's historical percentile within crop and year. Its production prior blends 80% three-year-half-life recency weighting with 20% of the stable long-history mean. The retrospective forward-year test predicts each year using only earlier years for that county.

| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |
|---:|---:|---:|---:|---:|---:|
| 2011 | 3,905 / 4,292 | 91.0% | 0.745 | 0.727 to 0.761 | 0.154 |
| 2012 | 4,119 / 4,324 | 95.3% | 0.600 | 0.580 to 0.620 | 0.194 |
| 2013 | 3,875 / 3,979 | 97.4% | 0.691 | 0.673 to 0.708 | 0.167 |
| 2014 | 4,029 / 4,119 | 97.8% | 0.734 | 0.717 to 0.750 | 0.153 |
| 2015 | 3,722 / 3,771 | 98.7% | 0.808 | 0.794 to 0.820 | 0.129 |
| 2016 | 3,782 / 3,830 | 98.8% | 0.798 | 0.784 to 0.812 | 0.132 |
| 2017 | 3,650 / 3,680 | 99.2% | 0.846 | 0.835 to 0.857 | 0.117 |
| 2018 | 3,278 / 3,300 | 99.3% | 0.864 | 0.854 to 0.873 | 0.112 |
| 2019 | 3,090 / 3,108 | 99.4% | 0.824 | 0.810 to 0.837 | 0.124 |
| 2020 | 3,994 / 4,054 | 98.5% | 0.854 | 0.844 to 0.863 | 0.114 |
| 2021 | 3,639 / 3,671 | 99.1% | 0.855 | 0.844 to 0.865 | 0.114 |
| 2022 | 3,699 / 3,724 | 99.3% | 0.849 | 0.838 to 0.860 | 0.116 |
| 2023 | 3,484 / 3,497 | 99.6% | 0.853 | 0.843 to 0.862 | 0.116 |
| 2024 | 2,433 / 2,443 | 99.6% | 0.812 | 0.795 to 0.828 | 0.128 |
| 2025 | 2,972 / 2,989 | 99.4% | 0.834 | 0.821 to 0.847 | 0.121 |

Pooled forward-year Spearman: **0.791** over 53,671 covered observations (95% interval 0.784 to 0.798).

## Fixed-window comparison

On the same 21,908 2019–2025 county-year rows, extending history from 2018 back to 2010 changed Spearman from **0.819** to **0.847** and percentile MAE from **0.126** to **0.117**. Gate: **PASS**.

## Calibrated uncertainty

The interval calibrator uses only 2011–2017 forward errors. On 2018–2025, the nominal 80% interval covered **84.1%** and the nominal 90% interval covered **92.5%** of 26,589 later outcomes. Mean 90% interval width was 0.506 percentile units. Gate: **PASS**.

## Spatial transfer

In the leave-one-county-out test, 54,677 of 54,781 target county-years had another reporting county within 100 km (99.8%). On locked 2023–2025 outcomes, nearest-county transfer reached Spearman **0.758** over 8,921 outcomes (95% interval 0.745 to 0.770).
Transfer intervals calibrated on 2011–2017 covered **83.5%** and **92.2%** on 2018–2025. Gate: **PASS**.

The production atlas contains 5,562 county-crop records. It is an observed historical prior with calibrated temporal and spatial-transfer uncertainty, not a parcel yield forecast.

> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.
