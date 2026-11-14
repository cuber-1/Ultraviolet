# CropFit EcoCrop surrogate v0.5

- Trained: 2026-11-14
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated training scenarios: 134,064
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: Random Forest
- MAE: 0.1519 suitability points
- R²: 0.9996
- 90th percentile absolute error: 0.4443 points

Version 0.5 adds four crop-relative features: temperature, water, pH, and solar
membership within each crop's absolute and optimum ranges. The 120-tree Random
Forest still receives the raw climate and profile fields. Against the v0.4
feature design, it improved held-out MAE on all five robustness seeds from
20261110 through 20261114. Mean MAE fell from 5.3968 to 0.1536 (97.15%). The
reproducible protocol and per-seed results are in
`evaluation/feature-validation-v0.5.md`.

Error bands are calibrated only on validation crop profiles, never the held-out
test profiles. The nominal p80 and p90 bands conservatively covered 95.71% and
97.72% of the held-out examples, respectively.

The CUDA XGBoost candidate completed 500 rounds with a cosine learning-rate
schedule from 0.08 to 0.005. It was not promoted because held-out-profile MAE
was worse (0.6395). The committed diagnostics are
`evaluation/training-curves-v0.5.png`,
`evaluation/selected-feature-importance-v0.5.png`, and
`evaluation/training-history-v0.5.csv`.

## Intended use

Monthly agroclimatic screening and crop-window comparison. The model estimates
how closely climate, water assumptions, soil pH, and solar resource match an
EcoCrop profile.

## Prohibited interpretation

The near-perfect R² is fidelity to a deterministic mechanistic teacher, not
real-world crop prediction accuracy. This version is not trained on observed
parcel yields. It must not be presented
as expected production, revenue, agronomic advice, or a property purchase
recommendation. USDA NASS and DSSAT calibration is the next evidence gate.

## Observed-outcome gate

The v0.5 rerun of the first external test uses 238 California county-crop yield
observations from 2018–2022, actual-year NASA POWER weather, and a gate declared before inspecting
the 2018–2021 results. The gate did not pass: pooled within-crop Spearman was
-0.0357 with a grouped-bootstrap interval crossing zero. CropFit remains an
agroclimatic screening model. See `evaluation/observed-validation-v0.5.md`.

A second protocol was declared before inspecting nationwide results. It tested
17,857 published 2018–2022 county-year yields for corn, soybeans, and winter
wheat across the contiguous U.S., excluding California. The independent gate
also did not pass. Pooled within-crop-year Spearman was 0.0804 (grouped 95%
interval 0.0582–0.1031): statistically detectable at this sample size but far
below the predeclared 0.30 threshold. Corn and 2019 were negative. See
`evaluation/national-observed-validation-v0.5.md`.

## Historical county evidence

CropFit also returns a separate USDA observed county prior for corn, soybeans,
and wheat when a published county centroid is within 100 km. This evidence does
not alter CropFit suitability or ranking. Atlas v2 contains 5,562 county-crop
records from 2010–2025 and adds crop/history-count conditional conformal
uncertainty bands.

On the same 21,908 2019–2025 county-year rows, extending the available history
from 2018 back to 2010 improved pooled Spearman from 0.819 to 0.841 and reduced
percentile MAE from 0.127 to 0.120. Coverage increased from 21,908 to 23,311
rows. Uncertainty was calibrated on 2011–2017 only; across 26,589 later
2018–2025 outcomes, nominal 80% and 90% intervals covered 83.5% and 92.3%.
This measures persistence of county yield ranks, not parcel yield forecasting.
See `evaluation/yield-atlas-validation-v2.md`.

## Rural regional ranking

The rural workflow uses the observed county prior—not the EcoCrop score—to
order regions for corn, soybeans, and wheat when nearby USDA evidence exists.
CropFit still supplies planting timing; unsupported crops continue to use its
agroclimatic suitability.

This policy was tested on 8,889 untouched 2023–2025 county-year outcomes. The
observed prior reached Spearman 0.8269 versus 0.0299 for climate-only ranking;
the paired county-crop bootstrap advantage was 0.7691–0.8243 and was positive
for every supported crop. A 90% prior / 10% climate blend was rejected because
soybean regressed despite a small positive pooled result. Urban rooftop ranking
is unchanged because county farm yields are not roof-specific. See
`evaluation/ranking-validation-v1.md`.
