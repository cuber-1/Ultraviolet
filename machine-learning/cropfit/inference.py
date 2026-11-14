from __future__ import annotations

import calendar
from pathlib import Path

import joblib
import numpy as np
import requests

from .features import feature_row, teacher_scores
from .profiles import load_profiles, resolve_profile


MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


class CropFitPredictor:
    def __init__(self, artifact: Path, profiles_path: Path):
        bundle = joblib.load(artifact)
        self.model = bundle["model"]
        self.booster = bundle.get("booster")
        self.metadata = bundle["metadata"]
        self.profiles = load_profiles(profiles_path)

    def climate(self, latitude: float, longitude: float) -> list[dict[str, float | str]]:
        response = requests.get(
            "https://power.larc.nasa.gov/api/temporal/climatology/point",
            params={
                "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN",
                "community": "AG", "longitude": longitude, "latitude": latitude, "format": "JSON",
            },
            timeout=25,
        )
        response.raise_for_status()
        parameters = response.json()["properties"]["parameter"]
        return [{
            "month": month,
            "temperatureC": float(parameters["T2M"][month]),
            "precipitationMmDay": float(parameters["PRECTOTCORR"][month]),
            "solarMjM2Day": float(parameters["ALLSKY_SFC_SW_DWN"][month]),
        } for month in MONTHS]

    def predict(self, crop: str, latitude: float, longitude: float, soil_ph: float = 6.5, irrigated: bool = False, climate: list[dict] | None = None):
        profile = resolve_profile(crop, self.profiles)
        climate_values = climate or self.climate(latitude, longitude)
        cycle_days = min(365, max(30, round((profile.growing_days_min + profile.growing_days_max) / 2)))
        rows = []
        teacher = []
        establishment = []
        seasonal_climate = []
        for start_index, month in enumerate(climate_values):
            remaining = cycle_days
            cursor = start_index
            temperature_total = precipitation_total = solar_total = 0.0
            while remaining > 0:
                current = climate_values[cursor % 12]
                days = min(remaining, calendar.monthrange(2025, cursor % 12 + 1)[1])
                temperature_total += float(current["temperatureC"]) * days
                precipitation_total += float(current["precipitationMmDay"]) * days
                solar_total += float(current["solarMjM2Day"]) * days
                remaining -= days
                cursor += 1
            temperature = temperature_total / cycle_days
            solar = solar_total / cycle_days
            precipitation_mm_day = precipitation_total / cycle_days
            annualized_precipitation = precipitation_mm_day * 365.25
            seasonal_climate.append((temperature, precipitation_mm_day, solar))
            row = feature_row(profile, temperature, annualized_precipitation, soil_ph, solar, irrigated)
            rows.append(row)
            teacher.append(teacher_scores(profile, temperature, annualized_precipitation, soil_ph, solar, irrigated))
            start_precipitation = float(month["precipitationMmDay"]) * 365.25
            establishment.append(teacher_scores(profile, float(month["temperatureC"]), start_precipitation, soil_ph, float(month["solarMjM2Day"]), irrigated))
        tree_predictions = np.asarray([tree.predict(np.asarray(rows, dtype=np.float32)) for tree in self.model.estimators_])
        if self.booster is not None and self.metadata.get("selectedModel") == "xgboost":
            import xgboost as xgb
            predictions = self.booster.predict(xgb.DMatrix(np.asarray(rows, dtype=np.float32), feature_names=self.metadata["featureNames"]))
        else:
            predictions = tree_predictions.mean(axis=0)
        uncertainty = tree_predictions.std(axis=0)
        curve = []
        for index, month in enumerate(climate_values):
            component = {name: min(value, establishment[index][name]) for name, value in teacher[index].items()}
            temperature, precipitation_mm_day, solar = seasonal_climate[index]
            score = min(float(predictions[index]), establishment[index]["suitability"])
            curve.append({
                "month": str(month["month"]),
                "monthIndex": index + 1,
                "score": round(score, 1),
                "uncertainty": round(float(uncertainty[index]), 1),
                "temperatureC": round(temperature, 1),
                "precipitationMmDay": round(precipitation_mm_day, 2),
                "solarMjM2Day": round(solar, 1),
                "components": {name: round(value, 1) for name, value in component.items() if name != "suitability"},
            })
        best = max(curve, key=lambda item: item["score"])
        limiting = sorted(best["components"].items(), key=lambda item: item[1])[:2]
        threshold = max(55.0, float(best["score"]) - 12.0)
        suitable_months = [item["month"] for item in curve if item["score"] >= threshold]
        return {
            "crop": crop,
            "profile": profile.to_dict(),
            "location": {"latitude": latitude, "longitude": longitude},
            "score": best["score"],
            "confidence": round(max(0.15, min(.92, 1.0 - float(best["uncertainty"]) / 45.0)), 2),
            "bestPlantingMonth": best["month"],
            "suitableMonths": suitable_months,
            "growingDays": {"min": profile.growing_days_min, "max": profile.growing_days_max},
            "limitingFactors": [{"factor": name, "score": value} for name, value in limiting],
            "monthlyCurve": curve,
            "model": self.metadata,
            "evidenceGrade": "agroclimatic-screening",
            "disclaimer": "EcoCrop screening estimate; not a parcel-specific yield forecast or purchase recommendation.",
        }
