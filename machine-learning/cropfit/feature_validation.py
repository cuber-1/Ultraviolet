from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

from .features import FEATURE_NAMES
from .profiles import load_profiles
from .training import generate_examples


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residuals = np.abs(actual - predicted)
    return {
        "mae": round(float(mean_absolute_error(actual, predicted)), 4),
        "r2": round(float(r2_score(actual, predicted)), 4),
        "p90AbsoluteError": round(float(np.quantile(residuals, .9)), 4),
    }


def evaluate(raw: Path, samples_per_crop: int, seeds: list[int], estimators: int) -> dict:
    profiles = load_profiles(raw)
    results = []
    for seed in seeds:
        enriched, labels, groups = generate_examples(profiles, samples_per_crop, seed)
        baseline = enriched[:, :-4]
        train_validation, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(enriched, labels, groups))
        inner_groups = groups[train_validation]
        inner_train, _ = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(enriched[train_validation], labels[train_validation], inner_groups))
        train = train_validation[inner_train]
        pair = {}
        for name, values in (("absoluteFeatures", baseline), ("rangeRelativeFeatures", enriched)):
            model = RandomForestRegressor(n_estimators=estimators, min_samples_leaf=1, max_features=1.0, n_jobs=-1, random_state=seed)
            model.fit(values[train], labels[train])
            pair[name] = metrics(labels[test], model.predict(values[test]))
        pair["maeImprovementPercent"] = round(100 * (pair["absoluteFeatures"]["mae"] - pair["rangeRelativeFeatures"]["mae"]) / pair["absoluteFeatures"]["mae"], 2)
        results.append({"seed": seed, **pair})
        print(json.dumps(results[-1]), flush=True)
    return {
        "protocol": {
            "target": "mechanistic EcoCrop screening teacher; not observed yield",
            "split": "entire crop profiles held out; identical grouped split per feature set",
            "samplesPerCrop": samples_per_crop,
            "estimators": estimators,
            "seeds": seeds,
            "baselineFeatures": FEATURE_NAMES[:-4],
            "candidateFeatures": FEATURE_NAMES,
        },
        "results": results,
        "summary": {
            "wins": sum(item["rangeRelativeFeatures"]["mae"] < item["absoluteFeatures"]["mae"] for item in results),
            "seeds": len(results),
            "baselineMeanMae": round(float(np.mean([item["absoluteFeatures"]["mae"] for item in results])), 4),
            "candidateMeanMae": round(float(np.mean([item["rangeRelativeFeatures"]["mae"] for item in results])), 4),
            "meanMaeImprovementPercent": round(float(np.mean([item["maeImprovementPercent"] for item in results])), 2),
        },
        "interpretation": "This measures fidelity to the synthetic EcoCrop teacher on unseen crop profiles. It does not establish yield accuracy.",
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.5 range-relative feature validation",
        "",
        "The candidate was compared with the v0.4 absolute-feature design on identical grouped splits. Entire crop profiles were held out.",
        "",
        "| Seed | v0.4-style MAE | Candidate MAE | Improvement | Candidate R² | Candidate p90 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        old, new = item["absoluteFeatures"], item["rangeRelativeFeatures"]
        lines.append(f'| {item["seed"]} | {old["mae"]:.4f} | {new["mae"]:.4f} | {item["maeImprovementPercent"]:.2f}% | {new["r2"]:.4f} | {new["p90AbsoluteError"]:.4f} |')
    summary = report["summary"]
    lines += [
        "",
        f'Candidate wins: **{summary["wins"]}/{summary["seeds"]}**. Mean MAE: **{summary["baselineMeanMae"]:.4f} → {summary["candidateMeanMae"]:.4f}** ({summary["meanMaeImprovementPercent"]:.2f}% lower).',
        "",
        "These range-relative features encode where current conditions fall inside each crop's absolute and optimum ranges. They do not use crop identity or any held-out labels.",
        "",
        "> This is surrogate fidelity to a mechanistic EcoCrop screening target, not validation against observed farm yield. The national observed-yield gate remains failed.",
        "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    labels = [str(item["seed"])[-2:] for item in report["results"]]
    baseline = [item["absoluteFeatures"]["mae"] for item in report["results"]]
    candidate = [item["rangeRelativeFeatures"]["mae"] for item in report["results"]]
    positions = np.arange(len(labels)); width = .36
    figure, axis = plt.subplots(figsize=(11, 5.8))
    old_bars = axis.bar(positions - width / 2, baseline, width, label="v0.4 absolute features", color="#d98352")
    new_bars = axis.bar(positions + width / 2, candidate, width, label="v0.5 range-relative features", color="#315d49")
    axis.bar_label(old_bars, fmt="%.2f", padding=3, fontsize=9)
    axis.bar_label(new_bars, fmt="%.2f", padding=3, fontsize=9)
    axis.set(title="Held-out crop-profile MAE across five seeds", xlabel="seed suffix (202611xx)", ylabel="MAE · suitability points", xticks=positions, xticklabels=labels, ylim=(0, max(baseline) * 1.16))
    axis.grid(axis="y", alpha=.18); axis.legend()
    figure.text(.5, .01, "EcoCrop-teacher fidelity on unseen crop profiles · not observed yield accuracy", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/feature-validation-v0.5.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/feature-validation-v0.5.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/feature-validation-v0.5.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--estimators", type=int, default=120)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(20261110, 20261115)))
    args = parser.parse_args()
    report = evaluate(args.raw, args.samples_per_crop, args.seeds, args.estimators)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
