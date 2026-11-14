# CropFit ML

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

## Serve

```bash
PYTHONPATH=machine-learning machine-learning/.venv/bin/python -m uvicorn cropfit.api:app --host 127.0.0.1 --port 8100
```

The service obtains monthly climatology from NASA POWER unless the caller
provides climate values. `POST /predict` returns a 12-month suitability curve,
component scores, uncertainty, and the best screening window.

## Next evidence gate

Version 0.2 will calibrate crop outputs against USDA NASS county yield history
and DSSAT simulations. Until that gate passes, the UI must retain the
`agroclimatic-screening` evidence label.
