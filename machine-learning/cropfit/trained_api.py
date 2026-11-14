from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .inference import CLIMATE_HISTORY_END_YEAR, CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_YEARS, CropFitPredictor
from .yield_atlas import load_atlas, nearest_evidence


ROOT = Path(__file__).resolve().parents[1]
YIELD_ATLAS = ROOT / "evaluation/yield-atlas-v2.json"
app = FastAPI(title="Ultraviolet CropFit", version="0.6.1")

ClimateSeries = Annotated[list[dict], Field(min_length=12, max_length=24)]
ClimateYear = Annotated[list[dict], Field(min_length=12, max_length=12)]
ClimateHistory = Annotated[list[ClimateYear], Field(max_length=20)]


class PredictionRequest(BaseModel):
    crop: str = Field(min_length=2, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    soilPh: float = Field(default=6.5, ge=2.5, le=10.5)
    irrigated: bool = False
    climate: ClimateSeries | None = None
    climateHistory: ClimateHistory | None = None


@lru_cache(maxsize=1)
def predictor() -> CropFitPredictor:
    return CropFitPredictor(
        Path(os.environ.get("CROPFIT_ARTIFACT", ROOT / "artifacts/cropfit.joblib")),
        Path(os.environ.get("CROPFIT_PROFILES", ROOT / "data/raw/ecocrop.csv")),
    )


@lru_cache(maxsize=1)
def observed_evidence() -> dict:
    candidates = [
        ROOT / "evaluation/national-observed-validation-v0.5.json",
        ROOT / "evaluation/observed-validation-v0.5.json",
        ROOT / "evaluation/national-observed-validation-v0.4.json",
        ROOT / "evaluation/observed-validation-v0.4.json",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    if not path.exists():
        return {"grade": "agroclimatic-screening", "observedOutcomeGate": None}
    report = json.loads(path.read_text())
    evidence = {
        "grade": "agroclimatic-screening",
        "observedOutcomeGate": {
            "passed": report["gate"]["passed"],
            "scope": report["scope"],
            "observations": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["observations"],
            "spearman": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["spearman"],
            "bootstrap95": (report.get("pooledWithinCropYear") or report["pooledWithinCrop"])["bootstrap95"],
        },
    }
    if YIELD_ATLAS.exists():
        atlas = load_atlas(str(YIELD_ATLAS.resolve()))
        evidence["historicalYieldAtlas"] = {
            "available": True, "records": len(atlas["records"]), "crops": atlas["crops"],
            "years": atlas["years"], "validation": atlas["validation"],
            "historyWindowComparison": atlas.get("historyWindowComparison"),
            "uncertaintyValidation": atlas.get("uncertaintyValidation"),
        }
    return evidence


@app.get("/health")
def health():
    model = predictor()
    return {
        "status": "ok", "mode": "trained", "apiVersion": app.version,
        "model": model.metadata["model"], "metrics": model.metadata["metrics"],
        "requestLimits": {"climateMonths": [12, 24], "historyYearsMax": 20},
        "climateHistory": {
            "source": "NASA POWER Agroclimatology",
            "startYear": CLIMATE_HISTORY_START_YEAR,
            "endYear": CLIMATE_HISTORY_END_YEAR,
            "years": len(CLIMATE_HISTORY_YEARS),
        },
        "evidence": observed_evidence(),
    }


@app.post("/predict")
def predict(value: PredictionRequest):
    try:
        result = predictor().predict(value.crop, value.latitude, value.longitude, value.soilPh, value.irrigated, value.climate, value.climateHistory)
        result["observedYieldEvidence"] = nearest_evidence(value.crop, value.latitude, value.longitude, YIELD_ATLAS) if YIELD_ATLAS.exists() else None
        return result
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"CropFit prediction failed: {error}") from error
