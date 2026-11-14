# CropFit EcoCrop surrogate v0.4 nationwide observed-outcome validation

**Independent gate: NOT PASSED**

2018–2022 published county yields outside California, 17,857 observations. Pooled within-crop-year Spearman: 0.064 (county-crop grouped-bootstrap 95% interval 0.043 to 0.086).

| Crop | Observations | Spearman | 95% interval | Median score |
|---|---:|---:|---:|---:|
| corn | 7,234 | -0.014 | -0.047 to 0.021 | 80.8 |
| soybean | 6,442 | 0.058 | 0.028 to 0.086 | 91.4 |
| wheat | 4,181 | 0.300 | 0.253 to 0.343 | 79.0 |

| Year | Observations | Spearman | 95% interval |
|---|---:|---:|---:|
| 2018 | 3,300 | 0.094 | 0.057 to 0.128 |
| 2019 | 3,108 | -0.102 | -0.139 to -0.066 |
| 2020 | 4,054 | 0.102 | 0.070 to 0.133 |
| 2021 | 3,671 | 0.096 | 0.062 to 0.131 |
| 2022 | 3,724 | 0.096 | 0.063 to 0.129 |

Gate rule: pooled Spearman >= 0.30, grouped-bootstrap lower bound > 0, every crop positive, and at least 4 of 5 years positive.

Protocol timing: Declared after the California gate failed and before nationwide outcomes were scored.

Passing would only justify a separate yield-calibration study. It would not make the current suitability score a yield forecast.

## Limitations

- County yield reflects management, soil, genetics, pests, and economics in addition to weather.
- All-production-practice yield is evaluated with a non-irrigated model assumption.
- Quick Stats suppresses some county estimates; missing rows are not treated as zero yield.
