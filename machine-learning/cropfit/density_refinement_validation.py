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
from .training import TREE_STD_FLOOR, conformal_quantile, generate_examples


EVALUATION_DENSITY = 72
CHAMPION_DENSITY = 120
CHAMPION_TREES = 70
CANDIDATE_DENSITY = 240
CANDIDATE_TREES = 32


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


def active_calibrated_coverage(
    model: ExtraTreesRegressor,
    x: np.ndarray,
    y: np.ndarray,
    validation: np.ndarray,
    test: np.ndarray,
) -> dict:
    validation_trees = np.asarray([tree.predict(x[validation]) for tree in model.estimators_])
    validation_errors = np.abs(validation_trees.mean(axis=0) - y[validation])
    validation_std = validation_trees.std(axis=0)
    active_validation = y[validation] > 0
    normalized = validation_errors[active_validation] / (
        validation_std[active_validation] + TREE_STD_FLOOR
    )
    quantiles = {
        "p80": conformal_quantile(normalized, .8),
        "p90": conformal_quantile(normalized, .9),
    }
    test_trees = np.asarray([tree.predict(x[test]) for tree in model.estimators_])
    test_errors = np.abs(test_trees.mean(axis=0) - y[test])
    test_std = test_trees.std(axis=0)
    active_test = y[test] > 0
    result = {"validationExamples": int(np.sum(active_validation)), "testExamples": int(np.sum(active_test))}
    for name, quantile in quantiles.items():
        radii = np.ceil(quantile * (test_std + TREE_STD_FLOOR) * 1000) / 1000
        result[f"coverage{name[-2:]}"] = round(
            float(np.mean(test_errors[active_test] <= radii[active_test])), 4,
        )
        result[f"meanRadius{name[-2:]}"] = round(float(np.mean(radii[active_test])), 4)
    return result


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    champion_size = None
    candidate_size = None
    for seed in DEVELOPMENT_SEEDS + CONFIRMATION_SEEDS + FINAL_SEEDS:
        x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        fitting_groups = np.unique(groups[train])
        item = {"seed": seed, "phase": phase(seed), "testProfiles": len(np.unique(groups[test]))}
        models = {}
        for name, density, trees in (
            ("championV09", CHAMPION_DENSITY, CHAMPION_TREES),
            ("candidateV010", CANDIDATE_DENSITY, CANDIDATE_TREES),
        ):
            training_x, training_y, training_groups = generate_examples(profiles, density, seed)
            fitting_indices = np.flatnonzero(np.isin(training_groups, fitting_groups))
            model = estimator(trees, seed)
            started = perf_counter()
            model.fit(training_x[fitting_indices], training_y[fitting_indices])
            item[name] = {
                **error_metrics(y[test], model.predict(x[test])),
                "fitSeconds": round(perf_counter() - started, 3),
                "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]]),
                "calibration": calibrated_coverage(model, x, y, validation, test),
                "activeCalibration": active_calibrated_coverage(model, x, y, validation, test),
            }
            models[name] = model
        if champion_size is None:
            champion_size = serialized_size(models["championV09"])
            candidate_size = serialized_size(models["candidateV010"])
        item["maeImprovementPercent"] = round(
            100 * (item["championV09"]["mae"] - item["candidateV010"]["mae"])
            / item["championV09"]["mae"],
            3,
        )
        item["p90ImprovementPercent"] = round(
            100 * (
                item["championV09"]["p90AbsoluteError"]
                - item["candidateV010"]["p90AbsoluteError"]
            ) / item["championV09"]["p90AbsoluteError"],
            3,
        )
        item["latencyRatio"] = round(
            item["candidateV010"]["apiBatchLatencyMs"]
            / item["championV09"]["apiBatchLatencyMs"],
            3,
        )
        calibration = item["candidateV010"]["calibration"]
        active = item["candidateV010"]["activeCalibration"]
        item["passedPerSeedGate"] = (
            item["maeImprovementPercent"] > 0
            and item["p90ImprovementPercent"] > 0
            and .77 <= calibration["coverage80"] <= .83
            and .87 <= calibration["coverage90"] <= .93
            and .77 <= active["coverage80"] <= .83
            and .87 <= active["coverage90"] <= .93
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert champion_size is not None and candidate_size is not None
    locked = [item for item in results if item["phase"] in ("confirmation", "final")]
    final = [item for item in results if item["phase"] == "final"]
    locked_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in locked]))
    locked_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in locked]))
    locked_latency_ratio = float(np.mean([item["latencyRatio"] for item in locked]))
    final_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in final]))
    final_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in final]))
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in locked)
            and locked_mae_gain >= 5
            and locked_p90_gain >= 5
            and final_mae_gain >= 5
            and final_p90_gain >= 5
            and locked_latency_ratio <= 1.1
            and candidate_size < champion_size
            and candidate_size <= 65_000_000
        ),
        "rule": (
            "Every confirmation/final seed must improve MAE and p90 with global and active "
            "calibrated coverage within 3 points of nominal; locked and final mean gains must "
            "each be >=5% for MAE and p90; mean API-batch latency <=1.1x; compressed candidate "
            "must be smaller than the champion and <=65 MB."
        ),
    }
    return {
        "name": "CropFit v0.10 density-refinement validation",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.9.1, 120 fitting scenarios per crop, 70 Extra Trees",
            "candidate": "240 fitting scenarios per crop, 32 Extra Trees",
            "fixedEvaluation": "Both models use identical 72-scenario validation and test rows.",
            "selection": (
                "Six density/tree Pareto candidates were compared on development seeds only. "
                "The 240/32 candidate had the best mean MAE and p90 while remaining below the "
                "champion size. Confirmation and final seeds were opened only after selection."
            ),
            "developmentCandidates": [
                {"density": 120, "trees": 70}, {"density": 140, "trees": 60},
                {"density": 160, "trees": 50}, {"density": 180, "trees": 45},
                {"density": 200, "trees": 40}, {"density": 240, "trees": 32},
            ],
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "lockedSeedWins": sum(item["passedPerSeedGate"] for item in locked),
            "lockedSeeds": len(locked),
            "lockedMeanMaeImprovementPercent": round(locked_mae_gain, 2),
            "lockedMeanP90ImprovementPercent": round(locked_p90_gain, 2),
            "finalMeanMaeImprovementPercent": round(final_mae_gain, 2),
            "finalMeanP90ImprovementPercent": round(final_p90_gain, 2),
            "lockedMeanCoverage80": round(float(np.mean([
                item["candidateV010"]["calibration"]["coverage80"] for item in locked
            ])), 4),
            "lockedMeanCoverage90": round(float(np.mean([
                item["candidateV010"]["calibration"]["coverage90"] for item in locked
            ])), 4),
            "lockedMeanActiveCoverage80": round(float(np.mean([
                item["candidateV010"]["activeCalibration"]["coverage80"] for item in locked
            ])), 4),
            "lockedMeanActiveCoverage90": round(float(np.mean([
                item["candidateV010"]["activeCalibration"]["coverage90"] for item in locked
            ])), 4),
            "lockedMeanApiBatchLatencyRatio": round(locked_latency_ratio, 3),
            "championSerializedSizeBytes": champion_size,
            "candidateSerializedSizeBytes": candidate_size,
            "sizeReductionPercent": round(100 * (champion_size - candidate_size) / champion_size, 2),
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.10 density-refinement validation", "",
        "The candidate doubles fitting-only scenario density while reducing tree count. Validation and held-out crop profiles and rows remain identical. This measures EcoCrop-teacher fidelity, not observed yield.", "",
        "| Phase | Seed | v0.9.1 MAE | Candidate MAE | MAE gain | p90 gain | Active 80% | Active 90% | Latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        active = item["candidateV010"]["activeCalibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV09"]["mae"]:.5f} | '
            f'{item["candidateV010"]["mae"]:.5f} | {item["maeImprovementPercent"]:.2f}% | '
            f'{item["p90ImprovementPercent"]:.2f}% | {active["coverage80"]:.1%} | '
            f'{active["coverage90"]:.1%} | {item["latencyRatio"]:.2f}x |'
        )
    summary = report["summary"]
    lines += [
        "", f'Locked-seed wins: **{summary["lockedSeedWins"]}/{summary["lockedSeeds"]}**. Mean locked MAE improved **{summary["lockedMeanMaeImprovementPercent"]:.2f}%** and p90 improved **{summary["lockedMeanP90ImprovementPercent"]:.2f}%**.',
        "", f'Final-only mean gains were **{summary["finalMeanMaeImprovementPercent"]:.2f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.2f}% p90**. Active coverage was **{summary["lockedMeanActiveCoverage80"]:.1%} / {summary["lockedMeanActiveCoverage90"]:.1%}**.',
        "", f'The candidate is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB**, **{summary["sizeReductionPercent"]:.1f}% smaller**, with a **{summary["lockedMeanApiBatchLatencyRatio"]:.2f}x** latency ratio.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> Suitability remains an agroclimatic screening score, not a yield forecast or property recommendation.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    axes[0].plot(x, [item["maeImprovementPercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["p90ImprovementPercent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(0, color="#8f2f14", linestyle="--", label="per-seed floor")
    axes[0].axhline(5, color="#d98352", linestyle=":", label="mean gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="seed suffix", ylabel="Error reduction (%)", title="Denser fitting on unseen crop profiles")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["candidateV010"]["activeCalibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["candidateV010"]["activeCalibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65)
    axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="seed suffix", ylabel="Held-out coverage", title="Active-case uncertainty remains calibrated")
    axes[1].legend(); axes[1].grid(alpha=.18)
    for boundary in (2.5, 4.5):
        for axis in axes:
            axis.axvline(boundary, color="#777777", linestyle=":", alpha=.65)
    figure.suptitle("CropFit v0.10 candidate · 240 scenarios × 32 Extra Trees", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/density-refinement-validation-v0.10.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/density-refinement-validation-v0.10.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
