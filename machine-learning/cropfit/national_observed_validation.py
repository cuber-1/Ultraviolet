from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import rankdata, spearmanr

from .inference import CropFitPredictor
from .observed_validation import bootstrap_interval, climate, county_points, number, power_grids


CROP_NAMES = {"CORN": "corn", "SOYBEANS": "soybean", "WHEAT": "wheat"}
YEARS = tuple(range(2018, 2023))


def validate(data: Path, artifact: Path, profiles: Path) -> dict:
    points = county_points(data / "2022_Gaz_counties_national.zip", state=None)
    predictor = CropFitPredictor(artifact, profiles)
    grids = {year: power_grids(data, year) for year in YEARS}
    score_cache = data / "cropfit-v0.4-scores.json"
    if score_cache.exists():
        observations = json.loads(score_cache.read_text())
    else:
        observations = []
        with (data / "quickstats-county-yield-2018-2022.tsv").open(newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source, delimiter="\t"):
                if row["STATE_ALPHA"] in {"AK", "CA", "HI", "PR"} or not row["COUNTY_CODE"].strip():
                    continue
                observed_yield = number(row["VALUE"])
                if observed_yield is None:
                    continue
                fips = f"{int(row['STATE_FIPS_CODE']):02d}{int(row['COUNTY_CODE']):03d}"
                if fips not in points:
                    continue
                latitude, longitude, county_name = points[fips]
                if not (24 <= latitude <= 50 and -125 <= longitude <= -66):
                    continue
                year = int(row["YEAR"])
                crop = CROP_NAMES[row["COMMODITY_DESC"]]
                result = predictor.predict(crop, latitude, longitude, 6.5, False, climate(grids[year], latitude, longitude, year))
                observations.append({
                    "year": year, "crop": crop, "fips": fips, "state": row["STATE_ALPHA"], "county": county_name,
                    "yieldBushelsPerAcre": observed_yield, "cropFitScore": result["score"],
                })
                if len(observations) % 1000 == 0:
                    print(f"scored {len(observations)} county-year rows", flush=True)
        score_cache.write_text(json.dumps(observations, separators=(",", ":")) + "\n")
    by_crop_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in observations:
        by_crop_year[(row["crop"], row["year"])].append(row)
    for rows in by_crop_year.values():
        ranks = rankdata([row["yieldBushelsPerAcre"] for row in rows], method="average") / len(rows)
        for row, percentile in zip(rows, ranks):
            row["yieldPercentileWithinCropYear"] = float(percentile)

    def summary(rows: list[dict], groups: np.ndarray | None = None) -> dict:
        scores = np.asarray([row["cropFitScore"] for row in rows])
        yields = np.asarray([row["yieldPercentileWithinCropYear"] for row in rows])
        correlation = float(spearmanr(scores, yields).statistic)
        interval = bootstrap_interval(scores, yields, groups if groups is not None else np.asarray([f"{row['crop']}:{row['fips']}" for row in rows]))
        return {"observations": len(rows), "spearman": round(correlation, 4), "bootstrap95": list(interval), "medianScore": round(float(np.median(scores)), 2)}

    pooled = summary(observations)
    per_crop = [{"crop": crop, **summary([row for row in observations if row["crop"] == crop], np.asarray([row["fips"] for row in observations if row["crop"] == crop]))} for crop in sorted(CROP_NAMES.values())]
    per_year = [{"year": year, **summary([row for row in observations if row["year"] == year])} for year in YEARS]
    positive_crops = sum(item["spearman"] > 0 for item in per_crop)
    positive_years = sum(item["spearman"] > 0 for item in per_year)
    passed = pooled["spearman"] >= .3 and pooled["bootstrap95"][0] > 0 and positive_crops == len(per_crop) and positive_years >= 4
    metadata = json.loads((data / "download-metadata.json").read_text())
    return {
        "model": joblib.load(artifact)["metadata"]["model"],
        "evaluation": "independent nationwide observed county yield; not used in training or model selection",
        "years": list(YEARS), "scope": "contiguous U.S. counties excluding California",
        "assumptions": {"soilPh": 6.5, "irrigated": False, "score": "best planting month", "yieldNormalization": "percentile within crop and year"},
        "sources": {"quickStats": metadata["quickStats"], "countyCoordinates": "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2022_Gazetteer/2022_Gaz_counties_national.zip", "weather": "https://power.larc.nasa.gov/api/temporal/monthly/regional"},
        "pooledWithinCropYear": pooled, "perCrop": per_crop, "perYear": per_year,
        "gate": {"passed": passed, "rule": "pooled Spearman >= 0.30, grouped-bootstrap lower bound > 0, every crop positive, and at least 4 of 5 years positive"},
        "protocol": "Declared after the California gate failed and before nationwide outcomes were scored.",
        "limitations": [
            "County yield reflects management, soil, genetics, pests, and economics in addition to weather.",
            "All-production-practice yield is evaluated with a non-irrigated model assumption.",
            "Quick Stats suppresses some county estimates; missing rows are not treated as zero yield.",
        ],
    }


def markdown(report: dict) -> str:
    pooled = report["pooledWithinCropYear"]
    lines = [
        f"# {report['model']} nationwide observed-outcome validation", "",
        f"**Independent gate: {'PASS' if report['gate']['passed'] else 'NOT PASSED'}**", "",
        f"2018–2022 published county yields outside California, {pooled['observations']:,} observations. "
        f"Pooled within-crop-year Spearman: {pooled['spearman']:.3f} "
        f"(county-crop grouped-bootstrap 95% interval {pooled['bootstrap95'][0]:.3f} to {pooled['bootstrap95'][1]:.3f}).", "",
        "| Crop | Observations | Spearman | 95% interval | Median score |", "|---|---:|---:|---:|---:|",
    ]
    for item in report["perCrop"]:
        lines.append(f"| {item['crop']} | {item['observations']:,} | {item['spearman']:.3f} | {item['bootstrap95'][0]:.3f} to {item['bootstrap95'][1]:.3f} | {item['medianScore']:.1f} |")
    lines.extend(["", "| Year | Observations | Spearman | 95% interval |", "|---|---:|---:|---:|"])
    for item in report["perYear"]:
        lines.append(f"| {item['year']} | {item['observations']:,} | {item['spearman']:.3f} | {item['bootstrap95'][0]:.3f} to {item['bootstrap95'][1]:.3f} |")
    lines.extend([
        "", f"Gate rule: {report['gate']['rule']}.", "", f"Protocol timing: {report['protocol']}", "",
        "Passing would only justify a separate yield-calibration study. It would not make the current suitability score a yield forecast.", "", "## Limitations", "",
        *[f"- {item}" for item in report["limitations"]], "",
    ])
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/national-observed-validation-v0.4.json")
    args = parser.parse_args()
    report = validate(args.data, args.artifact, args.profiles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report["pooledWithinCropYear"] | report["gate"], indent=2))


if __name__ == "__main__":
    main()
