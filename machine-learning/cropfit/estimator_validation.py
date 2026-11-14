from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit

from .profiles import load_profiles
from .training import TREE_STD_FLOOR, conformal_quantile, generate_examples


DEVELOPMENT_SEEDS = list(range(20261210, 20261213))
CONFIRMATION_SEEDS = list(range(20261213, 20261215))
FINAL_SEEDS = list(range(20261215, 20261220))


def split_indices(x: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train_validation, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    inner_groups = groups[train_validation]
    inner_train, inner_validation = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(x[train_validation], y[train_validation], inner_groups))
    return train_validation[inner_train], train_validation[inner_validation], test


def error_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    errors = np.abs(predicted - actual)
    return {"mae": round(float(np.mean(errors)), 5), "p90AbsoluteError": round(float(np.quantile(errors, .9)), 5)}


def prediction_latency_ms(model, values: np.ndarray, repeats: int = 25) -> float:
    model.predict(values)
    timings = []
    for _ in range(repeats):
        started = perf_counter(); model.predict(values); timings.append((perf_counter() - started) * 1000)
    return round(float(np.median(timings)), 3)


def calibrated_coverage(model, x: np.ndarray, y: np.ndarray, validation: np.ndarray, test: np.ndarray) -> dict:
    validation_trees = np.asarray([tree.predict(x[validation]) for tree in model.estimators_])
    validation_errors = np.abs(validation_trees.mean(axis=0) - y[validation])
    validation_std = validation_trees.std(axis=0)
    normalized = validation_errors / (validation_std + TREE_STD_FLOOR)
    quantile80 = conformal_quantile(normalized, .8)
    quantile90 = conformal_quantile(normalized, .9)
    test_trees = np.asarray([tree.predict(x[test]) for tree in model.estimators_])
    test_errors = np.abs(test_trees.mean(axis=0) - y[test])
    test_std = test_trees.std(axis=0)
    radius80 = np.ceil(quantile80 * (test_std + TREE_STD_FLOOR) * 1000) / 1000
    radius90 = np.ceil(quantile90 * (test_std + TREE_STD_FLOOR) * 1000) / 1000
    return {
        "coverage80": round(float(np.mean(test_errors <= radius80)), 4),
        "coverage90": round(float(np.mean(test_errors <= radius90)), 4),
        "meanRadius80": round(float(np.mean(radius80)), 4),
        "meanRadius90": round(float(np.mean(radius90)), 4),
    }


def phase(seed: int) -> str:
    if seed in DEVELOPMENT_SEEDS:
        return "development"
    if seed in CONFIRMATION_SEEDS:
        return "confirmation"
    return "final"


def evaluate(profiles_path: Path, samples_per_crop: int, estimators: int) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    for seed in DEVELOPMENT_SEEDS + CONFIRMATION_SEEDS + FINAL_SEEDS:
        x, y, groups = generate_examples(profiles, samples_per_crop, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        models = {
            "randomForest": RandomForestRegressor(n_estimators=estimators, min_samples_leaf=1, max_features=1.0, n_jobs=-1, random_state=seed),
            "extraTrees": ExtraTreesRegressor(n_estimators=estimators, min_samples_leaf=1, max_features=1.0, n_jobs=-1, random_state=seed),
        }
        item = {"seed": seed, "phase": phase(seed), "trainProfiles": len(np.unique(groups[train])), "validationProfiles": len(np.unique(groups[validation])), "testProfiles": len(np.unique(groups[test]))}
        for name, model in models.items():
            started = perf_counter(); model.fit(x[train], y[train]); fit_seconds = perf_counter() - started
            predicted = model.predict(x[test])
            item[name] = {
                **error_metrics(y[test], predicted),
                "fitSeconds": round(fit_seconds, 3),
                "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]]),
            }
        item["extraTrees"]["calibration"] = calibrated_coverage(models["extraTrees"], x, y, validation, test)
        item["maeImprovementPercent"] = round(100 * (item["randomForest"]["mae"] - item["extraTrees"]["mae"]) / item["randomForest"]["mae"], 2)
        item["p90ImprovementPercent"] = round(100 * (item["randomForest"]["p90AbsoluteError"] - item["extraTrees"]["p90AbsoluteError"]) / item["randomForest"]["p90AbsoluteError"], 2)
        item["latencyRatio"] = round(item["extraTrees"]["apiBatchLatencyMs"] / item["randomForest"]["apiBatchLatencyMs"], 3)
        item["passedPerSeedGate"] = (
            item["maeImprovementPercent"] >= 20
            and item["p90ImprovementPercent"] >= 20
            and .77 <= item["extraTrees"]["calibration"]["coverage80"] <= .83
            and .87 <= item["extraTrees"]["calibration"]["coverage90"] <= .93
        )
        results.append(item)
        print(json.dumps(item), flush=True)
    locked = [item for item in results if item["phase"] in ("confirmation", "final")]
    final = [item for item in results if item["phase"] == "final"]
    mean_final_improvement = float(np.mean([item["maeImprovementPercent"] for item in final]))
    mean_locked_latency_ratio = float(np.mean([item["latencyRatio"] for item in locked]))
    gate = {
        "passed": all(item["passedPerSeedGate"] for item in locked) and mean_final_improvement >= 30 and mean_locked_latency_ratio <= 1.75,
        "rule": "Every confirmation/final seed must improve MAE and p90 by at least 20% with calibrated coverage within 3 points of nominal; final mean MAE improvement >=30%; mean API-batch latency <=1.75x.",
    }
    return {
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "baseline": "RandomForestRegressor, 120 trees",
            "candidate": "ExtraTreesRegressor, 120 trees",
            "features": "identical 23-feature v0.5 design",
            "split": "identical grouped crop-profile train/validation/test split per estimator",
            "samplesPerCrop": samples_per_crop, "estimators": estimators,
            "developmentSeeds": DEVELOPMENT_SEEDS, "confirmationSeeds": CONFIRMATION_SEEDS, "finalSeeds": FINAL_SEEDS,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "lockedSeedWins": sum(item["passedPerSeedGate"] for item in locked), "lockedSeeds": len(locked),
            "finalMeanMaeImprovementPercent": round(mean_final_improvement, 2),
            "finalMeanP90ImprovementPercent": round(float(np.mean([item["p90ImprovementPercent"] for item in final])), 2),
            "lockedMeanCoverage80": round(float(np.mean([item["extraTrees"]["calibration"]["coverage80"] for item in locked])), 4),
            "lockedMeanCoverage90": round(float(np.mean([item["extraTrees"]["calibration"]["coverage90"] for item in locked])), 4),
            "lockedMeanApiBatchLatencyRatio": round(mean_locked_latency_ratio, 3),
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.6 estimator validation", "",
        "Extra Trees and the production Random Forest use identical 23-feature inputs, 120 trees, generated scenarios, and grouped crop-profile splits. This measures EcoCrop-teacher fidelity, not observed yield accuracy.", "",
        "| Phase | Seed | RF MAE | Extra Trees MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency ratio |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        lines.append(f'| {item["phase"]} | {item["seed"]} | {item["randomForest"]["mae"]:.4f} | {item["extraTrees"]["mae"]:.4f} | {item["maeImprovementPercent"]:.1f}% | {item["p90ImprovementPercent"]:.1f}% | {item["extraTrees"]["calibration"]["coverage80"]:.1%} | {item["extraTrees"]["calibration"]["coverage90"]:.1%} | {item["latencyRatio"]:.2f}× |')
    summary = report["summary"]
    lines += [
        "", f'Locked-seed wins: **{summary["lockedSeedWins"]}/{summary["lockedSeeds"]}**. On the five final seeds, mean MAE improved **{summary["finalMeanMaeImprovementPercent"]:.1f}%** and p90 improved **{summary["finalMeanP90ImprovementPercent"]:.1f}%**.',
        "", f'Locked mean calibrated coverage was **{summary["lockedMeanCoverage80"]:.1%} / {summary["lockedMeanCoverage90"]:.1%}**. Mean API-sized batch latency was **{summary["lockedMeanApiBatchLatencyRatio"]:.2f}×** the Random Forest.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> Suitability remains an agroclimatic screening score. This estimator change does not make it a yield forecast or property recommendation.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results)); width = .36
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].bar(x - width / 2, [item["randomForest"]["mae"] for item in results], width, color="#d98352", label="v0.5.1 Random Forest")
    axes[0].bar(x + width / 2, [item["extraTrees"]["mae"] for item in results], width, color="#315d49", label="v0.6 Extra Trees")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="seed suffix", ylabel="Held-out MAE", title="Lower error on every crop-profile split"); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    axes[1].plot(x, [item["maeImprovementPercent"] for item in results], marker="o", linewidth=2.5, color="#315d49", label="MAE improvement")
    axes[1].plot(x, [item["p90ImprovementPercent"] for item in results], marker="o", linewidth=2.5, color="#6f9551", label="p90 improvement")
    axes[1].axhline(20, linestyle="--", color="#8f2f14", label="per-seed gate")
    axes[1].set(xticks=x, xticklabels=labels, ylim=(0, 55), xlabel="seed suffix", ylabel="Error reduction (%)", title="All locked seeds clear the 20% gate"); axes[1].legend(); axes[1].grid(alpha=.18)
    for boundary in (2.5, 4.5):
        for axis in axes: axis.axvline(boundary, color="#777777", linestyle=":", alpha=.65)
    figure.text(.27, .01, "development", ha="center", color="#666666"); figure.text(.47, .01, "confirmation", ha="center", color="#666666"); figure.text(.76, .01, "final", ha="center", color="#666666")
    figure.suptitle("CropFit v0.6 · Extra Trees estimator promotion", fontweight="bold")
    figure.tight_layout(rect=(0, .04, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/estimator-validation-v0.6.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/estimator-validation-v0.6.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--estimators", type=int, default=120)
    args = parser.parse_args()
    report = evaluate(args.profiles, args.samples_per_crop, args.estimators)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
