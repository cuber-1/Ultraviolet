from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np

from .density_refinement_validation import active_calibrated_coverage, estimator, serialized_size
from .estimator_validation import calibrated_coverage, error_metrics, prediction_latency_ms, split_indices
from .features import FEATURE_NAMES
from .profiles import load_profiles
from .scenario_shift_validation import coverage, model_metrics, shifted_examples, validation_quantiles
from .training import generate_examples


EVALUATION_DENSITY = 72
FITTING_DENSITY = 200
TREES = 40
FULL_COLUMNS = np.arange(len(FEATURE_NAMES))
COMPACT_FEATURE_NAMES = FEATURE_NAMES[-6:]
COMPACT_COLUMNS = np.arange(len(FEATURE_NAMES) - len(COMPACT_FEATURE_NAMES), len(FEATURE_NAMES))
CONFIRMATION_SEEDS = list(range(20270110, 20270115))
FINAL_SEEDS = list(range(20270115, 20270120))
SHIFT_SEED = 20270120


def selected(values: np.ndarray, columns: np.ndarray) -> np.ndarray:
    return values[:, columns]


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    training_x, training_y, training_groups = generate_examples(profiles, FITTING_DENSITY, seed)
    fitting_groups = np.unique(groups[train])
    fitting_indices = np.flatnonzero(np.isin(training_groups, fitting_groups))
    models = {}
    for name, columns in (("fullV010", FULL_COLUMNS), ("compactCandidate", COMPACT_COLUMNS)):
        model = estimator(TREES, seed)
        started = perf_counter()
        model.fit(selected(training_x[fitting_indices], columns), training_y[fitting_indices])
        models[name] = {
            "model": model,
            "columns": columns,
            "fitSeconds": round(perf_counter() - started, 3),
        }
    return models, x, y, groups, np.asarray([validation, test], dtype=object)


def gains(full: dict, compact: dict) -> dict:
    result = {}
    for source, output in (
        ("mae", "maePercent"),
        ("p90AbsoluteError", "p90Percent"),
        ("deployedMae", "deployedMaePercent"),
    ):
        if source in full and source in compact:
            result[output] = round(100 * (full[source] - compact[source]) / full[source], 2)
    return result


def evaluate(
    profiles_path: Path,
    confirmation_seeds: list[int] = CONFIRMATION_SEEDS,
    final_seeds: list[int] = FINAL_SEEDS,
    shift_seed: int = SHIFT_SEED,
    gate_global_coverage: bool = True,
    validation_name: str = "CropFit compact-feature validation v0.11 candidate",
) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    sizes = None
    for seed in confirmation_seeds + final_seeds:
        models, x, y, groups, indices = fit_pair(profiles, seed)
        validation, test = indices
        item = {
            "seed": seed,
            "phase": "confirmation" if seed in confirmation_seeds else "final",
            "testProfiles": len(np.unique(groups[test])),
        }
        for name in ("fullV010", "compactCandidate"):
            model = models[name]["model"]
            columns = models[name]["columns"]
            feature_x = selected(x, columns)
            item[name] = {
                **error_metrics(y[test], model.predict(feature_x[test])),
                "fitSeconds": models[name]["fitSeconds"],
                "apiBatchLatencyMs": prediction_latency_ms(model, feature_x[test[:132]]),
                "calibration": calibrated_coverage(model, feature_x, y, validation, test),
                "activeCalibration": active_calibrated_coverage(model, feature_x, y, validation, test),
            }
        if sizes is None:
            sizes = {
                name: serialized_size(models[name]["model"])
                for name in ("fullV010", "compactCandidate")
            }
        item["gains"] = gains(item["fullV010"], item["compactCandidate"])
        item["latencyRatio"] = round(
            item["compactCandidate"]["apiBatchLatencyMs"] / item["fullV010"]["apiBatchLatencyMs"], 3,
        )
        full_active = item["fullV010"]["activeCalibration"]
        compact_active = item["compactCandidate"]["activeCalibration"]
        compact_global = item["compactCandidate"]["calibration"]
        item["globalCoverageWithinThreePoints"] = (
            .77 <= compact_global["coverage80"] <= .83
            and .87 <= compact_global["coverage90"] <= .93
        )
        item["passedPerSeedGate"] = (
            item["gains"]["maePercent"] > 0
            and item["gains"]["p90Percent"] > 0
            and (item["globalCoverageWithinThreePoints"] or not gate_global_coverage)
            and .77 <= compact_active["coverage80"] <= .83
            and .87 <= compact_active["coverage90"] <= .93
            and compact_active["meanRadius80"] < full_active["meanRadius80"]
            and compact_active["meanRadius90"] < full_active["meanRadius90"]
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert sizes is not None
    final = [item for item in results if item["phase"] == "final"]
    mean = lambda rows, key: float(np.mean([item["gains"][key] for item in rows]))
    all_mae_gain = mean(results, "maePercent")
    all_p90_gain = mean(results, "p90Percent")
    final_mae_gain = mean(final, "maePercent")
    final_p90_gain = mean(final, "p90Percent")
    latency_ratio = float(np.mean([item["latencyRatio"] for item in results]))

    shift_models, shift_x, shift_y, shift_groups, shift_indices = fit_pair(profiles, shift_seed)
    shift_validation, shift_test = shift_indices
    shifted_x, shifted_y, irrigated = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=shift_seed,
    )
    shifted = {}
    for name in ("fullV010", "compactCandidate"):
        columns = shift_models[name]["columns"]
        shifted[name] = model_metrics(
            shift_models[name]["model"], selected(shifted_x, columns), shifted_y, irrigated,
        )
    compact_model = shift_models["compactCandidate"]["model"]
    compact_shift_x = selected(shift_x, COMPACT_COLUMNS)
    quantiles = validation_quantiles(
        compact_model, compact_shift_x, shift_y, shift_validation, active_only=True,
    )
    active_shift = shifted_y > 0
    shifted_coverage = coverage(
        shifted["compactCandidate"]["errors"], shifted["compactCandidate"]["treeStd"],
        active_shift, quantiles,
    )
    frozen_trees = np.asarray([
        tree.predict(compact_shift_x[shift_test]) for tree in compact_model.estimators_
    ])
    frozen_errors = np.abs(frozen_trees.mean(axis=0) - shift_y[shift_test])
    frozen_coverage = coverage(
        frozen_errors, frozen_trees.std(axis=0), shift_y[shift_test] > 0, quantiles,
    )
    shift_gains = gains(shifted["fullV010"], shifted["compactCandidate"])
    shift_gate = (
        min(shift_gains.values()) >= 20
        and shifted["compactCandidate"]["deployedMaximumAbsoluteError"]
        < shifted["fullV010"]["deployedMaximumAbsoluteError"]
        and all(
            shifted["compactCandidate"]["subgroups"][name]["mae"]
            < shifted["fullV010"]["subgroups"][name]["mae"]
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

    coverage_rule = (
        "preserve global and active 80%/90% coverage within 3 points"
        if gate_global_coverage else
        "preserve the API-served active 80%/90% coverage within 3 points while reporting pooled coverage"
    )
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in results)
            and all_mae_gain >= 20 and all_p90_gain >= 20
            and final_mae_gain >= 20 and final_p90_gain >= 20
            and latency_ratio <= 1.0
            and sizes["compactCandidate"] < sizes["fullV010"]
            and sizes["compactCandidate"] <= 64_000_000
            and shift_gate
        ),
        "rule": (
            f"Every fresh grouped seed must improve MAE and p90, {coverage_rule}, and tighten "
            "both active intervals. All-seed and "
            "final-only mean MAE/p90 gains must each be >=20%; latency must not increase; the "
            "compressed forest must be smaller than v0.10 and <=64 MB. A separate Latin-hypercube "
            "shift must improve raw MAE, raw p90, and deployed MAE by >=20%, improve irrigated, "
            "rainfed, and active MAE, reduce deployed maximum error, and preserve active coverage "
            "within 2 points of nominal."
        ),
    }
    return {
        "name": validation_name,
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.10.0, all 25 features, 200 fitting scenarios, 40 Extra Trees",
            "candidate": "six transparent range-relative and interaction features, otherwise identical",
            "candidateFeatures": COMPACT_FEATURE_NAMES,
            "selection": (
                "Three development seeds (20270101-20270103) compared all 25 features, the four "
                "range memberships alone, and the six range-plus-interaction features. Only the "
                "six-feature candidate advanced. All seeds and the shift seed in this report were "
                "reserved until after that choice."
            ),
            "fixedEvaluation": "Both models use identical fitting, validation, held-out profiles, and scenario rows.",
            "coveragePolicy": (
                "Gate both global and active calibration."
                if gate_global_coverage else
                "Report pooled coverage, but gate the conditionally calibrated active intervals served by the API; deterministic inactive predictions have zero score and zero radius."
            ),
            "confirmationSeeds": confirmation_seeds,
            "finalSeeds": final_seeds,
            "shiftSeed": shift_seed,
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "seedWins": sum(item["passedPerSeedGate"] for item in results),
            "seeds": len(results),
            "allMeanMaeImprovementPercent": round(all_mae_gain, 2),
            "allMeanP90ImprovementPercent": round(all_p90_gain, 2),
            "finalMeanMaeImprovementPercent": round(final_mae_gain, 2),
            "finalMeanP90ImprovementPercent": round(final_p90_gain, 2),
            "meanApiBatchLatencyRatio": round(latency_ratio, 3),
            "fullSerializedSizeBytes": sizes["fullV010"],
            "compactSerializedSizeBytes": sizes["compactCandidate"],
            "sizeReductionPercent": round(
                100 * (sizes["fullV010"] - sizes["compactCandidate"]) / sizes["fullV010"], 2,
            ),
        },
        "independentShift": {
            "seed": shift_seed,
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
        "# CropFit compact-feature validation", "",
        "The candidate keeps only six transparent, input-derived range and interaction features. Training density, estimator capacity, splits, and evaluation rows are unchanged from v0.10.", "",
        "| Phase | Seed | v0.10 MAE | Compact MAE | MAE gain | p90 gain | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        active = item["compactCandidate"]["activeCalibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["fullV010"]["mae"]:.5f} | '
            f'{item["compactCandidate"]["mae"]:.5f} | {item["gains"]["maePercent"]:.2f}% | '
            f'{item["gains"]["p90Percent"]:.2f}% | {active["coverage80"]:.1%} | {active["coverage90"]:.1%} |'
        )
    summary = report["summary"]
    shift = report["independentShift"]
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Final-only gains are **{summary["finalMeanMaeImprovementPercent"]:.2f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.2f}% p90**.',
        "", f'The forest is **{summary["compactSerializedSizeBytes"] / 1_000_000:.1f} MB** ({summary["sizeReductionPercent"]:.1f}% smaller) with **{summary["meanApiBatchLatencyRatio"]:.2f}x** batch latency.',
        "", "## Independent shift", "",
        f'Fresh-shift gains are **{shift["gains"]["maePercent"]:.2f}% raw MAE**, **{shift["gains"]["p90Percent"]:.2f}% raw p90**, and **{shift["gains"]["deployedMaePercent"]:.2f}% deployed MAE**.',
        "", f'Active shifted coverage is **{shift["activeCoverage"]["independentShift"]["p80"]:.1%} / {shift["activeCoverage"]["independentShift"]["p90"]:.1%}**.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> The compact inputs are derived only from current conditions and published crop ranges; they contain no crop identity, held-out label, or observed yield.", "",
        "> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    axes[0].plot(x, [item["gains"]["maePercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["gains"]["p90Percent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(20, color="#d98352", linestyle="--", label="mean gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="fresh seed suffix", ylabel="Error reduction (%)", title="Six-feature held-out gains")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["compactCandidate"]["activeCalibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["compactCandidate"]["activeCalibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="fresh seed suffix", ylabel="Coverage", title="Compact uncertainty calibration")
    axes[1].legend(); axes[1].grid(alpha=.18)
    gains_values = report["independentShift"]["gains"]
    names = ["raw MAE", "raw p90", "deployed MAE"]
    values = [gains_values["maePercent"], gains_values["p90Percent"], gains_values["deployedMaePercent"]]
    axes[2].bar(names, values, color=["#315d49", "#6f9551", "#315d49"])
    axes[2].axhline(20, color="#d98352", linestyle="--", label="shift gate")
    axes[2].set(ylabel="Error reduction (%)", title="Independent scenario shift")
    axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.11 candidate · fewer features, stronger transfer", fontweight="bold")
    figure.text(.5, .01, "Unseen crop profiles · compact input-derived features · not observed yield accuracy", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, .94))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/feature-compaction-validation-v0.11.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/feature-compaction-validation-v0.11.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/feature-compaction-validation-v0.11.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["gate"], indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Compact-feature promotion gate did not pass")


if __name__ == "__main__":
    main()
