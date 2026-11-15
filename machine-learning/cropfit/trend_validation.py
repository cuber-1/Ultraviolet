from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .recency_validation import CONFIRMATION_YEARS, FINAL_TEST_YEARS, bootstrap_delta, comparison
from .trend_development import forward_predictions, matched
from .yield_atlas import rows_from_quickstats


LOOKBACK_YEARS = 8
TREND_WEIGHT = .3
ENABLED_CROPS = ("corn", "soybean")


def gated_predictions(baseline: list[dict], candidate: list[dict]) -> list[dict]:
    return [
        probe if probe["crop"] in ENABLED_CROPS else {**probe, "prediction": champion["prediction"]}
        for champion, probe in zip(baseline, candidate, strict=True)
    ]


def phase(rows: list[dict], years: tuple[int, ...]) -> tuple[dict, list[dict], list[dict]]:
    baseline = forward_predictions(rows, years=years)
    candidate = forward_predictions(rows, TREND_WEIGHT, LOOKBACK_YEARS, years)
    base, probe = matched(baseline, candidate)
    gated = gated_predictions(base, probe)
    per_crop, per_year = slices_for_years(base, gated, years)
    return {**comparison(base, gated), "perCrop": per_crop, "perYear": per_year}, base, gated


def slices_for_years(baseline: list[dict], candidate: list[dict], years: tuple[int, ...]) -> tuple[list[dict], list[dict]]:
    per_crop = []
    for crop in ("corn", "soybean", "wheat"):
        base = [item for item in baseline if item["crop"] == crop]
        probe = [item for item in candidate if item["crop"] == crop]
        per_crop.append({"crop": crop, **comparison(base, probe)})
    per_year = []
    for year in years:
        base = [item for item in baseline if item["year"] == year]
        probe = [item for item in candidate if item["year"] == year]
        per_year.append({"year": year, **comparison(base, probe)})
    return per_crop, per_year


def nonregressing(items: list[dict]) -> bool:
    return all(item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in items)


def enabled_improve(items: list[dict]) -> bool:
    return all(
        item["spearmanDelta"] > 0 and item["maeDelta"] < 0
        for item in items if item["crop"] in ENABLED_CROPS
    )


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    confirmation, _, _ = phase(rows, CONFIRMATION_YEARS)
    final, final_baseline, final_candidate = phase(rows, FINAL_TEST_YEARS)
    final["spearmanDeltaBootstrap95"] = bootstrap_delta(final_baseline, final_candidate, seed=20270550)
    wheat = next(item for item in final["perCrop"] if item["crop"] == "wheat")
    checks = {
        "confirmationPooled": confirmation["spearmanDelta"] > 0 and confirmation["maeDelta"] < 0,
        "confirmationSlices": nonregressing(confirmation["perCrop"]) and nonregressing(confirmation["perYear"]),
        "confirmationEnabledCrops": enabled_improve(confirmation["perCrop"]),
        "finalPooled": final["spearmanDelta"] > 0 and final["maeDelta"] < 0,
        "finalRankBootstrap": final["spearmanDeltaBootstrap95"][0] > 0,
        "finalSlices": nonregressing(final["perCrop"]) and nonregressing(final["perYear"]),
        "finalEnabledCrops": enabled_improve(final["perCrop"]),
        "disabledWheatExact": wheat["spearmanDelta"] == 0 and wheat["maeDelta"] == 0,
    }
    return {
        "name": "USDA county-prior crop-gated trend validation v1",
        "target": "next-year county yield percentile within crop and year",
        "champion": "v11 shrunken three-year-half-life recency prior",
        "candidate": "champion plus 30% of a clipped eight-year OLS county-rank trend for corn and soybean; wheat unchanged",
        "protocol": {
            "selectionEvidence": "Parameters and crop gates were selected only on 2018–2020 development in trend-development-v1.json.",
            "lookbackYears": LOOKBACK_YEARS,
            "trendWeight": TREND_WEIGHT,
            "enabledCrops": list(ENABLED_CROPS),
            "confirmationYears": list(CONFIRMATION_YEARS),
            "finalYears": list(FINAL_TEST_YEARS),
            "declaredGate": "Confirmation and final pooled rank and MAE must improve; every crop and year must be non-regressing in both metrics; enabled crops must strictly improve both; wheat must remain exact; final grouped-bootstrap rank-delta lower bound must exceed zero.",
        },
        "confirmation": confirmation,
        "final": final,
        "gate": {"passed": all(checks.values()), "checks": checks},
        "interpretation": "Observed county-rank ordering only; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    lines = [
        "# USDA county-prior crop-gated trend validation", "",
        f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "The candidate was fixed before confirmation and final years were opened: 30% of a clipped eight-year county-rank trend for corn and soybean, with wheat exactly unchanged.", "",
        "| Phase | N | Rank delta | MAE delta |", "|---|---:|---:|---:|",
    ]
    for name in ("confirmation", "final"):
        item = report[name]
        lines.append(f'| {name} | {item["observations"]:,} | {item["spearmanDelta"]:+.4f} | {item["maeDelta"]:+.4f} |')
    final = report["final"]
    lines += [
        "", f'Final grouped-bootstrap 95% rank-delta interval: **{final["spearmanDeltaBootstrap95"][0]:+.4f} to {final["spearmanDeltaBootstrap95"][1]:+.4f}**.', "",
        "| Crop | N | Rank delta | MAE delta |", "|---|---:|---:|---:|",
    ]
    for item in final["perCrop"]:
        lines.append(f'| {item["crop"]} | {item["observations"]:,} | {item["spearmanDelta"]:+.4f} | {item["maeDelta"]:+.4f} |')
    lines += ["", f'Gate rule: {report["protocol"]["declaredGate"]}', "", f'> {report["interpretation"]}', ""]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    confirmation, final = report["confirmation"], report["final"]
    labels = ["confirmation", "final"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].bar(labels, [confirmation["spearmanDelta"], final["spearmanDelta"]], color="#315d49")
    axes[0].axhline(0, color="#777", linewidth=.8); axes[0].set(title="Pooled rank gain", ylabel="Spearman delta")
    crops = final["perCrop"]
    x = np.arange(len(crops)); width = .36
    axes[1].bar(x - width / 2, [item["spearmanDelta"] for item in crops], width, label="rank delta", color="#315d49")
    axes[1].bar(x + width / 2, [-item["maeDelta"] for item in crops], width, label="MAE reduction", color="#d98352")
    axes[1].axhline(0, color="#777", linewidth=.8); axes[1].set(xticks=x, xticklabels=[item["crop"] for item in crops], title="Locked 2023–2025 crop safety")
    axes[1].legend()
    for axis in axes:
        axis.grid(axis="y", alpha=.18)
    figure.suptitle("County-prior crop-gated trend · sealed validation", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--output", type=Path, default=root / "evaluation/trend-validation-v1.json")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"confirmation": report["confirmation"], "final": report["final"], "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Crop-gated trend promotion gate did not pass")


if __name__ == "__main__":
    main()
