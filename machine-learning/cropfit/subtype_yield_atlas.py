from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.neighbors import BallTree

from .crop_expansion_validation import candidate_rows, metric_summary
from .yield_atlas import STATE_TO_CENSUS_REGION, aggregate_neighbor_prior, conformal_quantile, history_bucket, metric_summary as point_summary, observed_prior_prediction


YEARS = tuple(range(2010, 2026))
CALIBRATION_YEARS = tuple(range(2011, 2018))
DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
FINAL_YEARS = (2023, 2024, 2025)
SCALE_CANDIDATES = (1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.33, 1.4, 1.5)
NEIGHBOR_CANDIDATES = tuple(
    (count, distance_power, history_power)
    for count in (1, 2, 3, 5, 8)
    for distance_power in (0.0, .5, 1.0, 2.0)
    for history_power in (0.0, .5, 1.0)
)
CROP_METADATA = {
    "silage corn": {"yieldUnit": "tons/acre", "usdaUnit": "TONS / ACRE"},
    "spring wheat": {"yieldUnit": "bu/acre", "usdaUnit": "BU / ACRE"},
}


def subtype_rows(data: Path) -> list[dict]:
    return [{
        **row,
        "yieldPerAcre": row["yield"],
        "yieldPercentileWithinCropYear": row["percentile"],
    } for row in candidate_rows(data) if row["crop"] in CROP_METADATA]


def spatial_transfer_examples(rows: list[dict]) -> list[dict]:
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for items in histories.values():
        items.sort(key=lambda item: item["year"])
    examples = []
    for year in YEARS[1:]:
        for crop in CROP_METADATA:
            sources = []
            for (source_crop, fips), items in histories.items():
                if source_crop != crop:
                    continue
                earlier = [item for item in items if item["year"] < year]
                if earlier:
                    latest = earlier[-1]
                    sources.append({
                        "fips": fips, "latitude": latest["latitude"], "longitude": latest["longitude"],
                        "prediction": observed_prior_prediction(earlier, year), "historyCount": len(earlier),
                    })
            targets = [row for row in rows if row["crop"] == crop and row["year"] == year]
            if len(sources) < 2 or not targets:
                continue
            tree = BallTree(np.radians([[item["latitude"], item["longitude"]] for item in sources]), metric="haversine")
            distances, indices = tree.query(
                np.radians([[item["latitude"], item["longitude"]] for item in targets]),
                k=min(max(count for count, _, _ in NEIGHBOR_CANDIDATES) + 1, len(sources)),
            )
            for target, target_distances, target_indices in zip(targets, distances, indices, strict=True):
                neighbors = [
                    {**sources[int(index)], "distanceKm": float(distance * 6371.0)}
                    for distance, index in zip(target_distances, target_indices, strict=True)
                    if sources[int(index)]["fips"] != target["fips"]
                    and float(distance * 6371.0) <= 100
                ]
                if not neighbors:
                    continue
                examples.append({**target, "neighbors": neighbors})
    return examples


def apply_neighborhood(
    items: list[dict], max_neighbors: int, distance_power: float, history_power: float = 0.0,
) -> list[dict]:
    scored = []
    for item in items:
        prediction, neighbor_count, effective_history, weights = aggregate_neighbor_prior(
            item["neighbors"], max_neighbors, distance_power, history_power,
        )
        scored.append({
            **item, "prediction": prediction, "historyCount": effective_history,
            "neighborCount": neighbor_count, "neighborWeights": weights,
            "distanceKm": item["neighbors"][0]["distanceKm"],
            "absoluteError": abs(prediction - item["yieldPercentileWithinCropYear"]),
        })
    return scored


def signal_summary(items: list[dict], rounded: bool = True) -> dict:
    return {
        "observations": len(items),
        **point_summary(
            [item["yieldPercentileWithinCropYear"] for item in items],
            [item["prediction"] for item in items],
            rounded=rounded,
        ),
    }


def point_comparison(nearest: list[dict], selected: list[dict], years: tuple[int, ...]) -> dict:
    baseline = signal_summary([item for item in nearest if item["year"] in years])
    candidate = signal_summary([item for item in selected if item["year"] in years])
    return {
        "nearestCounty": baseline, "selectedNeighborhood": candidate,
        "spearmanGain": round(candidate["spearman"] - baseline["spearman"], 4),
        "maeReduction": round(baseline["maePercentile"] - candidate["maePercentile"], 4),
    }


def candidate_comparison(baseline: list[dict], selected: list[dict], years: tuple[int, ...]) -> dict:
    baseline_summary = signal_summary([item for item in baseline if item["year"] in years])
    selected_summary = signal_summary([item for item in selected if item["year"] in years])
    return {
        "distanceOnly": baseline_summary, "selected": selected_summary,
        "spearmanGain": round(selected_summary["spearman"] - baseline_summary["spearman"], 4),
        "maeReduction": round(baseline_summary["maePercentile"] - selected_summary["maePercentile"], 4),
    }


def paired_rank_gain_interval(nearest: list[dict], selected: list[dict], seed: int = 20261115) -> list[float]:
    if [(item["year"], item["fips"]) for item in nearest] != [(item["year"], item["fips"]) for item in selected]:
        raise ValueError("Paired neighborhood comparisons must contain identical county-years.")
    actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in selected])
    baseline = np.asarray([item["prediction"] for item in nearest])
    candidate = np.asarray([item["prediction"] for item in selected])
    groups = np.asarray([item["fips"] for item in selected])
    unique_groups = np.unique(groups)
    random = np.random.default_rng(seed)
    deltas = []
    for _ in range(2000):
        sampled = random.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([np.flatnonzero(groups == group) for group in sampled])
        deltas.append(
            float(spearmanr(candidate[indices], actual[indices]).statistic)
            - float(spearmanr(baseline[indices], actual[indices]).statistic)
        )
    return [round(float(value), 4) for value in np.quantile(deltas, [.025, .975])]


def interval_metrics(
    items: list[dict], table: dict[tuple[str, str], dict], scales: dict[str, dict],
    regional_scales: dict[str, dict[str, dict]] | None = None,
) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        calibration = table[(item["crop"], history_bucket(item["historyCount"]))]
        crop_scales = scales[item["crop"]]
        region = STATE_TO_CENSUS_REGION[item["state"]]
        region_scales = (regional_scales or {}).get(item["crop"], {}).get(region, {"scale80": 1.0, "scale90": 1.0})
        radius80 = calibration["absoluteErrorP80"] * crop_scales["scale80"] * region_scales["scale80"]
        radius90 = calibration["absoluteErrorP90"] * crop_scales["scale90"] * region_scales["scale90"]
        interval80 = (max(0.0, item["prediction"] - radius80), min(1.0, item["prediction"] + radius80))
        interval90 = (max(0.0, item["prediction"] - radius90), min(1.0, item["prediction"] + radius90))
        actual = item["yieldPercentileWithinCropYear"]
        hits80.append(interval80[0] <= actual <= interval80[1])
        hits90.append(interval90[0] <= actual <= interval90[1])
        widths80.append(interval80[1] - interval80[0])
        widths90.append(interval90[1] - interval90[0])
    return {
        "observations": len(items),
        "coverage80": round(float(np.mean(hits80)), 4),
        "coverage90": round(float(np.mean(hits90)), 4),
        "meanWidth80": round(float(np.mean(widths80)), 4),
        "meanWidth90": round(float(np.mean(widths90)), 4),
    }


def build(data: Path) -> tuple[dict, dict]:
    rows = subtype_rows(data)
    raw_examples = spatial_transfer_examples(rows)
    neighborhood_selection = []
    selected_neighborhoods = {}
    distance_only_neighborhoods = {}
    examples = []
    for crop in CROP_METADATA:
        crop_raw = [item for item in raw_examples if item["crop"] == crop]
        development_raw = [item for item in crop_raw if item["year"] in DEVELOPMENT_YEARS]
        candidates = []
        candidate_scores = []
        for max_neighbors, distance_power, history_power in NEIGHBOR_CANDIDATES:
            scored = apply_neighborhood(development_raw, max_neighbors, distance_power, history_power)
            candidates.append({
                "maxNeighbors": max_neighbors, "distancePower": distance_power, "historyPower": history_power,
                "development": signal_summary(scored),
            })
            candidate_scores.append({
                "maxNeighbors": max_neighbors, "distancePower": distance_power, "historyPower": history_power,
                "development": signal_summary(scored, rounded=False),
            })
        selected = max(candidate_scores, key=lambda item: (
            item["development"]["spearman"], -item["development"]["maePercentile"],
        ))
        distance_only = max(
            (item for item in candidate_scores if item["historyPower"] == 0),
            key=lambda item: (item["development"]["spearman"], -item["development"]["maePercentile"]),
        )
        config = {
            "maxNeighbors": selected["maxNeighbors"], "distancePower": selected["distancePower"],
            "historyPower": selected["historyPower"], "distanceOffsetKm": 5.0,
        }
        distance_only_neighborhoods[crop] = {
            "maxNeighbors": distance_only["maxNeighbors"], "distancePower": distance_only["distancePower"],
            "historyPower": 0.0, "distanceOffsetKm": 5.0,
        }
        selected_neighborhoods[crop] = config
        crop_examples = apply_neighborhood(
            crop_raw, config["maxNeighbors"], config["distancePower"], config["historyPower"],
        )
        examples.extend(crop_examples)
        neighborhood_selection.append({
            "crop": crop, "candidates": candidates,
            "distanceOnlyBaseline": distance_only_neighborhoods[crop], "selected": config,
        })
    calibration_examples = [item for item in examples if item["year"] in CALIBRATION_YEARS]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in calibration_examples:
        grouped[(item["crop"], history_bucket(item["historyCount"]))].append(item["absoluteError"])
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }

    unit_scales = {crop: {"scale80": 1.0, "scale90": 1.0} for crop in CROP_METADATA}
    selection = []
    for crop in CROP_METADATA:
        crop_candidates = []
        for scale in SCALE_CANDIDATES:
            scales = {**unit_scales, crop: {"scale80": scale, "scale90": scale}}
            development = interval_metrics([item for item in examples if item["crop"] == crop and item["year"] in DEVELOPMENT_YEARS], table, scales)
            stability = interval_metrics([item for item in examples if item["crop"] == crop and item["year"] in STABILITY_YEARS], table, scales)
            crop_candidates.append({"scale": scale, "development": development, "stability": stability})
        scale80 = next(item["scale"] for item in crop_candidates if item["development"]["coverage80"] >= .78 and item["stability"]["coverage80"] >= .78)
        scale90 = next(item["scale"] for item in crop_candidates if item["development"]["coverage90"] >= .88 and item["stability"]["coverage90"] >= .88)
        unit_scales[crop] = {"scale80": scale80, "scale90": scale90}
        selection.append({"crop": crop, "candidates": crop_candidates, "selected": unit_scales[crop]})

    selected_regional_scales: dict[str, dict[str, dict]] = {}
    supported_regions: dict[str, list[str]] = {}
    regional_scale_selection = []
    for crop in CROP_METADATA:
        candidate_regions = sorted({STATE_TO_CENSUS_REGION[item["state"]] for item in examples if item["crop"] == crop})
        crop_regions = [
            region for region in candidate_regions
            if all(sum(
                1 for item in examples
                if item["crop"] == crop and item["year"] in years
                and STATE_TO_CENSUS_REGION[item["state"]] == region
            ) >= 50 for years in (DEVELOPMENT_YEARS, STABILITY_YEARS, FINAL_YEARS))
        ]
        supported_regions[crop] = crop_regions
        selected_regional_scales[crop] = {}
        for region in crop_regions:
            development_items = [
                item for item in examples
                if item["crop"] == crop and item["year"] in DEVELOPMENT_YEARS
                and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            stability_items = [
                item for item in examples
                if item["crop"] == crop and item["year"] in STABILITY_YEARS
                and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            candidates = []
            for scale in SCALE_CANDIDATES:
                regional = {crop: {region: {"scale80": scale, "scale90": scale}}}
                candidates.append({
                    "scale": scale,
                    "development": interval_metrics(development_items, table, unit_scales, regional),
                    "stability": interval_metrics(stability_items, table, unit_scales, regional),
                })
            scale80 = next(item["scale"] for item in candidates if item["development"]["coverage80"] >= .8 and item["stability"]["coverage80"] >= .8)
            scale90 = next(item["scale"] for item in candidates if item["development"]["coverage90"] >= .9 and item["stability"]["coverage90"] >= .9)
            selected = {"scale80": scale80, "scale90": scale90}
            selected_regional_scales[crop][region] = selected
            regional_scale_selection.append({"crop": crop, "region": region, "candidates": candidates, "selected": selected})

    per_crop = []
    for crop in CROP_METADATA:
        crop_examples = [item for item in examples if item["crop"] == crop]
        final_examples = [item for item in crop_examples if item["year"] in FINAL_YEARS]
        crop_raw = [item for item in raw_examples if item["crop"] == crop]
        baseline_examples = apply_neighborhood(crop_raw, 1, 0.0)
        baseline_final = [item for item in baseline_examples if item["year"] in FINAL_YEARS]
        distance_only = distance_only_neighborhoods[crop]
        distance_only_examples = apply_neighborhood(
            crop_raw, distance_only["maxNeighbors"], distance_only["distancePower"], distance_only["historyPower"],
        )
        published = sum(1 for row in rows if row["crop"] == crop and row["year"] in FINAL_YEARS)
        signal = metric_summary(final_examples, published)
        baseline_signal = metric_summary(baseline_final, published)
        gain_interval = paired_rank_gain_interval(baseline_final, final_examples)
        point_validation = {
            "development": point_comparison(baseline_examples, crop_examples, DEVELOPMENT_YEARS),
            "stability": point_comparison(baseline_examples, crop_examples, STABILITY_YEARS),
            "final": point_comparison(baseline_examples, crop_examples, FINAL_YEARS),
        }
        history_reliability_comparison = {
            "development": candidate_comparison(distance_only_examples, crop_examples, DEVELOPMENT_YEARS),
            "stability": candidate_comparison(distance_only_examples, crop_examples, STABILITY_YEARS),
            "final": candidate_comparison(distance_only_examples, crop_examples, FINAL_YEARS),
            "finalSpearmanGainBootstrap95": paired_rank_gain_interval(
                [item for item in distance_only_examples if item["year"] in FINAL_YEARS], final_examples,
            ),
        }
        per_region = []
        for region in sorted(selected_regional_scales[crop]):
            region_examples = [item for item in crop_examples if STATE_TO_CENSUS_REGION[item["state"]] == region]
            per_region.append({
                "region": region,
                "development": interval_metrics([item for item in region_examples if item["year"] in DEVELOPMENT_YEARS], table, unit_scales, selected_regional_scales),
                "stability": interval_metrics([item for item in region_examples if item["year"] in STABILITY_YEARS], table, unit_scales, selected_regional_scales),
                "final": interval_metrics([item for item in region_examples if item["year"] in FINAL_YEARS], table, unit_scales, selected_regional_scales),
            })
        item = {
            "crop": crop,
            "nearestCountySignal": baseline_signal, "signal": signal,
            "spearmanGain": round(signal["spearman"] - baseline_signal["spearman"], 4),
            "spearmanGainBootstrap95": gain_interval,
            "maeReduction": round(baseline_signal["maePercentile"] - signal["maePercentile"], 4),
            "pointValidation": point_validation,
            "historyReliabilityComparison": history_reliability_comparison,
            "development": interval_metrics([item for item in crop_examples if item["year"] in DEVELOPMENT_YEARS], table, unit_scales, selected_regional_scales),
            "stability": interval_metrics([item for item in crop_examples if item["year"] in STABILITY_YEARS], table, unit_scales, selected_regional_scales),
            "final": interval_metrics(final_examples, table, unit_scales, selected_regional_scales),
            "perRegion": per_region,
        }
        item["passed"] = (
            item["signal"]["observations"] >= 100
            and item["signal"]["spearman"] >= .5
            and item["signal"]["bootstrap95"][0] > .3
            and item["spearmanGainBootstrap95"][0] > 0
            and all(
                block["spearmanGain"] > 0 and block["maeReduction"] > 0
                for block in item["pointValidation"].values()
            )
            and all(
                block["spearmanGain"] >= 0 and block["maeReduction"] >= 0
                for key, block in item["historyReliabilityComparison"].items() if key != "finalSpearmanGainBootstrap95"
            )
            and item["development"]["coverage80"] >= .78 and item["development"]["coverage90"] >= .88
            and item["stability"]["coverage80"] >= .78 and item["stability"]["coverage90"] >= .88
            and .75 <= item["final"]["coverage80"] <= .9
            and .87 <= item["final"]["coverage90"] <= .96
            and item["final"]["meanWidth90"] <= .8
            and all(
                region["final"]["observations"] >= 50
                and region["final"]["coverage80"] >= .7
                and .85 <= region["final"]["coverage90"] <= .98
                and region["final"]["meanWidth90"] <= .9
                for region in item["perRegion"]
            )
        )
        per_crop.append(item)
    accepted_crops = [item["crop"] for item in per_crop if item["passed"]]
    gate_passed = accepted_crops == ["silage corn", "spring wheat"]
    report = {
        "name": "USDA crop-subtype yield atlas v1 validation",
        "calibrationYears": list(CALIBRATION_YEARS), "developmentYears": list(DEVELOPMENT_YEARS),
        "stabilityYears": list(STABILITY_YEARS), "finalTestYears": list(FINAL_YEARS),
        "calibrationExamples": len(calibration_examples),
        "calibrationGroups": [table[key] for key in sorted(table)],
        "neighborhoodSelection": neighborhood_selection,
        "selectedNeighborhoods": selected_neighborhoods,
        "distanceOnlyNeighborhoods": distance_only_neighborhoods,
        "scaleSelection": selection, "selectedScales": unit_scales, "perCrop": per_crop,
        "regionalScaleSelection": regional_scale_selection,
        "selectedRegionalScales": selected_regional_scales,
        "supportedRegionsByCrop": supported_regions,
        "acceptedCrops": accepted_crops,
        "gate": {
            "passed": gate_passed,
            "rule": "Select neighborhood size, distance power, and history-reliability power on 2018-2020 only. Leave-one-county-out transfer within 100 km then needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; paired-bootstrap rank-gain lower >0; positive rank gain and MAE reduction over one nearest county in development, stability, and locked final blocks; no rank or MAE regression versus the best development-selected distance-only candidate in any block. Regional interval multipliers selected on development/stability must reach 80%/90%; locked pooled coverage must be 75-90%/87-96%, and every region needs final N >=50, 80% coverage >=70%, 90% coverage 85-98%, and mean 90% width <=0.90.",
        },
        "interpretation": "Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.",
    }
    if not gate_passed:
        raise RuntimeError("Crop-subtype atlas promotion gate failed; no atlas was produced.")

    records = []
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for (crop, fips), items in sorted(histories.items()):
        if crop not in accepted_crops:
            continue
        items.sort(key=lambda item: item["year"])
        latest = items[-1]
        if STATE_TO_CENSUS_REGION[latest["state"]] not in supported_regions[crop]:
            continue
        values = np.asarray([item["yieldPerAcre"] for item in items])
        percentiles = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        expected = observed_prior_prediction(items, 2026)
        calibration = table[(crop, history_bucket(len(items)))]
        scales = unit_scales[crop]
        region_scales = selected_regional_scales[crop][STATE_TO_CENSUS_REGION[latest["state"]]]
        records.append({
            "crop": crop, "fips": fips, "state": latest["state"], "county": latest["county"],
            "latitude": latest["latitude"], "longitude": latest["longitude"],
            "yieldUnit": CROP_METADATA[crop]["yieldUnit"], "usdaUnit": CROP_METADATA[crop]["usdaUnit"],
            "years": [item["year"] for item in items], "observations": len(items),
            "meanPercentile": round(float(np.mean(percentiles)), 4),
            "p10Percentile": round(float(np.quantile(percentiles, .1)), 4),
            "p90Percentile": round(float(np.quantile(percentiles, .9)), 4),
            "meanYieldPerAcre": round(float(np.mean(values)), 2),
            "observedYieldPrior": {
                "expectedPercentile": round(expected, 4),
                "interval80": [round(max(0.0, expected - calibration["absoluteErrorP80"] * scales["scale80"] * region_scales["scale80"]), 4), round(min(1.0, expected + calibration["absoluteErrorP80"] * scales["scale80"] * region_scales["scale80"]), 4)],
                "interval90": [round(max(0.0, expected - calibration["absoluteErrorP90"] * scales["scale90"] * region_scales["scale90"]), 4), round(min(1.0, expected + calibration["absoluteErrorP90"] * scales["scale90"] * region_scales["scale90"]), 4)],
                "historyBucket": history_bucket(len(items)), "calibrationExamples": calibration["examples"],
                "intervalMethod": "spatial-neighborhood-conformal",
                "neighborCount": selected_neighborhoods[crop]["maxNeighbors"],
            },
            "history": [{"year": item["year"], "yieldPerAcre": item["yieldPerAcre"], "percentile": round(item["yieldPercentileWithinCropYear"], 4)} for item in items],
            "latest": {"year": latest["year"], "yieldPerAcre": latest["yieldPerAcre"]},
        })
    atlas = {
        "name": "USDA crop-subtype yield atlas v1", "evidenceGrade": "observed-subtype-county-calibrated",
        "scope": "contiguous U.S. counties excluding California; silage corn and non-durum spring wheat; 2010-2025",
        "source": "USDA NASS Quick Stats published county yields", "crops": accepted_crops,
        "years": list(YEARS), "records": records, "validation": report,
        "spatialTransferValidation": {
            "method": "Leave one reporting county out and aggregate the development-selected nearby counties with earlier history within 100 km.",
            "selectedNeighborhoodByCrop": selected_neighborhoods,
            "distanceOnlyNeighborhoodByCrop": distance_only_neighborhoods,
            "selectedRegionalScalesByCrop": selected_regional_scales,
            "supportedRegionsByCrop": supported_regions,
            "groups": [{
                **table[(crop, bucket)],
                "absoluteErrorP80": round(table[(crop, bucket)]["absoluteErrorP80"] * unit_scales[crop]["scale80"], 4),
                "absoluteErrorP90": round(table[(crop, bucket)]["absoluteErrorP90"] * unit_scales[crop]["scale90"], 4),
            } for crop in accepted_crops for bucket in ("1", "2-3", "4+")],
            "gate": report["gate"],
        },
        "predictionMethod": {"name": "shrunken exponential recency prior", "forecastYear": 2026, "halfLifeYears": 3.0, "recencyWeight": .8, "longHistoryWeight": .2},
        "disclaimer": "Observed subtype-specific county prior with split-conformal uncertainty; not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }
    return atlas, report


def markdown(report: dict, records: int) -> str:
    lines = [
        "# USDA crop-subtype yield atlas v1", "",
        report["gate"]["rule"], "",
        "| Crop subtype | Locked N | Transfer ρ | Δρ vs nearest (95% CI) | 80% coverage | 90% coverage | Decision |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["perCrop"]:
        signal, final = item["signal"], item["final"]
        gain_interval = item["spearmanGainBootstrap95"]
        lines.append(f'| {item["crop"]} | {signal["observations"]:,} | {signal["spearman"]:.3f} | +{item["spearmanGain"]:.3f} ({gain_interval[0]:+.3f} to {gain_interval[1]:+.3f}) | {final["coverage80"]:.1%} | {final["coverage90"]:.1%} | {"PROMOTE" if item["passed"] else "REJECT"} |')
    lines += [
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. Atlas records: **{records:,}**.', "",
        "Neighborhoods were selected on 2018-2020 development only; interval scales also had to hold on 2021-2022 stability. The 2023-2025 outcomes remained locked until final evaluation.", "",
        "## History-reliability ablation", "",
        "History-count weighting is retained only when the development-selected candidate does not regress rank or MAE against the best distance-only candidate in development, stability, or final blocks.", "",
        "| Crop subtype | History power | Locked Δρ | 95% CI | Locked MAE reduction |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["perCrop"]:
        comparison = item["historyReliabilityComparison"]
        interval = comparison["finalSpearmanGainBootstrap95"]
        lines.append(
            f'| {item["crop"]} | {report["selectedNeighborhoods"][item["crop"]]["historyPower"]:.1f} | '
            f'{comparison["final"]["spearmanGain"]:+.4f} | {interval[0]:+.4f} to {interval[1]:+.4f} | '
            f'{comparison["final"]["maeReduction"]:+.4f} |'
        )
    lines += [
        "",
        "## Region-safe uncertainty", "",
        "Only crop-region pairs with at least 50 examples in development, stability, and final blocks are published. Multipliers were selected before opening the final block.", "",
        "| Crop subtype | Region | 80% scale | 90% scale | Locked N | 80% coverage | 90% coverage | Mean 90% width |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["perCrop"]:
        for region in item["perRegion"]:
            scales = report["selectedRegionalScales"][item["crop"]][region["region"]]
            final = region["final"]
            lines.append(
                f'| {item["crop"]} | {region["region"]} | {scales["scale80"]:.2f}× | {scales["scale90"]:.2f}× | '
                f'{final["observations"]:,} | {final["coverage80"]:.1%} | {final["coverage90"]:.1%} | {final["meanWidth90"]:.3f} |'
            )
    lines += ["", "> " + report["interpretation"], ""]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    crops = [item["crop"] for item in report["perCrop"]]
    colors = ["#315d49" if item["passed"] else "#d98352" for item in report["perCrop"]]
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.5))
    x = np.arange(len(crops)); width = .32
    coverage80 = [item["final"]["coverage80"] * 100 for item in report["perCrop"]]
    coverage90 = [item["final"]["coverage90"] * 100 for item in report["perCrop"]]
    axes[0].bar(x - width / 2, coverage80, width, color=colors, alpha=.65, label="80% interval")
    axes[0].bar(x + width / 2, coverage90, width, color=colors, label="90% interval")
    axes[0].axhline(80, color="#78a55a", linestyle=":"); axes[0].axhline(90, color="#315d49", linestyle=":")
    axes[0].set(xticks=x, xticklabels=crops, ylim=(70, 100), ylabel="locked outcome coverage (%)", title="2023-2025 calibrated reliability")
    axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    regional_labels, regional_coverage, regional_scales, regional_colors = [], [], [], []
    for crop_index, item in enumerate(report["perCrop"]):
        for region in item["perRegion"]:
            regional_labels.append(f'{item["crop"]}\n{region["region"]}')
            regional_coverage.append(region["final"]["coverage90"] * 100)
            regional_scales.append(report["selectedRegionalScales"][item["crop"]][region["region"]]["scale90"])
            regional_colors.append(colors[crop_index])
    regional_x = np.arange(len(regional_labels))
    bars = axes[1].bar(regional_x, regional_coverage, color=regional_colors, alpha=.85)
    axes[1].axhline(90, color="#315d49", linestyle=":", label="nominal 90%")
    axes[1].axhline(85, color="#d98352", linestyle="--", label="regional gate")
    for bar, coverage, scale in zip(bars, regional_coverage, regional_scales, strict=True):
        axes[1].annotate(
            f'{coverage:.1f}%\n×{scale:.2f}',
            (bar.get_x() + bar.get_width() / 2, coverage),
            xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8,
        )
    axes[1].set(
        xticks=regional_x, xticklabels=regional_labels, ylim=(70, 100),
        ylabel="locked 90% interval coverage (%)", title="Reliability by supported region",
    )
    axes[1].tick_params(axis="x", labelsize=8)
    axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    correlations = [item["signal"]["spearman"] for item in report["perCrop"]]
    baselines = [item["nearestCountySignal"]["spearman"] for item in report["perCrop"]]
    lowers = [item["signal"]["bootstrap95"][0] for item in report["perCrop"]]
    uppers = [item["signal"]["bootstrap95"][1] for item in report["perCrop"]]
    axes[2].scatter(x - .11, baselines, s=75, facecolors="white", edgecolors="#777", linewidths=2, label="one nearest county", zorder=3)
    for position, baseline, correlation, lower, upper, color, item in zip(x, baselines, correlations, lowers, uppers, colors, report["perCrop"], strict=True):
        axes[2].plot([position - .11, position + .11], [baseline, correlation], color=color, linewidth=2, alpha=.7)
        axes[2].errorbar([position + .11], [correlation], yerr=[[correlation - lower], [upper - correlation]], fmt="o", markersize=10, capsize=6, color=color)
        axes[2].annotate(f'+{item["spearmanGain"]:.3f}', (position + .11, correlation), xytext=(0, 16), textcoords="offset points", ha="center", color=color, fontweight="bold", fontsize=9)
    axes[2].scatter([], [], s=75, color="#315d49", label="selected five-county prior")
    axes[2].axhline(.5, color="#d98352", linestyle="--", label="promotion floor")
    axes[2].set(xticks=x, xticklabels=crops, ylim=(.25, .9), ylabel="Spearman rank correlation", title="Locked gain from neighborhood aggregation")
    axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit subtype atlas · held-out spatial-transfer evidence", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .06, 1, .94)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-subtypes-v1.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-subtypes-validation-v1.json")
    args = parser.parse_args()
    atlas, report = build(args.data)
    args.atlas.write_text(json.dumps(atlas, separators=(",", ":")) + "\n")
    args.validation.write_text(json.dumps(report, indent=2) + "\n")
    args.validation.with_suffix(".md").write_text(markdown(report, len(atlas["records"])))
    plot(report, args.validation.with_suffix(".png"))
    print(json.dumps({"records": len(atlas["records"]), "gate": report["gate"], "perCrop": report["perCrop"]}, indent=2))


if __name__ == "__main__":
    main()
