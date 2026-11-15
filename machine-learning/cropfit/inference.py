from __future__ import annotations

import calendar
import hashlib
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import requests
import certifi

from .features import FEATURE_NAMES, feature_row, teacher_scores
from .profiles import load_profiles, resolve_profile


MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
CLIMATE_HISTORY_START_YEAR = 2016
CLIMATE_HISTORY_END_YEAR = 2025
CLIMATE_HISTORY_YEARS = tuple(range(CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_END_YEAR + 1))
MAX_CLIMATE_HISTORY_YEARS = 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def align_model_features(
    row: list[float],
    expected: int,
    model_feature_names: list[str] | None = None,
) -> list[float]:
    if model_feature_names and len(model_feature_names) == expected:
        if len(row) == expected:
            return row
        if len(row) == len(FEATURE_NAMES):
            unknown = set(model_feature_names) - set(FEATURE_NAMES)
            if unknown:
                raise RuntimeError(f"Artifact requests unknown features: {sorted(unknown)}")
            if len(set(model_feature_names)) != len(model_feature_names):
                raise RuntimeError("Artifact feature contract contains duplicate names")
            positions = {name: index for index, name in enumerate(FEATURE_NAMES)}
            return [row[positions[name]] for name in model_feature_names]
    if len(row) == expected:
        return row
    if len(row) == expected + 2:
        return row[:-2]
    raise RuntimeError(f"Artifact expects {expected} features but inference produced {len(row)}")


class CropFitPredictor:
    def __init__(self, artifact: Path, profiles_path: Path):
        bundle = joblib.load(artifact)
        if not isinstance(bundle, dict) or not {"model", "metadata"}.issubset(bundle):
            raise RuntimeError("CropFit artifact must contain model and metadata entries.")
        self.model = bundle["model"]
        self.booster = bundle.get("booster")
        self.metadata = bundle["metadata"]
        if not isinstance(self.metadata, dict) or not isinstance(self.metadata.get("model"), str):
            raise RuntimeError("CropFit artifact metadata is missing its model identity.")
        if not hasattr(self.model, "predict") or not hasattr(self.model, "n_features_in_"):
            raise RuntimeError("CropFit artifact model does not satisfy the inference contract.")
        expected_features = int(self.model.n_features_in_)
        metadata_features = self.metadata.get("featureNames")
        if metadata_features and len(metadata_features) not in (expected_features, expected_features + 2):
            raise RuntimeError(
                f"CropFit artifact feature contract is inconsistent: model={expected_features}, metadata={len(metadata_features)}."
            )
        if metadata_features and len(metadata_features) == expected_features:
            unknown = set(metadata_features) - set(FEATURE_NAMES)
            if unknown:
                raise RuntimeError(f"CropFit artifact requests unknown features: {sorted(unknown)}")
            if len(set(metadata_features)) != len(metadata_features):
                raise RuntimeError("CropFit artifact feature contract contains duplicate names.")
        if not getattr(self.model, "estimators_", None):
            raise RuntimeError("CropFit artifact does not contain fitted ensemble estimators.")
        self.artifact_sha256 = sha256_file(artifact)
        self.profiles = load_profiles(profiles_path)

    def model_features(self, row: list[float]) -> list[float]:
        """Select named compact features while retaining older 23/25-feature artifacts."""
        return align_model_features(
            row,
            int(self.model.n_features_in_),
            self.metadata.get("featureNames"),
        )

    def calibrated_error(self, tree_std: float, active: bool = True) -> tuple[float, float]:
        conditional = self.metadata.get("conditionalUncertaintyCalibration", {})
        conditional_quantiles = conditional.get("activeNormalizedErrorQuantiles")
        if conditional_quantiles:
            if not active:
                return 0.0, 0.0
            scale = tree_std + float(self.metadata.get("uncertaintyCalibration", {}).get("treeStdFloor", 0.01))
            return float(conditional_quantiles["p80"]) * scale, float(conditional_quantiles["p90"]) * scale
        calibration = self.metadata.get("uncertaintyCalibration", {})
        quantiles = calibration.get("normalizedErrorQuantiles")
        if quantiles:
            scale = tree_std + float(calibration.get("treeStdFloor", 0.01))
            return float(quantiles["p80"]) * scale, float(quantiles["p90"]) * scale
        bins = calibration.get("bins", [])
        for item in bins:
            upper = item.get("upperTreeStd")
            if tree_std >= float(item["lowerTreeStd"]) and (upper is None or tree_std < float(upper)):
                return float(item["p80AbsoluteError"]), float(item["p90AbsoluteError"])
        return tree_std, min(100.0, tree_std * 1.5)

    @lru_cache(maxsize=512)
    def climate_bundle(self, latitude: float, longitude: float) -> tuple[list[dict], list[list[dict]]]:
        response = requests.get(
            "https://power.larc.nasa.gov/api/temporal/monthly/point",
            params={
                "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN",
                "community": "AG", "longitude": longitude, "latitude": latitude, "format": "JSON",
                "start": str(CLIMATE_HISTORY_START_YEAR), "end": str(CLIMATE_HISTORY_END_YEAR),
            },
            timeout=25,
            verify=certifi.where(),
        )
        response.raise_for_status()
        parameters = response.json()["properties"]["parameter"]
        history = [[{
            "month": month,
            "year": year,
            "temperatureC": float(parameters["T2M"][f"{year}{index + 1:02d}"]),
            "precipitationMmDay": float(parameters["PRECTOTCORR"][f"{year}{index + 1:02d}"]),
            "solarMjM2Day": float(parameters["ALLSKY_SFC_SW_DWN"][f"{year}{index + 1:02d}"]),
        } for index, month in enumerate(MONTHS)] for year in CLIMATE_HISTORY_YEARS]
        baseline = [{
            "month": month,
            "temperatureC": float(np.mean([year[index]["temperatureC"] for year in history])),
            "precipitationMmDay": float(np.mean([year[index]["precipitationMmDay"] for year in history])),
            "solarMjM2Day": float(np.mean([year[index]["solarMjM2Day"] for year in history])),
        } for index, month in enumerate(MONTHS)]
        return baseline, history

    @staticmethod
    def validate_climate(climate: list[dict]) -> None:
        if len(climate) not in (12, 24):
            raise ValueError("Climate series must contain 12 months, optionally followed by the next 12 months.")
        for index, item in enumerate(climate):
            if str(item.get("month", "")).upper()[:3] != MONTHS[index % 12]:
                raise ValueError("Climate months must be ordered JAN through DEC.")
            try:
                temperature = float(item.get("temperatureC"))
                precipitation = float(item.get("precipitationMmDay"))
                solar = float(item.get("solarMjM2Day"))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Climate record {MONTHS[index % 12]} contains a missing or invalid value.") from error
            if not all(np.isfinite(value) for value in (temperature, precipitation, solar)):
                raise ValueError(f"Climate record {MONTHS[index % 12]} contains a non-finite value.")
            if not -100 <= temperature <= 80:
                raise ValueError(f"Climate record {MONTHS[index % 12]} has temperature outside -100 to 80 C.")
            if not 0 <= precipitation <= 1000:
                raise ValueError(f"Climate record {MONTHS[index % 12]} has precipitation outside 0 to 1000 mm/day.")
            if not 0 <= solar <= 100:
                raise ValueError(f"Climate record {MONTHS[index % 12]} has solar resource outside 0 to 100 MJ/m2/day.")

    @staticmethod
    def validate_request(
        crop: str, latitude: float, longitude: float, soil_ph: float,
        irrigated: bool, climate_history: list[list[dict]] | None,
    ) -> None:
        if not isinstance(crop, str) or not 2 <= len(crop.strip()) <= 100:
            raise ValueError("Crop name must contain 2 to 100 characters.")
        scalar_values = (latitude, longitude, soil_ph)
        if not all(isinstance(value, (int, float)) and np.isfinite(value) for value in scalar_values):
            raise ValueError("Latitude, longitude, and soil pH must be finite numbers.")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Latitude or longitude is outside the valid geographic range.")
        if not 2.5 <= soil_ph <= 10.5:
            raise ValueError("Soil pH must be between 2.5 and 10.5.")
        if not isinstance(irrigated, bool):
            raise ValueError("Irrigated must be a boolean.")
        if climate_history is None:
            return
        if not isinstance(climate_history, list) or len(climate_history) > MAX_CLIMATE_HISTORY_YEARS:
            raise ValueError(f"Climate history may contain at most {MAX_CLIMATE_HISTORY_YEARS} years.")
        for year in climate_history:
            if not isinstance(year, list) or len(year) != 12:
                raise ValueError("Each climate-history year must contain exactly 12 months.")

    def curve_inputs(self, profile, climate_values: list[dict], soil_ph: float, irrigated: bool) -> tuple[list, list, list, list]:
        self.validate_climate(climate_values)
        cycle_days = min(365, max(30, round((profile.growing_days_min + profile.growing_days_max) / 2)))
        rows = []
        teacher = []
        establishment = []
        seasonal_climate = []
        for start_index, month in enumerate(climate_values[:12]):
            remaining = cycle_days
            cursor = start_index
            temperature_total = precipitation_total = solar_total = 0.0
            while remaining > 0:
                current = climate_values[cursor] if cursor < len(climate_values) else climate_values[cursor % 12]
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
            row = self.model_features(feature_row(profile, temperature, annualized_precipitation, soil_ph, solar, irrigated))
            rows.append(row)
            teacher.append(teacher_scores(profile, temperature, annualized_precipitation, soil_ph, solar, irrigated))
            start_precipitation = float(month["precipitationMmDay"]) * 365.25
            establishment.append(teacher_scores(profile, float(month["temperatureC"]), start_precipitation, soil_ph, float(month["solarMjM2Day"]), irrigated))
        return rows, teacher, establishment, seasonal_climate

    def curves(self, profile, climate_series: list[list[dict]], soil_ph: float, irrigated: bool) -> list[list[dict]]:
        inputs = [self.curve_inputs(profile, values, soil_ph, irrigated) for values in climate_series]
        all_rows = np.asarray([row for rows, *_ in inputs for row in rows], dtype=np.float32)
        tree_predictions = np.asarray([tree.predict(all_rows) for tree in self.model.estimators_])
        if self.booster is not None and self.metadata.get("selectedModel") == "xgboost":
            import xgboost as xgb
            predictions = self.booster.predict(xgb.DMatrix(all_rows, feature_names=self.metadata["featureNames"]))
        else:
            predictions = tree_predictions.mean(axis=0)
        uncertainty = tree_predictions.std(axis=0)
        result = []
        offset = 0
        for climate_values, (_, teacher, establishment, seasonal_climate) in zip(climate_series, inputs, strict=True):
            curve = []
            for index, month in enumerate(climate_values[:12]):
                position = offset + index
                component = {name: min(value, establishment[index][name]) for name, value in teacher[index].items()}
                temperature, precipitation_mm_day, solar = seasonal_climate[index]
                # The surrogate may not extrapolate a hard zero at exact/out-of-domain
                # EcoCrop boundaries. Never let it exceed either deterministic ceiling.
                score = min(float(predictions[position]), teacher[index]["suitability"], establishment[index]["suitability"])
                active = teacher[index]["suitability"] > 0 and establishment[index]["suitability"] > 0
                error_p80, error_p90 = self.calibrated_error(float(uncertainty[position]), active)
                curve.append({
                    "month": str(month["month"]),
                    "monthIndex": index + 1,
                    "score": round(score, 1),
                    "uncertainty": round(float(uncertainty[position]), 1),
                    # Error radii round upward so serialization cannot weaken calibrated coverage.
                    "expectedAbsoluteErrorP80": float(np.ceil(error_p80 * 1000) / 1000),
                    "expectedAbsoluteErrorP90": float(np.ceil(error_p90 * 1000) / 1000),
                    "temperatureC": round(temperature, 1),
                    "precipitationMmDay": round(precipitation_mm_day, 2),
                    "solarMjM2Day": round(solar, 1),
                    "components": {name: round(value, 1) for name, value in component.items() if name != "suitability"},
                })
            result.append(curve)
            offset += len(curve)
        return result

    def curve(self, profile, climate_values: list[dict], soil_ph: float, irrigated: bool) -> list[dict]:
        return self.curves(profile, [climate_values], soil_ph, irrigated)[0]

    def predict(self, crop: str, latitude: float, longitude: float, soil_ph: float = 6.5, irrigated: bool = False,
                climate: list[dict] | None = None, climate_history: list[list[dict]] | None = None):
        self.validate_request(crop, latitude, longitude, soil_ph, irrigated, climate_history)
        profile = resolve_profile(crop, self.profiles)
        if climate is None:
            climate_values, fetched_history = self.climate_bundle(latitude, longitude)
            climate_history = climate_history or fetched_history
        else:
            climate_values = climate
        history = climate_history or []
        climate_series = [climate_values] + [year + (history[index + 1] if index + 1 < len(history) else climate_values) for index, year in enumerate(history)]
        curve, *historical_curves = self.curves(profile, climate_series, soil_ph, irrigated)
        for month_index, item in enumerate(curve):
            if not historical_curves:
                continue
            scores = np.asarray([year[month_index]["score"] for year in historical_curves], dtype=float)
            item.update({
                "historicalP10": round(float(np.percentile(scores, 10)), 1),
                "historicalMedian": round(float(np.median(scores)), 1),
                "historicalP90": round(float(np.percentile(scores, 90)), 1),
                "reliability": round(float(np.mean(scores >= 55.0)), 2),
            })
        best = max(curve, key=lambda item: item["score"])
        reliable_best = max(curve, key=lambda item: (item.get("historicalP10", item["score"]), item.get("historicalMedian", item["score"])))
        limiting = sorted(best["components"].items(), key=lambda item: item[1])[:2]
        threshold = max(55.0, float(best["score"]) - 12.0)
        reliable_months = [item["month"] for item in curve if item.get("reliability", 0) >= .7 and item.get("historicalMedian", 0) >= 55.0]
        suitable_months = reliable_months or [item["month"] for item in curve if item["score"] >= threshold]
        planting_reliability = None if not historical_curves else {
            "years": len(historical_curves),
            "successRate": reliable_best["reliability"],
            "p10Score": reliable_best["historicalP10"],
            "medianScore": reliable_best["historicalMedian"],
            "p90Score": reliable_best["historicalP90"],
            "threshold": 55.0,
        }
        return {
            "crop": crop,
            "profile": profile.to_dict(),
            "location": {"latitude": latitude, "longitude": longitude},
            "score": best["score"],
            "confidence": float(self.metadata.get("uncertaintyCalibration", {}).get("nominalCoverage", {}).get("p80", .8)),
            "expectedAbsoluteError": {"p80": best["expectedAbsoluteErrorP80"], "p90": best["expectedAbsoluteErrorP90"]},
            "bestPlantingMonth": best["month"],
            "bestReliablePlantingMonth": reliable_best["month"],
            "plantingReliability": planting_reliability,
            "suitableMonths": suitable_months,
            "growingDays": {"min": profile.growing_days_min, "max": profile.growing_days_max},
            "limitingFactors": [{"factor": name, "score": value} for name, value in limiting],
            "monthlyCurve": curve,
            "model": self.metadata,
            "evidenceGrade": "agroclimatic-screening",
            "disclaimer": f"EcoCrop screening estimate. Historical bands use NASA POWER {CLIMATE_HISTORY_START_YEAR}–{CLIMATE_HISTORY_END_YEAR} weather; they are not a yield forecast or purchase recommendation.",
        }
