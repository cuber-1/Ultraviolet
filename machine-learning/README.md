# CropFit crop-suitability model

The default development service loads the trained EcoCrop surrogate and returns
monthly suitability, uncertainty, limiting factors, and planting windows. It is
a screening model, not a measured-yield model, so it does not return pounds,
revenue, or a buy/sell recommendation.

## Run the trained model

On macOS or Linux, install the released v0.11.0 artifact, EcoCrop profiles, and
inference dependencies without access to the Spark:

```bash
./scripts/installCropFitModel.sh
npm run ml:serve:local
```

This local command binds only `127.0.0.1:8100`; set
`ML_MODEL_URL=http://127.0.0.1:8100` in the repository's `.env` to use the Mac
when the Spark is unavailable. To keep the Spark as primary and the Mac as an
automatic backup, set the Spark URL as `ML_MODEL_URL` and the local URL as
`ML_MODEL_FALLBACK_URL`.

The installer requires Python 3.10+, checksum-verifies the release bundle,
rejects unexpected archive members, installs pinned inference dependencies, and
runs offline inference verification against a staging copy before promoting the
artifact, metadata, and EcoCrop profiles with atomic file replacements. It
verifies the promoted files again before reporting success. Override its
interpreter with
`CROPFIT_PYTHON=/path/to/python3.12` when needed. To train a fresh
artifact instead, use the full setup below. Because the repository is private,
the installer uses an authenticated GitHub CLI session (`gh auth login`) or a
`GITHUB_TOKEN`.

Runtime API v0.19.0 serves the validated v0.11.0 estimator and hardens every direct
and HTTP prediction path with the same finite coordinate, soil-pH, boolean,
climate-shape, and 20-year history limits. Startup validates the artifact's
internal model/metadata contract. `GET /health` returns the artifact SHA-256 and
includes its first 12 characters in `revision`, so the web cache and operators
can identify the exact model binary serving a result.

Every push to `main` repeats the release installation and loopback HTTP test on
a GitHub-hosted Apple Silicon (`macos-15`, arm64) runner with Python 3.12.

```bash
python3 -m venv machine-learning/.venv
machine-learning/.venv/bin/pip install -r machine-learning/requirements.txt
machine-learning/.venv/bin/python machine-learning/download_ecocrop.py
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m cropfit.training
npm run ml:serve
```

`npm run ml:serve` is the separate network-service command: it binds port 8100 on all interfaces so an authorized
Tailscale peer can use it. Keep tailnet access controls or a host firewall in
front of the port; the API itself does not provide authentication.

Try a Houston tomato prediction:

```bash
curl -X POST http://127.0.0.1:8100/predict \
  -H 'content-type: application/json' \
  -d '{"crop":"tomato","latitude":29.7604,"longitude":-95.3698,"soilPh":6.5,"irrigated":true}'
```

The trained artifact and downloaded EcoCrop data are intentionally ignored by
Git, so each machine must train locally or receive those files separately.

## Lightweight five-vector demo

For a no-training fallback, install `requirements-runtime.txt` and run:

```bash
npm run ml:serve:demo
```

This compares a request with five transparent examples (Houston, Fresno, Des
Moines, Miami, and Seattle). Docker continues to package this lightweight demo.

## Train

```bash
python3 -m venv machine-learning/.venv
machine-learning/.venv/bin/pip install -r machine-learning/requirements.txt
machine-learning/.venv/bin/python machine-learning/download_ecocrop.py
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m cropfit.training
```

The evaluation split holds out entire crop profiles, so reported metrics test
generalization to unseen species rather than memorization of random scenarios.
Each run writes its full configuration, per-round train/validation history,
learning-rate schedule, error distribution, and feature importance to
`machine-learning/runs/<run-id>/`. A candidate is only promoted when it improves held-out
crop-profile error.

CropFit v0.11.0 fits 200 scenarios per training crop with 40 Extra Trees, but
selects only six transparent range-relative and interaction features from the
25 engineered inputs. Its promotion report compares the candidate with v0.10
on ten newly reserved grouped crop-profile splits plus a fresh independent
Latin-hypercube shift, including API-served active uncertainty, artifact size,
deployed worst-case error, and API-sized latency:

```bash
npm run ml:evaluate:feature-compaction
```

The first compact-feature report remains committed as a failed gate: one
pooled 80% interval covered 83.1% against an 83.0% ceiling. That pooled check
mixes active predictions with deterministic zero-score cases and is not the
conditional interval served by the API. The v2 gate was declared before ten
new seeds were opened; it reports pooled coverage but gates active intervals
and deterministic inactive behavior separately.

Its independent scenario-shift report uses a separately seeded Latin-hypercube
generator and verifies active-case conditional coverage rather than allowing
hard-zero cases to dominate the aggregate:

```bash
npm run ml:evaluate:scenario-shift
```

The earlier 240-scenario/32-tree experiment remains reproducible. It passes
every frozen grouped-split gate but is rejected because a separate
scenario-shift gate catches a 0.99% deployed-MAE regression:

```bash
npm run ml:evaluate:density-refinement
npm run ml:evaluate:density-shift
```

The later 300-scenario/28-tree refinement is also preserved as a rejection. It
improves average error, but fails fresh per-seed tail safety, the final p90
floor, and independent-shift deployed MAE:

```bash
npm run ml:evaluate:density-refinement-v3
```

Training refuses to replace the production artifact unless frozen MAE, p90,
R², held-out-profile-count, and conformal-coverage thresholds all pass. The
artifact and metadata are written atomically, so interruption cannot leave a
partially serialized model.

The historical 80-tree compact experiment is reproducible with
`npm run ml:evaluate:compact`; it remains rejected because all seven fresh
accuracy gates failed despite the smaller artifact.

The deployed score is capped by exact seasonal and establishment EcoCrop
constraints to prevent tree extrapolation at hard or out-of-domain boundaries.
Reproduce the held-out and boundary stress tests with:

```bash
npm run ml:evaluate:ood
```

The trained API obtains NASA POWER monthly history for 2016–2025 unless the
caller supplies a 12-month `climate` array and `climateHistory`. It evaluates
each month across all ten years and returns a risk-adjusted planting month,
historical success rate, and p10/median/p90 suitability bands. These describe
climate consistency, not observed yield accuracy.

Model-error radii use tree-disagreement-normalized split conformal calibration
on validation crop profiles. The committed uncertainty report tests nominal
80% and 90% marginal coverage on held-out crop profiles. The UI's
screening confidence is the calibrated 80% coverage level, not a parcel-success
probability or observed-yield confidence.

```bash
npm run ml:evaluate:uncertainty
```

This reproduces the production-seed comparison, a frozen five-seed robustness
sweep, their machine-readable report, and two presentation charts under
`machine-learning/evaluation/`.

For grain corn, soybeans, winter wheat, silage corn, and non-durum spring wheat,
the response may also include
`observedYieldEvidence`: nearby USDA reporting counties within 100 km, the
nearest county's
2010–2025 within-crop/year percentile history, and an observed county prior
with calibrated 80% and 90% uncertainty intervals. Atlas v9 uses the globally
selected 15% regional share only in Census regions where it improves both
2018–2020 development rank and MAE: the Midwest and South. The Northeast and
West fall back to the local county prior. On locked 2023–2025 outcomes, rank
Spearman improves from 0.8352 to 0.8376 (grouped-bootstrap delta 0.0018–0.0030)
and percentile MAE falls from 0.1208 to 0.1204. Every crop and final year
improves or holds MAE, with no confirmation or final-region regression. This
remains separate observed evidence and never changes
the EcoCrop suitability score. A production-specific conformal calibrator uses
27,034 pre-2018 errors, then selects regional safety scales on two later
pre-final blocks. Across 2018–2025 it preserves 84.4% / 92.9% coverage while
reducing mean 90% band width from 0.535 to 0.511 (4.3%). Western 90% coverage
is 90.0% on 2021–2022 and 95.7% on final 2023–2025 outcomes.

## Next evidence gate

External observed-outcome validation is reproducible with:

```bash
npm run ml:download:observed
npm run ml:evaluate:observed
npm run ml:download:observed:national
npm run ml:evaluate:observed:national
```

This compares CropFit with California's 2018–2022 county agricultural
commissioner yield reports using actual-year NASA POWER weather. The data are
not used for training or model selection. The current gate did not pass, so the
UI must retain the `agroclimatic-screening` evidence label until independent,
broader-state evidence supports a new claim.

The national command streams USDA NASS Quick Stats into a small filtered cache
and evaluates 17,857 county-year yields outside California. That independent
gate also did not pass; its committed report is the primary observed-outcome
evidence for v0.5. The cache is versioned with the model so a new artifact
cannot silently reuse an older model's scores.

## Reproduce feature selection

```bash
npm run ml:evaluate:features
```

This compares the v0.4 absolute-feature design with v0.5 range-relative
agronomic features on five identical grouped crop-profile splits. The committed
report explicitly measures EcoCrop-teacher fidelity, not observed yield.

## Rebuild the county yield atlas

```bash
npm run ml:build:yield-atlas
```

The builder uses the filtered USDA Quick Stats and Census county files from the
national observed-validation download. It writes atlas v9, a forward-year
validation report, and a presentation PNG under `evaluation/`. Atlas v9 uses
the development-selected 80% three-year-half-life recency / 20% long-history
prior. The report compares the 16-year and legacy 8-year histories on identical
future rows and tests conformal intervals calibrated on 2011–2017 against
2018–2025 outcomes. It also runs a leave-one-county-out nearest-neighbor test,
selects a regional neighborhood on development years, validates a region-gated
85% local / 15% regional production blend, and separately calibrates its sharper
location-facing intervals by crop and effective source-history depth.

## Validate rural ranking evidence

```bash
npm run ml:evaluate:ranking
```

This compares the observed county prior, CropFit agroclimatic score, and a
candidate blend. Weights are selected on 2018–2020; 2021–2022 is confirmation;
2023–2025 is the final untouched test. The current report rejects the fragile
blend and validates using the observed prior for supported rural crops only.

## Gate additional observed-prior crops

```bash
npm run ml:evaluate:crop-expansion
```

Crop-expansion v2 keeps nine USDA class/practice/unit definitions separate and
requires each to pass both the full 2018–2025 forward test and a locked
2023–2025 block. Each block needs at least 100 observations, Spearman at least
0.50, a county-bootstrap lower bound above 0.30, and at least 50% coverage.

Spring wheat passes with 257 final observations, Spearman 0.762, and a
0.670–0.830 interval. Silage corn passes with 576 observations, Spearman 0.551,
and a 0.469–0.617 interval. Dry peas and durum wheat have promising rank signal
but fail the final sample floor; beans, potatoes, and both sunflower definitions
also remain rejected. Grain/silage corn and winter/spring/durum wheat are never
pooled. A second gate then tests whether those county signals transfer to a
different nearby county before property lookup:

```bash
npm run ml:build:crop-subtype-atlas
```

It leaves each target county out and selects neighborhood aggregation using
2018–2020 only. Both crops select five counties with inverse-distance power 2;
silage additionally weights each county by its available history count, while
spring wheat remains distance-only. On locked 2023–2025 outcomes, spring-wheat
Spearman improves from 0.594 to 0.710 and MAE falls from 0.170 to 0.154; silage
improves from 0.444 to 0.522 and MAE from 0.216 to 0.201. Against the previous
distance-only silage prior, history weighting also improves rank and MAE in
development, stability, and final blocks; the locked incremental rank interval
is -0.009 to +0.029, so this small ablation gain is not presented as conclusive.
Silage also replaces the generic 80% recency blend with 25% recency only after
rank and MAE improved in both development and stability. It then improves the
locked generic-blend baseline from ρ=0.511 / MAE=0.203 to ρ=0.522 / MAE=0.201;
the paired rank-gain interval is +0.001 to +0.023. Spring wheat retains 80%
recency because no candidate cleared the +0.005 development rank floor.
Grouped-bootstrap lower bounds are 0.615 and 0.442; paired gains against one
nearest county are +0.047 to +0.194 and +0.020 to +0.141. A development-only
uncertainty search retains neighbor-disagreement scaling for spring wheat only:
it reduces development mean 90% width 8.0%. On locked outcomes, mean width
falls from 0.665 to 0.617 while coverage remains 85.2% / 92.6%. Western locked
coverage improves to 81.9% / 89.4% and its mean 90% width falls from 0.702 to
0.613. Region-conditioned pre-2018 groups with at least 50 errors per
region/history cell clear a separate 1% promotion floor
for spring wheat, reducing development width 1.3% and locked pooled width from
0.617 to 0.608 without changing 92.6% coverage. A second development-only
search then scales width continuously inside each coarse history bucket, for at
most one supported region per crop. It selects β=-0.02 for Western spring wheat
and Midwest silage: each additional effective history observation multiplies
the radius by `exp(-0.02)`. On locked outcomes, spring-wheat mean 90% width
falls again from 0.608 to 0.593 with 91.1% coverage, and silage width falls from
0.750 to 0.720 with 89.2% coverage. Both candidates first cleared a 1%
development-width floor and every pooled and regional coverage gate. Silage retains pooled groups
because regional calibration widens its development intervals, and retains α=0
because no candidate cleared the 1% development-width
floor. Its final intervals achieve 80.3% / 89.2% coverage with mean 90% width 0.720.
The 690-record artifact keeps
`bu/acre` and `tons/acre` explicit and publishes only crop-region pairs with at
least 50 examples in development, stability, and final blocks. Generic
grain-corn and winter-wheat queries remain on atlas v9. See
`evaluation/yield-atlas-subtypes-validation-v1.md`.

## Test recency weighting and atlas lookup

```bash
npm run ml:evaluate:recency
npm run ml:benchmark:atlas
npm run ml:benchmark:inference
```

The recency command tests shrinkage toward exponential history weighting under
fixed temporal splits. The v2 gate passes on confirmation and locked final
years, and its selected prior is used by atlas v9. The
benchmark compares the cached haversine spatial index with exact brute force
and verifies identical nearest counties for each supported crop.
