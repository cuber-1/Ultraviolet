# CropFit crop-suitability model

The default development service loads the trained EcoCrop surrogate and returns
monthly suitability, uncertainty, limiting factors, and planting windows. It is
a screening model, not a measured-yield model, so it does not return pounds,
revenue, or a buy/sell recommendation.

## Run the trained model

On macOS or Linux, install the released v0.5 artifact, EcoCrop profiles, and
inference dependencies without access to the Spark:

```bash
./scripts/installCropFitModel.sh
npm run ml:serve
```

The release bundle is checksum-verified before extraction. To train a fresh
artifact instead, use the full setup below. Because the repository is private,
the installer uses an authenticated GitHub CLI session (`gh auth login`) or a
`GITHUB_TOKEN`.

```bash
python3 -m venv machine-learning/.venv
machine-learning/.venv/bin/pip install -r machine-learning/requirements.txt
machine-learning/.venv/bin/python machine-learning/download_ecocrop.py
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m cropfit.training
npm run ml:serve
```

`npm run ml:serve` binds port 8100 on all interfaces so an authorized
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

The trained API obtains NASA POWER monthly history for 2015–2024 unless the
caller supplies a 12-month `climate` array and `climateHistory`. It evaluates
each month across all ten years and returns a risk-adjusted planting month,
historical success rate, and p10/median/p90 suitability bands. These describe
climate consistency, not observed yield accuracy.

For corn, soybeans, and wheat, the response may also include
`observedYieldEvidence`: the nearest USDA reporting county within 100 km, its
2010–2025 within-crop/year percentile history, and an observed county prior
with calibrated 80% and 90% uncertainty intervals. This is displayed as
separate observed evidence and never changes the EcoCrop suitability score.

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
national observed-validation download. It writes atlas v2, a forward-year
validation report, and a presentation PNG under `evaluation/`. The report
compares the 16-year and legacy 8-year histories on identical future rows and
tests conformal intervals calibrated on 2011–2017 against 2018–2025 outcomes.

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

This evaluates candidate USDA county series as forward-year rank priors without
changing production coverage. The committed v1 report rejects beans, potatoes,
and sunflowers. It also keeps the pre-2019 bean definition separate because
that series includes chickpeas, unlike the current USDA category.

## Test recency weighting and atlas lookup

```bash
npm run ml:evaluate:recency
npm run ml:benchmark:atlas
```

The recency command tests exponential history weighting under fixed temporal
splits and does not alter the production atlas unless every gate passes. The
benchmark compares the cached haversine spatial index with exact brute force
and verifies identical nearest counties for each supported crop.
