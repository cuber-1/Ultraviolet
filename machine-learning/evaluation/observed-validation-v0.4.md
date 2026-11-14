# CropFit EcoCrop surrogate v0.4 observed-outcome validation

**Gate: NOT PASSED**

California 2018–2022 county yields, 238 observations. Pooled within-crop Spearman: -0.028 (county-crop grouped-bootstrap 95% interval -0.202 to 0.146).

| Crop | Observations | Spearman | 95% interval | Median score | Median yield (tons/acre) |
|---|---:|---:|---:|---:|---:|
| corn | 49 | 0.144 | -0.038 to 0.272 | 92.9 | 5.260 |
| cucumber | 6 | 0.543 | 0.543 to 0.800 | 89.4 | 8.145 |
| lettuce | 26 | 0.226 | -0.181 to 0.634 | 81.0 | 14.975 |
| pepper | 33 | -0.357 | -0.751 to 0.104 | 92.6 | 22.110 |
| potato | 27 | -0.101 | -0.570 to 0.295 | 91.2 | 22.450 |
| strawberry | 8 | 0.119 | -0.737 to 0.842 | 96.5 | 40.530 |
| tomato | 28 | 0.121 | -0.304 to 0.367 | 93.2 | 21.240 |
| wheat | 61 | -0.243 | -0.547 to 0.095 | 86.5 | 2.700 |

| Year | Observations | Spearman |
|---|---:|---:|
| 2018 | 57 | 0.070 |
| 2019 | 54 | -0.041 |
| 2020 | 46 | 0.090 |
| 2021 | 35 | 0.053 |
| 2022 | 33 | 0.106 |

The gate rule was fixed before reading the result: pooled Spearman >= 0.30, bootstrap lower bound > 0, >=4 crops with >=6 observations, at least half of eligible crops positive, and at least 3 of 5 years positive.

## Interpretation

Passing would only justify continuing calibration work. It would not turn CropFit into a parcel-level yield forecast or property recommendation.

## Limitations

- County yield reflects cultivar, management, irrigation, soil, pests, economics, and reporting—not climate alone.
- One state across five years is an external face-validity test, not sufficient yield calibration.
- Confidence intervals resample county-crop groups, but one state still limits geographic independence.
- Suppressed or unreported county-crop combinations are absent rather than treated as zero yield.
