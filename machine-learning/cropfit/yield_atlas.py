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
SPATIAL_NEIGHBOR_CANDIDATES = tuple((neighbors, power) for neighbors in (2, 3, 5, 8) for power in (0.0, 0.5, 1.0, 2.0))
SPATIAL_DISTANCE_OFFSET_KM = 5.0
PRODUCTION_REGIONAL_WEIGHT_CANDIDATES = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5)
PRODUCTION_INTERVAL_SCALE_CANDIDATES = (1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.33, 1.4, 1.45, 1.5)
STATE_TO_CENSUS_REGION = {
    **{state: "Northeast" for state in ("CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA")},
    **{state: "Midwest" for state in ("IN", "IL", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD")},
    **{state: "South" for state in ("DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX")},
    **{state: "West" for state in ("AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "OR", "WA")},
}
CENSUS_REGIONS = ("Northeast", "Midwest", "South", "West")


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


def aggregate_neighbor_prior(
    neighbors: list[dict], max_neighbors: int, distance_power: float, history_power: float = 0.0,
) -> tuple[float, int, int, list[float]]:
    selected = neighbors[:max_neighbors]
    if not selected:
        raise ValueError("At least one regional neighbor is required.")
    distances = np.asarray([item["distanceKm"] for item in selected], dtype=float)
    distance_weights = (
        np.ones(len(selected)) if distance_power == 0
        else 1 / np.power(distances + SPATIAL_DISTANCE_OFFSET_KM, distance_power)
    )
    history_weights = np.power([item["historyCount"] for item in selected], history_power)
    weights = distance_weights * history_weights
    normalized = weights / np.sum(weights)
    prediction = float(np.average([item["prediction"] for item in selected], weights=weights))
    effective_history = round(float(np.average([item["historyCount"] for item in selected], weights=weights)))
    return prediction, len(selected), effective_history, normalized.tolist()


def conformal_quantile(values: list[float], probability: float) -> float:
    ordered = np.sort(np.asarray(values, dtype=float))
    rank = min(len(ordered), math.ceil((len(ordered) + 1) * probability))
    return float(ordered[rank - 1])


def metric_summary(actual: list[float] | np.ndarray, predicted: list[float] | np.ndarray, rounded: bool = True) -> dict:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    spearman = float(spearmanr(predicted_values, actual_values).statistic)
    mae = float(np.mean(np.abs(predicted_values - actual_values)))
    return {
        "spearman": round(spearman, 4) if rounded else spearman,
        "maePercentile": round(mae, 4) if rounded else mae,
    }


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


def spatial_transfer_validation(rows: list[dict]) -> tuple[dict, dict[tuple[str, str], dict]]:
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for items in histories.values():
        items.sort(key=lambda item: item["year"])

    examples = []
    eligible = 0
    maximum_neighbors = max(item[0] for item in SPATIAL_NEIGHBOR_CANDIDATES)
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
            sources_by_fips = {item["fips"]: item for item in sources}
            tree = BallTree(np.radians([[item["latitude"], item["longitude"]] for item in sources]), metric="haversine")
            distances, indices = tree.query(
                np.radians([[item["latitude"], item["longitude"]] for item in targets]),
                k=min(maximum_neighbors + 1, len(sources)),
            )
            for target, target_distances, target_indices in zip(targets, distances, indices, strict=True):
                candidates = [{
                    **sources[int(index)], "distanceKm": float(distance * 6371.0),
                } for distance, index in zip(target_distances, target_indices, strict=True) if sources[int(index)]["fips"] != target["fips"]]
                if not candidates:
                    continue
                eligible += 1
                neighbors = [item for item in candidates if item["distanceKm"] <= SPATIAL_TRANSFER_MAX_DISTANCE_KM]
                if not neighbors:
                    continue
                own = sources_by_fips.get(target["fips"])
                examples.append({
                    **target, "neighbors": neighbors, "nearestPrediction": neighbors[0]["prediction"],
                    "distanceKm": neighbors[0]["distanceKm"], "distanceBucket": distance_bucket(neighbors[0]["distanceKm"]),
                    "ownPrediction": own["prediction"] if own else None,
                    "ownHistoryCount": own["historyCount"] if own else None,
                })

    def basic_summary(items: list[dict], prediction_key: str = "prediction", rounded: bool = True) -> dict:
        actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        predicted = np.asarray([item[prediction_key] for item in items])
        return {"observations": len(items), **metric_summary(actual, predicted, rounded)}

    development = [item for item in examples if item["year"] in (2018, 2019, 2020)]
    candidate_selection = []
    candidate_selection_scores = []
    for max_neighbors, distance_power in SPATIAL_NEIGHBOR_CANDIDATES:
        candidate = []
        for item in development:
            prediction, neighbor_count, effective_history, _ = aggregate_neighbor_prior(item["neighbors"], max_neighbors, distance_power)
            candidate.append({**item, "prediction": prediction, "neighborCount": neighbor_count, "effectiveHistoryCount": effective_history})
        candidate_selection.append({
            "maxNeighbors": max_neighbors, "distancePower": distance_power,
            **basic_summary(candidate),
        })
        candidate_selection_scores.append({
            "maxNeighbors": max_neighbors, "distancePower": distance_power,
            **basic_summary(candidate, rounded=False),
        })
    selected = max(candidate_selection_scores, key=lambda item: (item["spearman"], -item["maePercentile"]))
    for item in examples:
        prediction, neighbor_count, effective_history, weights = aggregate_neighbor_prior(
            item["neighbors"], selected["maxNeighbors"], selected["distancePower"],
        )
        item.update({
            "prediction": prediction, "neighborCount": neighbor_count, "effectiveHistoryCount": effective_history,
            "neighborWeights": weights, "absoluteError": abs(prediction - item["yieldPercentileWithinCropYear"]),
        })

    def comparison(items: list[dict]) -> dict:
        baseline = basic_summary(items, "nearestPrediction"); candidate = basic_summary(items)
        return {
            "observations": len(items), "nearestCounty": baseline, "regionalNeighborhood": candidate,
            "spearmanDelta": round(candidate["spearman"] - baseline["spearman"], 4),
            "maeDelta": round(candidate["maePercentile"] - baseline["maePercentile"], 4),
        }

    production_examples = [item for item in examples if item["ownPrediction"] is not None]
    production_development = [item for item in production_examples if item["year"] in (2018, 2019, 2020)]
    production_candidates = []
    production_candidate_scores = []
    for regional_weight in PRODUCTION_REGIONAL_WEIGHT_CANDIDATES:
        candidates = [{
            **item, "productionPrediction": (1 - regional_weight) * item["ownPrediction"] + regional_weight * item["prediction"],
        } for item in production_development]
        production_candidates.append({
            "regionalWeight": regional_weight,
            **basic_summary([{**item, "prediction": item["productionPrediction"]} for item in candidates]),
        })
        production_candidate_scores.append({
            "regionalWeight": regional_weight,
            **basic_summary([{
                **item, "prediction": item["productionPrediction"],
            } for item in candidates], rounded=False),
        })
    production_selected = min(production_candidate_scores, key=lambda item: (item["maePercentile"], -item["spearman"]))
    production_region_checks = []
    production_selected_by_region = {}
    for region in CENSUS_REGIONS:
        group_items = [item for item in production_development if STATE_TO_CENSUS_REGION[item["state"]] == region]
        baseline = basic_summary(group_items, "ownPrediction")
        baseline_score = basic_summary(group_items, "ownPrediction", rounded=False)
        regional_weight = production_selected["regionalWeight"]
        candidate_items = [{
            **item,
            "productionPrediction": (1 - regional_weight) * item["ownPrediction"] + regional_weight * item["prediction"],
        } for item in group_items]
        candidate = basic_summary([{**item, "prediction": item["productionPrediction"]} for item in candidate_items])
        candidate_score = basic_summary([{
            **item, "prediction": item["productionPrediction"],
        } for item in candidate_items], rounded=False)
        enabled = (
            candidate_score["spearman"] > baseline_score["spearman"]
            and candidate_score["maePercentile"] < baseline_score["maePercentile"]
        )
        production_selected_by_region[region] = regional_weight if enabled else 0.0
        production_region_checks.append({
            "region": region, "observations": len(group_items), "ownCountyPrior": baseline,
            "globalBlend": candidate, "enabled": enabled,
        })
    for item in production_examples:
        regional_weight = production_selected_by_region[STATE_TO_CENSUS_REGION[item["state"]]]
        item["productionPrediction"] = (
            (1 - regional_weight) * item["ownPrediction"] + regional_weight * item["prediction"]
        )
        item["productionEffectiveHistoryCount"] = round(
            (1 - regional_weight) * item["ownHistoryCount"] + regional_weight * item["effectiveHistoryCount"]
        )

    def production_comparison(items: list[dict]) -> dict:
        baseline = basic_summary([{**item, "prediction": item["ownPrediction"]} for item in items])
        candidate = basic_summary([{**item, "prediction": item["productionPrediction"]} for item in items])
        return {
            "observations": len(items), "ownCountyPrior": baseline, "blendedPrior": candidate,
            "spearmanDelta": round(candidate["spearman"] - baseline["spearman"], 4),
            "maeDelta": round(candidate["maePercentile"] - baseline["maePercentile"], 4),
        }

    def paired_bootstrap_delta(items: list[dict], seed: int = 20261115) -> list[float]:
        actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        baseline = np.asarray([item["nearestPrediction"] for item in items])
        candidate = np.asarray([item["prediction"] for item in items])
        groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in items])
        unique, inverse = np.unique(groups, return_inverse=True)
        indices = [np.flatnonzero(inverse == index) for index in range(len(unique))]
        random = np.random.default_rng(seed)
        deltas = []
        for _ in range(2000):
            selection = np.concatenate([indices[index] for index in random.integers(0, len(unique), len(unique))])
            deltas.append(float(
                spearmanr(candidate[selection], actual[selection]).statistic
                - spearmanr(baseline[selection], actual[selection]).statistic
            ))
        return [round(float(value), 4) for value in np.quantile(deltas, [.025, .975])]

    def production_bootstrap_delta(items: list[dict], seed: int = 20261116) -> list[float]:
        actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        baseline = np.asarray([item["ownPrediction"] for item in items])
        candidate = np.asarray([item["productionPrediction"] for item in items])
        groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in items])
        unique, inverse = np.unique(groups, return_inverse=True)
        indices = [np.flatnonzero(inverse == index) for index in range(len(unique))]
        random = np.random.default_rng(seed)
        deltas = []
        for _ in range(2000):
            selection = np.concatenate([indices[index] for index in random.integers(0, len(unique), len(unique))])
            deltas.append(float(
                spearmanr(candidate[selection], actual[selection]).statistic
                - spearmanr(baseline[selection], actual[selection]).statistic
            ))
        return [round(float(value), 4) for value in np.quantile(deltas, [.025, .975])]

    calibration = [item for item in examples if item["year"] <= CALIBRATION_END_YEAR]
    test = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in calibration:
        grouped[(item["crop"], history_bucket(item["effectiveHistoryCount"]))].append(item["absoluteError"])
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }

    production_grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in production_examples:
        if item["year"] <= CALIBRATION_END_YEAR:
            production_grouped[(item["crop"], history_bucket(item["productionEffectiveHistoryCount"]))].append(
                abs(item["productionPrediction"] - item["yieldPercentileWithinCropYear"])
            )
    production_table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in production_grouped.items()
    }

    def scored(
        items: list[dict], prediction_key: str = "prediction",
        calibration_table: dict[tuple[str, str], dict] = table,
        history_key: str = "effectiveHistoryCount",
        regional_interval_scales: dict[str, dict[str, float]] | None = None,
    ) -> dict:
        hits80, hits90, widths80, widths90 = [], [], [], []
        for item in items:
            calibration_item = calibration_table[(item["crop"], history_bucket(item[history_key]))]
            prediction = item[prediction_key]; actual = item["yieldPercentileWithinCropYear"]
            intervals = []
            region_scales = (regional_interval_scales or {}).get(
                STATE_TO_CENSUS_REGION[item["state"]], {"scale80": 1.0, "scale90": 1.0},
            )
            for key, scale_key in (("absoluteErrorP80", "scale80"), ("absoluteErrorP90", "scale90")):
                radius = calibration_item[key] * region_scales[scale_key]
                intervals.append((max(0.0, prediction - radius), min(1.0, prediction + radius)))
            hits80.append(intervals[0][0] <= actual <= intervals[0][1]); hits90.append(intervals[1][0] <= actual <= intervals[1][1])
            widths80.append(intervals[0][1] - intervals[0][0]); widths90.append(intervals[1][1] - intervals[1][0])
        return {
            "observations": len(items), "coverage80": round(float(np.mean(hits80)), 4),
            "coverage90": round(float(np.mean(hits90)), 4), "meanWidth80": round(float(np.mean(widths80)), 4),
            "meanWidth90": round(float(np.mean(widths90)), 4),
        }

    confirmation = [item for item in examples if item["year"] in (2021, 2022)]
    final = [item for item in examples if item["year"] in (2023, 2024, 2025)]
    confirmation_comparison = comparison(confirmation)
    final_comparison = comparison(final)
    final_comparison["spearmanDeltaBootstrap95"] = paired_bootstrap_delta(final)
    per_crop_signal = [{"crop": crop, **comparison([item for item in final if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    per_year_signal = [{"year": year, **comparison([item for item in final if item["year"] == year])} for year in (2023, 2024, 2025)]
    production_confirmation = [item for item in production_examples if item["year"] in (2021, 2022)]
    production_final = [item for item in production_examples if item["year"] in (2023, 2024, 2025)]
    production_confirmation_comparison = production_comparison(production_confirmation)
    production_final_comparison = production_comparison(production_final)
    production_final_comparison["spearmanDeltaBootstrap95"] = production_bootstrap_delta(production_final)
    production_per_crop = [{"crop": crop, **production_comparison([item for item in production_final if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    production_per_year = [{"year": year, **production_comparison([item for item in production_final if item["year"] == year])} for year in (2023, 2024, 2025)]
    production_confirmation_per_region = [{
        "region": region,
        **production_comparison([item for item in production_confirmation if STATE_TO_CENSUS_REGION[item["state"]] == region]),
    } for region in CENSUS_REGIONS]
    production_final_per_region = [{
        "region": region,
        **production_comparison([item for item in production_final if STATE_TO_CENSUS_REGION[item["state"]] == region]),
    } for region in CENSUS_REGIONS]
    production_test = [item for item in production_examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    production_interval_scale_candidates = []
    production_interval_scales = {}
    for region in CENSUS_REGIONS:
        region_development = [
            item for item in production_development if STATE_TO_CENSUS_REGION[item["state"]] == region
        ]
        region_stability = [
            item for item in production_confirmation if STATE_TO_CENSUS_REGION[item["state"]] == region
        ]
        candidates = []
        for scale in PRODUCTION_INTERVAL_SCALE_CANDIDATES:
            development_summary = scored(
                region_development, "productionPrediction", production_table, "productionEffectiveHistoryCount",
                {region: {"scale80": scale, "scale90": scale}},
            )
            stability_summary = scored(
                region_stability, "productionPrediction", production_table, "productionEffectiveHistoryCount",
                {region: {"scale80": scale, "scale90": scale}},
            )
            candidates.append({"scale": scale, "development": development_summary, "stability": stability_summary})
        scale80 = next((item["scale"] for item in candidates if (
            item["development"]["coverage80"] >= .80 and item["stability"]["coverage80"] >= .80
        )), candidates[-1]["scale"])
        scale90 = next((item["scale"] for item in candidates if (
            item["development"]["coverage90"] >= .90 and item["stability"]["coverage90"] >= .90
        )), candidates[-1]["scale"])
        production_interval_scale_candidates.append({"region": region, "candidates": candidates})
        production_interval_scales[region] = {"scale80": scale80, "scale90": scale90}
    production_baseline_intervals = scored(production_test, "productionPrediction")
    production_intervals = scored(production_test, "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales)
    production_confirmation_intervals = scored(production_confirmation, "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales)
    production_final_intervals = scored(production_final, "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales)
    production_per_crop_intervals = [{
        "crop": crop,
        **scored([item for item in production_test if item["crop"] == crop], "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales),
    } for crop in sorted(CROP_NAMES.values())]
    production_per_region_intervals = [{
        "region": region,
        **scored([
            item for item in production_test if STATE_TO_CENSUS_REGION[item["state"]] == region
        ], "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales),
    } for region in CENSUS_REGIONS]
    production_confirmation_per_region_intervals = [{
        "region": region,
        **scored([
            item for item in production_confirmation if STATE_TO_CENSUS_REGION[item["state"]] == region
        ], "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales),
    } for region in CENSUS_REGIONS]
    production_final_per_region_intervals = [{
        "region": region,
        **scored([
            item for item in production_final if STATE_TO_CENSUS_REGION[item["state"]] == region
        ], "productionPrediction", production_table, "productionEffectiveHistoryCount", production_interval_scales),
    } for region in CENSUS_REGIONS]
    production_width_reduction90 = round(
        1 - production_intervals["meanWidth90"] / production_baseline_intervals["meanWidth90"], 4,
    )
    production_passed = (
        production_confirmation_comparison["spearmanDelta"] > 0 and production_confirmation_comparison["maeDelta"] < 0
        and production_final_comparison["spearmanDelta"] > 0 and production_final_comparison["spearmanDeltaBootstrap95"][0] > 0
        and production_final_comparison["maeDelta"] < 0
        and all(item["spearmanDelta"] > 0 and item["maeDelta"] <= 0 for item in (*production_per_crop, *production_per_year))
        and all(item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in (*production_confirmation_per_region, *production_final_per_region))
        and .80 <= production_intervals["coverage80"] <= .87 and .88 <= production_intervals["coverage90"] <= .94
        and production_width_reduction90 >= .04
        and all(item["coverage90"] >= .88 for item in production_per_crop_intervals)
        and all(item["coverage90"] >= .90 for item in production_confirmation_per_region_intervals)
        and all(
            item["coverage80"] >= .75 and .85 <= item["coverage90"] <= .98 and item["meanWidth90"] <= .70
            for item in production_final_per_region_intervals
        )
        and .80 <= production_confirmation_intervals["coverage80"] <= .87 and .88 <= production_confirmation_intervals["coverage90"] <= .95
        and .80 <= production_final_intervals["coverage80"] <= .87 and .88 <= production_final_intervals["coverage90"] <= .95
    )
    pooled_uncertainty = scored(test)
    per_crop_uncertainty = [{"crop": crop, **scored([item for item in test if item["crop"] == crop])} for crop in sorted(CROP_NAMES.values())]
    covered = len(examples) / eligible
    passed = (
        len(final) >= 8_000 and covered >= .99
        and confirmation_comparison["spearmanDelta"] > 0 and confirmation_comparison["maeDelta"] < 0
        and final_comparison["spearmanDelta"] > 0 and final_comparison["spearmanDeltaBootstrap95"][0] > 0 and final_comparison["maeDelta"] < 0
        and all(item["spearmanDelta"] > 0 and item["maeDelta"] < 0 for item in (*per_crop_signal, *per_year_signal))
        and .80 <= pooled_uncertainty["coverage80"] <= .87 and .88 <= pooled_uncertainty["coverage90"] <= .94
        and pooled_uncertainty["meanWidth90"] <= .60 and all(item["coverage90"] >= .88 for item in per_crop_uncertainty)
    )
    report = {
        "method": "For each target county-year, exclude that county and aggregate nearby counties whose priors use only earlier years.",
        "maxDistanceKm": SPATIAL_TRANSFER_MAX_DISTANCE_KM,
        "eligibleExamples": eligible, "coveredExamples": len(examples), "coverage": round(covered, 4),
        "developmentYears": [2018, 2019, 2020], "candidateSelection": candidate_selection,
        "selectedNeighborhood": {
            "maxNeighbors": selected["maxNeighbors"], "distancePower": selected["distancePower"],
            "distanceOffsetKm": SPATIAL_DISTANCE_OFFSET_KM,
        },
        "confirmationYears": [2021, 2022], "confirmation": confirmation_comparison,
        "finalTestYears": [2023, 2024, 2025], "finalSignal": final_comparison,
        "perCropFinalSignal": per_crop_signal, "perYearFinalSignal": per_year_signal,
        "productionBlend": {
            "method": "Use the globally development-selected regional share only in Census regions where it improves both development rank and MAE; otherwise use the local prior.",
            "candidateSelection": production_candidates,
            "regionDevelopmentChecks": production_region_checks,
            "selectedWeights": {
                "regionalNeighborhoodByRegion": {
                    region: production_selected_by_region[region] for region in CENSUS_REGIONS
                },
            },
            "confirmation": production_confirmation_comparison, "finalSignal": production_final_comparison,
            "perCropFinalSignal": production_per_crop, "perYearFinalSignal": production_per_year,
            "perRegionConfirmation": production_confirmation_per_region,
            "perRegionFinalSignal": production_final_per_region,
            "intervalCalibration": {
                "method": "Crop/history split-conformal base radii fitted before 2018, with the smallest Census-region safety scales that meet nominal coverage in both 2018-2020 and 2021-2022.",
                "calibrationYears": list(range(YEARS[1], CALIBRATION_END_YEAR + 1)),
                "calibrationExamples": sum(len(errors) for errors in production_grouped.values()),
                "developmentYears": [2018, 2019, 2020],
                "stabilityYears": [2021, 2022],
                "regionalScaleCandidateSelection": production_interval_scale_candidates,
                "selectedRegionalScales": production_interval_scales,
                "groups": [production_table[key] for key in sorted(production_table)],
                "testYears": list(UNCERTAINTY_TEST_YEARS),
                "regionalTransferRadii": production_baseline_intervals,
                "productionBlendRadii": production_intervals,
                "meanWidth90Reduction": production_width_reduction90,
                "confirmation": production_confirmation_intervals,
                "final": production_final_intervals,
                "perCrop": production_per_crop_intervals,
                "perRegion": production_per_region_intervals,
                "perRegionConfirmation": production_confirmation_per_region_intervals,
                "perRegionFinal": production_final_per_region_intervals,
            },
            "gate": {
                "passed": production_passed,
                "rule": "Point-estimate gates pass by crop/year and no Census region regresses rank or MAE; production-specific test coverage remains 80-87%/88-94%; mean 90% width shrinks >=4%; every crop has >=88% 90%-coverage; pooled stability/final coverage remains in bounds; every region has >=90% 90%-coverage in the stability block, then final 80% coverage >=75%, 90% coverage 85-98%, and mean 90% width <=0.70.",
            },
        },
        "calibrationYears": list(range(YEARS[1], CALIBRATION_END_YEAR + 1)), "testYears": list(UNCERTAINTY_TEST_YEARS),
        "groups": [table[key] for key in sorted(table)],
        "uncertainty": {"pooled": pooled_uncertainty, "perCrop": per_crop_uncertainty},
        "gate": {
            "passed": passed,
            "rule": "Coverage within 100 km >=99%; confirmation and final neighborhood rank must improve and MAE fall; final rank-delta bootstrap lower >0; every crop/year improves both; test coverage 80-87%/88-94%, mean 90% width <=0.60, every crop >=88% 90%-coverage; production blend gate must pass.",
        },
        "interpretation": "Validates regional county-prior aggregation and its uncertainty, not parcel yield, revenue, or purchase returns.",
    }
    report["gate"]["passed"] = report["gate"]["passed"] and production_passed
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
        "name": "USDA county yield atlas v9", "evidenceGrade": "observed-region-gated-calibrated-blend",
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
        "disclaimer": "Observed local-plus-regional county prior with retrospectively calibrated temporal and spatial-transfer uncertainty; not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }


def markdown(validation: dict, comparison: dict, uncertainty: dict, spatial_transfer: dict, atlas: dict) -> str:
    lines = [
        "# USDA county yield atlas v9 validation", "",
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
        f'In the leave-one-county-out test, {spatial_transfer["coveredExamples"]:,} of {spatial_transfer["eligibleExamples"]:,} target county-years had reporting neighbors within 100 km ({spatial_transfer["coverage"]:.1%}). Development selection chose up to {spatial_transfer["selectedNeighborhood"]["maxNeighbors"]} counties with inverse-distance power {spatial_transfer["selectedNeighborhood"]["distancePower"]:.0f}. On locked 2023–2025 outcomes, regional aggregation reached Spearman **{spatial_transfer["finalSignal"]["regionalNeighborhood"]["spearman"]:.3f}** versus {spatial_transfer["finalSignal"]["nearestCounty"]["spearman"]:.3f} for one nearest county (delta {spatial_transfer["finalSignal"]["spearmanDelta"]:+.3f}; paired 95% interval {spatial_transfer["finalSignal"]["spearmanDeltaBootstrap95"][0]:+.3f} to {spatial_transfer["finalSignal"]["spearmanDeltaBootstrap95"][1]:+.3f}).',
        "", f'For production queries, the globally selected regional share is enabled only where it improves both development rank and MAE: {spatial_transfer["productionBlend"]["selectedWeights"]["regionalNeighborhoodByRegion"]}. On locked outcomes, Spearman changed from {spatial_transfer["productionBlend"]["finalSignal"]["ownCountyPrior"]["spearman"]:.4f} to **{spatial_transfer["productionBlend"]["finalSignal"]["blendedPrior"]["spearman"]:.4f}** (delta {spatial_transfer["productionBlend"]["finalSignal"]["spearmanDelta"]:+.4f}; grouped-bootstrap 95% interval {spatial_transfer["productionBlend"]["finalSignal"]["spearmanDeltaBootstrap95"][0]:+.4f} to {spatial_transfer["productionBlend"]["finalSignal"]["spearmanDeltaBootstrap95"][1]:+.4f}).',
        f'The production-specific conformal calibrator uses {spatial_transfer["productionBlend"]["intervalCalibration"]["calibrationExamples"]:,} pre-2018 errors, then selects the smallest regional safety scales that meet nominal coverage in both 2018–2020 and 2021–2022. Across 2018–2025, coverage is **{spatial_transfer["productionBlend"]["intervalCalibration"]["productionBlendRadii"]["coverage80"]:.1%}** / **{spatial_transfer["productionBlend"]["intervalCalibration"]["productionBlendRadii"]["coverage90"]:.1%}**, while mean 90% width falls from {spatial_transfer["productionBlend"]["intervalCalibration"]["regionalTransferRadii"]["meanWidth90"]:.3f} to **{spatial_transfer["productionBlend"]["intervalCalibration"]["productionBlendRadii"]["meanWidth90"]:.3f}** ({spatial_transfer["productionBlend"]["intervalCalibration"]["meanWidth90Reduction"]:.1%} narrower).',
        "", "### Regional interval reliability", "",
        "| Census region | 80% scale | 90% scale | 2021–2022 90% coverage | 2023–2025 90% coverage | Final mean 90% width |",
        "|---|---:|---:|---:|---:|---:|",
        *[
            f'| {stability["region"]} | {spatial_transfer["productionBlend"]["intervalCalibration"]["selectedRegionalScales"][stability["region"]]["scale80"]:.2f}× | {spatial_transfer["productionBlend"]["intervalCalibration"]["selectedRegionalScales"][stability["region"]]["scale90"]:.2f}× | {stability["coverage90"]:.1%} | {final["coverage90"]:.1%} | {final["meanWidth90"]:.3f} |'
            for stability, final in zip(
                spatial_transfer["productionBlend"]["intervalCalibration"]["perRegionConfirmation"],
                spatial_transfer["productionBlend"]["intervalCalibration"]["perRegionFinal"], strict=True,
            )
        ],
        f'Transfer intervals calibrated on 2011–2017 covered **{spatial_transfer["uncertainty"]["pooled"]["coverage80"]:.1%}** and **{spatial_transfer["uncertainty"]["pooled"]["coverage90"]:.1%}** on 2018–2025. Gate: **{"PASS" if spatial_transfer["gate"]["passed"] else "NOT PASSED"}**.',
        "", f'The production atlas contains {len(atlas["records"]):,} county-crop records. It is an observed local-plus-regional prior with calibrated temporal and spatial-transfer uncertainty, not a parcel yield forecast.',
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
    figure, axes = plt.subplots(2, 2, figsize=(18, 10))
    axes = axes.ravel()
    axes[0].plot(years, extended, marker="o", linewidth=2.5, color="#315d49", label="16-year history")
    axes[0].plot(years, legacy, marker="o", linewidth=2, color="#d98352", linestyle="--", label="8-year history")
    axes[0].set(ylim=(.65, .9), ylabel="Spearman correlation", xlabel="test year", xticks=years, title="Same future rows · longer history")
    axes[0].grid(alpha=.18); axes[0].legend(loc="lower right")
    axes[0].text(.02, .04, f'Pooled ρ {comparison["extendedHistory"]["spearman"]:.3f} vs {comparison["legacyHistory"]["spearman"]:.3f}\nMAE {comparison["extendedHistory"]["maePercentile"]:.3f} vs {comparison["legacyHistory"]["maePercentile"]:.3f}', transform=axes[0].transAxes, fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 6})
    axes[1].plot(interval_years, coverage80, marker="o", linewidth=2.2, color="#557f2d", label="80% interval")
    axes[1].plot(interval_years, coverage90, marker="o", linewidth=2.2, color="#315d49", label="90% interval")
    axes[1].axhline(80, color="#557f2d", alpha=.4, linestyle=":"); axes[1].axhline(90, color="#315d49", alpha=.4, linestyle=":")
    axes[1].set(ylim=(65, 100), ylabel="observed coverage (%)", xlabel="test year", xticks=interval_years, title="Base intervals calibrated on 2011–2017 only")
    axes[1].grid(alpha=.18); axes[1].legend(loc="lower right")
    axes[1].text(.02, .04, f'Pooled coverage\n80% band: {uncertainty["pooled"]["coverage80"]:.1%}\n90% band: {uncertainty["pooled"]["coverage90"]:.1%}', transform=axes[1].transAxes, fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 6})
    production = spatial_transfer["productionBlend"]
    interval_calibration = production["intervalCalibration"]
    baseline_intervals = interval_calibration["regionalTransferRadii"]
    production_intervals = interval_calibration["productionBlendRadii"]
    regions = [item["region"] for item in interval_calibration["perRegionConfirmation"]]
    stability_coverage = [item["coverage90"] * 100 for item in interval_calibration["perRegionConfirmation"]]
    final_coverage = [item["coverage90"] * 100 for item in interval_calibration["perRegionFinal"]]
    region_positions = np.arange(len(regions)); region_width = .35
    axes[2].bar(region_positions - region_width / 2, stability_coverage, region_width, color="#d98352", label="2021–2022 stability")
    axes[2].bar(region_positions + region_width / 2, final_coverage, region_width, color="#315d49", label="2023–2025 final")
    axes[2].axhline(90, color="#315d49", alpha=.45, linestyle=":")
    axes[2].set(xticks=region_positions, xticklabels=regions, ylim=(70, 100), ylabel="90% interval coverage (%)", title="Regional reliability across time blocks")
    axes[2].grid(axis="y", alpha=.18); axes[2].legend(loc="lower left")
    for position, region, value in zip(region_positions, regions, final_coverage, strict=True):
        scale = interval_calibration["selectedRegionalScales"][region]["scale90"]
        axes[2].text(position + region_width / 2, value + .6, f'×{scale:g}', ha="center", fontsize=8.5, color="#315d49")
    axes[2].text(.02, .97, "Scale selected before final block\nDotted line = nominal 90%", transform=axes[2].transAxes, va="top", fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 5})
    positions = np.arange(2); width = .34
    axes[3].bar(positions - width / 2, [baseline_intervals["meanWidth80"] * 100, baseline_intervals["meanWidth90"] * 100], width, color="#d98352", label="transfer radii")
    axes[3].bar(positions + width / 2, [production_intervals["meanWidth80"] * 100, production_intervals["meanWidth90"] * 100], width, color="#315d49", label="production radii")
    axes[3].set(xticks=positions, xticklabels=["80% band", "90% band"], ylim=(0, 65), ylabel="mean width (percentile points)", title="Sharper bands, coverage preserved")
    axes[3].grid(axis="y", alpha=.18); axes[3].legend(loc="lower right")
    axes[3].text(.02, .96, f'2018–2025 production coverage\n80%: {production_intervals["coverage80"]:.1%} · 90%: {production_intervals["coverage90"]:.1%}\n90% width: {interval_calibration["meanWidth90Reduction"]:.1%} narrower', transform=axes[3].transAxes, va="top", fontsize=9, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 5})
    axes[3].text(.02, .04, f'Production ρ {production["finalSignal"]["ownCountyPrior"]["spearman"]:.4f} → {production["finalSignal"]["blendedPrior"]["spearman"]:.4f}\nΔ CI {production["finalSignal"]["spearmanDeltaBootstrap95"][0]:+.4f} to {production["finalSignal"]["spearmanDeltaBootstrap95"][1]:+.4f} · gate {"PASS" if production["gate"]["passed"] else "NOT PASSED"}', transform=axes[3].transAxes, fontsize=8.5, color="#315d49", bbox={"facecolor": "white", "edgecolor": "#d8dfda", "alpha": .9, "pad": 5})
    figure.suptitle("USDA observed-yield prior v9 · geographically stable uncertainty", fontweight="bold")
    figure.text(.5, .01, "County-level corn, soybean, wheat · not a parcel yield forecast", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, .97)); figure.savefig(output, dpi=180); plt.close(figure)


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
    transfer = atlas.get("spatialTransferValidation", {})
    neighborhood = transfer.get("selectedNeighborhoodByCrop", {}).get(
        crop_key,
        transfer.get("selectedNeighborhood", {"maxNeighbors": 1, "distancePower": 0.0, "distanceOffsetKm": SPATIAL_DISTANCE_OFFSET_KM}),
    )
    max_neighbors = int(neighborhood["maxNeighbors"])
    production_blend = transfer.get("productionBlend", {})
    query_neighbors = max_neighbors + 1 if production_blend.get("gate", {}).get("passed") else max_neighbors
    distances, indices = tree.query(np.radians([[latitude, longitude]]), k=min(query_neighbors, len(records)))
    neighbors = [{
        "record": records[int(index)], "prediction": records[int(index)]["observedYieldPrior"]["expectedPercentile"],
        "historyCount": records[int(index)]["observations"], "distanceKm": float(distance * 6371.0),
    } for distance, index in zip(distances[0], indices[0], strict=True) if float(distance * 6371.0) <= max_distance_km]
    if not neighbors:
        return None
    used_regional_blend = False
    if production_blend.get("gate", {}).get("passed") and len(neighbors) > 1:
        primary, regional = neighbors[0], neighbors[1:]
        selected_weights = production_blend["selectedWeights"]
        weights_by_region = selected_weights.get("regionalNeighborhoodByRegion")
        regional_weight = float(
            weights_by_region[STATE_TO_CENSUS_REGION[primary["record"]["state"]]]
            if weights_by_region else selected_weights["regionalNeighborhood"]
        )
        if regional_weight > 0:
            used_regional_blend = True
            regional_expected, regional_count, regional_history, regional_weights = aggregate_neighbor_prior(
                regional, max_neighbors, float(neighborhood["distancePower"]),
                float(neighborhood.get("historyPower", 0.0)),
            )
            expected = (1 - regional_weight) * primary["prediction"] + regional_weight * regional_expected
            weights = [1 - regional_weight, *[regional_weight * weight for weight in regional_weights]]
            neighbor_count = 1 + regional_count
            effective_history = round((1 - regional_weight) * primary["historyCount"] + regional_weight * regional_history)
        else:
            neighbors = [primary]
            expected, neighbor_count, effective_history, weights = primary["prediction"], 1, primary["historyCount"], [1.0]
    else:
        expected, neighbor_count, effective_history, weights = aggregate_neighbor_prior(
            neighbors, max_neighbors, float(neighborhood["distancePower"]),
            float(neighborhood.get("historyPower", 0.0)),
        )
    record = neighbors[0]["record"]
    distance = neighbors[0]["distanceKm"]
    prior = dict(record.get("observedYieldPrior", {}))
    bucket = distance_bucket(distance)
    production_calibration = production_blend.get("intervalCalibration", {})
    calibration_groups = production_calibration.get("groups") or transfer.get("groups", [])
    calibration = next((item for item in calibration_groups if (
        item["crop"] == crop_key and item["historyBucket"] == history_bucket(effective_history)
    )), None)
    if calibration and prior:
        interval_scales = production_calibration.get("selectedRegionalScales", {}).get(
            STATE_TO_CENSUS_REGION[record["state"]],
            transfer.get("selectedRegionalScalesByCrop", {}).get(crop_key, {}).get(
                STATE_TO_CENSUS_REGION[record["state"]], {"scale80": 1.0, "scale90": 1.0},
            ),
        )
        prior.update({
            "expectedPercentile": round(expected, 4),
            "interval80": [round(max(0.0, expected - calibration["absoluteErrorP80"] * interval_scales["scale80"]), 4), round(min(1.0, expected + calibration["absoluteErrorP80"] * interval_scales["scale80"]), 4)],
            "interval90": [round(max(0.0, expected - calibration["absoluteErrorP90"] * interval_scales["scale90"]), 4), round(min(1.0, expected + calibration["absoluteErrorP90"] * interval_scales["scale90"]), 4)],
            "intervalMethod": (
                "local-regional-blend-conformal" if used_regional_blend
                else "region-gated-local-conformal"
            ) if production_calibration.get("groups") else "spatial-neighborhood-conformal",
            "distanceBucket": bucket,
            "calibrationExamples": calibration["examples"], "neighborCount": neighbor_count,
            "effectiveHistoryCount": effective_history, "effectiveHistoryBucket": history_bucket(effective_history),
        })
    regional_neighbors = [{
        "county": item["record"]["county"], "state": item["record"]["state"], "fips": item["record"]["fips"],
        "distanceKm": round(item["distanceKm"], 1), "expectedPercentile": item["record"]["observedYieldPrior"]["expectedPercentile"],
        "weight": round(weight, 6),
    } for item, weight in zip(neighbors, weights, strict=True)]
    normalized_record = dict(record)
    if "meanYieldPerAcre" not in normalized_record and "meanYieldBushelsPerAcre" in normalized_record:
        normalized_record["meanYieldPerAcre"] = normalized_record["meanYieldBushelsPerAcre"]
        normalized_record["yieldUnit"] = "bu/acre"
    normalized_record["history"] = [{
        **item,
        "yieldPerAcre": item.get("yieldPerAcre", item.get("yieldBushelsPerAcre")),
    } for item in normalized_record.get("history", [])]
    return {
        **normalized_record, "observedYieldPrior": prior, "regionalNeighbors": regional_neighbors,
        "distanceKm": round(distance, 1), "evidenceGrade": atlas["evidenceGrade"],
        "source": atlas["source"], "disclaimer": atlas["disclaimer"],
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-v9.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-validation-v9.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/yield-atlas-validation-v9.png")
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
        "productionBlend": spatial_transfer["productionBlend"]["finalSignal"],
        "productionBlendGate": spatial_transfer["productionBlend"]["gate"],
        "spatialTransferGate": spatial_transfer["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
