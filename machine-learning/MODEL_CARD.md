# CropFit EcoCrop surrogate v0.3

- Trained: 2026-11-14
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated training scenarios: 134,064
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: ExtraTrees
- MAE: 6.6077 suitability points
- R²: 0.8365
- 90th percentile absolute error: 20.0545 points

Version 0.3 uses 120 ExtraTrees estimators, one-sample leaves, and all features
at each split. Against the previous configuration, it improved held-out MAE on
all five robustness seeds from 20261110 through 20261114. Mean MAE fell from
7.3086 to 6.7431 (7.7%). The production-seed artifact is also smaller than a
160-tree version of the same candidate, keeping local Mac inference practical.

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
