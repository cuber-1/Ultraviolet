# CropFit EcoCrop surrogate v0.8

- Trained: 2026-11-15
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated training scenarios: 134,064
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: Extra Trees
- Raw estimator MAE: 0.0175 suitability points
- Deployed score MAE after deterministic seasonal ceiling: 0.00679 points
- R²: 1.0000
- Raw estimator 90th percentile absolute error: 0.0491 points
- Deployed score 90th percentile absolute error: 0.00125 points

Version 0.8 adds two transparent input-derived interactions: temperature-water
fit and pH-solar fit. They factor the known multiplicative EcoCrop structure
without supplying the final suitability label or crop identity. This lets the
ensemble shrink from 200 to 120 trees. Across two confirmation and five final
grouped crop-profile seeds, it cleared all 7/7 gates: locked mean MAE fell
80.00% and p90 error fell 79.25%. On the production split, MAE fell from 0.0867
to 0.0175 and p90 fell from 0.2234 to 0.0491. See
`evaluation/interaction-validation-v0.8.md`.

The compressed artifact is 73.2 MB versus 125.9 MB for v0.7. On the development
host, clean-process peak RSS fell from 1,187,060 KiB to 772,688 KiB and full
11-scenario reliability prediction median latency fell from 7.09 ms to 4.71 ms.
The locked 132-row batch latency ratio was 0.58×. Timings and RSS are
machine-dependent; Apple Silicon installation and loopback inference remain CI
requirements.

An 80-tree compact candidate reduced serialized estimator size to about 67% of
the champion, but failed the frozen accuracy tolerance on all seven fresh
seeds: mean MAE regressed 4.1% and mean p90 error regressed 5.9%. It was
rejected; that experiment did not replace the 120-tree v0.6 champion. See
`evaluation/compact-validation-v1.md`.

## Out-of-distribution ceiling

API v0.8.0 retains the v0.6.1 safety ceiling that caps the ML score by the exact
seasonal and establishment EcoCrop suitability already computed for
limiting-factor explanations. This is a one-sided safety constraint: the
ensemble still determines underprediction but cannot claim suitability above
the mechanistic target it approximates.

On the production held-out split, the ceiling reduced MAE from 0.0175 to
0.00679 and p90 error from 0.0491 to 0.00125 without increasing any example's
error. Existing intervals remained conservative at 89.9%/95.0% coverage. It also
eliminates errors at the tested exact hard solar and temperature boundaries,
where continuous random training samples do not land. See
`evaluation/ood-validation-v0.8.md`.

Version 0.5 adds four crop-relative features: temperature, water, pH, and solar
membership within each crop's absolute and optimum ranges. The 120-tree Random
Forest still receives the raw climate and profile fields. Against the v0.4
feature design, it improved held-out MAE on all five robustness seeds from
20261110 through 20261114. Mean MAE fell from 5.3968 to 0.1536 (97.15%). The
reproducible protocol and per-seed results are in
`evaluation/feature-validation-v0.5.md`.

Version 0.8 refits the tree-disagreement-normalized split-conformal
calibrator using only 224 validation crop profiles. On 26,856 held-out examples
from 373 crop profiles, nominal 80% and 90% bands covered 79.96% and 90.01%; the
mean 90% radius was 0.0145 suitability points. Across the seven locked
interaction-validation seeds, mean coverage was 80.25% and 90.13%. These are marginal
EcoCrop-teacher fidelity bands, not per-species or observed-yield guarantees.

The CUDA XGBoost candidate completed 500 rounds with a cosine learning-rate
schedule from 0.08 to 0.005. It was not promoted because held-out-profile MAE
was worse (0.1057). The committed diagnostics are
`evaluation/training-curves-v0.8.png`,
`evaluation/selected-feature-importance-v0.8.png`, and
`evaluation/training-history-v0.8.csv`.

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

CropFit also returns a separate USDA observed local-plus-regional prior for corn, soybeans,
and wheat when published county centroids are within 100 km. This evidence does
not alter CropFit suitability. Atlas v9 contains 5,562 county-crop
records from 2010–2025, uses a validated shrunken-recency prior, and includes
crop/history-count conditional conformal uncertainty bands. Location-facing
bands are separately calibrated for regional spatial transfer.

On the same 21,908 2019–2025 county-year rows, extending the available history
from 2018 back to 2010 improved pooled Spearman from 0.819 to 0.847 and reduced
percentile MAE from 0.126 to 0.117. Coverage increased from 21,908 to 23,311
rows. Uncertainty was calibrated on 2011–2017 only; across 26,589 later
2018–2025 outcomes, nominal 80% and 90% intervals covered 84.1% and 92.5%.
This measures persistence of county yield ranks, not parcel yield forecasting.
See `evaluation/yield-atlas-validation-v9.md`.

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

Atlas v9 shrinks an exponential recency estimate toward the stable long-history
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
levels. See `evaluation/yield-atlas-validation-v9.md`.

The production API transfers nearby reporting-county priors to an arbitrary
location, so atlas v9 validates that operation directly. A leave-one-county-out
test excludes each target county. Development years selected up to eight
neighbors with inverse-square distance weighting. On locked 2023–2025 outcomes,
regional Spearman reached 0.8060 versus 0.7580 for one nearest county (delta
+0.0480; paired grouped-bootstrap 95% interval +0.0409 to +0.0551), while
percentile MAE fell from 0.1453 to 0.1330. Every supported crop and final-test
year improved both metrics. Regional bands calibrated on 2011–2017 covered
83.4% and 92.4% on 2018–2025 and narrowed mean 90% width from 0.595 to 0.545.
API responses expose all contributing counties and label bands
`spatial-neighborhood-conformal`.

For production queries, development MAE selected an 85% nearest-county / 15%
regional-neighborhood blend. It passed confirmation and improved locked
2023–2025 Spearman from 0.8352 to 0.8380 (grouped-bootstrap delta interval
+0.0021 to +0.0034), while MAE fell from 0.1208 to 0.1204. Every crop and year
improved rank with non-worse MAE; re-centered interval coverage was 85.9% and
93.5%.

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

API v0.8.0 exposes its API+training-run revision through `/health`. The browser
proxy reads it once per prediction request. If revision health is unavailable,
model predictions continue but bypass the cache until provenance is verified.

## Local-plus-regional yield evidence

Atlas v9 adds the development-selected 15% regional neighborhood only in the
Midwest and South, where the same fixed blend improved both development rank
and MAE. The Northeast and West use the local county prior. It passes 2021–2022
confirmation and improves locked 2023–2025 Spearman from 0.8352 to 0.8376 while
reducing percentile MAE from 0.1208 to 0.1204 across 8,881 county-years. Every
crop and final year improves rank without worse MAE, no region regresses, and
the grouped-bootstrap rank-delta interval is +0.0018–+0.0030. A
production-specific conformal calibrator fitted on 27,034 pre-2018 errors uses
the smallest regional safety scales that satisfy nominal coverage in both
2018–2020 and 2021–2022. It retains 84.4% / 92.9% coverage across 2018–2025
while reducing mean 90% width from 0.535 to 0.511 (4.3%). Western 90% coverage
is 90.0% on the 2021–2022 stability block and 95.7% on final 2023–2025 outcomes.
This remains county-level evidence,
not a parcel yield or property-return forecast.

Transient health failures are not cached as an API type. A recovered Spark is
reprobed on the next request and immediately resumes as the CropFit primary;
the failover test covers down → Mac backup → recovered primary → calendar.
