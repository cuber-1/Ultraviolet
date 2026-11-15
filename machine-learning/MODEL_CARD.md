# CropFit EcoCrop surrogate v0.11.0

- Trained: 2026-11-15
- Source: FAO EcoCrop environmental requirement profiles via OpenCLIM
- Usable crop profiles: 1,862
- Generated fitting scenarios: 372,400 (253,000 from training profiles)
- Frozen validation/test scenarios: 134,064 before profile splitting
- Evaluation: entire crop profiles held out (373 profiles)
- Selected production estimator: Extra Trees
- Selected model inputs: 6 of 25 engineered features
- Raw estimator MAE: 0.0106 suitability points
- Deployed score MAE after deterministic seasonal ceiling: 0.00385 points
- R²: 1.0000
- Raw estimator 90th percentile absolute error: 0.0284 points
- Deployed score 90th percentile absolute error: 0.00000 points

Version 0.11 keeps the v0.10 training density and 40-tree capacity but removes
19 redundant raw/profile inputs from the fitted forest. The retained inputs are
temperature, water, pH, and solar range fit plus temperature-water and pH-solar
interactions. They are derived only from current conditions and published crop
ranges; they contain no crop identity, held-out label, or observed yield. On
ten fresh grouped-profile seeds, the compact model wins 10/10 with mean MAE
down 24.81% and p90 error down 29.58%; final-only gains remain 23.95%/28.45%.
On a separately reserved shift, raw MAE/p90 improve 22.19%/24.81%, deployed MAE
improves 32.92%, and deployed maximum error falls 28.7%. The forest is 3.7%
smaller with 0.959× batch latency. See
`evaluation/feature-compaction-v2-validation-v0.11.md`.

The first compact-feature gate is preserved as a rejection rather than erased:
it passed every accuracy and active-coverage requirement but one pooled 80%
coverage result was 83.1% against an 83.0% ceiling. Pooled coverage mixes
conditionally calibrated active cases with deterministic zero-score cases. A
v2 protocol declared before opening ten new seeds reports that diagnostic but
gates the active intervals actually served by the API and zero-radius inactive
policy separately. See `evaluation/feature-compaction-validation-v0.11.md`.

A subsequent v0.12 experiment retained only the two interaction features and
used 60 leaf-smoothed trees. Its averages were attractive—MAE fell 40.89%, p90
fell 35.60%, the serialized forest shrank 40.17%, and mean batch latency was
0.92×—but it was rejected. On fresh final seed 20270218, deployed maximum error
rose from 0.356 to 0.456, violating the per-seed tail-safety gate. The passing
independent shift and strong averages do not override that failure. Production
therefore remains the six-feature v0.11 model. See
`evaluation/interaction-compaction-validation-v0.12.md`.

A six-feature smoothing follow-up also failed. Increasing to 72 trees with
`min_samples_leaf=2` improved mean MAE 10.15% and reduced size 7.18%, but only
4/10 fresh seeds cleared every gate. Independent-shift p90 improved just 1.93%
against a 5% floor, while deployed maximum error worsened from 0.698 to 1.200.
See `evaluation/leaf-smoothing-validation-v0.12.md`.

A denser six-feature follow-up fitted 300 scenarios per crop and reduced the
forest to 28 trees. It improved all-seed MAE/p90 by 7.94%/7.39%, but only 5/10
fresh seeds cleared every gate. Final-only p90 improved 4.82%, below the 5%
floor; four seeds worsened deployed maximum error; and independent-shift
deployed MAE regressed 2.67%. Its 66.9 MB artifact was also 4.16% larger. The
experiment's declared 70 MB ceiling allowed that measured increase; correcting
an inherited smaller-than-v0.11 harness clause did not affect the rejection,
which independently fails accuracy and tail gates. See
`evaluation/density-refinement-v3-validation-v0.12.md`.

A subsequent development-only screen kept all confirmation, final, and shift
seeds closed while comparing additional density/tree balances, 48-tree
capacity, Poisson splitting, and active-case upper tree quantiles. None
advanced. The strongest average candidate, 300 scenarios with 32 trees,
improved MAE/p90 by 11.65%/14.05% but cleared only 2/3 development seed
screens. Poisson variants cleared 0/3 and produced deployed maximum errors as
high as 8.75 points; upper quantiles regressed raw error by 35–120%. See
`evaluation/density-capacity-development-v0.12.md`.

Version 0.9 increases generated fitting coverage from 72 to 120 scenarios per
training crop while preserving the exact v0.8 validation and held-out rows. The
denser fitting data lets the ensemble shrink from 120 to 70 trees. Across two
confirmation and five final grouped crop-profile seeds, it cleared all 7/7
gates: locked mean MAE fell 12.53% and p90 error fell 14.02%. On the production
split, MAE fell from 0.0175 to 0.0145 and p90 fell from 0.0491 to 0.0407. See
`evaluation/training-density-validation-v0.9.md`.

Version 0.9.1 corrects uncertainty reporting for active growing conditions.
The previous marginal calibration was dominated by deterministic hard-zero
cases: on an independent Latin-hypercube test, its active-case 90% coverage was
only 55.1%. Calibration now uses active validation examples separately and
returns zero radius only where the deterministic ceiling fixes the deployed
score at zero. Active coverage is 80.6%/90.9% on the frozen-random test and
81.4%/91.4% under independent scenario shift. The same shift test confirms
v0.9's raw and deployed error gains remain between 12.7% and 77.5%. See
`evaluation/scenario-shift-validation-v0.9.1.md`.

The compressed v0.10 artifact is 66.7 MB, 6.3% smaller than v0.9.1. Its locked
132-row batch latency ratio is 0.95×. Timings are machine-dependent; Apple
Silicon installation and loopback inference remain CI requirements.

A first v0.10 density candidate doubled fitting coverage to 240 scenarios per crop
while reducing the ensemble to 32 trees. It won all seven frozen
confirmation/final splits, reducing locked MAE 10.9% and p90 error 10.3%, with
a 9.5% smaller artifact. It was still rejected: on an independent
Latin-hypercube shift test, raw MAE improved only 4.83% against a declared 5%
floor and deployed seasonal-ceiling MAE regressed 0.99%, so it was rejected.
See `evaluation/density-refinement-validation-v0.10.md`
and `evaluation/density-shift-validation-v0.10.md`.

The promoted v0.10 candidate instead fits 200 scenarios per crop with 40 trees.
It wins all ten newly reserved confirmation/final seeds: mean MAE falls 8.62%,
p90 falls 8.49%, final-only gains remain 8.65%/7.73%, and API-batch latency is
0.95×. On a separately reserved Latin-hypercube seed, raw and deployed MAE
improve 10.72% and 10.43%; every active subgroup improves and shifted active
coverage is 80.7%/90.8%. See
`evaluation/density-refinement-v2-validation-v0.10.md`.

An 80-tree compact candidate reduced serialized estimator size to about 67% of
the champion, but failed the frozen accuracy tolerance on all seven fresh
seeds: mean MAE regressed 4.1% and mean p90 error regressed 5.9%. It was
rejected; that experiment did not replace the 120-tree v0.6 champion. See
`evaluation/compact-validation-v1.md`.

## Out-of-distribution ceiling

API v0.19.0 retains the v0.6.1 safety ceiling that caps the ML score by the exact
seasonal and establishment EcoCrop suitability already computed for
limiting-factor explanations. This is a one-sided safety constraint: the
ensemble still determines underprediction but cannot claim suitability above
the mechanistic target it approximates.

On the production held-out split, the ceiling reduces MAE from 0.01058 to
0.00385 and p90 error from 0.02844 to 0 without increasing any example's
error. Existing intervals remain conservative at 98.3%/99.2% coverage after
the ceiling. It also
eliminates errors at the tested exact hard solar and temperature boundaries,
where continuous random training samples do not land. See
`evaluation/ood-validation-v0.11.0.md`.

Version 0.5 adds four crop-relative features: temperature, water, pH, and solar
membership within each crop's absolute and optimum ranges. The 120-tree Random
Forest still receives the raw climate and profile fields. Against the v0.4
feature design, it improved held-out MAE on all five robustness seeds from
20261110 through 20261114. Mean MAE fell from 5.3968 to 0.1536 (97.15%). The
reproducible protocol and per-seed results are in
`evaluation/feature-validation-v0.5.md`.

Version 0.11.0 fits its active-case tree-disagreement-normalized split-conformal
calibrator using 3,395 active examples from 224 validation crop profiles. On
5,628 active held-out examples from the 373 test profiles, nominal 80% and 90%
bands cover 78.2% and 89.5%; mean radii are 0.068 and 0.094 suitability points.
Hard-zero deployed scores receive zero radius because the deterministic ceiling
fixes their value. These are conditional EcoCrop-teacher fidelity bands, not
per-species or observed-yield guarantees.

The CUDA XGBoost candidate completed 500 rounds with a cosine learning-rate
schedule from 0.08 to 0.005. It was not promoted because held-out-profile MAE
was worse (0.0845). The committed diagnostics are
`evaluation/training-curves-v0.11.0.png`,
`evaluation/selected-feature-importance-v0.11.0.png`, and
`evaluation/training-history-v0.11.0.csv`.

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

## Observed subtype expansion gate

Crop-expansion v2 evaluates nine exact USDA class/practice/unit definitions
without pooling definition breaks. Every candidate must pass both 2018–2025
forward evaluation and a locked 2023–2025 block with at least 100 observations,
Spearman at least 0.50, a grouped-bootstrap lower bound above 0.30, and at least
50% published-row coverage. Spring wheat passes the recent block with 257
observations and Spearman 0.762 (95% interval 0.670–0.830); silage corn passes
with 576 observations and 0.551 (0.469–0.617). Dry peas and durum wheat fail the
recent sample floor despite positive rank signal. The accepted subtypes remain
outside atlas v9. A development-selected five-county aggregation passes the
leave-one-county-out transfer gate for both. On locked 2023–2025 outcomes,
spring-wheat Spearman improves from 0.594 to 0.710 and silage from 0.444 to
0.522, while both reduce MAE. Silage weights neighbors by history count because
that development-selected candidate also improves rank and MAE in stability and
final blocks versus the previous distance-only method. Its incremental final
rank interval is -0.009 to +0.029, so the ablation gain is not conclusive.
Silage uses a 25% recency blend after it improves both development and stability
against the generic 80% blend. Locked rank improves from 0.511 to 0.522 and MAE
from 0.203 to 0.201, with paired rank-gain interval +0.001 to +0.023. Spring
wheat retains 80% recency because its candidates do not clear the +0.005
development floor. Grouped-bootstrap lower bounds are 0.615 and 0.442, and paired rank-gain
intervals against one nearest county stay above zero (+0.047 to +0.194 and
+0.020 to +0.141). Development selects neighbor-disagreement scaling for
spring wheat only after an 8.0% mean-width reduction clears a predeclared 1%
floor. On locked outcomes, its mean 90% width falls from 0.665 to 0.617 while
coverage remains 85.2% / 92.6%; Western coverage is 81.9% / 89.4% with width
0.613 instead of 0.702. Spring-wheat region-conditioned groups, each backed by
at least 50 pre-2018 errors, then clear a
separate 1% development-width floor and narrow locked pooled width from 0.617
to 0.608 at the same 92.6% coverage. A final development-only search allows one
region per crop to vary continuously inside the coarse history buckets. It
selects β=-0.02 for Western spring wheat and Midwest silage, equivalent to a
0.9802 radius multiplier per additional effective history observation. Locked
spring-wheat width falls from 0.608 to 0.593 with 91.1% coverage; locked silage
width falls from 0.750 to 0.720 with 89.2% coverage. Both keep every regional
gate. Silage retains pooled calibration because its regional candidate is
wider, and it retains α=0. The separate
690-record atlas preserves explicit `bu/acre` and `tons/acre` units and excludes
crop-region pairs without at least 50 examples in every validation block. See
`evaluation/yield-atlas-subtypes-validation-v1.md`.

## Inference request safety

API v0.19.0 bounds caller-supplied climate to 12 or 24 ordered months and at
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

API v0.19.0 exposes its API+training-run+artifact-hash revision and the full
artifact SHA-256 through `/health`. The browser proxy reads the revision once
per prediction request. Startup rejects artifacts missing the fitted ensemble,
model identity, or a consistent feature contract. Direct and HTTP inference
share finite coordinate, geographic, soil-pH, boolean irrigation, climate, and
history-size checks. If revision health is unavailable, model predictions
continue but bypass the cache until provenance is verified.

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
