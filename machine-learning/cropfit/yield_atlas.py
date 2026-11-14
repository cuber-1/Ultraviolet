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
from sklearn.neighbors import BallTree

from .national_observed_validation import CROP_NAMES
from .observed_validation import bootstrap_interval, county_points, number

YEARS = tuple(range(2010, 2026))
LEGACY_YEARS = tuple(range(2018, 2026))
CALIBRATION_END_YEAR = 2017
UNCERTAINTY_TEST_YEARS = tuple(range(2018, 2026))


def rows_from_quickstats(data: Path) -> list[dict]:
    points = county_points(data / "2022_Gaz_counties_national.zip", state=None)
    rows = []
    with (data / "quickstats-county-yield-2010-2025.tsv").open(newline="", encoding="utf-8") as source:
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


def forward_examples(rows: list[dict], years: tuple[int, ...], history_start: int) -> tuple[list[dict], dict[int, int]]:
    examples = []
    published = {}
    for test_year in years[1:]:
        history: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in rows:
            if history_start <= row["year"] < test_year:
                history[(row["crop"], row["fips"])].append(row["yieldPercentileWithinCropYear"])
        test_rows = [row for row in rows if row["year"] == test_year]
        published[test_year] = len(test_rows)
        for row in test_rows:
            values = history.get((row["crop"], row["fips"]), [])
            if values:
                examples.append({
                    **row,
                    "prediction": float(np.mean(values)),
                    "historyCount": len(values),
                    "absoluteError": abs(float(np.mean(values)) - row["yieldPercentileWithinCropYear"]),
                })
    return examples, published


def point_summary(examples: list[dict], with_interval: bool = True) -> dict:
    actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in examples])
    predicted = np.asarray([item["prediction"] for item in examples])
    result = {
        "observations": len(examples),
        "spearman": round(float(spearmanr(predicted, actual).statistic), 4),
        "maePercentile": round(float(np.mean(np.abs(predicted - actual))), 4),
    }
    if with_interval:
        groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in examples])
        result["bootstrap95"] = list(bootstrap_interval(predicted, actual, groups))
    return result


def temporal_validation(rows: list[dict]) -> dict:
    examples, published = forward_examples(rows, YEARS, YEARS[0])
    results = []
    for test_year in YEARS[1:]:
        covered = [item for item in examples if item["year"] == test_year]
        summary = point_summary(covered)
        per_crop = {}
        for crop in sorted(CROP_NAMES.values()):
            crop_examples = [item for item in covered if item["crop"] == crop]
            per_crop[crop] = point_summary(crop_examples, with_interval=False)
        results.append({
            "year": test_year, "observations": published[test_year], "covered": len(covered),
            "coverage": round(len(covered) / published[test_year], 4),
            **{key: value for key, value in summary.items() if key != "observations"},
            "perCrop": per_crop,
        })
    return {
        "method": "For each test year, average only earlier within-crop/year county percentiles; no future year enters its prediction.",
        "years": results,
        "pooled": point_summary(examples),
    }


def history_window_comparison(rows: list[dict]) -> dict:
    extended, extended_published = forward_examples(rows, LEGACY_YEARS, YEARS[0])
    legacy, _ = forward_examples(rows, LEGACY_YEARS, LEGACY_YEARS[0])
    legacy_by_key = {(item["year"], item["crop"], item["fips"]): item for item in legacy}
    common_extended = [item for item in extended if (item["year"], item["crop"], item["fips"]) in legacy_by_key]
    common_legacy = [legacy_by_key[(item["year"], item["crop"], item["fips"])] for item in common_extended]
    extended_summary = point_summary(common_extended)
    legacy_summary = point_summary(common_legacy)
    per_year = []
    for year in LEGACY_YEARS[1:]:
        extended_year = [item for item in common_extended if item["year"] == year]
        legacy_year = [item for item in common_legacy if item["year"] == year]
        per_year.append({
            "year": year,
            "extended": point_summary(extended_year, with_interval=False),
            "legacy": point_summary(legacy_year, with_interval=False),
        })
    passed = (
        extended_summary["spearman"] > legacy_summary["spearman"]
        and extended_summary["maePercentile"] < legacy_summary["maePercentile"]
        and len(extended) >= len(legacy)
    )
    return {
        "testYears": list(LEGACY_YEARS[1:]),
        "comparisonRows": len(common_extended),
        "publishedRows": sum(extended_published.values()),
        "extendedHistory": {"years": list(YEARS), "covered": len(extended), **extended_summary},
        "legacyHistory": {"years": list(LEGACY_YEARS), "covered": len(legacy), **legacy_summary},
        "perYear": per_year,
        "gate": {
            "passed": passed,
            "rule": "On identical 2019–2025 rows, 2010–2025 history must improve pooled Spearman and percentile MAE; extended coverage must not decrease.",
        },
    }


def history_bucket(count: int) -> str:
    return "1" if count == 1 else "2-3" if count <= 3 else "4+"


def conformal_quantile(values: list[float], probability: float) -> float:
    ordered = np.sort(np.asarray(values, dtype=float))
    rank = min(len(ordered), math.ceil((len(ordered) + 1) * probability))
    return float(ordered[rank - 1])


def uncertainty_calibration(rows: list[dict]) -> tuple[dict, dict[tuple[str, str], dict]]:
    examples, _ = forward_examples(rows, YEARS, YEARS[0])
    calibration = [item for item in examples if item["year"] <= CALIBRATION_END_YEAR]
    test = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in calibration:
        grouped[(item["crop"], history_bucket(item["historyCount"]))].append(item["absoluteError"])
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }

    def scored(items: list[dict]) -> dict:
        hits80, hits90, widths80, widths90 = [], [], [], []
        for item in items:
            calibration_item = table[(item["crop"], history_bucket(item["historyCount"]))]
            intervals = []
            for key in ("absoluteErrorP80", "absoluteErrorP90"):
                radius = calibration_item[key]
                intervals.append((max(0.0, item["prediction"] - radius), min(1.0, item["prediction"] + radius)))
            actual = item["yieldPercentileWithinCropYear"]
            hits80.append(intervals[0][0] <= actual <= intervals[0][1])
            hits90.append(intervals[1][0] <= actual <= intervals[1][1])
            widths80.append(intervals[0][1] - intervals[0][0]); widths90.append(intervals[1][1] - intervals[1][0])
        return {
            "observations": len(items),
            "coverage80": round(float(np.mean(hits80)), 4),
            "coverage90": round(float(np.mean(hits90)), 4),
            "meanWidth80": round(float(np.mean(widths80)), 4),
            "meanWidth90": round(float(np.mean(widths90)), 4),
        }

    per_year = [{"year": year, **scored([item for item in test if item["year"] == year])} for year in UNCERTAINTY_TEST_YEARS]
    per_crop = [{"crop": crop, **scored([item for item in test if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    pooled = scored(test)
    passed = (
        .77 <= pooled["coverage80"] <= .85
        and .87 <= pooled["coverage90"] <= .94
        and pooled["meanWidth90"] <= .55
        and all(item["coverage90"] >= .85 for item in per_crop)
    )
    report = {
        "method": "Crop- and history-count-conditional split conformal absolute-error intervals around the earlier-year county mean.",
        "calibrationYears": list(range(YEARS[1], CALIBRATION_END_YEAR + 1)),
        "testYears": list(UNCERTAINTY_TEST_YEARS),
        "calibrationExamples": len(calibration),
        "groups": [table[key] for key in sorted(table)],
        "pooled": pooled, "perYear": per_year, "perCrop": per_crop,
        "gate": {
            "passed": passed,
            "rule": "2018–2025 pooled coverage must be 77–85% for the 80% interval and 87–94% for the 90% interval; mean 90% width <= 0.55; every crop >= 85% 90%-interval coverage.",
        },
    }
    return report, table


def build_atlas(rows: list[dict], validation: dict, comparison: dict, uncertainty: dict, calibration_table: dict[tuple[str, str], dict]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["crop"], row["fips"])].append(row)
    records = []
    for (crop, fips), items in sorted(groups.items()):
        items = sorted(items, key=lambda item: item["year"])
        percentiles = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        yields = np.asarray([item["yieldBushelsPerAcre"] for item in items])
        last = max(items, key=lambda item: item["year"])
        calibration = calibration_table[(crop, history_bucket(len(items)))]
        expected = float(np.mean(percentiles))
        interval80 = [max(0.0, expected - calibration["absoluteErrorP80"]), min(1.0, expected + calibration["absoluteErrorP80"])]
        interval90 = [max(0.0, expected - calibration["absoluteErrorP90"]), min(1.0, expected + calibration["absoluteErrorP90"])]
        records.append({
            "crop": crop, "fips": fips, "state": last["state"], "county": last["county"],
            "latitude": last["latitude"], "longitude": last["longitude"],
            "years": sorted(item["year"] for item in items), "observations": len(items),
            "meanPercentile": round(float(np.mean(percentiles)), 4),
            "p10Percentile": round(float(np.quantile(percentiles, .1)), 4),
            "p90Percentile": round(float(np.quantile(percentiles, .9)), 4),
            "meanYieldBushelsPerAcre": round(float(np.mean(yields)), 2),
            "observedYieldPrior": {
                "expectedPercentile": round(expected, 4),
                "interval80": [round(value, 4) for value in interval80],
                "interval90": [round(value, 4) for value in interval90],
                "historyBucket": history_bucket(len(items)),
                "calibrationExamples": calibration["examples"],
            },
            "history": [{
                "year": item["year"], "yieldBushelsPerAcre": item["yieldBushelsPerAcre"],
                "percentile": round(item["yieldPercentileWithinCropYear"], 4),
            } for item in items],
            "latest": {"year": last["year"], "yieldBushelsPerAcre": last["yieldBushelsPerAcre"]},
        })
    return {
        "name": "USDA county yield atlas v2", "evidenceGrade": "observed-county-prior",
        "scope": "contiguous U.S. counties excluding California; corn, soybean, and wheat; 2010–2025",
        "source": "USDA NASS Quick Stats published county yields",
        "crops": sorted(CROP_NAMES.values()), "years": list(YEARS), "records": records,
        "validation": validation["pooled"],
        "historyWindowComparison": comparison,
        "uncertaintyValidation": uncertainty,
        "disclaimer": "Observed county prior with retrospectively calibrated uncertainty; not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }


def markdown(validation: dict, comparison: dict, uncertainty: dict, atlas: dict) -> str:
    lines = [
        "# USDA county yield atlas v2 validation", "",
        "The atlas stores each county's historical percentile within crop and year. The retrospective forward-year test predicts each year using only earlier years for that county.", "",
        "| Test year | Covered / published | Coverage | Spearman | Grouped 95% interval | Percentile MAE |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for item in validation["years"]:
        lines.append(f'| {item["year"]} | {item["covered"]:,} / {item["observations"]:,} | {item["coverage"]:.1%} | {item["spearman"]:.3f} | {item["bootstrap95"][0]:.3f} to {item["bootstrap95"][1]:.3f} | {item["maePercentile"]:.3f} |')
    pooled = validation["pooled"]
    extended = comparison["extendedHistory"]; legacy = comparison["legacyHistory"]; intervals = uncertainty["pooled"]
    lines += [
        "", f'Pooled forward-year Spearman: **{pooled["spearman"]:.3f}** over {pooled["observations"]:,} covered observations (95% interval {pooled["bootstrap95"][0]:.3f} to {pooled["bootstrap95"][1]:.3f}).',
        "", "## Fixed-window comparison", "",
        f'On the same {comparison["comparisonRows"]:,} 2019–2025 county-year rows, extending history from 2018 back to 2010 changed Spearman from **{legacy["spearman"]:.3f}** to **{extended["spearman"]:.3f}** and percentile MAE from **{legacy["maePercentile"]:.3f}** to **{extended["maePercentile"]:.3f}**. Gate: **{"PASS" if comparison["gate"]["passed"] else "NOT PASSED"}**.',
        "", "## Calibrated uncertainty", "",
        f'The interval calibrator uses only 2011–2017 forward errors. On 2018–2025, the nominal 80% interval covered **{intervals["coverage80"]:.1%}** and the nominal 90% interval covered **{intervals["coverage90"]:.1%}** of {intervals["observations"]:,} later outcomes. Mean 90% interval width was {intervals["meanWidth90"]:.3f} percentile units. Gate: **{"PASS" if uncertainty["gate"]["passed"] else "NOT PASSED"}**.',
        "", f'The production atlas contains {len(atlas["records"]):,} county-crop records. It is an observed historical prior with calibrated uncertainty, not a parcel yield forecast.',
        "", "> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.", "",
    ]
    return "\n".join(lines)


def plot(comparison: dict, uncertainty: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    years = [item["year"] for item in comparison["perYear"]]
    extended = [item["extended"]["spearman"] for item in comparison["perYear"]]
    legacy = [item["legacy"]["spearman"] for item in comparison["perYear"]]
    interval_years = [item["year"] for item in uncertainty["perYear"]]
    coverage80 = [item["coverage80"] * 100 for item in uncertainty["perYear"]]
    coverage90 = [item["coverage90"] * 100 for item in uncertainty["perYear"]]
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    axes[0].plot(years, extended, marker="o", linewidth=2.5, color="#315d49", label="16-year history")
    axes[0].plot(years, legacy, marker="o", linewidth=2, color="#d98352", linestyle="--", label="8-year history")
    axes[0].set(ylim=(.65, .9), ylabel="Spearman correlation", xlabel="test year", xticks=years, title="Same future rows · longer history")
    axes[0].grid(alpha=.18); axes[0].legend(loc="lower right")
    axes[0].text(.02, .04, f'Pooled ρ {comparison["extendedHistory"]["spearman"]:.3f} vs {comparison["legacyHistory"]["spearman"]:.3f}\nMAE {comparison["extendedHistory"]["maePercentile"]:.3f} vs {comparison["legacyHistory"]["maePercentile"]:.3f}', transform=axes[0].transAxes, fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 6})
    axes[1].plot(interval_years, coverage80, marker="o", linewidth=2.2, color="#557f2d", label="80% interval")
    axes[1].plot(interval_years, coverage90, marker="o", linewidth=2.2, color="#315d49", label="90% interval")
    axes[1].axhline(80, color="#557f2d", alpha=.4, linestyle=":"); axes[1].axhline(90, color="#315d49", alpha=.4, linestyle=":")
    axes[1].set(ylim=(65, 100), ylabel="observed coverage (%)", xlabel="test year", xticks=interval_years, title="Intervals calibrated on 2011–2017 only")
    axes[1].grid(alpha=.18); axes[1].legend(loc="lower right")
    axes[1].text(.02, .04, f'Pooled coverage\n80% band: {uncertainty["pooled"]["coverage80"]:.1%}\n90% band: {uncertainty["pooled"]["coverage90"]:.1%}', transform=axes[1].transAxes, fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 6})
    figure.suptitle("USDA observed-yield prior v2 · temporal validation", fontweight="bold")
    figure.text(.5, .01, "County-level corn, soybean, wheat · not a parcel yield forecast", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


@lru_cache(maxsize=4)
def load_atlas(path: str) -> dict:
    return json.loads(Path(path).read_text())


def haversine_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a); delta_lambda = math.radians(longitude_b - longitude_a)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@lru_cache(maxsize=4)
def atlas_spatial_index(path: str) -> dict[str, tuple[tuple[dict, ...], BallTree]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in load_atlas(path)["records"]:
        grouped[record["crop"]].append(record)
    return {
        crop: (
            tuple(records),
            BallTree(np.radians([[record["latitude"], record["longitude"]] for record in records]), metric="haversine"),
        )
        for crop, records in grouped.items()
    }


def nearest_evidence(crop: str, latitude: float, longitude: float, path: Path, max_distance_km: float = 100.0) -> dict | None:
    resolved = str(path.resolve())
    atlas = load_atlas(resolved)
    crop_key = {"maize": "corn", "soybeans": "soybean", "winter wheat": "wheat"}.get(crop.strip().lower(), crop.strip().lower())
    indexed = atlas_spatial_index(resolved).get(crop_key)
    if indexed is None:
        return None
    records, tree = indexed
    distances, indices = tree.query(np.radians([[latitude, longitude]]), k=1)
    record = records[int(indices[0, 0])]
    distance = float(distances[0, 0] * 6371.0)
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
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-v2.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-validation-v2.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/yield-atlas-validation-v2.png")
    args = parser.parse_args()
    rows = rows_from_quickstats(args.data)
    validation = temporal_validation(rows)
    comparison = history_window_comparison(rows)
    uncertainty, calibration_table = uncertainty_calibration(rows)
    atlas = build_atlas(rows, validation, comparison, uncertainty, calibration_table)
    args.atlas.write_text(json.dumps(atlas, separators=(",", ":")) + "\n")
    report = {"temporalValidation": validation, "historyWindowComparison": comparison, "uncertaintyValidation": uncertainty}
    args.validation.write_text(json.dumps(report, indent=2) + "\n")
    args.validation.with_suffix(".md").write_text(markdown(validation, comparison, uncertainty, atlas))
    plot(comparison, uncertainty, args.plot)
    print(json.dumps({
        "records": len(atlas["records"]),
        "temporal": validation["pooled"],
        "historyGate": comparison["gate"],
        "uncertainty": uncertainty["pooled"],
        "uncertaintyGate": uncertainty["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
