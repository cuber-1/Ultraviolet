from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

from .national_observed_validation import CROP_NAMES, YEARS
from .observed_validation import bootstrap_interval, county_points, number


def rows_from_quickstats(data: Path) -> list[dict]:
    points = county_points(data / "2022_Gaz_counties_national.zip", state=None)
    rows = []
    with (data / "quickstats-county-yield-2018-2022.tsv").open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            if row["STATE_ALPHA"] in {"AK", "CA", "HI", "PR"} or not row["COUNTY_CODE"].strip():
                continue
            observed = number(row["VALUE"])
            fips = f"{int(row['STATE_FIPS_CODE']):02d}{int(row['COUNTY_CODE']):03d}"
            if observed is None or fips not in points:
                continue
            latitude, longitude, county = points[fips]
            if not (24 <= latitude <= 50 and -125 <= longitude <= -66):
                continue
            rows.append({
                "year": int(row["YEAR"]), "crop": CROP_NAMES[row["COMMODITY_DESC"]],
                "fips": fips, "state": row["STATE_ALPHA"], "county": county,
                "latitude": latitude, "longitude": longitude, "yieldBushelsPerAcre": observed,
            })
    by_crop_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        by_crop_year[(row["crop"], row["year"])].append(row)
    for group in by_crop_year.values():
        percentiles = rankdata([row["yieldBushelsPerAcre"] for row in group], method="average") / len(group)
        for row, percentile in zip(group, percentiles, strict=True):
            row["yieldPercentileWithinCropYear"] = float(percentile)
    return rows


def temporal_validation(rows: list[dict]) -> dict:
    results = []
    all_actual, all_predicted, all_groups = [], [], []
    for test_year in YEARS[1:]:
        history: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in rows:
            if row["year"] < test_year:
                history[(row["crop"], row["fips"])].append(row["yieldPercentileWithinCropYear"])
        test_rows = [row for row in rows if row["year"] == test_year]
        covered = [row for row in test_rows if (row["crop"], row["fips"]) in history]
        actual = np.asarray([row["yieldPercentileWithinCropYear"] for row in covered])
        predicted = np.asarray([np.mean(history[(row["crop"], row["fips"])]) for row in covered])
        groups = np.asarray([f"{row['crop']}:{row['fips']}" for row in covered])
        per_crop = {}
        for crop in sorted(CROP_NAMES.values()):
            mask = np.asarray([row["crop"] == crop for row in covered])
            per_crop[crop] = {
                "observations": int(mask.sum()),
                "spearman": round(float(spearmanr(predicted[mask], actual[mask]).statistic), 4),
            }
        results.append({
            "year": test_year, "observations": len(test_rows), "covered": len(covered),
            "coverage": round(len(covered) / len(test_rows), 4),
            "spearman": round(float(spearmanr(predicted, actual).statistic), 4),
            "bootstrap95": list(bootstrap_interval(predicted, actual, groups)),
            "maePercentile": round(float(np.mean(np.abs(predicted - actual))), 4),
            "perCrop": per_crop,
        })
        all_actual.extend(actual); all_predicted.extend(predicted); all_groups.extend(groups)
    actual = np.asarray(all_actual); predicted = np.asarray(all_predicted); groups = np.asarray(all_groups)
    return {
        "method": "For each test year, average only earlier within-crop/year county percentiles; no future year enters its prediction.",
        "years": results,
        "pooled": {
            "observations": len(actual), "spearman": round(float(spearmanr(predicted, actual).statistic), 4),
            "bootstrap95": list(bootstrap_interval(predicted, actual, groups)),
            "maePercentile": round(float(np.mean(np.abs(predicted - actual))), 4),
        },
    }


def build_atlas(rows: list[dict], validation: dict) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["crop"], row["fips"])].append(row)
    records = []
    for (crop, fips), items in sorted(groups.items()):
        percentiles = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        yields = np.asarray([item["yieldBushelsPerAcre"] for item in items])
        last = max(items, key=lambda item: item["year"])
        records.append({
            "crop": crop, "fips": fips, "state": last["state"], "county": last["county"],
            "latitude": last["latitude"], "longitude": last["longitude"],
            "years": sorted(item["year"] for item in items), "observations": len(items),
            "meanPercentile": round(float(np.mean(percentiles)), 4),
            "p10Percentile": round(float(np.quantile(percentiles, .1)), 4),
            "p90Percentile": round(float(np.quantile(percentiles, .9)), 4),
            "meanYieldBushelsPerAcre": round(float(np.mean(yields)), 2),
            "latest": {"year": last["year"], "yieldBushelsPerAcre": last["yieldBushelsPerAcre"]},
        })
    return {
        "name": "USDA county yield atlas v1", "evidenceGrade": "historical-county-context",
        "scope": "contiguous U.S. counties excluding California; corn, soybean, and wheat; 2018–2022",
        "source": "USDA NASS Quick Stats published county yields",
        "crops": sorted(CROP_NAMES.values()), "years": list(YEARS), "records": records,
        "validation": validation["pooled"],
        "disclaimer": "Historical county context, not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }


def markdown(validation: dict, atlas: dict) -> str:
    lines = [
        "# USDA county yield atlas v1 validation", "",
        "The atlas stores each county's historical percentile within crop and year. The retrospective forward-year test predicts each year using only earlier years for that county.", "",
        "| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for item in validation["years"]:
        lines.append(f'| {item["year"]} | {item["covered"]:,} / {item["observations"]:,} | {item["coverage"]:.1%} | {item["spearman"]:.3f} | {item["bootstrap95"][0]:.3f} to {item["bootstrap95"][1]:.3f} | {item["maePercentile"]:.3f} |')
    pooled = validation["pooled"]
    lines += [
        "", f'Pooled forward-year Spearman: **{pooled["spearman"]:.3f}** over {pooled["observations"]:,} covered observations (95% interval {pooled["bootstrap95"][0]:.3f} to {pooled["bootstrap95"][1]:.3f}).',
        "", f'The production atlas contains {len(atlas["records"]):,} county-crop records. It is a descriptive historical prior, not a trained yield forecast.',
        "", "> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.", "",
    ]
    return "\n".join(lines)


def plot(validation: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    years = [item["year"] for item in validation["years"]]
    correlations = [item["spearman"] for item in validation["years"]]
    coverage = [item["coverage"] * 100 for item in validation["years"]]
    figure, left = plt.subplots(figsize=(10, 5.6)); right = left.twinx()
    bars = left.bar(years, correlations, color="#315d49", width=.58, label="forward-year Spearman")
    left.bar_label(bars, fmt="%.3f", padding=4); left.set(ylim=(0, 1), ylabel="Spearman correlation", xlabel="test year", xticks=years)
    right.plot(years, coverage, color="#d98352", marker="o", linewidth=2, label="coverage")
    right.set(ylim=(0, 105), ylabel="published rows with prior history (%)")
    left.set_title("USDA county yield atlas · forward-year validation"); left.grid(axis="y", alpha=.18)
    handles = [*left.get_legend_handles_labels()[0], *right.get_legend_handles_labels()[0]]
    labels = [*left.get_legend_handles_labels()[1], *right.get_legend_handles_labels()[1]]
    left.legend(handles, labels, loc="lower right")
    figure.text(.5, .01, "Historical county context · corn, soybean, wheat · not a parcel yield forecast", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


@lru_cache(maxsize=4)
def load_atlas(path: str) -> dict:
    return json.loads(Path(path).read_text())


def haversine_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a); delta_lambda = math.radians(longitude_b - longitude_a)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def nearest_evidence(crop: str, latitude: float, longitude: float, path: Path, max_distance_km: float = 100.0) -> dict | None:
    atlas = load_atlas(str(path.resolve()))
    crop_key = {"maize": "corn", "soybeans": "soybean", "winter wheat": "wheat"}.get(crop.strip().lower(), crop.strip().lower())
    candidates = [record for record in atlas["records"] if record["crop"] == crop_key]
    if not candidates:
        return None
    record = min(candidates, key=lambda item: haversine_km(latitude, longitude, item["latitude"], item["longitude"]))
    distance = haversine_km(latitude, longitude, record["latitude"], record["longitude"])
    if distance > max_distance_km:
        return None
    return {
        **record, "distanceKm": round(distance, 1), "evidenceGrade": atlas["evidenceGrade"],
        "source": atlas["source"], "disclaimer": atlas["disclaimer"],
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-v1.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-validation-v1.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/yield-atlas-validation-v1.png")
    args = parser.parse_args()
    rows = rows_from_quickstats(args.data); validation = temporal_validation(rows); atlas = build_atlas(rows, validation)
    args.atlas.write_text(json.dumps(atlas, separators=(",", ":")) + "\n")
    args.validation.write_text(json.dumps(validation, indent=2) + "\n")
    args.validation.with_suffix(".md").write_text(markdown(validation, atlas))
    plot(validation, args.plot)
    print(json.dumps({"records": len(atlas["records"]), **validation["pooled"]}, indent=2))


if __name__ == "__main__":
    main()
