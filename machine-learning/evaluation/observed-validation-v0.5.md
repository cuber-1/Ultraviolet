# CropFit EcoCrop surrogate v0.5 observed-outcome validation

**Gate: NOT PASSED**

California 2018–2022 county yields, 238 observations. Pooled within-crop Spearman: -0.036 (county-crop grouped-bootstrap 95% interval -0.201 to 0.134).

| Crop | Observations | Spearman | 95% interval | Median score | Median yield (tons/acre) |
|---|---:|---:|---:|---:|---:|
| corn | 49 | 0.180 | -0.011 to 0.338 | 93.2 | 5.260 |
| cucumber | 6 | 0.441 | 0.441 to 0.564 | 98.2 | 8.145 |
| lettuce | 26 | 0.307 | 0.255 to 0.577 | 100.0 | 14.975 |
| pepper | 33 | -0.168 | -0.397 to 0.326 | 98.9 | 22.110 |
| potato | 27 | -0.470 | -0.831 to 0.071 | 95.2 | 22.450 |
| strawberry | 8 | — | — | 100.0 | 40.530 |
| tomato | 28 | 0.053 | -0.601 to 0.450 | 96.7 | 21.240 |
| wheat | 61 | -0.211 | -0.576 to 0.177 | 96.1 | 2.700 |

| Year | Observations | Spearman |
|---|---:|---:|
| 2018 | 57 | -0.067 |
| 2019 | 54 | -0.168 |
| 2020 | 46 | 0.189 |
| 2021 | 35 | 0.019 |
| 2022 | 33 | -0.102 |

The gate rule was fixed before reading the result: pooled Spearman >= 0.30, bootstrap lower bound > 0, >=4 crops with >=6 observations, at least half of eligible crops positive, and at least 3 of 5 years positive.

## Interpretation

Passing would only justify continuing calibration work. It would not turn CropFit into a parcel-level yield forecast or property recommendation.

## Limitations

- County yield reflects cultivar, management, irrigation, soil, pests, economics, and reporting—not climate alone.
- One state across five years is an external face-validity test, not sufficient yield calibration.
- Confidence intervals resample county-crop groups, but one state still limits geographic independence.
- Suppressed or unreported county-crop combinations are absent rather than treated as zero yield.
