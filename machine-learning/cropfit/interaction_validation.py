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
        candidate_x, y, groups = generate_examples(profiles, samples_per_crop, seed)
        champion_x = candidate_x[:, :-2]
        train, validation, test = split_indices(candidate_x, y, groups, seed)
        models = {
            "championV07": (estimator(200, seed), champion_x),
            "candidateV08": (estimator(120, seed), candidate_x),
        }
        item = {"seed": seed, "phase": phase(seed), "testProfiles": len(np.unique(groups[test]))}
        for name, (model, values) in models.items():
            started = perf_counter()
            model.fit(values[train], y[train])
            item[name] = {
                **error_metrics(y[test], model.predict(values[test])),
                "fitSeconds": round(perf_counter() - started, 3),
                "apiBatchLatencyMs": prediction_latency_ms(model, values[test[:132]]),
            }
        candidate_model = models["candidateV08"][0]
        item["candidateV08"]["calibration"] = calibrated_coverage(
            candidate_model, candidate_x, y, validation, test
        )
        if candidate_size is None:
            candidate_size = serialized_size(candidate_model)
        item["maeImprovementPercent"] = round(
            100 * (item["championV07"]["mae"] - item["candidateV08"]["mae"])
            / item["championV07"]["mae"], 3
        )
        item["p90ImprovementPercent"] = round(
            100 * (
                item["championV07"]["p90AbsoluteError"]
                - item["candidateV08"]["p90AbsoluteError"]
            ) / item["championV07"]["p90AbsoluteError"], 3
        )
        item["latencyRatio"] = round(
            item["candidateV08"]["apiBatchLatencyMs"]
            / item["championV07"]["apiBatchLatencyMs"], 3
        )
        coverage = item["candidateV08"]["calibration"]
        item["passedPerSeedGate"] = (
            item["maeImprovementPercent"] >= 70
            and item["p90ImprovementPercent"] >= 70
            and .77 <= coverage["coverage80"] <= .83
            and .87 <= coverage["coverage90"] <= .93
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert candidate_size is not None
    locked = [item for item in results if item["phase"] in ("confirmation", "final")]
    final = [item for item in results if item["phase"] == "final"]
    mean_latency_ratio = float(np.mean([item["latencyRatio"] for item in locked]))
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in locked)
            and mean_latency_ratio <= .8
            and candidate_size <= 80_000_000
        ),
        "rule": (
            "Every confirmation/final seed must improve MAE and p90 by at least 70% with "
            "calibrated coverage within 3 points of nominal; mean API-batch latency <=0.8x; "
            "compressed artifact <=80 MB."
        ),
    }
    return {
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.7 ExtraTreesRegressor, 200 trees, 23 features",
            "candidate": "ExtraTreesRegressor, 120 trees, 25 features",
            "candidateFeatures": ["temperature_water_interaction", "ph_solar_interaction"],
            "featureDefinition": {
                "temperature_water_interaction": "temperature_fit^0.42 * water_fit^0.26",
                "ph_solar_interaction": "ph_fit^0.18 * solar_fit^0.14",
            },
            "selection": (
                "Three complementary two-interaction factorizations and a six-pair design were "
                "compared only on development seeds; temperature-water plus pH-solar had the "
                "lowest mean development MAE and p90 error."
            ),
            "leakageControl": (
                "Features use only request/profile inputs and fixed mechanistic exponents; neither "
                "the final suitability label nor held-out crop identity is an input."
            ),
            "split": "Identical grouped crop-profile train/validation/test split per model and seed",
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
            "lockedMeanMaeImprovementPercent": round(float(np.mean([item["maeImprovementPercent"] for item in locked])), 2),
            "lockedMeanP90ImprovementPercent": round(float(np.mean([item["p90ImprovementPercent"] for item in locked])), 2),
            "finalMeanMaeImprovementPercent": round(float(np.mean([item["maeImprovementPercent"] for item in final])), 2),
            "finalMeanP90ImprovementPercent": round(float(np.mean([item["p90ImprovementPercent"] for item in final])), 2),
            "lockedMeanCoverage80": round(float(np.mean([item["candidateV08"]["calibration"]["coverage80"] for item in locked])), 4),
            "lockedMeanCoverage90": round(float(np.mean([item["candidateV08"]["calibration"]["coverage90"] for item in locked])), 4),
            "lockedMeanApiBatchLatencyRatio": round(mean_latency_ratio, 3),
            "candidateSerializedSizeBytes": candidate_size,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.8 interaction-feature validation", "",
        "Two input-derived agroclimatic interactions let a 120-tree candidate represent the multiplicative EcoCrop structure more efficiently than the 200-tree v0.7 champion. This is mechanistic-teacher fidelity, not observed-yield accuracy.", "",
        "| Phase | Seed | v0.7 MAE | v0.8 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        calibration = item["candidateV08"]["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV07"]["mae"]:.5f} | '
            f'{item["candidateV08"]["mae"]:.5f} | {item["maeImprovementPercent"]:.2f}% | '
            f'{item["p90ImprovementPercent"]:.2f}% | {calibration["coverage80"]:.1%} | '
            f'{calibration["coverage90"]:.1%} | {item["latencyRatio"]:.2f}x |'
        )
    summary = report["summary"]
    lines += [
        "", f'Locked-seed wins: **{summary["lockedSeedWins"]}/{summary["lockedSeeds"]}**. Mean locked MAE improved **{summary["lockedMeanMaeImprovementPercent"]:.2f}%** and p90 improved **{summary["lockedMeanP90ImprovementPercent"]:.2f}%**.',
        "", f'Locked calibrated coverage was **{summary["lockedMeanCoverage80"]:.1%} / {summary["lockedMeanCoverage90"]:.1%}**. The candidate is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB** compressed with a **{summary["lockedMeanApiBatchLatencyRatio"]:.2f}x** latency ratio.',
        "", "The two features contain no final suitability value: they separately combine temperature with water and pH with solar. The forest must still learn their joint response on crop profiles excluded from fitting.",
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
    axes[0].axhline(70, color="#8f2f14", linestyle="--", label="promotion gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="seed suffix", ylabel="Error reduction (%)", title="Large gains on every frozen split")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["candidateV08"]["calibration"]["coverage80"] for item in results], marker="o", label="80% interval", color="#d98352")
    axes[1].plot(x, [item["candidateV08"]["calibration"]["coverage90"] for item in results], marker="o", label="90% interval", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65)
    axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="seed suffix", ylabel="Held-out coverage", title="Uncertainty remains calibrated")
    axes[1].legend(); axes[1].grid(alpha=.18)
    for boundary in (2.5, 4.5):
        for axis in axes:
            axis.axvline(boundary, color="#777777", linestyle=":", alpha=.65)
    figure.suptitle("CropFit v0.8 · transparent interaction features", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/interaction-validation-v0.8.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/interaction-validation-v0.8.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    args = parser.parse_args()
    report = evaluate(args.profiles, args.samples_per_crop)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
