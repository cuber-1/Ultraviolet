from __future__ import annotations

import argparse
import json
from pathlib import Path

from .features import FEATURE_NAMES
from .inference import MONTHS, CropFitPredictor
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
    predictor = CropFitPredictor(artifact, profiles)
    assert predictor.model.n_features_in_ == len(FEATURE_NAMES), "artifact and feature code disagree"
    history = [climate(18.0 + offset) for offset in (-3, -2, -1, 0, 0, 1, 1, 2, 3, 5)]
    result = predictor.predict("tomato", 29.76, -95.37, 6.5, True, climate(20.0), history)
    assert result["plantingReliability"]["years"] == 10
    assert result["bestReliablePlantingMonth"] in MONTHS
    assert len(result["monthlyCurve"]) == 12
    for month in result["monthlyCurve"]:
        assert month["historicalP10"] <= month["historicalMedian"] <= month["historicalP90"]
        assert 0 <= month["reliability"] <= 1

    profile = resolve_profile("tomato", predictor.profiles)
    ordinary = predictor.curve(profile, climate(20.0) + climate(20.0), 6.5, True)
    hot_next_year = predictor.curve(profile, climate(20.0) + climate(45.0), 6.5, True)
    assert ordinary[-1]["score"] != hot_next_year[-1]["score"], "late planting did not use following-year climate"

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

    print(f"CropFit inference verified: {predictor.metadata['model']} ({len(FEATURE_NAMES)} features, 10-year reliability, county evidence)")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    args = parser.parse_args()
    verify(args.artifact, args.profiles)


if __name__ == "__main__":
    main()
