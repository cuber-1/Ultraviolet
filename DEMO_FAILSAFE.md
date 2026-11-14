# Demo failsafe

Ultraviolet can finish a crop search without the DGX Spark. The server uses this
order automatically:

1. `ML_MODEL_URL` — the trained CropFit service on the Spark.
2. `ML_MODEL_FALLBACK_URL` — an optional second CropFit or compatible API.
3. Built-in crop calendar — no model process or GPU required.

The final fallback uses the NASA monthly climate already fetched by the app and
the committed crop temperature, sunlight, and growing-season requirements. It
is explicitly labelled `CROP CALENDAR · MODEL OFFLINE`; it never pretends to be
the trained model.

## Recommended demo configuration

```bash
ML_MODEL_URL="http://100.119.73.13:8100"
ML_MODEL_FALLBACK_URL="https://your-hosted-backup.example.com"
ML_MODEL_TIMEOUT_MS=5000
```

The backup URL is optional. With no backup, a failed Spark call moves directly
to the calendar. Leave `ML_STRICT` unset for a resilient demo; `ML_STRICT=1`
intentionally disables the calendar fallback.

## Zero-Spark rehearsal

Start only the web app with `ML_MODEL_URL` unset. Open **How it works → Model
Explorer** and run several cities and crops. Results should appear with the
crop-calendar label. Saved searches remain available for instant replay from
**Recent searches** even when model and agent services are unavailable.

## Optional lightweight backup service

The committed five-vector service requires no training or GPU:

```bash
python3 -m venv machine-learning/.venv
machine-learning/.venv/bin/pip install -r machine-learning/requirements-runtime.txt
npm run ml:serve:demo
```

It can run on a MacBook or a small CPU host. Point
`ML_MODEL_FALLBACK_URL` at that service if you want a second HTTP model before
the built-in calendar takes over.
