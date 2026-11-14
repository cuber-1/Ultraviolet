from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from .features import FEATURE_NAMES
from .inference import CLIMATE_HISTORY_END_YEAR, CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_YEARS, MONTHS, CropFitPredictor
from .profiles import resolve_profile
from .yield_atlas import haversine_km, load_atlas, nearest_evidence


def climate(temperature: float) -> list[dict]:
    return [{
        "month": month,
        "temperatureC": temperature,
        "precipitationMmDay": 3.0,
        "solarMjM2Day": 18.0,
    } for month in MONTHS]


def verify(artifact: Path, profiles: Path) -> None:
    assert (CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_END_YEAR, len(CLIMATE_HISTORY_YEARS)) == (2016, 2025, 10)
    predictor = CropFitPredictor(artifact, profiles)
    assert predictor.model.n_features_in_ == len(FEATURE_NAMES), "artifact and feature code disagree"
    history = [climate(18.0 + offset) for offset in (-3, -2, -1, 0, 0, 1, 1, 2, 3, 5)]
    result = predictor.predict("tomato", 29.76, -95.37, 6.5, True, climate(20.0), history)
    assert result["plantingReliability"]["years"] == 10
    assert "2016–2025" in result["disclaimer"]
    calibration = predictor.metadata["uncertaintyCalibration"]
    if calibration.get("normalizedErrorQuantiles"):
        assert calibration["gate"]["passed"]
        assert result["confidence"] == calibration["nominalCoverage"]["p80"] == .8
        assert result["expectedAbsoluteError"]["p80"] <= result["expectedAbsoluteError"]["p90"]
    assert result["bestReliablePlantingMonth"] in MONTHS
    assert len(result["monthlyCurve"]) == 12
    for month in result["monthlyCurve"]:
        assert month["historicalP10"] <= month["historicalMedian"] <= month["historicalP90"]
        assert 0 <= month["reliability"] <= 1

    profile = resolve_profile("tomato", predictor.profiles)
    ordinary = predictor.curve(profile, climate(20.0) + climate(20.0), 6.5, True)
    hot_next_year = predictor.curve(profile, climate(20.0) + climate(45.0), 6.5, True)
    assert ordinary[-1]["score"] != hot_next_year[-1]["score"], "late planting did not use following-year climate"
    scenarios = [climate(18.0), climate(20.0) + climate(21.0), climate(25.0)]
    assert predictor.curves(profile, scenarios, 6.5, True) == [predictor.curve(profile, values, 6.5, True) for values in scenarios]
    onboarding_profiles = {
        "basil": "Ocimum basilicum",
        "kale": "Brassica oleracea var. acephala",
        "common bean": "Phaseolus vulgaris",
        "melon": "Cucumis melo",
        "onion": "Allium cepa",
        "sunflower": "Helianthus annuus",
    }
    for name, scientific_name in onboarding_profiles.items():
        assert resolve_profile(name, predictor.profiles).scientific_name == scientific_name

    invalid = climate(20.0) + climate(20.0)
    invalid[-1]["precipitationMmDay"] = -1
    try:
        predictor.curve(profile, invalid, 6.5, True)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid second-year climate was accepted")

    atlas = artifact.parents[1] / "evaluation/yield-atlas-v2.json"
    if atlas.exists():
        atlas_report = load_atlas(str(atlas.resolve()))
        assert atlas_report["years"] == list(range(2010, 2026))
        assert atlas_report["historyWindowComparison"]["gate"]["passed"]
        assert atlas_report["uncertaintyValidation"]["gate"]["passed"]
        evidence = nearest_evidence("corn", 29.7604, -95.3698, atlas)
        assert evidence and evidence["county"] == "Fort Bend County" and evidence["observations"] == 14
        assert evidence["latest"]["year"] == 2025
        assert [item["year"] for item in evidence["history"]][-3:] == [2023, 2024, 2025]
        assert evidence["observedYieldPrior"]["interval80"][0] <= evidence["meanPercentile"] <= evidence["observedYieldPrior"]["interval80"][1]
        assert evidence["observedYieldPrior"]["expectedPercentile"] == evidence["meanPercentile"], "failed recency candidate entered production"
        assert evidence["observedYieldPrior"]["interval90"][0] <= evidence["observedYieldPrior"]["interval80"][0]
        assert evidence["observedYieldPrior"]["interval90"][1] >= evidence["observedYieldPrior"]["interval80"][1]
        assert nearest_evidence("tomato", 29.7604, -95.3698, atlas) is None
        for crop, latitude, longitude in (("corn", 40.1, -88.2), ("soybean", 35.5, -90.4), ("wheat", 46.8, -100.8)):
            indexed = nearest_evidence(crop, latitude, longitude, atlas, max_distance_km=10_000)
            brute = min(
                (record for record in atlas_report["records"] if record["crop"] == crop),
                key=lambda record: haversine_km(latitude, longitude, record["latitude"], record["longitude"]),
            )
            assert indexed and indexed["fips"] == brute["fips"], f"spatial index changed nearest county for {crop}"

    ranking_validation = artifact.parents[1] / "evaluation/ranking-validation-v1.json"
    if ranking_validation.exists():
        ranking_report = json.loads(ranking_validation.read_text())
        assert not ranking_report["blendGate"]["passed"]
        assert ranking_report["productionGate"]["passed"]
        assert ranking_report["priorVsClimateFinalTest"]["priorAdvantageBootstrap95"][0] > 0

    recency_validation = artifact.parents[1] / "evaluation/recency-validation-v1.json"
    if recency_validation.exists():
        recency_report = json.loads(recency_validation.read_text())
        assert recency_report["selectedHalfLifeYears"] == 3
        assert not recency_report["gate"]["passed"]
        assert recency_report["finalTest"]["spearmanDeltaBootstrap95"][0] > 0
        assert any(item["spearmanDelta"] < 0 for item in recency_report["perYearFinalTest"])

    from .trained_api import PredictionRequest, predict as api_predict

    valid_climate = climate(20.0)
    PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, climate=valid_climate, climateHistory=[valid_climate] * 10)
    for invalid in (
        {"climate": valid_climate[:11]},
        {"climateHistory": [valid_climate] * 21},
        {"climateHistory": [valid_climate[:11]]},
    ):
        try:
            PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, **invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"unbounded or malformed climate request was accepted: {invalid.keys()}")

    class InvalidClimatePredictor:
        @staticmethod
        def predict(*_args, **_kwargs):
            raise ValueError("invalid climate")

    with patch("cropfit.trained_api.predictor", return_value=InvalidClimatePredictor()):
        try:
            api_predict(PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, climate=valid_climate))
        except HTTPException as error:
            assert error.status_code == 422
        else:
            raise AssertionError("invalid caller climate was not mapped to HTTP 422")

    print(f"CropFit inference verified: {predictor.metadata['model']} ({len(FEATURE_NAMES)} features, batched 10-year reliability, county evidence)")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    args = parser.parse_args()
    verify(args.artifact, args.profiles)


if __name__ == "__main__":
    main()
