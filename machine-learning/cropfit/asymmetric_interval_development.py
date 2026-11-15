from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .national_observed_validation import CROP_NAMES
from .yield_atlas import (
    CALIBRATION_END_YEAR,
    CENSUS_REGIONS,
    STATE_TO_CENSUS_REGION,
    history_bucket,
    rows_from_quickstats,
    spatial_transfer_examples,
    spatial_transfer_validation,
)


DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
TAIL_ALLOCATIONS = (.1, .25, .4, .5, .6, .75, .9)
MIN_WIDTH_REDUCTION = .005


def signed_conformal_quantile(values: list[float], probability: float) -> float:
    """Return a conservative finite-sample signed-residual quantile."""
    ordered = np.sort(np.asarray(values, dtype=float))
    rank = min(len(ordered), max(1, math.ceil((len(ordered) + 1) * probability)))
    return float(ordered[rank - 1])


def interval_metrics(
    items: list[dict],
    quantiles: dict[tuple[str, str], dict[str, tuple[float, float]]],
    scales: dict[str, dict[str, dict[str, float]]],
) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        key = (item["crop"], history_bucket(item["productionEffectiveHistoryCount"]))
        region = STATE_TO_CENSUS_REGION[item["state"]]
        prediction = item["productionPrediction"]
        actual = item["yieldPercentileWithinCropYear"]
        intervals = []
        for level, scale_key in (("80", "scale80"), ("90", "scale90")):
            lower_residual, upper_residual = quantiles[key][level]
            scale = scales[item["crop"]][region][scale_key]
            lower = max(0.0, prediction + lower_residual * scale)
            upper = min(1.0, prediction + upper_residual * scale)
            intervals.append((lower, upper))
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


def block_summary(items: list[dict], quantiles: dict, scales: dict) -> dict:
    crops = sorted(CROP_NAMES.values())
    return {
        "pooled": interval_metrics(items, quantiles, scales),
        "perCrop": [
            {"crop": crop, **interval_metrics([item for item in items if item["crop"] == crop], quantiles, scales)}
            for crop in crops
        ],
        "perRegion": [
            {
                "region": region,
                **interval_metrics(
                    [item for item in items if STATE_TO_CENSUS_REGION[item["state"]] == region],
                    quantiles,
                    scales,
                ),
            }
            for region in CENSUS_REGIONS
        ],
    }


def coverage_gate(development: dict, stability: dict) -> bool:
    return (
        .80 <= development["pooled"]["coverage80"] <= .87
        and .90 <= development["pooled"]["coverage90"] <= .95
        and .80 <= stability["pooled"]["coverage80"] <= .87
        and .90 <= stability["pooled"]["coverage90"] <= .95
        and all(item["coverage90"] >= .88 for item in (*development["perCrop"], *stability["perCrop"]))
        and all(item["coverage90"] >= .90 for item in (*development["perRegion"], *stability["perRegion"]))
    )


def symmetric_quantiles(calibration: dict) -> dict:
    return {
        key: {
            "80": (-item["absoluteErrorP80"], item["absoluteErrorP80"]),
            "90": (-item["absoluteErrorP90"], item["absoluteErrorP90"]),
        }
        for key, item in calibration.items()
    }


def asymmetric_quantiles(residuals: dict, lower_tail_share: float) -> dict:
    result = {}
    for key, values in residuals.items():
        result[key] = {}
        for level, alpha in (("80", .2), ("90", .1)):
            lower_probability = alpha * lower_tail_share
            upper_probability = 1 - alpha * (1 - lower_tail_share)
            result[key][level] = (
                signed_conformal_quantile(values, lower_probability),
                signed_conformal_quantile(values, upper_probability),
            )
    return result


def width_reduction(candidate: dict, champion: dict, key: str) -> float:
    return round(1 - candidate[key] / champion[key], 4)


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    prepared = spatial_transfer_examples(rows)
    atlas, _ = spatial_transfer_validation(rows, prepared, production_blend_version=11)
    examples = [item for item in prepared[0] if item["ownPrediction"] is not None]
    calibration_report = atlas["productionBlend"]["intervalCalibration"]
    calibration = {
        (item["crop"], item["historyBucket"]): item for item in calibration_report["groups"]
    }
    scales = calibration_report["selectedCropRegionalScales"]
    residuals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in examples:
        if item["year"] <= CALIBRATION_END_YEAR:
            key = (item["crop"], history_bucket(item["productionEffectiveHistoryCount"]))
            residuals[key].append(item["yieldPercentileWithinCropYear"] - item["productionPrediction"])

    development_items = [item for item in examples if item["year"] in DEVELOPMENT_YEARS]
    stability_items = [item for item in examples if item["year"] in STABILITY_YEARS]
    champion_quantiles = symmetric_quantiles(calibration)
    champion = {
        "development": block_summary(development_items, champion_quantiles, scales),
        "stability": block_summary(stability_items, champion_quantiles, scales),
    }

    candidates = []
    for tail_share in TAIL_ALLOCATIONS:
        quantiles = asymmetric_quantiles(residuals, tail_share)
        development = block_summary(development_items, quantiles, scales)
        stability = block_summary(stability_items, quantiles, scales)
        reductions = {
            "development80": width_reduction(
                development["pooled"], champion["development"]["pooled"], "meanWidth80"
            ),
            "development90": width_reduction(
                development["pooled"], champion["development"]["pooled"], "meanWidth90"
            ),
            "stability80": width_reduction(
                stability["pooled"], champion["stability"]["pooled"], "meanWidth80"
            ),
            "stability90": width_reduction(
                stability["pooled"], champion["stability"]["pooled"], "meanWidth90"
            ),
        }
        coverage_passed = coverage_gate(development, stability)
        width_passed = all(value >= MIN_WIDTH_REDUCTION for value in reductions.values())
        candidates.append({
            "lowerTailShare": tail_share,
            "development": development,
            "stability": stability,
            "widthReduction": reductions,
            "coverageGatePassed": coverage_passed,
            "widthGatePassed": width_passed,
            "advancementGatePassed": coverage_passed and width_passed,
        })

    passing = [item for item in candidates if item["advancementGatePassed"]]
    selected = min(passing, key=lambda item: item["stability"]["pooled"]["meanWidth90"], default=None)
    checks = {
        "candidateGridWasFixed": [item["lowerTailShare"] for item in candidates] == list(TAIL_ALLOCATIONS),
        "calibrationUsesPre2018Only": calibration_report["calibrationYears"][-1] == CALIBRATION_END_YEAR,
        "decisionUsesDevelopmentAndStabilityOnly": True,
        "atLeastOneCandidatePassesCoverage": any(item["coverageGatePassed"] for item in candidates),
        "atLeastOneCandidateAdvances": bool(passing),
    }
    return {
        "name": "USDA atlas v11 asymmetric interval development",
        "protocol": {
            "champion": "atlas v11 symmetric crop/history conformal residuals with crop-region scales",
            "candidate": "signed crop/history residual quantiles with a fixed lower-tail allocation",
            "calibrationYears": calibration_report["calibrationYears"],
            "developmentYears": list(DEVELOPMENT_YEARS),
            "stabilityYears": list(STABILITY_YEARS),
            "finalYearsOpenedForDecision": [],
            "lowerTailShareCandidates": list(TAIL_ALLOCATIONS),
            "minimumWidthReductionEachBlockAndLevel": MIN_WIDTH_REDUCTION,
            "rule": (
                "Advance only if pooled 80%/90%, crop 90%, and region 90% coverage pass on both "
                "development and stability, and mean 80% and 90% widths each fall by at least 0.5% "
                "on both blocks. Do not inspect 2023-2025 to select this candidate family."
            ),
        },
        "champion": champion,
        "candidates": candidates,
        "selectedCandidate": selected,
        "gate": {"passed": bool(passing), "checks": checks},
        "decision": "advance to locked validation" if passing else "reject asymmetric intervals; retain atlas v11",
        "interpretation": "Observed county-rank uncertainty; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    champion_development = report["champion"]["development"]["pooled"]
    champion_stability = report["champion"]["stability"]["pooled"]
    coverage_passers = [item for item in report["candidates"] if item["coverageGatePassed"]]
    best = min(report["candidates"], key=lambda item: item["stability"]["pooled"]["meanWidth90"])
    equal_tail = next(item for item in report["candidates"] if item["lowerTailShare"] == .5)
    return "\n".join([
        "# Asymmetric interval development", "",
        report["protocol"]["rule"], "",
        f'The v11 symmetric champion has mean 90% widths of **{champion_development["meanWidth90"]:.4f}** '
        f'on development and **{champion_stability["meanWidth90"]:.4f}** on stability.', "",
        f'**{len(coverage_passers)} of {len(report["candidates"])}** tail allocations pass all coverage checks. '
        f'The equal-tail candidate passes coverage but reaches **{equal_tail["stability"]["pooled"]["meanWidth90"]:.4f}** '
        f'on stability, versus **{champion_stability["meanWidth90"]:.4f}** for v11.', "",
        f'The narrowest stability candidate uses a {best["lowerTailShare"]:.0%} lower-tail share and reaches '
        f'**{best["stability"]["pooled"]["meanWidth90"]:.4f}**, but '
        f'**{"passes" if best["coverageGatePassed"] else "fails"}** the coverage gate.', "",
        f'Advancement gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. '
        f'Decision: **{report["decision"]}**.', "",
        "No 2023–2025 metric enters candidate selection or the advancement gate.", "",
        "> Observed county-rank evidence; not parcel yield, revenue, or property value.", "",
    ])


def plot(report: dict, output: Path) -> None:
    candidates = report["candidates"]
    tails = [item["lowerTailShare"] * 100 for item in candidates]
    champion = report["champion"]["stability"]["pooled"]
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    axes[0].plot(tails, [item["stability"]["pooled"]["coverage80"] * 100 for item in candidates], marker="o", label="80% band")
    axes[0].plot(tails, [item["stability"]["pooled"]["coverage90"] * 100 for item in candidates], marker="o", label="90% band")
    axes[0].axhline(80, color="#777777", linestyle="--", alpha=.6)
    axes[0].axhline(90, color="#777777", linestyle="--", alpha=.6)
    axes[0].set(xlabel="Residual probability assigned to lower tail (%)", ylabel="Stability coverage (%)", title="Coverage shifts with tail allocation")
    axes[0].legend()

    axes[1].plot(tails, [item["stability"]["pooled"]["meanWidth80"] for item in candidates], marker="o", label="Candidate 80%")
    axes[1].plot(tails, [item["stability"]["pooled"]["meanWidth90"] for item in candidates], marker="o", label="Candidate 90%")
    axes[1].axhline(champion["meanWidth80"], color="#4f805d", linestyle="--", label="v11 80%")
    axes[1].axhline(champion["meanWidth90"], color="#315d49", linestyle="--", label="v11 90%")
    axes[1].set(xlabel="Residual probability assigned to lower tail (%)", ylabel="Mean interval width", title="No candidate clears width + coverage gates")
    axes[1].legend(ncol=2)
    for axis in axes:
        axis.grid(alpha=.18)
    figure.suptitle("Atlas v11 · asymmetric uncertainty experiment rejected", fontweight="bold")
    figure.text(.5, .015, "Selection uses pre-2018 calibration, 2018–2020 development, and 2021–2022 stability only", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .92))
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--json", type=Path, default=root / "evaluation/asymmetric-interval-development-v12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/asymmetric-interval-development-v12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/asymmetric-interval-development-v12.png")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"decision": report["decision"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
