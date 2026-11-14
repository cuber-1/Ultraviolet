from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from .yield_atlas import rows_from_quickstats


DEVELOPMENT_YEARS = (2018, 2019, 2020)
CONFIRMATION_YEARS = (2021, 2022)
FINAL_TEST_YEARS = (2023, 2024, 2025)
HALF_LIFE_CANDIDATES = (1, 2, 3, 5, 8, 16)


def forward_predictions(rows: list[dict], half_life: float | None) -> list[dict]:
    history: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        history[(row["crop"], row["fips"])].append(row)
    examples = []
    for items in history.values():
        items.sort(key=lambda item: item["year"])
        for index, item in enumerate(items):
            if index == 0 or item["year"] not in (*DEVELOPMENT_YEARS, *CONFIRMATION_YEARS, *FINAL_TEST_YEARS):
                continue
            earlier = items[:index]
            values = np.asarray([row["yieldPercentileWithinCropYear"] for row in earlier])
            if half_life is None:
                prediction = float(np.mean(values))
            else:
                ages = np.asarray([item["year"] - row["year"] for row in earlier], dtype=float)
                weights = np.power(.5, ages / half_life)
                prediction = float(np.average(values, weights=weights))
            examples.append({
                "year": item["year"], "crop": item["crop"], "fips": item["fips"],
                "actual": item["yieldPercentileWithinCropYear"], "prediction": prediction,
            })
    return examples


def matched(baseline: list[dict], candidate: list[dict], years: tuple[int, ...]) -> tuple[list[dict], list[dict]]:
    baseline_by_key = {(item["year"], item["crop"], item["fips"]): item for item in baseline if item["year"] in years}
    candidate_by_key = {(item["year"], item["crop"], item["fips"]): item for item in candidate if item["year"] in years}
    keys = sorted(baseline_by_key.keys() & candidate_by_key.keys())
    return [baseline_by_key[key] for key in keys], [candidate_by_key[key] for key in keys]


def metrics(examples: list[dict]) -> dict:
    actual = np.asarray([item["actual"] for item in examples])
    predicted = np.asarray([item["prediction"] for item in examples])
    return {
        "observations": len(examples),
        "spearman": round(float(spearmanr(predicted, actual).statistic), 4),
        "maePercentile": round(float(np.mean(np.abs(predicted - actual))), 4),
    }


def comparison(baseline: list[dict], candidate: list[dict]) -> dict:
    base = metrics(baseline); recency = metrics(candidate)
    return {
        "observations": base["observations"], "baseline": base, "recency": recency,
        "spearmanDelta": round(recency["spearman"] - base["spearman"], 4),
        "maeDelta": round(recency["maePercentile"] - base["maePercentile"], 4),
    }


def bootstrap_delta(baseline: list[dict], candidate: list[dict], seed: int = 20261114) -> list[float]:
    actual = np.asarray([item["actual"] for item in baseline])
    base = np.asarray([item["prediction"] for item in baseline])
    recency = np.asarray([item["prediction"] for item in candidate])
    groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in baseline])
    unique, inverse = np.unique(groups, return_inverse=True)
    indices = [np.flatnonzero(inverse == index) for index in range(len(unique))]
    random = np.random.default_rng(seed)
    deltas = []
    for _ in range(2000):
        selection = np.concatenate([indices[index] for index in random.integers(0, len(unique), len(unique))])
        deltas.append(float(
            spearmanr(recency[selection], actual[selection]).statistic
            - spearmanr(base[selection], actual[selection]).statistic
        ))
    return [round(float(value), 4) for value in np.quantile(deltas, [.025, .975])]


def validate(data: Path) -> dict:
    rows = rows_from_quickstats(data)
    baseline = forward_predictions(rows, None)
    candidates = []
    predictions = {}
    for half_life in HALF_LIFE_CANDIDATES:
        candidate = forward_predictions(rows, half_life)
        predictions[half_life] = candidate
        base_dev, candidate_dev = matched(baseline, candidate, DEVELOPMENT_YEARS)
        candidates.append({"halfLifeYears": half_life, **comparison(base_dev, candidate_dev)})
    selected = max(candidates, key=lambda item: (item["recency"]["spearman"], -item["recency"]["maePercentile"]))
    half_life = selected["halfLifeYears"]
    candidate = predictions[half_life]
    base_confirmation, candidate_confirmation = matched(baseline, candidate, CONFIRMATION_YEARS)
    confirmation = comparison(base_confirmation, candidate_confirmation)
    base_final, candidate_final = matched(baseline, candidate, FINAL_TEST_YEARS)
    final_test = comparison(base_final, candidate_final)
    final_test["spearmanDeltaBootstrap95"] = bootstrap_delta(base_final, candidate_final)
    per_crop = []
    for crop in ("corn", "soybean", "wheat"):
        base_crop = [item for item in base_final if item["crop"] == crop]
        candidate_crop = [item for item in candidate_final if item["crop"] == crop]
        per_crop.append({"crop": crop, **comparison(base_crop, candidate_crop)})
    per_year = []
    for year in FINAL_TEST_YEARS:
        base_year = [item for item in base_final if item["year"] == year]
        candidate_year = [item for item in candidate_final if item["year"] == year]
        per_year.append({"year": year, **comparison(base_year, candidate_year)})
    passed = (
        confirmation["spearmanDelta"] >= 0 and confirmation["maeDelta"] <= 0
        and final_test["spearmanDelta"] > 0 and final_test["spearmanDeltaBootstrap95"][0] > 0
        and final_test["maeDelta"] <= 0
        and all(item["spearmanDelta"] >= 0 for item in per_crop)
        and all(item["spearmanDelta"] >= 0 for item in per_year)
    )
    return {
        "name": "USDA observed-prior recency validation v1",
        "target": "next-year county yield percentile within crop and year",
        "baseline": "unweighted mean of all earlier county percentiles",
        "candidate": "exponentially weighted mean of earlier county percentiles",
        "developmentYears": list(DEVELOPMENT_YEARS), "candidateSelection": candidates,
        "selectedHalfLifeYears": half_life,
        "confirmationYears": list(CONFIRMATION_YEARS), "confirmation": confirmation,
        "finalTestYears": list(FINAL_TEST_YEARS), "finalTest": final_test,
        "perCropFinalTest": per_crop, "perYearFinalTest": per_year,
        "gate": {
            "passed": passed,
            "rule": "Confirmation must not regress rank or MAE. On the locked 2023–2025 test, pooled rank delta and grouped-bootstrap lower bound must be >0, MAE must not regress, and every crop and year rank delta must be non-negative.",
        },
        "interpretation": "This tests county-level regional ordering only, not parcel yield or purchase returns.",
    }


def markdown(report: dict) -> str:
    final = report["finalTest"]
    lines = [
        "# USDA observed-prior recency validation v1", "",
        f'**Production gate: {"PASS" if report["gate"]["passed"] else "NOT PASSED"}**', "",
        f'The half-life was selected on 2018–2020 only. Selected: **{report["selectedHalfLifeYears"]} years**.', "",
        f'On the locked 2023–2025 test ({final["observations"]:,} rows), Spearman changed from **{final["baseline"]["spearman"]:.4f}** to **{final["recency"]["spearman"]:.4f}** (delta {final["spearmanDelta"]:+.4f}; grouped-bootstrap 95% interval {final["spearmanDeltaBootstrap95"][0]:+.4f} to {final["spearmanDeltaBootstrap95"][1]:+.4f}). Percentile MAE changed by {final["maeDelta"]:+.4f}.', "",
        "| Crop | N | Baseline rho | Recency rho | Delta | MAE delta |", "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["perCropFinalTest"]:
        lines.append(f'| {item["crop"]} | {item["observations"]:,} | {item["baseline"]["spearman"]:.4f} | {item["recency"]["spearman"]:.4f} | {item["spearmanDelta"]:+.4f} | {item["maeDelta"]:+.4f} |')
    lines += ["", f'Gate rule: {report["gate"]["rule"]}', "", f'> {report["interpretation"]}', ""]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    candidates = report["candidateSelection"]
    crops = report["perCropFinalTest"]
    years = report["perYearFinalTest"]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].plot([item["halfLifeYears"] for item in candidates], [item["recency"]["spearman"] for item in candidates], marker="o", color="#315d49", label="recency prior")
    axes[0].axhline(candidates[0]["baseline"]["spearman"], color="#777", linestyle="--", label="unweighted baseline")
    axes[0].axvline(report["selectedHalfLifeYears"], color="#d98352", linestyle=":", label="selected")
    axes[0].set(xlabel="history half-life (years)", ylabel="development Spearman", title="Selection · 2018–2020 only", xticks=list(HALF_LIFE_CANDIDATES)); axes[0].grid(alpha=.18); axes[0].legend()
    labels = [item["crop"] for item in crops] + [str(item["year"]) for item in years]
    deltas = [item["spearmanDelta"] for item in crops] + [item["spearmanDelta"] for item in years]
    bars = axes[1].bar(labels, deltas, color=["#315d49" if value >= 0 else "#d98352" for value in deltas])
    axes[1].bar_label(bars, fmt="%+.4f", padding=3, fontsize=8); axes[1].axhline(0, color="#777", linewidth=.8)
    axes[1].set(ylabel="recency minus baseline Spearman", title="Locked test · 2023–2025"); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("USDA county-prior recency test", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--output", type=Path, default=root / "evaluation/recency-validation-v1.json")
    args = parser.parse_args()
    report = validate(args.data)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"selectedHalfLifeYears": report["selectedHalfLifeYears"], "confirmation": report["confirmation"], "finalTest": report["finalTest"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
