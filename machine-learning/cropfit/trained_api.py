from __future__ import annotations

import os
from functools import lru_cache
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .inference import CropFitPredictor


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Ultraviolet CropFit", version="0.4.0")


class PredictionRequest(BaseModel):
    crop: str = Field(min_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soilPh: float = Field(default=6.5, ge=2.5, le=10.5)
    irrigated: bool = False
    climate: list[dict] | None = None


@lru_cache(maxsize=1)
def predictor() -> CropFitPredictor:
    return CropFitPredictor(
        Path(os.environ.get("CROPFIT_ARTIFACT", ROOT / "artifacts/cropfit.joblib")),
        Path(os.environ.get("CROPFIT_PROFILES", ROOT / "data/raw/ecocrop.csv")),
    )


@lru_cache(maxsize=1)
def observed_evidence() -> dict:
    path = ROOT / "evaluation/national-observed-validation-v0.4.json"
    if not path.exists():
        path = ROOT / "evaluation/observed-validation-v0.4.json"
    if not path.exists():
        return {"grade": "agroclimatic-screening", "observedOutcomeGate": None}
    report = json.loads(path.read_text())
    return {
        "grade": "agroclimatic-screening",
        "observedOutcomeGate": {
            "passed": report["gate"]["passed"],
            "scope": report["scope"],
            "observations": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["observations"],
            "spearman": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["spearman"],
            "bootstrap95": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["bootstrap95"],
        },
    }


@app.get("/health")
def health():
    model = predictor()
    return {"status": "ok", "mode": "trained", "model": model.metadata["model"], "metrics": model.metadata["metrics"], "evidence": observed_evidence()}


@app.post("/predict")
def predict(value: PredictionRequest):
    try:
        return predictor().predict(value.crop, value.latitude, value.longitude, value.soilPh, value.irrigated, value.climate)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"CropFit prediction failed: {error}") from error
