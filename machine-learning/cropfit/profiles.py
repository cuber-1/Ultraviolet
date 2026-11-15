from __future__ import annotations

import csv
import math
from dataclasses import dataclass, asdict
from pathlib import Path


ALIASES = {
    "corn": "Zea mays",
    "maize": "Zea mays",
    "silage corn": "Zea mays",
    "sweet corn": "Zea mays ssp. saccharata",
    "soy": "Glycine max",
    "soybean": "Glycine max",
    "wheat": "Triticum aestivum",
    "spring wheat": "Triticum aestivum",
    "rice": "Oryza sativa",
    "tomato": "Lycopersicon esculentum",
    "strawberry": "Fragaria x ananassa",
    "lettuce": "Lactuca sativa var. capitata",
    "spinach": "Spinacia oleracea",
    "potato": "Solanum tuberosum",
    "cucumber": "Cucumis sativus",
    "pepper": "Capsicum annuum",
    "okra": "Abelmoschus esculentus",
    "basil": "Ocimum basilicum",
    "kale": "Brassica oleracea var. acephala",
    "bean": "Phaseolus vulgaris",
    "beans": "Phaseolus vulgaris",
    "common bean": "Phaseolus vulgaris",
    "melon": "Cucumis melo",
    "melons": "Cucumis melo",
    "onion": "Allium cepa",
    "onions": "Allium cepa",
    "sunflower": "Helianthus annuus",
    "sunflowers": "Helianthus annuus",
}


def _number(value: str | None) -> float | None:
    if not value or value.strip().upper() == "NA":
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


@dataclass(frozen=True)
class CropProfile:
    scientific_name: str
    common_name: str
    category: str
    temp_opt_min: float
    temp_opt_max: float
    temp_abs_min: float
    temp_abs_max: float
    rain_opt_min: float
    rain_opt_max: float
    rain_abs_min: float
    rain_abs_max: float
    ph_opt_min: float
    ph_opt_max: float
    ph_abs_min: float
    ph_abs_max: float
    growing_days_min: float
    growing_days_max: float

    def model_values(self) -> list[float]:
        return [
            self.temp_opt_min, self.temp_opt_max, self.temp_abs_min, self.temp_abs_max,
            self.rain_opt_min, self.rain_opt_max, self.rain_abs_min, self.rain_abs_max,
            self.ph_opt_min, self.ph_opt_max, self.ph_abs_min, self.ph_abs_max,
            self.growing_days_min, self.growing_days_max,
        ]

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


def load_profiles(path: Path) -> list[CropProfile]:
    profiles: list[CropProfile] = []
    with path.open(encoding="latin-1", newline="") as source:
        for row in csv.DictReader(source):
            values = {
                key: _number(row.get(column))
                for key, column in {
                    "temp_opt_min": "TOPMN", "temp_opt_max": "TOPMX",
                    "temp_abs_min": "TMIN", "temp_abs_max": "TMAX",
                    "rain_opt_min": "ROPMN", "rain_opt_max": "ROPMX",
                    "rain_abs_min": "RMIN", "rain_abs_max": "RMAX",
                    "ph_opt_min": "PHOPMN", "ph_opt_max": "PHOPMX",
                    "ph_abs_min": "PHMIN", "ph_abs_max": "PHMAX",
                    "growing_days_min": "GMIN", "growing_days_max": "GMAX",
                }.items()
            }
            if any(value is None for value in values.values()):
                continue
            if not (
                values["temp_abs_min"] <= values["temp_opt_min"] <= values["temp_opt_max"] <= values["temp_abs_max"]
                and values["rain_abs_min"] <= values["rain_opt_min"] <= values["rain_opt_max"] <= values["rain_abs_max"]
                and values["ph_abs_min"] <= values["ph_opt_min"] <= values["ph_opt_max"] <= values["ph_abs_max"]
                and values["growing_days_max"] >= values["growing_days_min"] > 0
            ):
                continue
            common = (row.get("COMNAME") or row.get("ScientificName") or "unknown").split(",")[0].strip()
            profiles.append(CropProfile(
                scientific_name=(row.get("ScientificName") or "unknown").strip(),
                common_name=common,
                category=(row.get("CAT") or "uncategorized").strip(),
                **{key: float(value) for key, value in values.items() if value is not None},
            ))
    return profiles


def resolve_profile(query: str, profiles: list[CropProfile]) -> CropProfile:
    normalized = query.strip().lower()
    scientific = ALIASES.get(normalized, query).lower()
    exact = [profile for profile in profiles if profile.scientific_name.lower() == scientific]
    if exact:
        return exact[0]
    common = [profile for profile in profiles if normalized == profile.common_name.lower()]
    if common:
        return common[0]
    contained = [profile for profile in profiles if normalized in profile.common_name.lower()]
    if contained:
        return contained[0]
    raise KeyError(f"No EcoCrop profile found for {query!r}")
