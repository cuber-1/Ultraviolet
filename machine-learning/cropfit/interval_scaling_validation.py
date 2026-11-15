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
SCALE_CANDIDATES = (
    .7, .75, .8, .85, .9, .95, 1.0, 1.05, 1.1, 1.15, 1.2,
    1.25, 1.33, 1.4, 1.45, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.25, 2.5,
)


def interval_metrics(
    items: list[dict], groups: dict[tuple[str, str], dict],
    scales: dict[tuple[str, str], tuple[float, float]],
) -> dict:
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


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    prepared = spatial_transfer_examples(rows)
    champion, _ = spatial_transfer_validation(rows, prepared, production_blend_version=10)
    examples = [item for item in prepared[0] if item["ownPrediction"] is not None]
    crops = sorted(CROP_NAMES.values())
    development = [item for item in examples if item["year"] in DEVELOPMENT_YEARS]
    stability = [item for item in examples if item["year"] in STABILITY_YEARS]
    final = [item for item in examples if item["year"] in FINAL_YEARS]
    test = [item for item in examples if item["year"] in UNCERTAINTY_TEST_YEARS]
    calibration = champion["productionBlend"]["intervalCalibration"]
    groups = {(item["crop"], item["historyBucket"]): item for item in calibration["groups"]}
    regional_scales = calibration["selectedRegionalScales"]
    champion_scales = {
        (crop, region): (regional_scales[region]["scale80"], regional_scales[region]["scale90"])
        for crop in crops for region in CENSUS_REGIONS
    }
    candidate_scales = dict(champion_scales)
    selections = []
    for crop in crops:
        for region in CENSUS_REGIONS:
            development_group = [
                item for item in development
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            stability_group = [
                item for item in stability
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            enough = min(len(development_group), len(stability_group)) >= MIN_BLOCK_EXAMPLES
            if not enough:
                selections.append({
                    "crop": crop, "region": region,
                    "developmentObservations": len(development_group),
                    "stabilityObservations": len(stability_group),
                    "fallback": "v10 regional scale", "passed": True,
                    "selected": {"scale80": champion_scales[(crop, region)][0], "scale90": champion_scales[(crop, region)][1]},
                })
                continue
            candidates = []
            for scale in SCALE_CANDIDATES:
                probe_scales = dict(candidate_scales)
                probe_scales[(crop, region)] = (scale, scale)
                candidates.append({
                    "scale": scale,
                    "development": interval_metrics(development_group, groups, probe_scales),
                    "stability": interval_metrics(stability_group, groups, probe_scales),
                })
            selected80 = next((item for item in candidates if (
                item["development"]["coverage80"] >= .80 and item["stability"]["coverage80"] >= .80
            )), None)
            selected90 = next((item for item in candidates if (
                item["development"]["coverage90"] >= .90 and item["stability"]["coverage90"] >= .90
            )), None)
            passed = selected80 is not None and selected90 is not None
            selected = (
                selected80["scale"] if selected80 else champion_scales[(crop, region)][0],
                selected90["scale"] if selected90 else champion_scales[(crop, region)][1],
            )
            candidate_scales[(crop, region)] = selected
            selections.append({
                "crop": crop, "region": region,
                "developmentObservations": len(development_group),
                "stabilityObservations": len(stability_group),
                "fallback": None, "passed": passed,
                "selected": {"scale80": selected[0], "scale90": selected[1]},
                "candidates": candidates,
            })

    champion_test = interval_metrics(test, groups, champion_scales)
    candidate_test = interval_metrics(test, groups, candidate_scales)
    candidate_stability = interval_metrics(stability, groups, candidate_scales)
    candidate_final = interval_metrics(final, groups, candidate_scales)
    per_crop = [{
        "crop": crop,
        **interval_metrics([item for item in test if item["crop"] == crop], groups, candidate_scales),
    } for crop in crops]
    per_region_stability = [{
        "region": region,
        **interval_metrics([
            item for item in stability if STATE_TO_CENSUS_REGION[item["state"]] == region
        ], groups, candidate_scales),
    } for region in CENSUS_REGIONS]
    per_region_final = [{
        "region": region,
        **interval_metrics([
            item for item in final if STATE_TO_CENSUS_REGION[item["state"]] == region
        ], groups, candidate_scales),
    } for region in CENSUS_REGIONS]
    per_crop_region_final = []
    for crop in crops:
        for region in CENSUS_REGIONS:
            group = [
                item for item in final
                if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region
            ]
            if group:
                per_crop_region_final.append({
                    "crop": crop, "region": region,
                    **interval_metrics(group, groups, candidate_scales),
                })
    width_reduction = round(1 - candidate_test["meanWidth90"] / champion_test["meanWidth90"], 4)
    checks = {
        "allEligibleSelectionsCalibrated": all(item["passed"] for item in selections),
        "pooledWidthReductionAtLeast4Percent": width_reduction >= .04,
        "pooledCoverage": .80 <= candidate_test["coverage80"] <= .87 and .90 <= candidate_test["coverage90"] <= .94,
        "stabilityCoverage": .80 <= candidate_stability["coverage80"] <= .87 and .90 <= candidate_stability["coverage90"] <= .95,
        "finalCoverage": .80 <= candidate_final["coverage80"] <= .87 and .90 <= candidate_final["coverage90"] <= .95,
        "cropCoverage": all(item["coverage90"] >= .88 for item in per_crop),
        "regionalStability": all(item["coverage90"] >= .90 for item in per_region_stability),
        "regionalFinal": all(
            item["coverage80"] >= .75 and .85 <= item["coverage90"] <= .98 and item["meanWidth90"] <= .70
            for item in per_region_final
        ),
        "cropRegionFinal": all(
            item["observations"] < MIN_BLOCK_EXAMPLES or item["coverage90"] >= .85
            for item in per_crop_region_final
        ),
    }
    return {
        "name": "USDA county yield atlas crop-region interval scaling candidate",
        "protocol": {
            "champion": "atlas v10 crop/history radii with Census-region scales",
            "candidate": "crop/history radii with separately selected crop-region scales",
            "calibrationYears": list(range(2011, 2018)),
            "developmentYears": list(DEVELOPMENT_YEARS),
            "stabilityYears": list(STABILITY_YEARS),
            "finalYears": list(FINAL_YEARS),
            "minimumExamplesPerSelectionBlock": MIN_BLOCK_EXAMPLES,
            "scaleCandidates": list(SCALE_CANDIDATES),
            "rule": "Select the smallest crop-region scale meeting nominal coverage in both development and stability; sparse groups retain v10. Require >=4% narrower pooled 90% bands, calibrated pooled/stability/final blocks, reliable crop and region slices, and no final region above 98% 90%-coverage.",
        },
        "selection": selections,
        "championV10": champion_test,
        "candidate": candidate_test,
        "stability": candidate_stability,
        "final": candidate_final,
        "perCrop": per_crop,
        "perRegionStability": per_region_stability,
        "perRegionFinal": per_region_final,
        "perCropRegionFinal": per_crop_region_final,
        "meanWidth90Reduction": width_reduction,
        "gate": {"passed": all(checks.values()), "checks": checks},
        "decision": "reject; retain atlas v10 regional interval scales",
        "interpretation": "Observed county-rank uncertainty; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    champion = report["championV10"]
    candidate = report["candidate"]
    west = next(item for item in report["perRegionFinal"] if item["region"] == "West")
    return "\n".join([
        "# Crop-region interval scaling validation", "",
        report["protocol"]["rule"], "",
        f'The candidate reduces mean 90% width from **{champion["meanWidth90"]:.4f}** to **{candidate["meanWidth90"]:.4f}** ({report["meanWidth90Reduction"]:.1%}) while pooled coverage remains {candidate["coverage80"]:.1%} / {candidate["coverage90"]:.1%}.', "",
        f'It is **not promoted**: locked West 90% coverage rises to **{west["coverage90"]:.1%}**, above the predeclared 98% upper bound. This is over-conservative rather than falsely narrow, but it fails calibration sharpness.', "",
        f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "Decision: retain atlas v10 regional interval scales.", "",
        "> Observed county-rank evidence; not parcel yield, revenue, or property value.", "",
    ])


def plot(report: dict, output: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    champion, candidate = report["championV10"], report["candidate"]
    axes[0].bar(["v10", "candidate"], [champion["meanWidth90"], candidate["meanWidth90"]], color=["#8fae82", "#315d49"])
    axes[0].set(ylabel="Mean 90% width", title=f'{report["meanWidth90Reduction"]:.1%} narrower pooled bands')
    blocks = [report["candidate"], report["stability"], report["final"]]
    x = np.arange(3)
    axes[1].plot(x, [item["coverage80"] * 100 for item in blocks], marker="o", label="80%", color="#d98352")
    axes[1].plot(x, [item["coverage90"] * 100 for item in blocks], marker="o", label="90%", color="#315d49")
    axes[1].axhline(80, color="#d98352", linestyle="--", alpha=.5); axes[1].axhline(90, color="#315d49", linestyle="--", alpha=.5)
    axes[1].set(xticks=x, xticklabels=["pooled", "stability", "final"], ylim=(75, 97), ylabel="Coverage (%)", title="Pooled calibration holds"); axes[1].legend()
    regions = [item["region"] for item in report["perRegionFinal"]]
    coverage = [item["coverage90"] * 100 for item in report["perRegionFinal"]]
    axes[2].bar(regions, coverage, color=["#8fae82", "#8fae82", "#8fae82", "#8f2f14"])
    axes[2].axhline(98, color="#8f2f14", linestyle="--", alpha=.7)
    axes[2].set(ylim=(80, 102), ylabel="Final 90% coverage (%)", title="Rejected · West over-covers")
    for axis in axes:
        axis.grid(axis="y", alpha=.18)
    figure.suptitle("Atlas v11 interval-scaling candidate rejected", fontweight="bold")
    figure.text(.5, .01, "Locked 2023–2025 county outcomes · v10 retained", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--json", type=Path, default=root / "evaluation/interval-scaling-validation-v11-candidate.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/interval-scaling-validation-v11-candidate.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/interval-scaling-validation-v11-candidate.png")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"candidate": report["candidate"], "gate": report["gate"]}, indent=2))
    if report["gate"]["passed"]:
        raise SystemExit("Rejected interval-scaling candidate unexpectedly passed")


if __name__ == "__main__":
    main()
