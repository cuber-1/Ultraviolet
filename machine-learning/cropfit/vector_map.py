from __future__ import annotations

import json
import math
from pathlib import Path

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
SCIENTIFIC_NAMES = {
    "almond": "Prunus dulcis", "corn": "Zea mays", "grape": "Vitis vinifera",
    "lettuce": "Lactuca sativa", "okra": "Abelmoschus esculentus", "pepper": "Capsicum annuum",
    "soybean": "Glycine max", "spinach": "Spinacia oleracea", "strawberry": "Fragaria × ananassa",
    "sweet potato": "Ipomoea batatas", "tomato": "Solanum lycopersicum", "wheat": "Triticum aestivum",
}


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    lat1, lat2 = math.radians(a_lat), math.radians(b_lat)
    d_lat, d_lon = lat2 - lat1, math.radians(b_lon - a_lon)
    value = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(value))


class DemoVectorMap:
    def __init__(self, path: Path):
        self.examples = json.loads(path.read_text())

    @staticmethod
    def input_vector(latitude: float, longitude: float, acreage: float, environment: str,
                     irrigated: bool, low_maintenance: bool, commercial: bool) -> dict[str, float]:
        rural = {"urban": 0.1, "suburban": 0.45, "rural": 1.0}.get(environment.lower(), 0.65)
        return {"latitude": latitude, "longitude": longitude, "acreage": max(0.1, acreage),
                "rural": rural, "irrigated": float(irrigated), "lowMaintenance": float(low_maintenance),
                "commercial": float(commercial)}

    @staticmethod
    def distance(query: dict[str, float], example: dict[str, float]) -> float:
        geo = min(1.0, _haversine_km(query["latitude"], query["longitude"], example["latitude"], example["longitude"]) / 3000)
        acreage = min(1.0, abs(math.log10(query["acreage"] + 1) - math.log10(example["acreage"] + 1)) / 2.5)
        return (0.55 * geo + 0.12 * acreage + 0.11 * abs(query["rural"] - example["rural"])
                + 0.08 * abs(query["irrigated"] - example["irrigated"])
                + 0.07 * abs(query["lowMaintenance"] - example["lowMaintenance"])
                + 0.07 * abs(query["commercial"] - example["commercial"]))

    def matches(self, query: dict[str, float]) -> list[tuple[float, dict]]:
        return sorted(((max(0.0, 1.0 - self.distance(query, item["vector"])), item) for item in self.examples), reverse=True, key=lambda pair: pair[0])

    def recommend(self, query: dict[str, float], preferences: list[str]) -> dict:
        matches = self.matches(query)
        wanted = {item.strip().lower() for item in preferences}
        candidates: dict[str, dict] = {}
        for similarity, example in matches[:3]:
            for recommendation in example["recommendations"]:
                crop = recommendation["crop"]
                tag_boost = 5 if wanted.intersection(recommendation.get("tags", [])) else 0
                score = round(min(99, recommendation["score"] * (0.72 + similarity * 0.28) + tag_boost), 1)
                candidate = {**recommendation, "score": score, "sourceExample": example["location"]}
                if crop not in candidates or score > candidates[crop]["score"]:
                    candidates[crop] = candidate
        return {"mode": "five-example-vector-map", "queryVector": query,
                "recommendations": sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:5],
                "matchedExamples": [{"id": item["id"], "location": item["location"], "similarity": round(similarity, 3)} for similarity, item in matches[:3]],
                "disclaimer": "Five-example demo similarity, not agronomic or financial advice."}

    def predict(self, crop: str, query: dict[str, float]) -> dict:
        matches = self.matches(query)
        selected = next(((similarity, example, rec) for similarity, example in matches for rec in example["recommendations"] if rec["crop"].lower() == crop.lower()), None)
        similarity, example, recommendation = selected or (matches[0][0], matches[0][1], {"crop": crop.lower(), "score": 68, "bestPlantingMonth": "APR"})
        best_index = MONTHS.index(recommendation["bestPlantingMonth"])
        best_score = min(98.0, float(recommendation["score"]) * (0.78 + 0.22 * similarity))
        curve = []
        for index, month in enumerate(MONTHS):
            gap = min((index - best_index) % 12, (best_index - index) % 12)
            score = max(4.0, best_score - gap * 16.0)
            curve.append({"month": month, "monthIndex": index + 1, "score": round(score, 1),
                          "uncertainty": round(8 + (1 - similarity) * 20, 1), "temperatureC": example["monthlyTemperatureC"][index],
                          "precipitationMmDay": 3.0, "solarMjM2Day": 16.0,
                          "components": {"temperature": round(score, 1), "water": 75.0, "soil_ph": 80.0, "solar": 78.0}})
        suitable = [item["month"] for item in curve if item["score"] >= best_score - 12]
        return {"crop": crop, "profile": {"scientific_name": SCIENTIFIC_NAMES.get(crop.lower(), crop.title()), "common_name": crop.lower(),
                "category": "five-example demo", "growing_days_min": 60, "growing_days_max": 150},
                "location": {"latitude": query["latitude"], "longitude": query["longitude"]},
                "score": round(best_score, 1), "confidence": round(0.5 + similarity * 0.35, 2),
                "bestPlantingMonth": recommendation["bestPlantingMonth"], "suitableMonths": suitable,
                "growingDays": {"min": 60, "max": 150},
                "limitingFactors": [{"factor": "demo coverage", "score": round(similarity * 100, 1)}, {"factor": "soil data", "score": 55}],
                "monthlyCurve": curve, "model": {"model": "CropFit five-example vector map", "labelType": "nearest demo similarity",
                "profiles": 5, "examples": 5, "metrics": {"mae": 0, "r2": 0, "p90AbsoluteError": 0}},
                "evidenceGrade": "demo-vector-map", "disclaimer": "Five-example demo similarity, not agronomic or financial advice."}
