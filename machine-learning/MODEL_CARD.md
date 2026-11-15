# CropFit EcoCrop surrogate v0.6

- Trained: 2026-11-14
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated training scenarios: 134,064
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: Extra Trees
- Raw estimator MAE: 0.0894 suitability points
- Deployed score MAE after deterministic seasonal ceiling: 0.0362 points
- R²: 0.9998
- Raw estimator 90th percentile absolute error: 0.2289 points
- Deployed score 90th percentile absolute error: 0.0361 points

Version 0.6 replaces the 120-tree Random Forest with a 120-tree Extra Trees
estimator while preserving the same 23 inputs and Mac-compatible scikit-learn
runtime. Across two confirmation and five final grouped crop-profile seeds, it
won 7/7 gates. Final-seed mean MAE fell 43.2% and p90 error fell 47.6%; mean
API-sized batch latency was 1.05× the Random Forest. On the production split,
MAE fell from 0.1519 to 0.0894. See
`evaluation/estimator-validation-v0.6.md`.

The compressed artifact is 73 MB versus 43 MB for v0.5.1. On the development
host, clean-load peak RSS was 754 MiB versus 531 MiB and full reliability
prediction median latency was 5.30 ms versus 5.18 ms. Timings and RSS are
machine-dependent; Apple Silicon installation and loopback inference remain CI
requirements.

An 80-tree compact candidate reduced serialized estimator size to about 67% of
the champion, but failed the frozen accuracy tolerance on all seven fresh
seeds: mean MAE regressed 4.1% and mean p90 error regressed 5.9%. It was
rejected; v0.6 retains 120 trees. See `evaluation/compact-validation-v1.md`.

## Out-of-distribution ceiling

API v0.6.1 caps the ML score by the exact seasonal and establishment EcoCrop
suitability already computed for limiting-factor explanations. This is a
one-sided safety constraint: the ensemble still determines underprediction but
cannot claim suitability above the mechanistic target it approximates.

On the production held-out split, the ceiling reduced MAE from 0.0894 to 0.0362
and p90 error from 0.2289 to 0.0361 without increasing any example's error.
Existing intervals remained conservative at 88.2%/93.7% coverage. It also
eliminated raw errors as high as 64.6 points at exact hard solar boundaries,
where continuous random training samples do not land. See
`evaluation/ood-validation-v0.6.1.md`.

Version 0.5 adds four crop-relative features: temperature, water, pH, and solar
membership within each crop's absolute and optimum ranges. The 120-tree Random
Forest still receives the raw climate and profile fields. Against the v0.4
feature design, it improved held-out MAE on all five robustness seeds from
20261110 through 20261114. Mean MAE fell from 5.3968 to 0.1536 (97.15%). The
reproducible protocol and per-seed results are in
`evaluation/feature-validation-v0.5.md`.

Version 0.6 refits the v0.5.1 tree-disagreement-normalized split-conformal
calibrator using only 224 validation crop profiles. On 26,856 held-out examples
from 373 crop profiles, nominal 80% and 90% bands covered 80.06% and 90.10%; the
mean 90% radius was 0.068 suitability points. Across the seven locked estimator
validation seeds, mean coverage was 79.95% and 90.08%. These are marginal
EcoCrop-teacher fidelity bands, not per-species or observed-yield guarantees.

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
not alter CropFit suitability or ranking. Atlas v3 contains 5,562 county-crop
records from 2010–2025, uses a validated shrunken-recency prior, and includes
crop/history-count conditional conformal uncertainty bands.

On the same 21,908 2019–2025 county-year rows, extending the available history
from 2018 back to 2010 improved pooled Spearman from 0.819 to 0.847 and reduced
percentile MAE from 0.126 to 0.117. Coverage increased from 21,908 to 23,311
rows. Uncertainty was calibrated on 2011–2017 only; across 26,589 later
2018–2025 outcomes, nominal 80% and 90% intervals covered 84.1% and 92.5%.
This measures persistence of county yield ranks, not parcel yield forecasting.
See `evaluation/yield-atlas-validation-v3.md`.

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

## Crop-coverage expansion gate

Three additional USDA county series were tested before expanding the observed
prior: dry edible beans, potatoes, and oil-type sunflowers. None passed the
predeclared forward-year gate (at least 100 predictions, Spearman at least
0.50, county-bootstrap lower bound above 0.30, and at least 50% coverage).

The current bean definition produced 81 forward predictions with Spearman
0.3184 (95% interval 0.0036–0.5446). The apparently stronger legacy bean series
was not joined to it: USDA NASS states that dry edible beans began excluding
chickpeas in 2019. Potatoes had only four predictions, while sunflower reached
135 but only 0.2724 Spearman. Production coverage therefore remains corn,
soybeans, and wheat. See `evaluation/crop-expansion-validation-v1.md`.

## Recency experiment

Atlas v3 shrinks an exponential recency estimate toward the stable long-history
mean. The half-life and shrinkage weight were selected on 2018–2020 only: 80%
three-year-half-life recency and 20% long-history mean. Confirmation Spearman
improved from 0.8497 to 0.8513 while MAE fell from 0.1167 to 0.1150. On the
locked 2023–2025 test, Spearman improved from 0.8269 to 0.8352 (delta +0.0083;
grouped-bootstrap 95% interval +0.0061 to +0.0104) and MAE fell by 0.0040.
Every supported crop and every final-test year improved both rank and MAE, so
the predeclared production gate passed. See
`evaluation/recency-validation-v2.md`.

Rebuilding the full forward-year atlas with the promoted prior improved pooled
Spearman from 0.7871 to 0.7914. On identical 2019–2025 rows, 16-year-history
Spearman improved from 0.8405 to 0.8465 and MAE from 0.1199 to 0.1168. Fresh
split-conformal calibration covered 84.1% and 92.5% at the nominal 80% and 90%
levels. See `evaluation/yield-atlas-validation-v3.md`.

Atlas lookup now uses a cached exact haversine spatial index instead of scanning
all 5,562 records per request. The reproducible benchmark and exact-identity
check are in `evaluation/atlas-lookup-benchmark-v1.md`; timing ratios are
machine-dependent.

## Inference request safety

API v0.5.6 bounds caller-supplied climate to 12 or 24 ordered months and at
most 20 complete history years. Temperature, precipitation, and solar inputs
must be finite and remain within documented physical limits. Invalid caller
data returns HTTP 422 instead of being mislabeled as a model/upstream failure;
the limits are advertised by `GET /health` and enforced in offline inference
tests used by the Mac installer and CI.

## Batched reliability inference

API v0.5.7 evaluates the baseline and ten historical climate scenarios in one
tree-ensemble pass rather than invoking every tree once per scenario. The
committed benchmark requires exact nested output equality and measured a
machine-dependent median reduction from 26.4 ms to 4.5 ms (**5.9x faster**) on
the development host. See `evaluation/inference-benchmark-v1.md`.

## Onboarding crop coverage

All 16 onboarding choices now reach CropFit in resilient mode, up from 10.
Grouped choices disclose their representative EcoCrop profile in result notes:
leafy greens use lettuce, herbs use basil, kale and brassicas use kale, beans
use common bean, cucumbers and squash use cucumber, and melons use rock melon.
Strict mode supports 15 choices and intentionally excludes microgreens because
a mature lettuce profile does not represent a 2–3 week microgreen cycle. CI
checks the complete ID-to-profile mapping on every push.

## Client cache correctness

The web server's one-hour CropFit cache is content-addressed over the complete
request, model URL, API version, and training run. Climate, soil pH, irrigation,
coordinate, crop, primary/backup, deployment, or retraining changes cannot
reuse a stale prediction. The cache is a bounded 2,048-entry LRU, and CI checks
key sensitivity, revision invalidation, model isolation, expiry, and
least-recently-used eviction.

API v0.6.3 exposes its API+training-run revision through `/health`. The browser
proxy reads it once per prediction request. If revision health is unavailable,
model predictions continue but bypass the cache until provenance is verified.

Transient health failures are not cached as an API type. A recovered Spark is
reprobed on the next request and immediately resumes as the CropFit primary;
the failover test covers down → Mac backup → recovered primary → calendar.
