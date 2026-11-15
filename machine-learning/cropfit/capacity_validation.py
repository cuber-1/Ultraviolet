from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

from .estimator_validation import (
    CONFIRMATION_SEEDS,
    DEVELOPMENT_SEEDS,
    FINAL_SEEDS,
    calibrated_coverage,
    error_metrics,
    phase,
    prediction_latency_ms,
    split_indices,
)
from .profiles import load_profiles
from .training import generate_examples


CHAMPION_TREES = 120
CANDIDATE_TREES = 200


def estimator(trees: int, seed: int) -> ExtraTreesRegressor:
    return ExtraTreesRegressor(
        n_estimators=trees,
        min_samples_leaf=1,
        max_features=1.0,
        n_jobs=-1,
        random_state=seed,
    )


def serialized_size(model: ExtraTreesRegressor) -> int:
    with tempfile.NamedTemporaryFile(suffix=".joblib") as output:
        joblib.dump({"model": model}, output.name, compress=3)
        return Path(output.name).stat().st_size


def evaluate(profiles_path: Path, samples_per_crop: int) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    candidate_size = None
    for seed in DEVELOPMENT_SEEDS + CONFIRMATION_SEEDS + FINAL_SEEDS:
        x, y, groups = generate_examples(profiles, samples_per_crop, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        models = {
            "champion120": estimator(CHAMPION_TREES, seed),
            "candidate200": estimator(CANDIDATE_TREES, seed),
        }
        item = {
            "seed": seed,
            "phase": phase(seed),
            "testProfiles": len(np.unique(groups[test])),
        }
        for name, model in models.items():
            started = perf_counter()
            model.fit(x[train], y[train])
            item[name] = {
                **error_metrics(y[test], model.predict(x[test])),
                "fitSeconds": round(perf_counter() - started, 3),
                "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]]),
            }
        item["candidate200"]["calibration"] = calibrated_coverage(
            models["candidate200"], x, y, validation, test
        )
        if candidate_size is None:
            candidate_size = serialized_size(models["candidate200"])
        item["maeImprovementPercent"] = round(
            100
            * (item["champion120"]["mae"] - item["candidate200"]["mae"])
            / item["champion120"]["mae"],
            3,
        )
        item["p90ImprovementPercent"] = round(
            100
            * (
                item["champion120"]["p90AbsoluteError"]
                - item["candidate200"]["p90AbsoluteError"]
            )
            / item["champion120"]["p90AbsoluteError"],
            3,
        )
        item["latencyRatio"] = round(
            item["candidate200"]["apiBatchLatencyMs"]
            / item["champion120"]["apiBatchLatencyMs"],
            3,
        )
        coverage = item["candidate200"]["calibration"]
        item["passedPerSeedGate"] = (
            item["maeImprovementPercent"] > 0
            and item["p90ImprovementPercent"] > 0
            and .77 <= coverage["coverage80"] <= .83
            and .87 <= coverage["coverage90"] <= .93
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert candidate_size is not None
    locked = [item for item in results if item["phase"] in ("confirmation", "final")]
    final = [item for item in results if item["phase"] == "final"]
    mean_locked_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in locked]))
    mean_locked_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in locked]))
    mean_locked_latency_ratio = float(np.mean([item["latencyRatio"] for item in locked]))
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in locked)
            and mean_locked_mae_gain >= 2
            and mean_locked_p90_gain >= 1
            and mean_locked_latency_ratio <= 2
            and candidate_size <= 130_000_000
        ),
        "rule": (
            "Every confirmation/final seed must improve MAE and p90 with calibrated coverage "
            "within 3 points of nominal; locked mean gains must be >=2% MAE and >=1% p90; "
            "mean API-batch latency <=2x; compressed artifact <=130 MB."
        ),
    }
    return {
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "ExtraTreesRegressor, 120 trees",
            "candidate": "ExtraTreesRegressor, 200 trees",
            "selection": (
                "Tree count and feature-subsampling options were compared only on development seeds; "
                "200 full-feature trees had the best development MAE within the declared Mac size ceiling."
            ),
            "split": "Identical grouped crop-profile train/validation/test split per estimator and seed",
            "samplesPerCrop": samples_per_crop,
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "lockedSeedWins": sum(item["passedPerSeedGate"] for item in locked),
            "lockedSeeds": len(locked),
            "lockedMeanMaeImprovementPercent": round(mean_locked_mae_gain, 2),
            "lockedMeanP90ImprovementPercent": round(mean_locked_p90_gain, 2),
            "finalMeanMaeImprovementPercent": round(
                float(np.mean([item["maeImprovementPercent"] for item in final])), 2
            ),
            "finalMeanP90ImprovementPercent": round(
                float(np.mean([item["p90ImprovementPercent"] for item in final])), 2
            ),
            "lockedMeanCoverage80": round(
                float(np.mean([item["candidate200"]["calibration"]["coverage80"] for item in locked])), 4
            ),
            "lockedMeanCoverage90": round(
                float(np.mean([item["candidate200"]["calibration"]["coverage90"] for item in locked])), 4
            ),
            "lockedMeanApiBatchLatencyRatio": round(mean_locked_latency_ratio, 3),
            "candidateSerializedSizeBytes": candidate_size,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.7 capacity validation",
        "",
        "A 200-tree Extra Trees candidate was compared with the 120-tree v0.6 champion on identical grouped crop-profile splits. This measures EcoCrop-teacher fidelity, not observed yield accuracy.",
        "",
        "| Phase | Seed | v0.6 MAE | v0.7 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        calibration = item["candidate200"]["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["champion120"]["mae"]:.5f} | '
            f'{item["candidate200"]["mae"]:.5f} | {item["maeImprovementPercent"]:.2f}% | '
            f'{item["p90ImprovementPercent"]:.2f}% | {calibration["coverage80"]:.1%} | '
            f'{calibration["coverage90"]:.1%} | {item["latencyRatio"]:.2f}x |'
        )
    summary = report["summary"]
    lines += [
        "",
        f'Locked-seed wins: **{summary["lockedSeedWins"]}/{summary["lockedSeeds"]}**. Mean locked MAE improved **{summary["lockedMeanMaeImprovementPercent"]:.2f}%** and p90 improved **{summary["lockedMeanP90ImprovementPercent"]:.2f}%**.',
        "",
        f'Locked mean calibrated coverage was **{summary["lockedMeanCoverage80"]:.1%} / {summary["lockedMeanCoverage90"]:.1%}**. The candidate is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB** compressed and its mean API-batch latency ratio is **{summary["lockedMeanApiBatchLatencyRatio"]:.2f}x**.',
        "",
        f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.',
        "",
        "> Suitability remains an agroclimatic screening score. More trees improve approximation fidelity; they do not turn CropFit into a field-yield model.",
        "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot(x, [item["maeImprovementPercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["p90ImprovementPercent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(0, color="#8f2f14", linestyle="--")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="seed suffix", ylabel="Error reduction (%)", title="Candidate wins every frozen split")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["candidate200"]["calibration"]["coverage80"] for item in results], marker="o", label="80% interval", color="#d98352")
    axes[1].plot(x, [item["candidate200"]["calibration"]["coverage90"] for item in results], marker="o", label="90% interval", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65)
    axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="seed suffix", ylabel="Held-out coverage", title="Uncertainty remains calibrated")
    axes[1].legend(); axes[1].grid(alpha=.18)
    for boundary in (2.5, 4.5):
        for axis in axes:
            axis.axvline(boundary, color="#777777", linestyle=":", alpha=.65)
    figure.suptitle("CropFit v0.7 · 200-tree capacity promotion", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/capacity-validation-v0.7.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/capacity-validation-v0.7.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    args = parser.parse_args()
    report = evaluate(args.profiles, args.samples_per_crop)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
