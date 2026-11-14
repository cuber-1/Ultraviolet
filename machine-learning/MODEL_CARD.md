# CropFit EcoCrop surrogate v0.4

- Trained: 2026-11-14
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated training scenarios: 134,064
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: Random Forest
- MAE: 5.3558 suitability points
- R²: 0.8470
- 90th percentile absolute error: 18.6914 points

Version 0.4 uses 120 Random Forest estimators, one-sample leaves, and all
features at each split. Against v0.3 ExtraTrees, it improved held-out MAE on all
five robustness seeds from 20261110 through 20261114. Mean MAE fell from 6.7431
to 5.3968 (20.0%). The artifact also shrank from 99 MB to 52 MB.

Tree disagreement has a 0.97 Spearman correlation with absolute error on the
validation split. Error bands are calibrated only on validation crop profiles,
never the held-out test profiles. The nominal p80 and p90 bands conservatively
covered 90.08% and 95.19% of the held-out examples, respectively.

The CUDA XGBoost candidate completed 500 rounds with a cosine learning-rate
schedule from 0.08 to 0.005. It was not promoted because held-out-profile MAE
was worse (8.951). Every run stores `history.csv`, `config.json`, metrics,
learning-rate/loss/error plots, and feature-importance plots under `machine-learning/runs/`.

## Intended use

Monthly agroclimatic screening and crop-window comparison. The model estimates
how closely climate, water assumptions, soil pH, and solar resource match an
EcoCrop profile.

## Prohibited interpretation

This version is not trained on observed parcel yields. It must not be presented
as expected production, revenue, agronomic advice, or a property purchase
recommendation. USDA NASS and DSSAT calibration is the next evidence gate.

## Observed-outcome gate

The first external test uses 238 California county-crop yield observations from
2018–2022, actual-year NASA POWER weather, and a gate declared before inspecting
the 2018–2021 results. The gate did not pass: pooled within-crop Spearman was
-0.0276 with a grouped-bootstrap interval crossing zero. CropFit remains an
agroclimatic screening model. See `evaluation/observed-validation-v0.4.md`.

A second protocol was declared before inspecting nationwide results. It tested
17,857 published 2018–2022 county-year yields for corn, soybeans, and winter
wheat across the contiguous U.S., excluding California. The independent gate
also did not pass. Pooled within-crop-year Spearman was 0.0644 (grouped 95%
interval 0.0428–0.0856): statistically detectable at this sample size but far
below the predeclared 0.30 threshold. Corn was slightly negative and 2019 was
negative. See `evaluation/national-observed-validation-v0.4.md`.
