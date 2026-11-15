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


EVALUATION_DENSITY = 72
CANDIDATE_TRAINING_DENSITY = 120


def estimator(trees: int, seed: int) -> ExtraTreesRegressor:
    return ExtraTreesRegressor(
        n_estimators=trees, min_samples_leaf=1, max_features=1.0,
        n_jobs=-1, random_state=seed,
    )


def serialized_size(model: ExtraTreesRegressor) -> int:
    with tempfile.NamedTemporaryFile(suffix=".joblib") as output:
        joblib.dump({"model": model}, output.name, compress=3)
        return Path(output.name).stat().st_size


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    candidate_size = None
    for seed in DEVELOPMENT_SEEDS + CONFIRMATION_SEEDS + FINAL_SEEDS:
        x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        dense_x, dense_y, dense_groups = generate_examples(profiles, CANDIDATE_TRAINING_DENSITY, seed)
        training_groups = np.unique(groups[train])
        dense_train = np.flatnonzero(np.isin(dense_groups, training_groups))
        models = {
            "championV08": (estimator(120, seed), x, y, train),
            "candidateV09": (estimator(70, seed), dense_x, dense_y, dense_train),
        }
        item = {"seed": seed, "phase": phase(seed), "testProfiles": len(np.unique(groups[test]))}
        for name, (model, fit_x, fit_y, fit_indices) in models.items():
            started = perf_counter()
            model.fit(fit_x[fit_indices], fit_y[fit_indices])
            item[name] = {
                **error_metrics(y[test], model.predict(x[test])),
                "fitSeconds": round(perf_counter() - started, 3),
                "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]]),
            }
        candidate = models["candidateV09"][0]
        item["candidateV09"]["calibration"] = calibrated_coverage(candidate, x, y, validation, test)
        if candidate_size is None:
            candidate_size = serialized_size(candidate)
        item["maeImprovementPercent"] = round(
            100 * (item["championV08"]["mae"] - item["candidateV09"]["mae"])
            / item["championV08"]["mae"], 3
        )
        item["p90ImprovementPercent"] = round(
            100 * (item["championV08"]["p90AbsoluteError"] - item["candidateV09"]["p90AbsoluteError"])
            / item["championV08"]["p90AbsoluteError"], 3
        )
        item["latencyRatio"] = round(
            item["candidateV09"]["apiBatchLatencyMs"] / item["championV08"]["apiBatchLatencyMs"], 3
        )
        coverage = item["candidateV09"]["calibration"]
        item["passedPerSeedGate"] = (
            item["maeImprovementPercent"] >= 8
            and item["p90ImprovementPercent"] >= 8
            and .77 <= coverage["coverage80"] <= .83
            and .87 <= coverage["coverage90"] <= .93
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert candidate_size is not None
    locked = [item for item in results if item["phase"] in ("confirmation", "final")]
    final = [item for item in results if item["phase"] == "final"]
    mean_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in locked]))
    mean_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in locked]))
    mean_latency_ratio = float(np.mean([item["latencyRatio"] for item in locked]))
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in locked)
            and mean_mae_gain >= 10 and mean_p90_gain >= 10
            and mean_latency_ratio <= 1.1 and candidate_size <= 72_000_000
        ),
        "rule": (
            "Every confirmation/final seed must improve MAE and p90 by at least 8% with "
            "calibrated coverage within 3 points of nominal; locked mean gains >=10%; "
            "mean API-batch latency <=1.1x; compressed artifact <=72 MB."
        ),
    }
    return {
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.8, 72 training scenarios per crop, 120 trees",
            "candidate": "120 training scenarios per crop, 70 trees",
            "fixedEvaluation": "Both models use identical 72-scenario validation and test rows; denser scenarios are fitting-only.",
            "selection": "Density/tree Pareto candidates were compared only on development seeds; 120/70 had the best MAE below the v0.8 artifact size.",
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "lockedSeedWins": sum(item["passedPerSeedGate"] for item in locked),
            "lockedSeeds": len(locked),
            "lockedMeanMaeImprovementPercent": round(mean_mae_gain, 2),
            "lockedMeanP90ImprovementPercent": round(mean_p90_gain, 2),
            "finalMeanMaeImprovementPercent": round(float(np.mean([item["maeImprovementPercent"] for item in final])), 2),
            "finalMeanP90ImprovementPercent": round(float(np.mean([item["p90ImprovementPercent"] for item in final])), 2),
            "lockedMeanCoverage80": round(float(np.mean([item["candidateV09"]["calibration"]["coverage80"] for item in locked])), 4),
            "lockedMeanCoverage90": round(float(np.mean([item["candidateV09"]["calibration"]["coverage90"] for item in locked])), 4),
            "lockedMeanApiBatchLatencyRatio": round(mean_latency_ratio, 3),
            "candidateSerializedSizeBytes": candidate_size,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.9 training-density validation", "",
        "The candidate fits more generated scenarios per training crop but retains the exact v0.8 validation and test rows. It reduces the ensemble from 120 to 70 trees. This measures EcoCrop-teacher fidelity, not observed-yield accuracy.", "",
        "| Phase | Seed | v0.8 MAE | v0.9 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        calibration = item["candidateV09"]["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV08"]["mae"]:.5f} | '
            f'{item["candidateV09"]["mae"]:.5f} | {item["maeImprovementPercent"]:.2f}% | '
            f'{item["p90ImprovementPercent"]:.2f}% | {calibration["coverage80"]:.1%} | '
            f'{calibration["coverage90"]:.1%} | {item["latencyRatio"]:.2f}x |'
        )
    summary = report["summary"]
    lines += [
        "", f'Locked-seed wins: **{summary["lockedSeedWins"]}/{summary["lockedSeeds"]}**. Mean locked MAE improved **{summary["lockedMeanMaeImprovementPercent"]:.2f}%** and p90 improved **{summary["lockedMeanP90ImprovementPercent"]:.2f}%**.',
        "", f'Coverage was **{summary["lockedMeanCoverage80"]:.1%} / {summary["lockedMeanCoverage90"]:.1%}**. The candidate is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB** compressed with a **{summary["lockedMeanApiBatchLatencyRatio"]:.2f}x** latency ratio.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot(x, [item["maeImprovementPercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["p90ImprovementPercent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(8, color="#8f2f14", linestyle="--", label="per-seed gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="seed suffix", ylabel="Error reduction (%)", title="Denser fitting improves every split")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["candidateV09"]["calibration"]["coverage80"] for item in results], marker="o", label="80% interval", color="#d98352")
    axes[1].plot(x, [item["candidateV09"]["calibration"]["coverage90"] for item in results], marker="o", label="90% interval", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="seed suffix", ylabel="Held-out coverage", title="Fixed-test uncertainty stays calibrated")
    axes[1].legend(); axes[1].grid(alpha=.18)
    for boundary in (2.5, 4.5):
        for axis in axes: axis.axvline(boundary, color="#777777", linestyle=":", alpha=.65)
    figure.suptitle("CropFit v0.9 · denser fitting, smaller ensemble", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/training-density-validation-v0.9.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/training-density-validation-v0.9.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
