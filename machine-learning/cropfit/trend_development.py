from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .recency_validation import DEVELOPMENT_YEARS, comparison, metrics
from .yield_atlas import observed_prior_prediction, rows_from_quickstats


TREND_WEIGHTS = (.1, .2, .3, .5)
LOOKBACK_YEARS = (5, 8, 16)
MINIMUM_HISTORY = 4
MAXIMUM_ANNUAL_SLOPE = .05


def trend_prediction(history: list[dict], prediction_year: int, trend_weight: float, lookback_years: int) -> float:
    baseline = observed_prior_prediction(history, prediction_year)
    recent = [item for item in history if item["year"] >= prediction_year - lookback_years]
    if len(recent) < MINIMUM_HISTORY:
        return baseline
    years = np.asarray([item["year"] for item in recent], dtype=float)
    values = np.asarray([item["yieldPercentileWithinCropYear"] for item in recent], dtype=float)
    centered = years - float(np.mean(years))
    denominator = float(centered @ centered)
    if denominator == 0:
        return baseline
    slope = float(centered @ (values - float(np.mean(values))) / denominator)
    slope = float(np.clip(slope, -MAXIMUM_ANNUAL_SLOPE, MAXIMUM_ANNUAL_SLOPE))
    horizon = max(1, prediction_year - int(years[-1]))
    return float(np.clip(baseline + trend_weight * slope * horizon, 0, 1))


def forward_predictions(
    rows: list[dict], trend_weight: float = 0, lookback_years: int = 16,
    years: tuple[int, ...] = DEVELOPMENT_YEARS,
) -> list[dict]:
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    examples = []
    for items in histories.values():
        items.sort(key=lambda item: item["year"])
        for index, item in enumerate(items):
            if index == 0 or item["year"] not in years:
                continue
            earlier = items[:index]
            baseline = observed_prior_prediction(earlier, item["year"])
            prediction = (
                trend_prediction(earlier, item["year"], trend_weight, lookback_years)
                if trend_weight else baseline
            )
            examples.append({
                "year": item["year"], "crop": item["crop"], "fips": item["fips"],
                "actual": item["yieldPercentileWithinCropYear"], "prediction": prediction,
            })
    return examples


def matched(baseline: list[dict], candidate: list[dict]) -> tuple[list[dict], list[dict]]:
    baseline_by_key = {(item["year"], item["crop"], item["fips"]): item for item in baseline}
    candidate_by_key = {(item["year"], item["crop"], item["fips"]): item for item in candidate}
    keys = sorted(baseline_by_key.keys() & candidate_by_key.keys())
    return [baseline_by_key[key] for key in keys], [candidate_by_key[key] for key in keys]


def slices(baseline: list[dict], candidate: list[dict]) -> tuple[list[dict], list[dict]]:
    per_crop = []
    for crop in ("corn", "soybean", "wheat"):
        base = [item for item in baseline if item["crop"] == crop]
        probe = [item for item in candidate if item["crop"] == crop]
        per_crop.append({"crop": crop, **comparison(base, probe)})
    per_year = []
    for year in DEVELOPMENT_YEARS:
        base = [item for item in baseline if item["year"] == year]
        probe = [item for item in candidate if item["year"] == year]
        per_year.append({"year": year, **comparison(base, probe)})
    return per_crop, per_year


def evaluate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    baseline = forward_predictions(rows)
    candidates = []
    predictions = {}
    for lookback in LOOKBACK_YEARS:
        for weight in TREND_WEIGHTS:
            candidate = forward_predictions(rows, weight, lookback)
            base, probe = matched(baseline, candidate)
            result = {
                "lookbackYears": lookback,
                "trendWeight": weight,
                **comparison(base, probe),
            }
            candidates.append(result)
            predictions[(lookback, weight)] = (base, probe)
    eligible = [
        item for item in candidates
        if item["spearmanDelta"] > 0 and item["maeDelta"] < 0
    ]
    selected = max(
        eligible or candidates,
        key=lambda item: (item["spearmanDelta"], -item["maeDelta"]),
    )
    base, probe = predictions[(selected["lookbackYears"], selected["trendWeight"])]
    global_per_crop, _ = slices(base, probe)
    enabled_crops = [
        item["crop"] for item in global_per_crop
        if item["spearmanDelta"] > 0 and item["maeDelta"] < 0
    ]
    gated_probe = [
        candidate if candidate["crop"] in enabled_crops else {**candidate, "prediction": champion["prediction"]}
        for champion, candidate in zip(base, probe, strict=True)
    ]
    gated = comparison(base, gated_probe)
    per_crop, per_year = slices(base, gated_probe)
    checks = {
        "atLeastOneCropEnabled": bool(enabled_crops),
        "pooledRankImproves": gated["spearmanDelta"] > 0,
        "pooledMaeImproves": gated["maeDelta"] < 0,
        "everyCropRankAndMaeNonRegressing": all(
            item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in per_crop
        ),
        "everyYearRankAndMaeNonRegressing": all(
            item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in per_year
        ),
    }
    return {
        "name": "USDA county-prior trend development v1",
        "target": "next-year county yield percentile within crop and year",
        "champion": "v11 shrunken three-year-half-life recency prior",
        "candidate": "champion plus a development-gated clipped OLS county-rank trend correction",
        "protocol": {
            "developmentYears": list(DEVELOPMENT_YEARS),
            "confirmationYearsOpened": False,
            "finalYearsOpened": False,
            "minimumHistory": MINIMUM_HISTORY,
            "maximumAnnualSlope": MAXIMUM_ANNUAL_SLOPE,
            "trendWeights": list(TREND_WEIGHTS),
            "lookbackYears": list(LOOKBACK_YEARS),
            "cropGate": "Enable the fixed trend correction only for crops whose development Spearman and MAE both improve; all other crops retain the champion exactly.",
            "advanceRule": "At least one crop must enable; gated development pooled Spearman and MAE must improve; no crop or development year may regress either metric. Only then may fixed parameters advance to a separately committed confirmation/final protocol.",
        },
        "championMetrics": metrics(base),
        "candidateSelection": candidates,
        "selectedGlobal": selected,
        "selected": {
            "lookbackYears": selected["lookbackYears"],
            "trendWeight": selected["trendWeight"],
            "enabledCrops": enabled_crops,
            **gated,
        },
        "perCrop": per_crop,
        "perYear": per_year,
        "gate": {"passed": all(checks.values()), "checks": checks},
        "interpretation": "Observed county-rank ordering only; not parcel yield, revenue, or property value.",
    }


def markdown(report: dict) -> str:
    selected = report["selected"]
    lines = [
        "# USDA county-prior trend development", "",
        f'Development gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        f'The selected development candidate uses a **{selected["lookbackYears"]}-year** lookback and **{selected["trendWeight"]:.0%}** of a clipped county-rank trend correction.',
        f'Pooled Spearman delta: **{selected["spearmanDelta"]:+.4f}**; percentile-MAE delta: **{selected["maeDelta"]:+.4f}**.', "",
        "| Crop | N | Rank delta | MAE delta |", "|---|---:|---:|---:|",
    ]
    for item in report["perCrop"]:
        lines.append(f'| {item["crop"]} | {item["observations"]:,} | {item["spearmanDelta"]:+.4f} | {item["maeDelta"]:+.4f} |')
    lines += ["", f'Advance rule: {report["protocol"]["advanceRule"]}', "", f'> {report["interpretation"]}', ""]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    candidates = report["candidateSelection"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for lookback in LOOKBACK_YEARS:
        rows = [item for item in candidates if item["lookbackYears"] == lookback]
        axes[0].plot([item["trendWeight"] for item in rows], [item["spearmanDelta"] for item in rows], marker="o", label=f"{lookback} years")
        axes[1].plot([item["trendWeight"] for item in rows], [item["maeDelta"] for item in rows], marker="o", label=f"{lookback} years")
    axes[0].axhline(0, color="#777", linewidth=.8); axes[1].axhline(0, color="#777", linewidth=.8)
    axes[0].set(title="Development rank change", xlabel="trend weight", ylabel="Spearman delta")
    axes[1].set(title="Development error change", xlabel="trend weight", ylabel="percentile-MAE delta")
    for axis in axes:
        axis.grid(alpha=.18); axis.legend()
    figure.suptitle("County-rank trend screen · 2018–2020 only", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--output", type=Path, default=root / "evaluation/trend-development-v1.json")
    args = parser.parse_args()
    report = evaluate(args.data)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"selected": report["selected"], "perCrop": report["perCrop"], "perYear": report["perYear"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
