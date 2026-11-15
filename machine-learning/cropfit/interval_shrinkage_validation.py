from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .national_observed_validation import CROP_NAMES
from .yield_atlas import (
    CENSUS_REGIONS,
    STATE_TO_CENSUS_REGION,
    UNCERTAINTY_TEST_YEARS,
    history_bucket,
    rows_from_quickstats,
    spatial_transfer_examples,
    spatial_transfer_validation,
)


DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
FINAL_YEARS = (2023, 2024, 2025)
MIN_BLOCK_EXAMPLES = 100
SCALE_CANDIDATES = (.7, .75, .8, .85, .9, .95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.33, 1.4, 1.45, 1.5)
SHRINKAGE_CANDIDATES = (.25, .4, .5, .6, .7, .75, .8, 1.0)


def interval_metrics(items: list[dict], groups: dict[tuple[str, str], dict], scales: dict[tuple[str, str], tuple[float, float]]) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        calibration = groups[(item["crop"], history_bucket(item["productionEffectiveHistoryCount"]))]
        scale80, scale90 = scales[(item["crop"], STATE_TO_CENSUS_REGION[item["state"]])]
        prediction = item["productionPrediction"]
        actual = item["yieldPercentileWithinCropYear"]
        radius80 = calibration["absoluteErrorP80"] * scale80
        radius90 = calibration["absoluteErrorP90"] * scale90
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


def block_summaries(items: list[dict], crops: list[str], groups: dict, scales: dict) -> dict:
    return {
        "pooled": interval_metrics(items, groups, scales),
        "perCrop": [{
            "crop": crop,
            **interval_metrics([item for item in items if item["crop"] == crop], groups, scales),
        } for crop in crops],
        "perRegion": [{
            "region": region,
            **interval_metrics([
                item for item in items if STATE_TO_CENSUS_REGION[item["state"]] == region
            ], groups, scales),
        } for region in CENSUS_REGIONS],
    }


def prefinal_gate(development: dict, stability: dict) -> bool:
    return (
        .80 <= development["pooled"]["coverage80"] <= .87
        and .90 <= development["pooled"]["coverage90"] <= .95
        and .80 <= stability["pooled"]["coverage80"] <= .87
        and .90 <= stability["pooled"]["coverage90"] <= .95
        and all(item["coverage90"] >= .88 for item in (*development["perCrop"], *stability["perCrop"]))
        and all(item["coverage90"] >= .90 for item in (*development["perRegion"], *stability["perRegion"]))
    )


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    prepared = spatial_transfer_examples(rows)
    champion, _ = spatial_transfer_validation(rows, prepared, production_blend_version=10)
    examples = [item for item in prepared[0] if item["ownPrediction"] is not None]
    crops = sorted(CROP_NAMES.values())
    development_items = [item for item in examples if item["year"] in DEVELOPMENT_YEARS]
    stability_items = [item for item in examples if item["year"] in STABILITY_YEARS]
    final_items = [item for item in examples if item["year"] in FINAL_YEARS]
    test_items = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    calibration = champion["productionBlend"]["intervalCalibration"]
    groups = {(item["crop"], item["historyBucket"]): item for item in calibration["groups"]}
    regional_scales = calibration["selectedRegionalScales"]
    champion_scales = {
        (crop, region): (regional_scales[region]["scale80"], regional_scales[region]["scale90"])
        for crop in crops for region in CENSUS_REGIONS
    }
    sharpening_scales = dict(champion_scales)
    scale_selection = []
    for crop in crops:
        for region in CENSUS_REGIONS:
            development_group = [
                item for item in development_items
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            stability_group = [
                item for item in stability_items
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            enough = min(len(development_group), len(stability_group)) >= MIN_BLOCK_EXAMPLES
            champion_scale80, champion_scale90 = champion_scales[(crop, region)]
            if not enough:
                scale_selection.append({
                    "crop": crop, "region": region,
                    "developmentObservations": len(development_group),
                    "stabilityObservations": len(stability_group),
                    "fallback": "v10 regional scale", "required": None,
                    "sharpeningTarget": {"scale80": champion_scale80, "scale90": champion_scale90},
                })
                continue
            candidates = []
            for scale in SCALE_CANDIDATES:
                probe = dict(champion_scales)
                probe[(crop, region)] = (scale, scale)
                candidates.append({
                    "scale": scale,
                    "development": interval_metrics(development_group, groups, probe),
                    "stability": interval_metrics(stability_group, groups, probe),
                })
            required80 = next((item["scale"] for item in candidates if (
                item["development"]["coverage80"] >= .80 and item["stability"]["coverage80"] >= .80
            )), None)
            required90 = next((item["scale"] for item in candidates if (
                item["development"]["coverage90"] >= .90 and item["stability"]["coverage90"] >= .90
            )), None)
            target80 = required80 if required80 is not None and required80 < champion_scale80 else champion_scale80
            target90 = required90 if required90 is not None and required90 < champion_scale90 else champion_scale90
            sharpening_scales[(crop, region)] = (target80, target90)
            scale_selection.append({
                "crop": crop, "region": region,
                "developmentObservations": len(development_group),
                "stabilityObservations": len(stability_group),
                "fallback": None,
                "required": {"scale80": required80, "scale90": required90},
                "sharpeningTarget": {"scale80": target80, "scale90": target90},
                "candidates": candidates,
            })

    shrinkage_selection = []
    scale_options = {}
    for alpha in SHRINKAGE_CANDIDATES:
        scales = {
            key: (
                champion_scales[key][0] + alpha * (sharpening_scales[key][0] - champion_scales[key][0]),
                champion_scales[key][1] + alpha * (sharpening_scales[key][1] - champion_scales[key][1]),
            )
            for key in champion_scales
        }
        scale_options[alpha] = scales
        development = block_summaries(development_items, crops, groups, scales)
        stability = block_summaries(stability_items, crops, groups, scales)
        shrinkage_selection.append({
            "shrinkage": alpha, "development": development, "stability": stability,
            "passed": prefinal_gate(development, stability),
        })
    selected = max((item for item in shrinkage_selection if item["passed"]), key=lambda item: item["shrinkage"])
    selected_scales = scale_options[selected["shrinkage"]]
    champion_test = interval_metrics(test_items, groups, champion_scales)
    candidate_test = interval_metrics(test_items, groups, selected_scales)
    final = block_summaries(final_items, crops, groups, selected_scales)
    final_crop_regions = []
    for crop in crops:
        for region in CENSUS_REGIONS:
            group = [
                item for item in final_items
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            if group:
                final_crop_regions.append({
                    "crop": crop, "region": region,
                    **interval_metrics(group, groups, selected_scales),
                })
    width_reduction = round(1 - candidate_test["meanWidth90"] / champion_test["meanWidth90"], 4)
    checks = {
        "prefinalSelectionPassed": selected["passed"],
        "selectedShrinkageIsMaximumPassing": selected["shrinkage"] == max(
            item["shrinkage"] for item in shrinkage_selection if item["passed"]
        ),
        "pooledWidthReductionAtLeast2_5Percent": width_reduction >= .025,
        "pooledFinalCoverage": .80 <= final["pooled"]["coverage80"] <= .87 and .90 <= final["pooled"]["coverage90"] <= .95,
        "cropFinalCoverage": all(item["coverage90"] >= .88 for item in final["perCrop"]),
        "regionFinalCoverage": all(
            item["coverage80"] >= .75 and .85 <= item["coverage90"] <= .98 and item["meanWidth90"] <= .70
            for item in final["perRegion"]
        ),
        "cropRegionFinalCoverage": all(
            item["observations"] < MIN_BLOCK_EXAMPLES or item["coverage90"] >= .85
            for item in final_crop_regions
        ),
        "noScaleWidened": all(
            selected_scales[key][index] <= champion_scales[key][index]
            for key in selected_scales for index in (0, 1)
        ),
    }
    nested_scales = {
        crop: {
            region: {"scale80": round(selected_scales[(crop, region)][0], 4), "scale90": round(selected_scales[(crop, region)][1], 4)}
            for region in CENSUS_REGIONS
        }
        for crop in crops
    }
    return {
        "name": "USDA county yield atlas v11 interval-shrinkage validation",
        "protocol": {
            "champion": "atlas v10 crop/history radii with Census-region scales",
            "candidate": "shrink v10 scales toward development-selected crop-region sharpening targets",
            "developmentYears": list(DEVELOPMENT_YEARS), "stabilityYears": list(STABILITY_YEARS),
            "finalYears": list(FINAL_YEARS), "minimumExamplesPerSelectionBlock": MIN_BLOCK_EXAMPLES,
            "scaleCandidates": list(SCALE_CANDIDATES), "shrinkageCandidates": list(SHRINKAGE_CANDIDATES),
            "rule": "Crop-region targets may only narrow v10 scales. Select the largest global shrinkage preserving pooled, crop, and region coverage on development and stability, then require >=2.5% narrower pooled 90% bands plus calibrated locked pooled/crop/region/crop-region coverage.",
        },
        "scaleSelection": scale_selection,
        "shrinkageSelection": shrinkage_selection,
        "selectedShrinkage": selected["shrinkage"],
        "selectedCropRegionalScales": nested_scales,
        "championV10": champion_test, "candidate": candidate_test,
        "meanWidth90Reduction": width_reduction,
        "final": final, "perCropRegionFinal": final_crop_regions,
        "gate": {"passed": all(checks.values()), "checks": checks},
        "decision": "promote interval shrinkage to atlas v11" if all(checks.values()) else "reject; retain atlas v10",
        "interpretation": "Observed county-rank uncertainty; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    champion, candidate, final = report["championV10"], report["candidate"], report["final"]["pooled"]
    return "\n".join([
        "# Stability-selected interval shrinkage validation", "",
        report["protocol"]["rule"], "",
        f'Development/stability selection chooses **{report["selectedShrinkage"]:.0%}** shrinkage toward crop-region sharpening targets.', "",
        f'Mean 90% width falls from **{champion["meanWidth90"]:.4f}** to **{candidate["meanWidth90"]:.4f}** ({report["meanWidth90Reduction"]:.1%}) without widening any crop-region scale.', "",
        f'On locked 2023–2025 outcomes, pooled coverage is **{final["coverage80"]:.1%} / {final["coverage90"]:.1%}**. Every crop remains at least 88% and every sufficiently sampled crop-region remains at least 85% for the 90% band.', "",
        f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> Observed county-rank evidence; not parcel yield, revenue, or property value.", "",
    ])


def plot(report: dict, output: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    champion, candidate = report["championV10"], report["candidate"]
    axes[0].bar(["v10", "v11"], [champion["meanWidth90"], candidate["meanWidth90"]], color=["#8fae82", "#315d49"])
    axes[0].set(ylabel="Mean 90% width", title=f'{report["meanWidth90Reduction"]:.1%} narrower bands')
    selection = report["shrinkageSelection"]
    axes[1].plot([item["shrinkage"] * 100 for item in selection], [item["stability"]["pooled"]["coverage90"] * 100 for item in selection], marker="o", color="#315d49")
    axes[1].axhline(90, color="#315d49", linestyle="--", alpha=.5)
    axes[1].axvline(report["selectedShrinkage"] * 100, color="#d98352", linestyle=":")
    axes[1].set(xlabel="Shrinkage toward sharper targets (%)", ylabel="Stability 90% coverage (%)", title="Largest pre-final passing shrinkage")
    labels = [item["crop"] for item in report["final"]["perCrop"]]
    coverage = [item["coverage90"] * 100 for item in report["final"]["perCrop"]]
    axes[2].bar(labels, coverage, color="#315d49")
    axes[2].axhline(88, color="#d98352", linestyle="--", alpha=.7)
    axes[2].set(ylim=(84, 96), ylabel="Final 90% coverage (%)", title="Every crop passes locked coverage")
    for axis in axes:
        axis.grid(axis="y", alpha=.18)
    figure.suptitle("Atlas v11 · stability-selected interval shrinkage", fontweight="bold")
    figure.text(.5, .01, "Locked 2023–2025 county outcomes · point predictions unchanged", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--json", type=Path, default=root / "evaluation/interval-shrinkage-validation-v11.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/interval-shrinkage-validation-v11.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/interval-shrinkage-validation-v11.png")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"selectedShrinkage": report["selectedShrinkage"], "candidate": report["candidate"], "final": report["final"]["pooled"], "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Interval-shrinkage promotion gate did not pass")


if __name__ == "__main__":
    main()
