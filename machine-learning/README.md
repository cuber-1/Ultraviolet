# CropFit vector-map demo

The default demo does not train a model. It compares the request with five
transparent examples (Houston, Fresno, Des Moines, Miami, and Seattle) and
returns the nearest crop recommendations. The original experimental training
pipeline remains in this folder for later work, but is not used by Docker.

## Run on macOS or any ordinary computer

```bash
python3 -m venv machine-learning/.venv
machine-learning/.venv/bin/pip install -r machine-learning/requirements-runtime.txt
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m uvicorn cropfit.api:app --host 127.0.0.1 --port 8100
```

Try the Houston example:

```bash
curl -X POST http://127.0.0.1:8100/recommend \
  -H 'content-type: application/json' \
  -d '{"latitude":29.7604,"longitude":-95.3698,"acreage":10,"environment":"rural","irrigated":true,"commercial":true,"preferences":["vegetable"]}'
```

The endpoint is also available through Ultraviolet at
`POST /api/cropfit/recommend`. `POST /predict` remains compatible with the
existing planting-window chart and uses the same demo vectors.

## Experimental training pipeline

CropFit is Ultraviolet's first crop-location model. Version 0.1 learns an
agroclimatic suitability function from FAO EcoCrop environmental requirements.
It is a screening model, not a measured-yield model. Its API deliberately does
not return pounds, revenue, or a buy/sell recommendation.

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

## Serve the experimental trained model

```bash
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m uvicorn cropfit.api:app --host 127.0.0.1 --port 8100
```

The legacy inference module obtains monthly climatology from NASA POWER. It is
kept for future evidence work, but the default API and Docker image do not load
its model artifact.

## Next evidence gate

Version 0.2 will calibrate crop outputs against USDA NASS county yield history
and DSSAT simulations. Until that gate passes, the UI must retain the
`agroclimatic-screening` evidence label.
