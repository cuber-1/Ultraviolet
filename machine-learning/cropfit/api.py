from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .vector_map import DemoVectorMap

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Ultraviolet CropFit Demo", version="0.3.0")


class VectorRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    acreage: float = Field(default=10, gt=0, le=1_000_000)
    environment: str = "rural"
    irrigated: bool = False
    lowMaintenance: bool = False
    commercial: bool = True
    preferences: list[str] = Field(default_factory=list)


class PredictionRequest(VectorRequest):
    crop: str = Field(min_length=2)
    soilPh: float = Field(default=6.5, ge=2.5, le=10.5)


@lru_cache(maxsize=1)
def vector_map() -> DemoVectorMap:
    return DemoVectorMap(ROOT / "demo_vectors.json")


def query_vector(value: VectorRequest) -> dict[str, float]:
    return vector_map().input_vector(value.latitude, value.longitude, value.acreage, value.environment,
                                     value.irrigated, value.lowMaintenance, value.commercial)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "five-example-vector-map", "examples": len(vector_map().examples), "trainingRequired": False}


@app.post("/recommend")
def recommend(value: VectorRequest):
    return vector_map().recommend(query_vector(value), value.preferences)


@app.post("/predict")
def predict(value: PredictionRequest):
    return vector_map().predict(value.crop, query_vector(value))
