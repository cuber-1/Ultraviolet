# CropFit EcoCrop surrogate v0.5 nationwide observed-outcome validation

**Independent gate: NOT PASSED**

2018–2022 published county yields outside California, 17,857 observations. Pooled within-crop-year Spearman: 0.080 (county-crop grouped-bootstrap 95% interval 0.058 to 0.103).

| Crop | Observations | Spearman | 95% interval | Median score |
|---|---:|---:|---:|---:|
| corn | 7,234 | -0.026 | -0.060 to 0.009 | 83.9 |
| soybean | 6,442 | 0.163 | 0.132 to 0.192 | 100.0 |
| wheat | 4,181 | 0.282 | 0.237 to 0.323 | 79.7 |

| Year | Observations | Spearman | 95% interval |
|---|---:|---:|---:|
| 2018 | 3,300 | 0.123 | 0.088 to 0.157 |
| 2019 | 3,108 | -0.062 | -0.097 to -0.026 |
| 2020 | 4,054 | 0.102 | 0.071 to 0.133 |
| 2021 | 3,671 | 0.099 | 0.065 to 0.134 |
| 2022 | 3,724 | 0.121 | 0.090 to 0.152 |

Gate rule: pooled Spearman >= 0.30, grouped-bootstrap lower bound > 0, every crop positive, and at least 4 of 5 years positive.

Protocol timing: Declared after the California gate failed and before nationwide outcomes were scored.

Passing would only justify a separate yield-calibration study. It would not make the current suitability score a yield forecast.

## Limitations

- County yield reflects management, soil, genetics, pests, and economics in addition to weather.
- All-production-practice yield is evaluated with a non-irrigated model assumption.
- Quick Stats suppresses some county estimates; missing rows are not treated as zero yield.
