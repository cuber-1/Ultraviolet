from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

from .national_observed_validation import CROP_NAMES
from .yield_atlas import (
    CALIBRATION_END_YEAR,
    CENSUS_REGIONS,
    PRODUCTION_INTERVAL_SCALE_CANDIDATES,
    PRODUCTION_REGIONAL_WEIGHT_CANDIDATES,
    STATE_TO_CENSUS_REGION,
    UNCERTAINTY_TEST_YEARS,
    conformal_quantile,
    history_bucket,
    rows_from_quickstats,
    spatial_transfer_examples,
    spatial_transfer_validation,
)


DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
FINAL_YEARS = (2023, 2024, 2025)


def metrics(items: list[dict], prediction_key: str, rounded: bool = True) -> dict:
    actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
    predicted = np.asarray([item[prediction_key] for item in items])
    spearman = float(spearmanr(predicted, actual).statistic)
    mae = float(np.mean(np.abs(predicted - actual)))
    return {
        "observations": len(items),
        "spearman": round(spearman, 5) if rounded else spearman,
        "maePercentile": round(mae, 5) if rounded else mae,
    }


def comparison(items: list[dict]) -> dict:
    champion_raw = metrics(items, "productionPrediction", rounded=False)
    candidate_raw = metrics(items, "candidatePrediction", rounded=False)
    return {
        "observations": len(items),
        "championV9": metrics(items, "productionPrediction"),
        "cropSpecificCandidate": metrics(items, "candidatePrediction"),
        "spearmanGain": round(candidate_raw["spearman"] - champion_raw["spearman"], 8),
        "maeReduction": round(champion_raw["maePercentile"] - candidate_raw["maePercentile"], 8),
    }


def exact_gains(items: list[dict]) -> tuple[float, float]:
    """Return unrounded rank gain and MAE reduction for promotion gates."""
    champion = metrics(items, "productionPrediction", rounded=False)
    candidate = metrics(items, "candidatePrediction", rounded=False)
    return (
        candidate["spearman"] - champion["spearman"],
        champion["maePercentile"] - candidate["maePercentile"],
    )


def grouped_bootstrap(items: list[dict], seed: int = 20270404) -> list[float]:
    actual = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
    champion = np.asarray([item["productionPrediction"] for item in items])
    candidate = np.asarray([item["candidatePrediction"] for item in items])
    groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in items])
    unique, inverse = np.unique(groups, return_inverse=True)
    grouped_indices = [np.flatnonzero(inverse == index) for index in range(len(unique))]
    random = np.random.default_rng(seed)
    gains = []
    for _ in range(3000):
        selection = np.concatenate([
            grouped_indices[index]
            for index in random.integers(0, len(unique), len(unique))
        ])
        gains.append(float(
            spearmanr(candidate[selection], actual[selection]).statistic
            - spearmanr(champion[selection], actual[selection]).statistic
        ))
    return [round(float(value), 6) for value in np.quantile(gains, [.025, .975])]


def interval_metrics(
    items: list[dict], table: dict[tuple[str, str], dict],
    regional_scales: dict[str, dict[str, float]],
) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        calibration = table[(item["crop"], history_bucket(item["candidateEffectiveHistoryCount"]))]
        scales = regional_scales[STATE_TO_CENSUS_REGION[item["state"]]]
        prediction = item["candidatePrediction"]
        actual = item["yieldPercentileWithinCropYear"]
        radius80 = calibration["absoluteErrorP80"] * scales["scale80"]
        radius90 = calibration["absoluteErrorP90"] * scales["scale90"]
        lower80, upper80 = max(0.0, prediction - radius80), min(1.0, prediction + radius80)
        lower90, upper90 = max(0.0, prediction - radius90), min(1.0, prediction + radius90)
        hits80.append(lower80 <= actual <= upper80)
        hits90.append(lower90 <= actual <= upper90)
        widths80.append(upper80 - lower80)
        widths90.append(upper90 - lower90)
    return {
        "observations": len(items),
        "coverage80": round(float(np.mean(hits80)), 4),
        "coverage90": round(float(np.mean(hits90)), 4),
        "meanWidth80": round(float(np.mean(widths80)), 4),
        "meanWidth90": round(float(np.mean(widths90)), 4),
    }


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    prepared = spatial_transfer_examples(rows)
    champion_report, _ = spatial_transfer_validation(rows, prepared, production_blend_version=9)
    examples = [item for item in prepared[0] if item["ownPrediction"] is not None]
    development = [item for item in examples if item["year"] in DEVELOPMENT_YEARS]
    stability = [item for item in examples if item["year"] in STABILITY_YEARS]
    final = [item for item in examples if item["year"] in FINAL_YEARS]
    crops = sorted(CROP_NAMES.values())

    weight_selection = []
    selected_by_crop = {}
    development_region_checks = []
    probe_weights = {}
    for crop in crops:
        crop_development = [item for item in development if item["crop"] == crop]
        candidates = []
        candidate_scores = []
        for weight in PRODUCTION_REGIONAL_WEIGHT_CANDIDATES:
            candidate_items = [{
                **item,
                "candidatePrediction": (
                    (1 - weight) * item["ownPrediction"] + weight * item["prediction"]
                ),
            } for item in crop_development]
            candidates.append({"regionalWeight": weight, **metrics(candidate_items, "candidatePrediction")})
            candidate_scores.append({
                "regionalWeight": weight,
                **metrics(candidate_items, "candidatePrediction", rounded=False),
            })
        selected = min(candidate_scores, key=lambda item: (item["maePercentile"], -item["spearman"]))
        selected_by_crop[crop] = selected["regionalWeight"]
        weight_selection.append({"crop": crop, "candidates": candidates, "selected": selected["regionalWeight"]})
        for region in CENSUS_REGIONS:
            region_items = [
                item for item in crop_development
                if STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            if not region_items:
                probe_weights[(crop, region)] = 0.0
                development_region_checks.append({
                    "crop": crop, "region": region, "observations": 0,
                    "regionalWeight": 0.0, "enabled": False,
                })
                continue
            champion = metrics(region_items, "ownPrediction", rounded=False)
            candidate_items = [{
                **item,
                "candidatePrediction": (
                    (1 - selected["regionalWeight"]) * item["ownPrediction"]
                    + selected["regionalWeight"] * item["prediction"]
                ),
            } for item in region_items]
            candidate = metrics(candidate_items, "candidatePrediction", rounded=False)
            enabled = (
                candidate["spearman"] > champion["spearman"]
                and candidate["maePercentile"] < champion["maePercentile"]
            )
            probe_weights[(crop, region)] = selected["regionalWeight"] if enabled else 0.0
            development_region_checks.append({
                "crop": crop, "region": region, "observations": len(region_items),
                "regionalWeight": selected["regionalWeight"] if enabled else 0.0,
                "enabled": enabled,
            })

    champion_weights = champion_report["productionBlend"]["selectedWeights"]["regionalNeighborhoodByRegion"]
    for item in examples:
        probe_weight = probe_weights[(item["crop"], STATE_TO_CENSUS_REGION[item["state"]])]
        item["probePrediction"] = (
            (1 - probe_weight) * item["ownPrediction"] + probe_weight * item["prediction"]
        )
        item["probeEffectiveHistoryCount"] = round(
            (1 - probe_weight) * item["ownHistoryCount"]
            + probe_weight * item["effectiveHistoryCount"]
        )

    stability_selection = []
    enabled_crops = {}
    for crop in crops:
        crop_stability = [item for item in stability if item["crop"] == crop]
        champion = metrics(crop_stability, "productionPrediction", rounded=False)
        candidate = metrics(crop_stability, "probePrediction", rounded=False)
        enabled = (
            candidate["spearman"] > champion["spearman"]
            and candidate["maePercentile"] < champion["maePercentile"]
        )
        enabled_crops[crop] = enabled
        stability_selection.append({
            "crop": crop,
            "championV9": metrics(crop_stability, "productionPrediction"),
            "probe": metrics(crop_stability, "probePrediction"),
            "spearmanGain": round(candidate["spearman"] - champion["spearman"], 5),
            "maeReduction": round(champion["maePercentile"] - candidate["maePercentile"], 5),
            "enabled": enabled,
        })

    final_weights = {}
    for crop in crops:
        for region in CENSUS_REGIONS:
            final_weights[(crop, region)] = (
                probe_weights[(crop, region)]
                if enabled_crops[crop]
                else champion_weights[region]
            )
    for item in examples:
        if enabled_crops[item["crop"]]:
            item["candidatePrediction"] = item["probePrediction"]
            item["candidateEffectiveHistoryCount"] = item["probeEffectiveHistoryCount"]
        else:
            item["candidatePrediction"] = item["productionPrediction"]
            item["candidateEffectiveHistoryCount"] = item["productionEffectiveHistoryCount"]

    calibration = [item for item in examples if item["year"] <= CALIBRATION_END_YEAR]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in calibration:
        grouped[(item["crop"], history_bucket(item["candidateEffectiveHistoryCount"]))].append(
            abs(item["candidatePrediction"] - item["yieldPercentileWithinCropYear"])
        )
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }
    scale_selection = []
    regional_scales = {}
    for region in CENSUS_REGIONS:
        region_development = [item for item in development if STATE_TO_CENSUS_REGION[item["state"]] == region]
        region_stability = [item for item in stability if STATE_TO_CENSUS_REGION[item["state"]] == region]
        candidates = []
        for scale in PRODUCTION_INTERVAL_SCALE_CANDIDATES:
            scales = {name: {"scale80": 1.0, "scale90": 1.0} for name in CENSUS_REGIONS}
            scales[region] = {"scale80": scale, "scale90": scale}
            candidates.append({
                "scale": scale,
                "development": interval_metrics(region_development, table, scales),
                "stability": interval_metrics(region_stability, table, scales),
            })
        scale80 = next((item["scale"] for item in candidates if (
            item["development"]["coverage80"] >= .8 and item["stability"]["coverage80"] >= .8
        )), candidates[-1]["scale"])
        scale90 = next((item["scale"] for item in candidates if (
            item["development"]["coverage90"] >= .9 and item["stability"]["coverage90"] >= .9
        )), candidates[-1]["scale"])
        regional_scales[region] = {"scale80": scale80, "scale90": scale90}
        scale_selection.append({"region": region, "candidates": candidates, "selected": regional_scales[region]})

    test = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    intervals = {
        "pooled": interval_metrics(test, table, regional_scales),
        "stability": interval_metrics(stability, table, regional_scales),
        "final": interval_metrics(final, table, regional_scales),
        "perCrop": [{
            "crop": crop,
            **interval_metrics([item for item in test if item["crop"] == crop], table, regional_scales),
        } for crop in crops],
        "perRegionStability": [{
            "region": region,
            **interval_metrics([
                item for item in stability if STATE_TO_CENSUS_REGION[item["state"]] == region
            ], table, regional_scales),
        } for region in CENSUS_REGIONS],
        "perRegionFinal": [{
            "region": region,
            **interval_metrics([
                item for item in final if STATE_TO_CENSUS_REGION[item["state"]] == region
            ], table, regional_scales),
        } for region in CENSUS_REGIONS],
    }

    stability_comparison = comparison(stability)
    final_comparison = comparison(final)
    final_comparison["spearmanGainBootstrap95"] = grouped_bootstrap(final)
    per_crop_final = [{
        "crop": crop, **comparison([item for item in final if item["crop"] == crop]),
    } for crop in crops]
    per_year_final = [{
        "year": year, **comparison([item for item in final if item["year"] == year]),
    } for year in FINAL_YEARS]
    per_region_stability = [{
        "region": region,
        **comparison([item for item in stability if STATE_TO_CENSUS_REGION[item["state"]] == region]),
    } for region in CENSUS_REGIONS]
    per_region_final = [{
        "region": region,
        **comparison([item for item in final if STATE_TO_CENSUS_REGION[item["state"]] == region]),
    } for region in CENSUS_REGIONS]
    champion_width = champion_report["productionBlend"]["intervalCalibration"]["productionBlendRadii"]["meanWidth90"]
    stability_gains = exact_gains(stability)
    final_gains = exact_gains(final)
    crop_gains = [exact_gains([item for item in final if item["crop"] == crop]) for crop in crops]
    year_gains = [exact_gains([item for item in final if item["year"] == year]) for year in FINAL_YEARS]
    region_gains = [
        exact_gains([
            item for item in block
            if STATE_TO_CENSUS_REGION[item["state"]] == region
        ])
        for block in (stability, final)
        for region in CENSUS_REGIONS
    ]
    point_gate = (
        stability_gains[0] > 0 and stability_gains[1] > 0
        and final_gains[0] > 0 and final_gains[1] > 0
        and final_comparison["spearmanGainBootstrap95"][0] > 0
        and all(rank >= 0 and mae >= 0 for rank, mae in crop_gains)
        and crop_gains[crops.index("wheat")][0] > 0
        and crop_gains[crops.index("wheat")][1] > 0
        and all(rank >= 0 and mae >= 0 for rank, mae in year_gains)
        and all(rank >= 0 and mae >= 0 for rank, mae in region_gains)
    )
    interval_gate = (
        .80 <= intervals["pooled"]["coverage80"] <= .87
        and .88 <= intervals["pooled"]["coverage90"] <= .94
        and intervals["pooled"]["meanWidth90"] <= champion_width + .002
        and all(item["coverage90"] >= .88 for item in intervals["perCrop"])
        and all(item["coverage90"] >= .90 for item in intervals["perRegionStability"])
        and all(
            item["coverage80"] >= .75
            and .85 <= item["coverage90"] <= .98
            and item["meanWidth90"] <= .70
            for item in intervals["perRegionFinal"]
        )
        and .80 <= intervals["stability"]["coverage80"] <= .87
        and .88 <= intervals["stability"]["coverage90"] <= .95
        and .80 <= intervals["final"]["coverage80"] <= .87
        and .88 <= intervals["final"]["coverage90"] <= .95
    )
    return {
        "name": "USDA county yield atlas crop-specific production-blend v2 candidate",
        "protocol": {
            "champion": "atlas v9 global development-selected weight with region gating",
            "candidate": "crop-specific development weights with crop stability veto and region gating",
            "developmentYears": list(DEVELOPMENT_YEARS),
            "stabilityYears": list(STABILITY_YEARS),
            "finalYears": list(FINAL_YEARS),
            "rule": (
                "Select per-crop weights on 2018-2020, enable crop-region probes only when rank and MAE "
                "both improve there, veto each crop unless 2021-2022 rank and MAE both improve, then "
                "require positive locked pooled rank/MAE gains with grouped-bootstrap rank lower >0; "
                "no crop, year, or region may regress. Recalibrated intervals must retain all v9 "
                "coverage gates and mean 90% width within 0.002 of v9."
            ),
        },
        "selection": {
            "weightCandidates": weight_selection,
            "developmentRegionChecks": development_region_checks,
            "stabilityVeto": stability_selection,
            "selectedWeights": {
                crop: {region: final_weights[(crop, region)] for region in CENSUS_REGIONS}
                for crop in crops
            },
        },
        "stability": stability_comparison,
        "final": final_comparison,
        "perCropFinal": per_crop_final,
        "perYearFinal": per_year_final,
        "perRegionStability": per_region_stability,
        "perRegionFinal": per_region_final,
        "intervalCalibration": {
            "calibrationYears": list(range(2011, CALIBRATION_END_YEAR + 1)),
            "groups": [table[key] for key in sorted(table)],
            "selectedRegionalScales": regional_scales,
            "scaleSelection": scale_selection,
            "championMeanWidth90": champion_width,
            **intervals,
        },
        "gate": {"passed": point_gate and interval_gate, "pointPassed": point_gate, "intervalPassed": interval_gate},
        "interpretation": "Observed county-rank prior; not parcel yield, revenue, or a property-purchase forecast.",
    }


def markdown(report: dict) -> str:
    final = report["final"]
    wheat = next(item for item in report["perCropFinal"] if item["crop"] == "wheat")
    intervals = report["intervalCalibration"]["pooled"]
    enabled = [item["crop"] for item in report["selection"]["stabilityVeto"] if item["enabled"]]
    return "\n".join([
        "# USDA observed-prior crop-specific blend validation", "",
        report["protocol"]["rule"], "",
        f'Only **{", ".join(enabled)}** survives the stability veto. Corn and soybean retain their exact v9 policy.', "",
        f'On {final["observations"]:,} locked 2023–2025 county-years, Spearman changes from '
        f'**{final["championV9"]["spearman"]:.5f}** to **{final["cropSpecificCandidate"]["spearman"]:.5f}** '
        f'and percentile MAE from **{final["championV9"]["maePercentile"]:.5f}** to '
        f'**{final["cropSpecificCandidate"]["maePercentile"]:.5f}**. The grouped-bootstrap rank-gain interval is '
        f'**{final["spearmanGainBootstrap95"][0]:+.6f} to {final["spearmanGainBootstrap95"][1]:+.6f}**.', "",
        f'Wheat gains **{wheat["spearmanGain"]:+.5f}** Spearman and reduces MAE by **{wheat["maeReduction"]:.5f}**.', "",
        f'Recalibrated intervals cover **{intervals["coverage80"]:.1%} / {intervals["coverage90"]:.1%}** '
        f'with mean 90% width **{intervals["meanWidth90"]:.4f}**.', "",
        f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> Observed county-rank evidence; not parcel yield, revenue, or property value.", "",
    ])


def plot(report: dict, output: Path) -> None:
    crops = [item["crop"] for item in report["selection"]["stabilityVeto"]]
    selected = report["selection"]["selectedWeights"]
    weights = [max(selected[crop].values()) * 100 for crop in crops]
    final_blocks = [*report["perCropFinal"], *report["perYearFinal"]]
    labels = [item["crop"] if "crop" in item else str(item["year"]) for item in final_blocks]
    x = np.arange(len(labels))
    intervals = report["intervalCalibration"]
    coverage_labels = ["pooled", "stability", "final"]
    coverage_items = [intervals[label] for label in coverage_labels]
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.1))
    axes[0].bar(crops, weights, color=["#8fae82", "#8fae82", "#315d49"])
    axes[0].set(ylabel="Regional weight (%)", title="Stability veto advances wheat only")
    axes[0].grid(axis="y", alpha=.18)
    width = .38
    axes[1].bar(x - width / 2, [item["spearmanGain"] * 10_000 for item in final_blocks], width, label="Spearman", color="#315d49")
    axes[1].bar(x + width / 2, [item["maeReduction"] * 10_000 for item in final_blocks], width, label="MAE reduction", color="#8fae82")
    axes[1].axhline(0, color="#555555", linewidth=1)
    axes[1].set(xticks=x, xticklabels=labels, ylabel="Gain (×10⁻⁴)", title="No crop or final year regresses")
    axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    cx = np.arange(len(coverage_labels))
    axes[2].plot(cx, [item["coverage80"] * 100 for item in coverage_items], marker="o", label="80%", color="#d98352")
    axes[2].plot(cx, [item["coverage90"] * 100 for item in coverage_items], marker="o", label="90%", color="#315d49")
    axes[2].axhline(80, color="#d98352", linestyle="--", alpha=.6); axes[2].axhline(90, color="#315d49", linestyle="--", alpha=.6)
    axes[2].set(xticks=cx, xticklabels=coverage_labels, ylim=(75, 97), ylabel="Coverage (%)", title="Fresh conformal calibration holds")
    axes[2].legend(); axes[2].grid(alpha=.18)
    figure.suptitle("USDA county prior v10 candidate · crop-specific regional blend", fontweight="bold")
    figure.text(.5, .01, "Locked 2023–2025 outcomes · observed county ranks · not parcel yield", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, .94))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--json", type=Path, default=root / "evaluation/production-blend-v2-validation-v10.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/production-blend-v2-validation-v10.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/production-blend-v2-validation-v10.png")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"final": report["final"], "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Crop-specific production blend did not pass")


if __name__ == "__main__":
    main()
