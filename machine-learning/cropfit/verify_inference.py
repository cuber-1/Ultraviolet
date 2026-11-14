from __future__ import annotations

import argparse
from pathlib import Path

from .features import FEATURE_NAMES
from .inference import MONTHS, CropFitPredictor
from .profiles import resolve_profile
from .yield_atlas import nearest_evidence


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

    atlas = artifact.parents[1] / "evaluation/yield-atlas-v1.json"
    if atlas.exists():
        evidence = nearest_evidence("corn", 29.7604, -95.3698, atlas)
        assert evidence and evidence["county"] == "Fort Bend County" and evidence["observations"] == 7
        assert evidence["latest"]["year"] == 2025
        assert [item["year"] for item in evidence["history"]][-3:] == [2023, 2024, 2025]
        assert nearest_evidence("tomato", 29.7604, -95.3698, atlas) is None

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
