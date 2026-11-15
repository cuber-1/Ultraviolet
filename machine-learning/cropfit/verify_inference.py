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
    if predictor.metadata["model"].endswith("v0.6"):
        assert predictor.metadata["selectedModel"] == "extraTrees"
    if predictor.metadata.get("promotionGate"):
        assert predictor.metadata["promotionGate"]["passed"]
        assert all(predictor.metadata["promotionGate"]["checks"].values())
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
    stress = climate((profile.temp_opt_min + profile.temp_opt_max) / 2)
    for item in stress:
        item["precipitationMmDay"] = ((profile.rain_opt_min + profile.rain_opt_max) / 2) / 365.25
        item["solarMjM2Day"] = 34.0
    _, stress_teacher, _, _ = predictor.curve_inputs(profile, stress, 6.5, False)
    stress_curve = predictor.curve(profile, stress, 6.5, False)
    assert all(item["score"] <= target["suitability"] for item, target in zip(stress_curve, stress_teacher, strict=True))
    assert all(item["score"] == 0 for item in stress_curve), "seasonal EcoCrop ceiling did not stop boundary extrapolation"
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

    atlas = artifact.parents[1] / "evaluation/yield-atlas-v9.json"
    if atlas.exists():
        atlas_report = load_atlas(str(atlas.resolve()))
        assert atlas_report["years"] == list(range(2010, 2026))
        assert atlas_report["historyWindowComparison"]["gate"]["passed"]
        assert atlas_report["uncertaintyValidation"]["gate"]["passed"]
        assert atlas_report["spatialTransferValidation"]["gate"]["passed"]
        assert atlas_report["spatialTransferValidation"]["productionBlend"]["gate"]["passed"]
        production_blend = atlas_report["spatialTransferValidation"]["productionBlend"]
        assert production_blend["selectedWeights"] == {"regionalNeighborhoodByRegion": {
            "Northeast": 0.0, "Midwest": .15, "South": .15, "West": 0.0,
        }}
        assert all(
            item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0
            for item in (*production_blend["perRegionConfirmation"], *production_blend["perRegionFinalSignal"])
        )
        evidence = nearest_evidence("corn", 29.7604, -95.3698, atlas)
        assert evidence and evidence["county"] == "Fort Bend County" and evidence["observations"] == 14
        assert evidence["latest"]["year"] == 2025
        assert [item["year"] for item in evidence["history"]][-3:] == [2023, 2024, 2025]
        expected = evidence["observedYieldPrior"]["expectedPercentile"]
        assert evidence["observedYieldPrior"]["interval80"][0] <= expected <= evidence["observedYieldPrior"]["interval80"][1]
        assert evidence["observedYieldPrior"]["intervalMethod"] == "local-regional-blend-conformal"
        calibration = atlas_report["spatialTransferValidation"]["productionBlend"]["intervalCalibration"]
        assert calibration["meanWidth90Reduction"] >= .04
        assert .88 <= calibration["productionBlendRadii"]["coverage90"] <= .94
        assert calibration["selectedRegionalScales"] == {
            "Northeast": {"scale80": 1.05, "scale90": 1.0},
            "Midwest": {"scale80": 1.0, "scale90": 1.0},
            "South": {"scale80": 1.0, "scale90": 1.0},
            "West": {"scale80": 1.45, "scale90": 1.45},
        }
        assert all(.85 <= item["coverage90"] <= .98 for item in calibration["perRegionFinal"])
        assert evidence["observedYieldPrior"]["distanceBucket"] == "25-50"
        assert 1 <= evidence["observedYieldPrior"]["neighborCount"] <= 9
        assert len(evidence["regionalNeighbors"]) == evidence["observedYieldPrior"]["neighborCount"] == 6
        assert evidence["observedYieldPrior"]["expectedPercentile"] != evidence["regionalNeighbors"][0]["expectedPercentile"]
        assert abs(sum(item["weight"] for item in evidence["regionalNeighbors"]) - 1) < .0001
        western_evidence = nearest_evidence("wheat", 39.7392, -104.9903, atlas)
        assert western_evidence and western_evidence["state"] == "CO"
        assert western_evidence["observedYieldPrior"]["neighborCount"] == 1
        assert western_evidence["observedYieldPrior"]["intervalMethod"] == "region-gated-local-conformal"
        assert western_evidence["regionalNeighbors"][0]["weight"] == 1.0
        assert atlas_report["predictionMethod"] == {"name": "shrunken exponential recency prior", "forecastYear": 2026, "halfLifeYears": 3.0, "recencyWeight": .8, "longHistoryWeight": .2}
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

    recency_validation = artifact.parents[1] / "evaluation/recency-validation-v2.json"
    if recency_validation.exists():
        recency_report = json.loads(recency_validation.read_text())
        assert recency_report["selectedHalfLifeYears"] == 3
        assert recency_report["selectedRecencyWeight"] == .8
        assert recency_report["gate"]["passed"]
        assert recency_report["finalTest"]["spearmanDeltaBootstrap95"][0] > 0
        assert all(item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in recency_report["perYearFinalTest"])

    uncertainty_validation = artifact.parents[1] / "evaluation/uncertainty-validation-v0.5.1.json"
    if uncertainty_validation.exists():
        uncertainty_report = json.loads(uncertainty_validation.read_text())
        assert uncertainty_report["gate"]["passed"]
        assert uncertainty_report["robustness"]["gate"]["passed"]
        assert uncertainty_report["robustness"]["summary"]["wins"] == uncertainty_report["robustness"]["summary"]["seeds"] == 5

    estimator_validation = artifact.parents[1] / "evaluation/estimator-validation-v0.6.json"
    if estimator_validation.exists():
        estimator_report = json.loads(estimator_validation.read_text())
        assert estimator_report["gate"]["passed"]
        assert estimator_report["summary"]["lockedSeedWins"] == estimator_report["summary"]["lockedSeeds"] == 7
        assert estimator_report["summary"]["finalMeanMaeImprovementPercent"] >= 30

    compact_validation = artifact.parents[1] / "evaluation/compact-validation-v1.json"
    if compact_validation.exists():
        compact_report = json.loads(compact_validation.read_text())
        assert not compact_report["gate"]["passed"]
        assert compact_report["summary"]["seedWins"] == 0
        assert compact_report["summary"]["decision"].startswith("reject")

    ood_validation = artifact.parents[1] / "evaluation/ood-validation-v0.6.1.json"
    if ood_validation.exists():
        ood_report = json.loads(ood_validation.read_text())
        assert ood_report["gate"]["passed"]
        assert ood_report["heldOut"]["errorNeverIncreased"]
        assert ood_report["heldOut"]["seasonalCeiling"]["mae"] < ood_report["heldOut"]["rawSurrogate"]["mae"]

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
