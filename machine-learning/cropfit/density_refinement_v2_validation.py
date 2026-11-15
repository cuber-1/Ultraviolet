from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np

from .density_refinement_validation import (
    active_calibrated_coverage,
    estimator,
    serialized_size,
)
from .estimator_validation import (
    calibrated_coverage,
    error_metrics,
    prediction_latency_ms,
    split_indices,
)
from .profiles import load_profiles
from .scenario_shift_validation import coverage, model_metrics, shifted_examples, validation_quantiles
from .training import generate_examples


EVALUATION_DENSITY = 72
CHAMPION_DENSITY = 120
CHAMPION_TREES = 70
CANDIDATE_DENSITY = 200
CANDIDATE_TREES = 40
CONFIRMATION_SEEDS = list(range(20261220, 20261225))
FINAL_SEEDS = list(range(20261225, 20261230))
SHIFT_SEED = 20261230


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    fitting_groups = np.unique(groups[train])
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
        models[name] = {"model": model, "fitSeconds": round(perf_counter() - started, 3)}
    return models, x, y, groups, np.asarray([validation, test], dtype=object)


def relative_gains(champion: dict, candidate: dict) -> dict:
    return {
        "maePercent": round(100 * (champion["mae"] - candidate["mae"]) / champion["mae"], 2),
        "p90Percent": round(100 * (champion["p90AbsoluteError"] - candidate["p90AbsoluteError"]) / champion["p90AbsoluteError"], 2),
        "deployedMaePercent": round(100 * (champion["deployedMae"] - candidate["deployedMae"]) / champion["deployedMae"], 2),
        "deployedP90Percent": round(100 * (champion["deployedP90AbsoluteError"] - candidate["deployedP90AbsoluteError"]) / champion["deployedP90AbsoluteError"], 2),
    }


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    champion_size = None
    candidate_size = None
    for seed in CONFIRMATION_SEEDS + FINAL_SEEDS:
        models, x, y, groups, indices = fit_pair(profiles, seed)
        validation, test = indices
        item = {
            "seed": seed,
            "phase": "confirmation" if seed in CONFIRMATION_SEEDS else "final",
            "testProfiles": len(np.unique(groups[test])),
        }
        for name in ("championV09", "candidateV010"):
            model = models[name]["model"]
            item[name] = {
                **error_metrics(y[test], model.predict(x[test])),
                "fitSeconds": models[name]["fitSeconds"],
                "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]]),
                "calibration": calibrated_coverage(model, x, y, validation, test),
                "activeCalibration": active_calibrated_coverage(model, x, y, validation, test),
            }
        if champion_size is None:
            champion_size = serialized_size(models["championV09"]["model"])
            candidate_size = serialized_size(models["candidateV010"]["model"])
        item["maeImprovementPercent"] = round(
            100 * (item["championV09"]["mae"] - item["candidateV010"]["mae"])
            / item["championV09"]["mae"], 3,
        )
        item["p90ImprovementPercent"] = round(
            100 * (
                item["championV09"]["p90AbsoluteError"]
                - item["candidateV010"]["p90AbsoluteError"]
            ) / item["championV09"]["p90AbsoluteError"], 3,
        )
        item["latencyRatio"] = round(
            item["candidateV010"]["apiBatchLatencyMs"]
            / item["championV09"]["apiBatchLatencyMs"], 3,
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
    confirmation = [item for item in results if item["phase"] == "confirmation"]
    final = [item for item in results if item["phase"] == "final"]
    all_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in results]))
    all_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in results]))
    final_mae_gain = float(np.mean([item["maeImprovementPercent"] for item in final]))
    final_p90_gain = float(np.mean([item["p90ImprovementPercent"] for item in final]))
    latency_ratio = float(np.mean([item["latencyRatio"] for item in results]))

    shift_models, shift_x, shift_y, shift_groups, shift_indices = fit_pair(profiles, SHIFT_SEED)
    shift_validation, shift_test = shift_indices
    shifted_x, shifted_y, irrigated = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=SHIFT_SEED,
    )
    shifted = {}
    for name in ("championV09", "candidateV010"):
        shifted[name] = model_metrics(
            shift_models[name]["model"], shifted_x, shifted_y, irrigated,
        )
    candidate_model = shift_models["candidateV010"]["model"]
    quantiles = validation_quantiles(
        candidate_model, shift_x, shift_y, shift_validation, active_only=True,
    )
    active_shift = shifted_y > 0
    shifted_coverage = coverage(
        shifted["candidateV010"]["errors"], shifted["candidateV010"]["treeStd"],
        active_shift, quantiles,
    )
    frozen_trees = np.asarray([tree.predict(shift_x[shift_test]) for tree in candidate_model.estimators_])
    frozen_errors = np.abs(frozen_trees.mean(axis=0) - shift_y[shift_test])
    frozen_coverage = coverage(
        frozen_errors, frozen_trees.std(axis=0), shift_y[shift_test] > 0, quantiles,
    )
    shift_gains = relative_gains(shifted["championV09"], shifted["candidateV010"])
    shift_gate = (
        min(shift_gains.values()) >= 5
        and all(
            shifted["candidateV010"]["subgroups"][name]["mae"]
            < shifted["championV09"]["subgroups"][name]["mae"]
            for name in ("irrigated", "rainfed", "active")
        )
        and abs(frozen_coverage["p80"] - .8) <= .02
        and abs(frozen_coverage["p90"] - .9) <= .02
        and abs(shifted_coverage["p80"] - .8) <= .02
        and abs(shifted_coverage["p90"] - .9) <= .02
    )
    for item in shifted.values():
        item.pop("treeStd")
        item.pop("errors")

    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in results)
            and all_mae_gain >= 5 and all_p90_gain >= 5
            and final_mae_gain >= 5 and final_p90_gain >= 5
            and latency_ratio <= 1.1
            and candidate_size < champion_size and candidate_size <= 68_000_000
            and shift_gate
        ),
        "rule": (
            "Every fresh confirmation/final seed must improve MAE and p90 with global and active "
            "coverage within 3 points of nominal; all-seed and final-only mean gains must each be "
            ">=5%; latency <=1.1x; compressed size must be smaller than v0.9.1 and <=68 MB. On a "
            "separate fresh Latin-hypercube shift, all raw/deployed gains must be >=5%, each active "
            "subgroup MAE must improve, and active coverage must stay within 2 points of nominal."
        ),
    }
    return {
        "name": "CropFit v0.10 density-refinement v2 validation",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.9.1, 120 fitting scenarios per crop, 70 Extra Trees",
            "candidate": "200 fitting scenarios per crop, 40 Extra Trees",
            "selection": (
                "The first 240/32 candidate failed shift confirmation. Among the original "
                "development Pareto grid, 200/40 was the strongest candidate that improved both "
                "raw and deployed shift MAE. All seeds in this report and shift seed 20261230 were "
                "reserved after that selection."
            ),
            "fixedEvaluation": "Both models use identical 72-scenario validation and test rows.",
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "shiftSeed": SHIFT_SEED,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "seedWins": sum(item["passedPerSeedGate"] for item in results),
            "seeds": len(results),
            "confirmationMeanMaeImprovementPercent": round(float(np.mean([item["maeImprovementPercent"] for item in confirmation])), 2),
            "confirmationMeanP90ImprovementPercent": round(float(np.mean([item["p90ImprovementPercent"] for item in confirmation])), 2),
            "allMeanMaeImprovementPercent": round(all_mae_gain, 2),
            "allMeanP90ImprovementPercent": round(all_p90_gain, 2),
            "finalMeanMaeImprovementPercent": round(final_mae_gain, 2),
            "finalMeanP90ImprovementPercent": round(final_p90_gain, 2),
            "meanApiBatchLatencyRatio": round(latency_ratio, 3),
            "championSerializedSizeBytes": champion_size,
            "candidateSerializedSizeBytes": candidate_size,
            "sizeReductionPercent": round(100 * (champion_size - candidate_size) / champion_size, 2),
        },
        "independentShift": {
            "seed": SHIFT_SEED,
            "profiles": len(np.unique(shift_groups[shift_test])),
            "examples": len(shifted_y),
            **shifted,
            "gains": shift_gains,
            "activeCoverage": {
                "frozenRandom": {"p80": frozen_coverage["p80"], "p90": frozen_coverage["p90"]},
                "independentShift": shifted_coverage,
            },
            "passed": shift_gate,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit v0.10 density-refinement v2 validation", "",
        "The 200-scenario/40-tree candidate was selected only after the 240/32 candidate failed shift confirmation. This report uses ten new grouped seeds and a new independent scenario-shift seed.", "",
        "| Phase | Seed | v0.9.1 MAE | Candidate MAE | MAE gain | p90 gain | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        active = item["candidateV010"]["activeCalibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV09"]["mae"]:.5f} | '
            f'{item["candidateV010"]["mae"]:.5f} | {item["maeImprovementPercent"]:.2f}% | '
            f'{item["p90ImprovementPercent"]:.2f}% | {active["coverage80"]:.1%} | {active["coverage90"]:.1%} |'
        )
    summary, shift = report["summary"], report["independentShift"]
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Final-only gains are **{summary["finalMeanMaeImprovementPercent"]:.2f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.2f}% p90**.',
        "", f'The candidate is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB** ({summary["sizeReductionPercent"]:.1f}% smaller) with **{summary["meanApiBatchLatencyRatio"]:.2f}x** latency.',
        "", "## Independent shift", "",
        f'Fresh-seed gains are **{shift["gains"]["maePercent"]:.2f}% raw MAE**, **{shift["gains"]["p90Percent"]:.2f}% raw p90**, **{shift["gains"]["deployedMaePercent"]:.2f}% deployed MAE**, and **{shift["gains"]["deployedP90Percent"]:.2f}% deployed p90**.',
        "", f'Active shifted coverage is **{shift["activeCoverage"]["independentShift"]["p80"]:.1%} / {shift["activeCoverage"]["independentShift"]["p90"]:.1%}**.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    axes[0].plot(x, [item["maeImprovementPercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["p90ImprovementPercent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(5, color="#d98352", linestyle="--", label="mean gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="fresh seed suffix", ylabel="Error reduction (%)", title="Grouped crop-profile gains")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["candidateV010"]["activeCalibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["candidateV010"]["activeCalibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="fresh seed suffix", ylabel="Coverage", title="Active uncertainty calibration")
    axes[1].legend(); axes[1].grid(alpha=.18)
    gains = report["independentShift"]["gains"]
    names = ["raw MAE", "raw p90", "deployed MAE", "deployed p90"]
    values = [gains["maePercent"], gains["p90Percent"], gains["deployedMaePercent"], gains["deployedP90Percent"]]
    axes[2].bar(names, values, color=["#315d49", "#6f9551", "#315d49", "#6f9551"])
    axes[2].axhline(5, color="#d98352", linestyle="--", label="shift gate")
    axes[2].tick_params(axis="x", rotation=18); axes[2].set(ylabel="Error reduction (%)", title="Fresh independent scenario shift")
    axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    for axis in axes[:2]:
        axis.axvline(4.5, color="#777777", linestyle=":", alpha=.65)
    figure.suptitle("CropFit v0.10 candidate · 200 scenarios × 40 Extra Trees", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/density-refinement-v2-validation-v0.10.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/density-refinement-v2-validation-v0.10.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "independentShift": report["independentShift"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
