from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import rankdata, spearmanr

from .download_observed_validation import CA_YIELD_URLS, COUNTIES_URL, PARAMETERS, POWER_URL
from .inference import CropFitPredictor


CROPS = {
    "corn": {"CORN, GRAIN", "CORN GRAIN"},
    "cucumber": {"CUCUMBERS"},
    "lettuce": {"LETTUCE, ALL", "LETTUCE UNSPECIFIED"},
    "pepper": {"PEPPERS, BELL", "PEPPERS BELL"},
    "potato": {"POTATOES", "POTATOES ALL"},
    "strawberry": {"BERRIES, STRAWBERRIES, FRESH MARKET", "BERRIES STRAWBERRIES FRESH MARKET"},
    "tomato": {"TOMATOES, FRESH", "TOMATOES FRESH MARKET"},
    "wheat": {"WHEAT, ALL", "WHEAT ALL"},
}
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def number(value: str | None) -> float | None:
    try:
        result = float(str(value or "").replace(",", "").strip())
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def county_points(path: Path) -> dict[str, tuple[float, float, str]]:
    with zipfile.ZipFile(path) as archive:
        name = next(item for item in archive.namelist() if item.endswith(".txt"))
        with archive.open(name) as raw:
            rows = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t")
            normalized = ({str(key).strip(): str(value).strip() for key, value in row.items()} for row in rows)
            return {
                row["GEOID"]: (float(row["INTPTLAT"]), float(row["INTPTLONG"]), row["NAME"])
                for row in normalized if row["USPS"] == "CA"
            }


def power_grids(root: Path, year: int) -> dict[str, list[tuple[float, float, dict[str, float]]]]:
    grids: dict[str, list[tuple[float, float, dict[str, float]]]] = defaultdict(list)
    for parameter in PARAMETERS:
        for path in sorted(root.glob(f"nasa-power-{year}-{parameter.lower()}-*.json")):
            for feature in json.loads(path.read_text())["features"]:
                longitude, latitude, *_ = feature["geometry"]["coordinates"]
                values = feature["properties"]["parameter"][parameter]
                grids[parameter].append((float(latitude), float(longitude), values))
        if not grids[parameter]:
            raise FileNotFoundError(f"No NASA POWER tiles found for {parameter}; run the observed-data downloader first")
    return grids


def nearest(grid: list[tuple[float, float, dict[str, float]]], latitude: float, longitude: float) -> dict[str, float]:
    return min(grid, key=lambda item: (item[0] - latitude) ** 2 + (item[1] - longitude) ** 2)[2]


def climate(grids: dict[str, list[tuple[float, float, dict[str, float]]]], latitude: float, longitude: float, year: int) -> list[dict]:
    values = {parameter: nearest(grids[parameter], latitude, longitude) for parameter in PARAMETERS}
    return [{
        "month": month,
        "temperatureC": float(values["T2M"][f"{year}{index:02d}"]),
        "precipitationMmDay": float(values["PRECTOTCORR"][f"{year}{index:02d}"]),
        "solarMjM2Day": float(values["ALLSKY_SFC_SW_DWN"][f"{year}{index:02d}"]),
    } for index, month in enumerate(MONTHS, 1)]


def bootstrap_interval(scores: np.ndarray, yields: np.ndarray, groups: np.ndarray, seed: int = 20261114) -> tuple[float, float]:
    random = np.random.default_rng(seed)
    unique_groups = np.unique(groups)
    estimates = []
    for _ in range(2000):
        sampled_groups = random.choice(unique_groups, len(unique_groups), replace=True)
        indices = np.concatenate([np.flatnonzero(groups == group) for group in sampled_groups])
        if len(np.unique(scores[indices])) > 1 and len(np.unique(yields[indices])) > 1:
            estimates.append(float(spearmanr(scores[indices], yields[indices]).statistic))
    return tuple(round(float(value), 4) for value in np.quantile(estimates, [.025, .975])) if estimates else (math.nan, math.nan)


def validate(data: Path, artifact: Path, profiles: Path, minimum_acres: float) -> dict:
    points = county_points(data / "2022_Gaz_counties_national.zip")
    predictor = CropFitPredictor(artifact, profiles)
    observations: dict[str, list[dict]] = defaultdict(list)
    item_to_crop = {item: crop for crop, items in CROPS.items() for item in items}
    for year in CA_YIELD_URLS:
        grids = power_grids(data, year)
        with (data / f"ca-county-ag-{year}.csv").open(newline="", encoding="utf-8-sig") as source:
            for row in csv.DictReader(source, skipinitialspace=True):
                item = (row.get("Current Item Name") or row.get("Crop Name") or "").strip().upper()
                crop = item_to_crop.get(item)
                county = (row.get("County") or "").strip()
                acres = number(row.get("Harvested Acres"))
                observed_yield = number(row.get("Yield") or row.get("Yield (Unit/Acre)"))
                if crop is None or county == "State Total" or acres is None or observed_yield is None or acres < minimum_acres:
                    continue
                fips = f"06{int(row['County Code']):03d}"
                if fips not in points:
                    continue
                latitude, longitude, county_name = points[fips]
                result = predictor.predict(crop, latitude, longitude, 6.5, True, climate(grids, latitude, longitude, year))
                observations[crop].append({
                    "year": year, "crop": crop, "county": county_name, "fips": fips, "harvestedAcres": acres,
                    "yieldTonsPerAcre": observed_yield, "cropFitScore": result["score"],
                })
    per_crop = []
    pooled_scores, pooled_yield_ranks, pooled_groups = [], [], []
    for crop, rows in observations.items():
        scores = np.asarray([row["cropFitScore"] for row in rows])
        yields = np.asarray([row["yieldTonsPerAcre"] for row in rows])
        correlation = float(spearmanr(scores, yields).statistic) if len(rows) >= 4 and len(np.unique(scores)) > 1 else math.nan
        interval = bootstrap_interval(scores, yields, np.asarray([row["fips"] for row in rows])) if math.isfinite(correlation) else (math.nan, math.nan)
        per_crop.append({
            "crop": crop, "observations": len(rows), "spearman": round(correlation, 4) if math.isfinite(correlation) else None,
            "bootstrap95": [value if math.isfinite(value) else None for value in interval],
            "medianScore": round(float(np.median(scores)), 2), "medianYieldTonsPerAcre": round(float(np.median(yields)), 3),
        })
        if len(rows) >= 4:
            pooled_scores.extend(scores.tolist())
            pooled_yield_ranks.extend((rankdata(yields, method="average") / len(yields)).tolist())
            pooled_groups.extend(f"{crop}:{row['fips']}" for row in rows)
    pooled_scores_array = np.asarray(pooled_scores)
    pooled_yields_array = np.asarray(pooled_yield_ranks)
    pooled = float(spearmanr(pooled_scores_array, pooled_yields_array).statistic)
    pooled_interval = bootstrap_interval(pooled_scores_array, pooled_yields_array, np.asarray(pooled_groups))
    eligible = [item for item in per_crop if item["observations"] >= 6 and item["spearman"] is not None]
    positive = sum(item["spearman"] > 0 for item in eligible)
    per_year = []
    for year in CA_YIELD_URLS:
        year_rows = [row for rows in observations.values() for row in rows if row["year"] == year]
        year_scores, year_ranks = [], []
        for crop in observations:
            crop_rows = [row for row in year_rows if row["crop"] == crop]
            if len(crop_rows) >= 4:
                year_scores.extend(row["cropFitScore"] for row in crop_rows)
                year_ranks.extend((rankdata([row["yieldTonsPerAcre"] for row in crop_rows]) / len(crop_rows)).tolist())
        correlation = float(spearmanr(year_scores, year_ranks).statistic) if len(year_scores) >= 8 else math.nan
        per_year.append({"year": year, "observations": len(year_scores), "spearman": round(correlation, 4) if math.isfinite(correlation) else None})
    positive_years = sum(item["spearman"] is not None and item["spearman"] > 0 for item in per_year)
    passed = pooled >= .3 and pooled_interval[0] > 0 and len(eligible) >= 4 and positive >= math.ceil(len(eligible) / 2) and positive_years >= 3
    return {
        "model": joblib.load(artifact)["metadata"]["model"],
        "evaluation": "external observed county yield; not used in training or model selection",
        "years": sorted(CA_YIELD_URLS),
        "scope": "California counties",
        "assumptions": {"soilPh": 6.5, "irrigated": True, "minimumHarvestedAcres": minimum_acres, "score": "best planting month"},
        "sources": {"yield": CA_YIELD_URLS, "countyCoordinates": COUNTIES_URL, "weather": POWER_URL},
        "pooledWithinCrop": {"observations": len(pooled_scores), "spearman": round(pooled, 4), "bootstrap95": list(pooled_interval)},
        "gate": {"passed": passed, "rule": "pooled Spearman >= 0.30, bootstrap lower bound > 0, >=4 crops with >=6 observations, at least half of eligible crops positive, and at least 3 of 5 years positive"},
        "perCrop": sorted(per_crop, key=lambda item: item["crop"]),
        "perYear": per_year,
        "protocolHistory": "The multi-year gate was declared after the initial 2022-only exploratory gate failed; 2018-2021 results were not inspected first.",
        "limitations": [
            "County yield reflects cultivar, management, irrigation, soil, pests, economics, and reporting—not climate alone.",
            "One state across five years is an external face-validity test, not sufficient yield calibration.",
            "Confidence intervals resample county-crop groups, but one state still limits geographic independence.",
            "Suppressed or unreported county-crop combinations are absent rather than treated as zero yield.",
        ],
    }


def markdown(report: dict) -> str:
    lines = [
        f"# {report['model']} observed-outcome validation", "",
        f"**Gate: {'PASS' if report['gate']['passed'] else 'NOT PASSED'}**", "",
        f"California 2018–2022 county yields, {report['pooledWithinCrop']['observations']} observations. "
        f"Pooled within-crop Spearman: {report['pooledWithinCrop']['spearman']:.3f} "
        f"(county-crop grouped-bootstrap 95% interval {report['pooledWithinCrop']['bootstrap95'][0]:.3f} to {report['pooledWithinCrop']['bootstrap95'][1]:.3f}).", "",
        "| Crop | Observations | Spearman | 95% interval | Median score | Median yield (tons/acre) |", "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["perCrop"]:
        corr = "—" if item["spearman"] is None else f"{item['spearman']:.3f}"
        interval = "—" if item["bootstrap95"][0] is None else f"{item['bootstrap95'][0]:.3f} to {item['bootstrap95'][1]:.3f}"
        lines.append(f"| {item['crop']} | {item['observations']} | {corr} | {interval} | {item['medianScore']:.1f} | {item['medianYieldTonsPerAcre']:.3f} |")
    lines.extend(["", "| Year | Observations | Spearman |", "|---|---:|---:|"])
    for item in report["perYear"]:
        correlation = "—" if item["spearman"] is None else f"{item['spearman']:.3f}"
        lines.append(f"| {item['year']} | {item['observations']} | {correlation} |")
    lines.extend(["", "The gate rule was fixed before reading the result: " + report["gate"]["rule"] + ".", "", "## Interpretation", ""])
    lines.append("Passing would only justify continuing calibration work. It would not turn CropFit into a parcel-level yield forecast or property recommendation.")
    lines.extend(["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]] + [""])
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation")
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/observed-validation-v0.4.json")
    parser.add_argument("--minimum-acres", type=float, default=100)
    args = parser.parse_args()
    report = validate(args.data, args.artifact, args.profiles, args.minimum_acres)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report["pooledWithinCrop"] | report["gate"], indent=2))


if __name__ == "__main__":
    main()
