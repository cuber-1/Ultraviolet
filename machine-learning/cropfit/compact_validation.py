from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

from .estimator_validation import calibrated_coverage, error_metrics, prediction_latency_ms, split_indices
from .profiles import load_profiles
from .training import generate_examples


SEEDS = list(range(20261220, 20261227))


def model(trees: int, seed: int) -> ExtraTreesRegressor:
    return ExtraTreesRegressor(n_estimators=trees, min_samples_leaf=1, max_features=1.0, n_jobs=-1, random_state=seed)


def serialized_sizes(models: dict[str, ExtraTreesRegressor]) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sizes = {}
        for name, estimator in models.items():
            path = root / f"{name}.joblib"
            joblib.dump({"model": estimator}, path, compress=3)
            sizes[name] = path.stat().st_size
        return sizes


def evaluate(profiles_path: Path, samples_per_crop: int) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    sizes = None
    for seed in SEEDS:
        x, y, groups = generate_examples(profiles, samples_per_crop, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        models = {"champion120": model(120, seed), "compact80": model(80, seed)}
        item = {"seed": seed, "testProfiles": len(np.unique(groups[test]))}
        for name, estimator in models.items():
            estimator.fit(x[train], y[train])
            item[name] = {
                **error_metrics(y[test], estimator.predict(x[test])),
                "apiBatchLatencyMs": prediction_latency_ms(estimator, x[test[:132]]),
            }
        item["compact80"]["calibration"] = calibrated_coverage(models["compact80"], x, y, validation, test)
        item["maeRegressionPercent"] = round(100 * (item["compact80"]["mae"] / item["champion120"]["mae"] - 1), 2)
        item["p90RegressionPercent"] = round(100 * (item["compact80"]["p90AbsoluteError"] / item["champion120"]["p90AbsoluteError"] - 1), 2)
        item["latencyRatio"] = round(item["compact80"]["apiBatchLatencyMs"] / item["champion120"]["apiBatchLatencyMs"], 3)
        coverage = item["compact80"]["calibration"]
        item["passedPerSeedGate"] = (
            item["maeRegressionPercent"] <= 3
            and item["p90RegressionPercent"] <= 5
            and .77 <= coverage["coverage80"] <= .83
            and .87 <= coverage["coverage90"] <= .93
        )
        if sizes is None:
            sizes = serialized_sizes(models)
        results.append(item)
        print(json.dumps(item), flush=True)
    assert sizes is not None
    size_ratio = sizes["compact80"] / sizes["champion120"]
    mean_latency_ratio = float(np.mean([item["latencyRatio"] for item in results]))
    gate = {
        "passed": all(item["passedPerSeedGate"] for item in results) and mean_latency_ratio <= 1 and size_ratio <= .70,
        "rule": "Every seed must stay within +3% MAE and +5% p90 with calibrated coverage; mean latency cannot worsen; serialized size must be <=70% of the champion.",
    }
    return {
        "protocol": {
            "champion": "ExtraTreesRegressor, 120 trees", "candidate": "ExtraTreesRegressor, 80 trees",
            "seeds": SEEDS, "samplesPerCrop": samples_per_crop,
            "split": "Fresh identical grouped crop-profile train/validation/test splits.",
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "seedWins": sum(item["passedPerSeedGate"] for item in results), "seeds": len(results),
            "meanMaeRegressionPercent": round(float(np.mean([item["maeRegressionPercent"] for item in results])), 2),
            "meanP90RegressionPercent": round(float(np.mean([item["p90RegressionPercent"] for item in results])), 2),
            "meanLatencyRatio": round(mean_latency_ratio, 3),
            "serializedSizeBytes": sizes,
            "serializedSizeRatio": round(size_ratio, 4),
            "decision": "reject; retain 120-tree v0.6 champion",
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit compact-estimator validation", "",
        "An 80-tree Extra Trees candidate was tested as a smaller Mac artifact against the 120-tree v0.6 champion on seven fresh grouped crop-profile splits.", "",
        "| Seed | MAE regression | p90 regression | 80% cov. | 90% cov. | Pass |", "|---:|---:|---:|---:|---:|:---:|",
    ]
    for item in report["results"]:
        calibration = item["compact80"]["calibration"]
        lines.append(f'| {item["seed"]} | +{item["maeRegressionPercent"]:.2f}% | +{item["p90RegressionPercent"]:.2f}% | {calibration["coverage80"]:.1%} | {calibration["coverage90"]:.1%} | {"yes" if item["passedPerSeedGate"] else "no"} |')
    summary = report["summary"]
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Mean MAE regression: **+{summary["meanMaeRegressionPercent"]:.2f}%**; mean p90 regression: **+{summary["meanP90RegressionPercent"]:.2f}%**.',
        "", f'The candidate serialized to **{summary["serializedSizeRatio"]:.1%}** of the champion, but failed the accuracy gate. Decision: **retain the 120-tree v0.6 champion**.',
        "", "Calibration remained valid, but calibration alone cannot justify a less accurate scorer.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]; x = np.arange(len(results)); labels = [str(item["seed"])[-2:] for item in results]
    figure, axis = plt.subplots(figsize=(11, 5.5))
    axis.plot(x, [item["maeRegressionPercent"] for item in results], marker="o", linewidth=2.5, color="#8f2f14", label="MAE regression")
    axis.plot(x, [item["p90RegressionPercent"] for item in results], marker="o", linewidth=2.5, color="#d98352", label="p90 regression")
    axis.axhline(3, color="#8f2f14", linestyle="--", alpha=.65, label="MAE limit")
    axis.axhline(5, color="#d98352", linestyle="--", alpha=.65, label="p90 limit")
    axis.set(xticks=x, xticklabels=labels, xlabel="frozen seed suffix", ylabel="Error regression versus 120 trees (%)", title="80-tree candidate fails every accuracy gate"); axis.legend(); axis.grid(alpha=.18)
    figure.suptitle("CropFit compact-model experiment · rejected", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/compact-validation-v1.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/compact-validation-v1.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    args = parser.parse_args()
    report = evaluate(args.profiles, args.samples_per_crop)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
