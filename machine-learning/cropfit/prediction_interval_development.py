from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .national_observed_validation import CROP_NAMES
from .yield_atlas import (
    CALIBRATION_END_YEAR,
    CENSUS_REGIONS,
    STATE_TO_CENSUS_REGION,
    conformal_quantile,
    history_bucket,
    rows_from_quickstats,
    spatial_transfer_examples,
    spatial_transfer_validation,
)


DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
BIN_CANDIDATES = ((.5,), (.33, .67), (.2, .4, .6, .8), (.1, .3, .5, .7, .9))
BLEND_CANDIDATES = (.25, .5, .75, 1.0)
MIN_CALIBRATION_EXAMPLES = 100
MIN_WIDTH_REDUCTION = .01


def prediction_band(prediction: float, cuts: tuple[float, ...]) -> int:
    return next((index for index, cut in enumerate(cuts) if prediction < cut), len(cuts))


def prepare(data: Path) -> tuple[list[dict], dict, dict]:
    rows = rows_from_quickstats(data)
    prepared = spatial_transfer_examples(rows)
    atlas, _ = spatial_transfer_validation(rows, prepared, production_blend_version=11)
    items = [item for item in prepared[0] if item["ownPrediction"] is not None]
    calibration = atlas["productionBlend"]["intervalCalibration"]
    base = {
        (item["crop"], item["historyBucket"]): item for item in calibration["groups"]
    }
    return items, base, calibration["selectedCropRegionalScales"]


def conditional_radii(items: list[dict], cuts: tuple[float, ...]) -> dict:
    grouped: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for item in items:
        if item["year"] <= CALIBRATION_END_YEAR:
            key = (
                item["crop"],
                history_bucket(item["productionEffectiveHistoryCount"]),
                prediction_band(item["productionPrediction"], cuts),
            )
            grouped[key].append(abs(item["yieldPercentileWithinCropYear"] - item["productionPrediction"]))
    return {
        key: {"examples": len(errors), "absoluteErrorP90": conformal_quantile(errors, .9)}
        for key, errors in grouped.items()
    }


def interval_metrics(
    items: list[dict], base: dict, scales: dict,
    cuts: tuple[float, ...] | None = None, conditional: dict | None = None, blend: float = 0.0,
) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        base_key = (item["crop"], history_bucket(item["productionEffectiveHistoryCount"]))
        base_item = base[base_key]
        radius80 = base_item["absoluteErrorP80"]
        radius90 = base_item["absoluteErrorP90"]
        if cuts is not None and conditional is not None:
            conditional_key = (*base_key, prediction_band(item["productionPrediction"], cuts))
            radius90 = (1 - blend) * radius90 + blend * conditional[conditional_key]["absoluteErrorP90"]
        region = STATE_TO_CENSUS_REGION[item["state"]]
        scale = scales[item["crop"]][region]
        prediction = item["productionPrediction"]
        actual = item["yieldPercentileWithinCropYear"]
        intervals = [
            (max(0.0, prediction - radius80 * scale["scale80"]), min(1.0, prediction + radius80 * scale["scale80"])),
            (max(0.0, prediction - radius90 * scale["scale90"]), min(1.0, prediction + radius90 * scale["scale90"])),
        ]
        hits80.append(intervals[0][0] <= actual <= intervals[0][1])
        hits90.append(intervals[1][0] <= actual <= intervals[1][1])
        widths80.append(intervals[0][1] - intervals[0][0])
        widths90.append(intervals[1][1] - intervals[1][0])
    return {
        "observations": len(items),
        "coverage80": round(float(np.mean(hits80)), 4),
        "coverage90": round(float(np.mean(hits90)), 4),
        "meanWidth80": round(float(np.mean(widths80)), 4),
        "meanWidth90": round(float(np.mean(widths90)), 4),
    }


def block_summary(items: list[dict], base: dict, scales: dict, cuts=None, conditional=None, blend=0.0) -> dict:
    arguments = (base, scales, cuts, conditional, blend)
    return {
        "pooled": interval_metrics(items, *arguments),
        "perCrop": [
            {"crop": crop, **interval_metrics([item for item in items if item["crop"] == crop], *arguments)}
            for crop in sorted(CROP_NAMES.values())
        ],
        "perRegion": [
            {
                "region": region,
                **interval_metrics(
                    [item for item in items if STATE_TO_CENSUS_REGION[item["state"]] == region], *arguments
                ),
            }
            for region in CENSUS_REGIONS
        ],
        "perPredictionBand": ([
            {
                "band": index,
                "lower": 0.0 if index == 0 else cuts[index - 1],
                "upper": 1.0 if index == len(cuts) else cuts[index],
                **interval_metrics(
                    [item for item in items if prediction_band(item["productionPrediction"], cuts) == index],
                    *arguments,
                ),
            }
            for index in range(len(cuts) + 1)
        ] if cuts is not None else []),
    }


def coverage_gate(development: dict, stability: dict) -> bool:
    return (
        .90 <= development["pooled"]["coverage90"] <= .95
        and .90 <= stability["pooled"]["coverage90"] <= .95
        and all(.88 <= item["coverage90"] <= .97 for item in (*development["perCrop"], *stability["perCrop"]))
        and all(.90 <= item["coverage90"] <= .98 for item in (*development["perRegion"], *stability["perRegion"]))
    )


def reduction(candidate: dict, champion: dict) -> float:
    return round(1 - candidate["meanWidth90"] / champion["meanWidth90"], 4)


def evaluate(data: Path) -> dict:
    items, base, scales = prepare(data)
    development_items = [item for item in items if item["year"] in DEVELOPMENT_YEARS]
    stability_items = [item for item in items if item["year"] in STABILITY_YEARS]
    champion = {
        "development": block_summary(development_items, base, scales),
        "stability": block_summary(stability_items, base, scales),
    }
    candidates = []
    for cuts in BIN_CANDIDATES:
        conditional = conditional_radii(items, cuts)
        minimum_examples = min(item["examples"] for item in conditional.values())
        for blend in BLEND_CANDIDATES:
            development = block_summary(development_items, base, scales, cuts, conditional, blend)
            stability = block_summary(stability_items, base, scales, cuts, conditional, blend)
            reductions = {
                "development": reduction(development["pooled"], champion["development"]["pooled"]),
                "stability": reduction(stability["pooled"], champion["stability"]["pooled"]),
            }
            checks = {
                "minimumCalibrationExamples": minimum_examples >= MIN_CALIBRATION_EXAMPLES,
                "coverage": coverage_gate(development, stability),
                "developmentWidthReduction": reductions["development"] >= MIN_WIDTH_REDUCTION,
                "stabilityWidthReduction": reductions["stability"] >= MIN_WIDTH_REDUCTION,
                "eightyPercentBandUnchanged": (
                    development["pooled"]["meanWidth80"] == champion["development"]["pooled"]["meanWidth80"]
                    and stability["pooled"]["meanWidth80"] == champion["stability"]["pooled"]["meanWidth80"]
                ),
            }
            candidates.append({
                "cuts": list(cuts), "blend": blend, "minimumCalibrationExamples": minimum_examples,
                "development": development, "stability": stability, "widthReduction90": reductions,
                "gate": {"passed": all(checks.values()), "checks": checks},
            })
    passing = [item for item in candidates if item["gate"]["passed"]]
    selected = max(passing, key=lambda item: (item["widthReduction90"]["stability"], item["widthReduction90"]["development"]))
    return {
        "name": "Atlas v12 prediction-stratified interval development",
        "protocol": {
            "champion": "atlas v11 symmetric crop/history radii and crop-region scales",
            "candidate": "retain v11 80% radii; blend v11 90% radii toward crop/history/prediction-band conformal radii",
            "calibrationYears": list(range(2011, CALIBRATION_END_YEAR + 1)),
            "developmentYears": list(DEVELOPMENT_YEARS), "stabilityYears": list(STABILITY_YEARS),
            "finalYearsOpenedForSelection": [], "binCandidates": [list(item) for item in BIN_CANDIDATES],
            "blendCandidates": list(BLEND_CANDIDATES), "minimumCalibrationExamples": MIN_CALIBRATION_EXAMPLES,
            "minimumWidthReductionEachBlock": MIN_WIDTH_REDUCTION,
            "rule": "Require >=100 calibration examples per conditional cell, pooled/crop/region 90% coverage on development and stability, unchanged 80% intervals, and >=1% narrower mean 90% intervals on both blocks; select the passing candidate with the largest stability reduction.",
        },
        "champion": champion, "candidates": candidates,
        "selectedCandidate": {key: selected[key] for key in ("cuts", "blend", "minimumCalibrationExamples", "development", "stability", "widthReduction90", "gate")},
        "gate": {"passed": bool(passing), "passingCandidates": len(passing)},
        "decision": "seal candidate for locked validation" if passing else "reject; retain atlas v11",
        "interpretation": "Observed county-rank uncertainty; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    selected = report["selectedCandidate"]
    champion = report["champion"]
    return "\n".join([
        "# Prediction-stratified interval development", "", report["protocol"]["rule"], "",
        f'**{report["gate"]["passingCandidates"]} of {len(report["candidates"])}** fixed candidates pass. '
        f'The selected cuts are **{selected["cuts"]}** with a **{selected["blend"]:.0%}** conditional blend.', "",
        f'Development mean 90% width falls from **{champion["development"]["pooled"]["meanWidth90"]:.4f}** to '
        f'**{selected["development"]["pooled"]["meanWidth90"]:.4f}** ({selected["widthReduction90"]["development"]:.1%}). '
        f'Stability falls from **{champion["stability"]["pooled"]["meanWidth90"]:.4f}** to '
        f'**{selected["stability"]["pooled"]["meanWidth90"]:.4f}** ({selected["widthReduction90"]["stability"]:.1%}).', "",
        f'Development/stability 90% coverage is **{selected["development"]["pooled"]["coverage90"]:.1%} / '
        f'{selected["stability"]["pooled"]["coverage90"]:.1%}**. Every crop and region passes its pre-final range.', "",
        "The candidate is sealed for a separate locked 2023–2025 validation; no final metric enters this selection.", "",
        "> Observed county-rank evidence; not parcel yield, revenue, or property value.", "",
    ])


def plot(report: dict, output: Path) -> None:
    selected = report["selectedCandidate"]
    champion = report["champion"]
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    labels = ["Development", "Stability"]
    champion_widths = [champion["development"]["pooled"]["meanWidth90"], champion["stability"]["pooled"]["meanWidth90"]]
    candidate_widths = [selected["development"]["pooled"]["meanWidth90"], selected["stability"]["pooled"]["meanWidth90"]]
    axes[0].plot(labels, champion_widths, marker="o", linewidth=2.5, markersize=9, label="v11", color="#91a98b")
    axes[0].plot(labels, candidate_widths, marker="o", linewidth=2.5, markersize=9, label="v12 candidate", color="#315d49")
    for index, reduction90 in enumerate((selected["widthReduction90"]["development"], selected["widthReduction90"]["stability"])):
        axes[0].annotate(f"{reduction90:.1%} narrower", (index, candidate_widths[index]), xytext=(0, -22), textcoords="offset points", ha="center", color="#315d49", fontweight="bold")
    axes[0].set(ylim=(.48, .505), ylabel="Mean 90% interval width", title="Narrower pre-final intervals")
    axes[0].legend()
    slices = [*selected["development"]["perRegion"], *selected["stability"]["perRegion"]]
    xlabels = [f'Dev {item["region"]}' for item in selected["development"]["perRegion"]] + [f'Stab {item["region"]}' for item in selected["stability"]["perRegion"]]
    axes[1].bar(xlabels, [item["coverage90"] * 100 for item in slices], color=["#6f9551"] * 4 + ["#315d49"] * 4)
    axes[1].axhline(90, color="#d98352", linestyle="--")
    axes[1].set(ylim=(88, 99), ylabel="90% interval coverage (%)", title="Every region clears pre-final coverage")
    axes[1].tick_params(axis="x", rotation=35)
    for axis in axes: axis.grid(axis="y", alpha=.18)
    figure.suptitle("Atlas v12 candidate · prediction-stratified uncertainty", fontweight="bold")
    figure.text(.5, .015, "Selected without candidate-specific 2023–2025 metrics", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .06, 1, .92)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--json", type=Path, default=root / "evaluation/prediction-interval-development-v12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/prediction-interval-development-v12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/prediction-interval-development-v12.png")
    args = parser.parse_args(); report = evaluate(args.data)
    args.json.write_text(json.dumps(report, indent=2) + "\n"); args.markdown.write_text(markdown(report)); plot(report, args.plot)
    print(json.dumps({"selected": {key: report["selectedCandidate"][key] for key in ("cuts", "blend", "widthReduction90")}, "gate": report["gate"]}, indent=2))


if __name__ == "__main__": main()
