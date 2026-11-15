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
PRIOR_RECENCY_HALF_LIFE_YEARS = 3.0
PRIOR_RECENCY_WEIGHT = 0.8
SPATIAL_TRANSFER_MAX_DISTANCE_KM = 100.0


def observed_prior_prediction(
    history: list[dict],
    prediction_year: int,
    half_life_years: float = PRIOR_RECENCY_HALF_LIFE_YEARS,
    recency_weight: float = PRIOR_RECENCY_WEIGHT,
) -> float:
    """Shrink a recency-weighted county prior toward its stable long-history mean."""
    values = np.asarray([item["yieldPercentileWithinCropYear"] for item in history], dtype=float)
    ages = np.asarray([prediction_year - item["year"] for item in history], dtype=float)
    if not len(values) or np.any(ages <= 0):
        raise ValueError("Observed-prior history must precede the prediction year.")
    baseline = float(np.mean(values))
    recency = float(np.average(values, weights=np.power(.5, ages / half_life_years)))
    return (1 - recency_weight) * baseline + recency_weight * recency


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
        history: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            if history_start <= row["year"] < test_year:
                history[(row["crop"], row["fips"])].append(row)
        test_rows = [row for row in rows if row["year"] == test_year]
        published[test_year] = len(test_rows)
        for row in test_rows:
            values = history.get((row["crop"], row["fips"]), [])
            if values:
                prediction = observed_prior_prediction(values, test_year)
                examples.append({
                    **row,
                    "prediction": prediction,
                    "historyCount": len(values),
                    "absoluteError": abs(prediction - row["yieldPercentileWithinCropYear"]),
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
        "method": "For each test year, blend an exponential recency estimate with the long-history county mean using only earlier within-crop/year percentiles; no future year enters its prediction.",
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


def distance_bucket(distance_km: float) -> str:
    return "0-25" if distance_km <= 25 else "25-50" if distance_km <= 50 else "50-100"


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
        "method": "Crop- and history-count-conditional split conformal absolute-error intervals around the shrunken recency prior.",
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


def spatial_transfer_validation(rows: list[dict]) -> tuple[dict, dict[tuple[str, str, str], dict]]:
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for items in histories.values():
        items.sort(key=lambda item: item["year"])

    examples = []
    eligible = 0
    for test_year in YEARS[1:]:
        for crop in sorted(CROP_NAMES.values()):
            sources = []
            for (source_crop, fips), items in histories.items():
                if source_crop != crop:
                    continue
                earlier = [item for item in items if item["year"] < test_year]
                if earlier:
                    latest = earlier[-1]
                    sources.append({
                        "fips": fips, "latitude": latest["latitude"], "longitude": latest["longitude"],
                        "prediction": observed_prior_prediction(earlier, test_year), "historyCount": len(earlier),
                    })
            targets = [row for row in rows if row["year"] == test_year and row["crop"] == crop]
            if len(sources) < 2 or not targets:
                continue
            tree = BallTree(np.radians([[item["latitude"], item["longitude"]] for item in sources]), metric="haversine")
            distances, indices = tree.query(
                np.radians([[item["latitude"], item["longitude"]] for item in targets]),
                k=min(3, len(sources)),
            )
            for target, target_distances, target_indices in zip(targets, distances, indices, strict=True):
                source = None
                distance = None
                for candidate_distance, candidate_index in zip(target_distances, target_indices, strict=True):
                    candidate = sources[int(candidate_index)]
                    if candidate["fips"] != target["fips"]:
                        source = candidate
                        distance = float(candidate_distance * 6371.0)
                        break
                if source is None or distance is None:
                    continue
                eligible += 1
                if distance > SPATIAL_TRANSFER_MAX_DISTANCE_KM:
                    continue
                prediction = source["prediction"]
                examples.append({
                    **target, "prediction": prediction, "sourceFips": source["fips"],
                    "sourceHistoryCount": source["historyCount"], "distanceKm": distance,
                    "distanceBucket": distance_bucket(distance),
                    "absoluteError": abs(prediction - target["yieldPercentileWithinCropYear"]),
                })

    calibration = [item for item in examples if item["year"] <= CALIBRATION_END_YEAR]
    test = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for item in calibration:
        grouped[(item["crop"], history_bucket(item["sourceHistoryCount"]), item["distanceBucket"])].append(item["absoluteError"])
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "distanceBucket": key[2], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }

    def scored(items: list[dict]) -> dict:
        hits80, hits90, widths80, widths90 = [], [], [], []
        for item in items:
            calibration_item = table[(item["crop"], history_bucket(item["sourceHistoryCount"]), item["distanceBucket"])]
            prediction = item["prediction"]
            actual = item["yieldPercentileWithinCropYear"]
            intervals = []
            for key in ("absoluteErrorP80", "absoluteErrorP90"):
                radius = calibration_item[key]
                intervals.append((max(0.0, prediction - radius), min(1.0, prediction + radius)))
            hits80.append(intervals[0][0] <= actual <= intervals[0][1])
            hits90.append(intervals[1][0] <= actual <= intervals[1][1])
            widths80.append(intervals[0][1] - intervals[0][0]); widths90.append(intervals[1][1] - intervals[1][0])
        return {
            "observations": len(items), "coverage80": round(float(np.mean(hits80)), 4),
            "coverage90": round(float(np.mean(hits90)), 4), "meanWidth80": round(float(np.mean(widths80)), 4),
            "meanWidth90": round(float(np.mean(widths90)), 4),
        }

    final = [item for item in examples if item["year"] in (2023, 2024, 2025)]
    final_summary = point_summary(final)
    per_crop_signal = [{"crop": crop, **point_summary([item for item in final if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    pooled_uncertainty = scored(test)
    per_crop_uncertainty = [{"crop": crop, **scored([item for item in test if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    per_distance = [{"distanceBucket": bucket, **scored([item for item in test if item["distanceBucket"] == bucket])} for bucket in ("0-25", "25-50", "50-100")]
    covered = len(examples) / eligible
    passed = (
        len(final) >= 8_000 and covered >= .99 and final_summary["spearman"] >= .65
        and final_summary["bootstrap95"][0] > .60 and all(item["spearman"] >= .65 for item in per_crop_signal)
        and .80 <= pooled_uncertainty["coverage80"] <= .87 and .88 <= pooled_uncertainty["coverage90"] <= .94
        and pooled_uncertainty["meanWidth90"] <= .65
        and all(item["coverage90"] >= .88 for item in per_crop_uncertainty)
    )
    report = {
        "method": "For each target county-year, exclude that county and use the nearest different county's prior built only from earlier years.",
        "maxDistanceKm": SPATIAL_TRANSFER_MAX_DISTANCE_KM,
        "eligibleExamples": eligible, "coveredExamples": len(examples), "coverage": round(covered, 4),
        "calibrationYears": list(range(YEARS[1], CALIBRATION_END_YEAR + 1)),
        "testYears": list(UNCERTAINTY_TEST_YEARS), "finalTestYears": [2023, 2024, 2025],
        "groups": [table[key] for key in sorted(table)],
        "finalSignal": final_summary, "perCropFinalSignal": per_crop_signal,
        "uncertainty": {"pooled": pooled_uncertainty, "perCrop": per_crop_uncertainty, "perDistance": per_distance},
        "gate": {
            "passed": passed,
            "rule": "Nearest-different-county coverage within 100 km >=99%; final N >=8,000, Spearman >=0.65 with bootstrap lower >0.60 and every crop >=0.65; test coverage 80-87%/88-94%, mean 90% width <=0.65, every crop >=88% 90%-coverage.",
        },
        "interpretation": "Validates regional county-prior transfer and its uncertainty, not parcel yield, revenue, or purchase returns.",
    }
    return report, table


def build_atlas(rows: list[dict], validation: dict, comparison: dict, uncertainty: dict, calibration_table: dict[tuple[str, str], dict], spatial_transfer: dict) -> dict:
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
        expected = observed_prior_prediction(items, YEARS[-1] + 1)
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
        "name": "USDA county yield atlas v4", "evidenceGrade": "observed-county-prior",
        "scope": "contiguous U.S. counties excluding California; corn, soybean, and wheat; 2010–2025",
        "source": "USDA NASS Quick Stats published county yields",
        "predictionMethod": {
            "name": "shrunken exponential recency prior",
            "forecastYear": YEARS[-1] + 1,
            "halfLifeYears": PRIOR_RECENCY_HALF_LIFE_YEARS,
            "recencyWeight": PRIOR_RECENCY_WEIGHT,
            "longHistoryWeight": round(1 - PRIOR_RECENCY_WEIGHT, 10),
        },
        "crops": sorted(CROP_NAMES.values()), "years": list(YEARS), "records": records,
        "validation": validation["pooled"],
        "historyWindowComparison": comparison,
        "uncertaintyValidation": uncertainty,
        "spatialTransferValidation": spatial_transfer,
        "disclaimer": "Observed nearest-county prior with retrospectively calibrated temporal and spatial-transfer uncertainty; not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }


def markdown(validation: dict, comparison: dict, uncertainty: dict, spatial_transfer: dict, atlas: dict) -> str:
    lines = [
        "# USDA county yield atlas v4 validation", "",
        "The atlas stores each county's historical percentile within crop and year. Its production prior blends 80% three-year-half-life recency weighting with 20% of the stable long-history mean. The retrospective forward-year test predicts each year using only earlier years for that county.", "",
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
        "", "## Spatial transfer", "",
        f'In the leave-one-county-out test, {spatial_transfer["coveredExamples"]:,} of {spatial_transfer["eligibleExamples"]:,} target county-years had another reporting county within 100 km ({spatial_transfer["coverage"]:.1%}). On locked 2023–2025 outcomes, nearest-county transfer reached Spearman **{spatial_transfer["finalSignal"]["spearman"]:.3f}** over {spatial_transfer["finalSignal"]["observations"]:,} outcomes (95% interval {spatial_transfer["finalSignal"]["bootstrap95"][0]:.3f} to {spatial_transfer["finalSignal"]["bootstrap95"][1]:.3f}).',
        f'Transfer intervals calibrated on 2011–2017 covered **{spatial_transfer["uncertainty"]["pooled"]["coverage80"]:.1%}** and **{spatial_transfer["uncertainty"]["pooled"]["coverage90"]:.1%}** on 2018–2025. Gate: **{"PASS" if spatial_transfer["gate"]["passed"] else "NOT PASSED"}**.',
        "", f'The production atlas contains {len(atlas["records"]):,} county-crop records. It is an observed historical prior with calibrated temporal and spatial-transfer uncertainty, not a parcel yield forecast.',
        "", "> County averages combine weather, soil, genetics, management, reporting, and economics. They must not be interpreted as parcel-specific production or investment advice.", "",
    ]
    return "\n".join(lines)


def plot(comparison: dict, uncertainty: dict, spatial_transfer: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    years = [item["year"] for item in comparison["perYear"]]
    extended = [item["extended"]["spearman"] for item in comparison["perYear"]]
    legacy = [item["legacy"]["spearman"] for item in comparison["perYear"]]
    interval_years = [item["year"] for item in uncertainty["perYear"]]
    coverage80 = [item["coverage80"] * 100 for item in uncertainty["perYear"]]
    coverage90 = [item["coverage90"] * 100 for item in uncertainty["perYear"]]
    figure, axes = plt.subplots(1, 3, figsize=(19, 5.6))
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
    transfer = spatial_transfer["uncertainty"]["perCrop"]
    positions = np.arange(len(transfer)); width = .34
    axes[2].bar(positions - width / 2, [item["coverage80"] * 100 for item in transfer], width, color="#557f2d", label="80% interval")
    axes[2].bar(positions + width / 2, [item["coverage90"] * 100 for item in transfer], width, color="#315d49", label="90% interval")
    axes[2].axhline(80, color="#557f2d", alpha=.4, linestyle=":"); axes[2].axhline(90, color="#315d49", alpha=.4, linestyle=":")
    axes[2].set(xticks=positions, xticklabels=[item["crop"] for item in transfer], ylim=(70, 100), ylabel="observed coverage (%)", title="Nearest-county transfer bands")
    axes[2].grid(axis="y", alpha=.18); axes[2].legend(loc="lower right")
    axes[2].text(.02, .04, f'2023–2025 transfer ρ {spatial_transfer["finalSignal"]["spearman"]:.3f}\nN {spatial_transfer["finalSignal"]["observations"]:,} · gate {"PASS" if spatial_transfer["gate"]["passed"] else "NOT PASSED"}', transform=axes[2].transAxes, fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 6})
    figure.suptitle("USDA observed-yield prior v4 · temporal and spatial validation", fontweight="bold")
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


def nearest_evidence(crop: str, latitude: float, longitude: float, path: Path, max_distance_km: float = SPATIAL_TRANSFER_MAX_DISTANCE_KM) -> dict | None:
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
    prior = dict(record.get("observedYieldPrior", {}))
    transfer = atlas.get("spatialTransferValidation", {})
    bucket = distance_bucket(distance)
    calibration = next((item for item in transfer.get("groups", []) if (
        item["crop"] == crop_key and item["historyBucket"] == history_bucket(record["observations"])
        and item["distanceBucket"] == bucket
    )), None)
    if calibration and prior:
        expected = prior["expectedPercentile"]
        prior.update({
            "interval80": [round(max(0.0, expected - calibration["absoluteErrorP80"]), 4), round(min(1.0, expected + calibration["absoluteErrorP80"]), 4)],
            "interval90": [round(max(0.0, expected - calibration["absoluteErrorP90"]), 4), round(min(1.0, expected + calibration["absoluteErrorP90"]), 4)],
            "intervalMethod": "spatial-transfer-conformal", "distanceBucket": bucket,
            "calibrationExamples": calibration["examples"],
        })
    return {
        **record, "observedYieldPrior": prior, "distanceKm": round(distance, 1), "evidenceGrade": atlas["evidenceGrade"],
        "source": atlas["source"], "disclaimer": atlas["disclaimer"],
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-v4.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-validation-v4.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/yield-atlas-validation-v4.png")
    args = parser.parse_args()
    rows = rows_from_quickstats(args.data)
    validation = temporal_validation(rows)
    comparison = history_window_comparison(rows)
    uncertainty, calibration_table = uncertainty_calibration(rows)
    spatial_transfer, _ = spatial_transfer_validation(rows)
    atlas = build_atlas(rows, validation, comparison, uncertainty, calibration_table, spatial_transfer)
    args.atlas.write_text(json.dumps(atlas, separators=(",", ":")) + "\n")
    report = {"temporalValidation": validation, "historyWindowComparison": comparison, "uncertaintyValidation": uncertainty, "spatialTransferValidation": spatial_transfer}
    args.validation.write_text(json.dumps(report, indent=2) + "\n")
    args.validation.with_suffix(".md").write_text(markdown(validation, comparison, uncertainty, spatial_transfer, atlas))
    plot(comparison, uncertainty, spatial_transfer, args.plot)
    print(json.dumps({
        "records": len(atlas["records"]),
        "temporal": validation["pooled"],
        "historyGate": comparison["gate"],
        "uncertainty": uncertainty["pooled"],
        "uncertaintyGate": uncertainty["gate"],
        "spatialTransfer": {"coverage": spatial_transfer["coverage"], "finalSignal": spatial_transfer["finalSignal"], "uncertainty": spatial_transfer["uncertainty"]["pooled"]},
        "spatialTransferGate": spatial_transfer["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
