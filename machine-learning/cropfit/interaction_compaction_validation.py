from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np

from .density_refinement_validation import active_calibrated_coverage, estimator, serialized_size
from .estimator_validation import calibrated_coverage, error_metrics, prediction_latency_ms, split_indices
from .features import COMPACT_FEATURE_COLUMNS, COMPACT_FEATURE_NAMES, FEATURE_NAMES
from .profiles import load_profiles
from .scenario_shift_validation import coverage, model_metrics, shifted_examples, validation_quantiles
from .training import generate_examples


EVALUATION_DENSITY = 72
FITTING_DENSITY = 200
CHAMPION_TREES = 40
CANDIDATE_TREES = 60
CANDIDATE_MIN_SAMPLES_LEAF = 2
INTERACTION_FEATURE_NAMES = FEATURE_NAMES[-2:]
INTERACTION_COLUMNS = np.arange(len(FEATURE_NAMES) - 2, len(FEATURE_NAMES))
CONFIRMATION_SEEDS = list(range(20270210, 20270215))
FINAL_SEEDS = list(range(20270215, 20270220))
SHIFT_SEED = 20270220


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    training_x, training_y, training_groups = generate_examples(profiles, FITTING_DENSITY, seed)
    fitting_indices = np.flatnonzero(np.isin(training_groups, np.unique(groups[train])))
    models = {}
    for name, columns, trees, leaf in (
        ("championV011", np.asarray(COMPACT_FEATURE_COLUMNS), CHAMPION_TREES, 1),
        ("interactionCandidate", INTERACTION_COLUMNS, CANDIDATE_TREES, CANDIDATE_MIN_SAMPLES_LEAF),
    ):
        model = estimator(trees, seed)
        model.set_params(min_samples_leaf=leaf)
        started = perf_counter()
        model.fit(training_x[fitting_indices][:, columns], training_y[fitting_indices])
        models[name] = {"model": model, "columns": columns, "fitSeconds": round(perf_counter() - started, 3)}
    return models, x, y, groups, np.asarray([validation, test], dtype=object)


def relative_gains(champion: dict, candidate: dict) -> dict:
    return {
        output: round(100 * (champion[source] - candidate[source]) / champion[source], 2)
        for source, output in (
            ("mae", "maePercent"),
            ("p90AbsoluteError", "p90Percent"),
            ("deployedMae", "deployedMaePercent"),
        )
        if source in champion and source in candidate
    }


def evaluate(
    profiles_path: Path,
    fit_pair_fn=fit_pair,
    confirmation_seeds: list[int] = CONFIRMATION_SEEDS,
    final_seeds: list[int] = FINAL_SEEDS,
    shift_seed: int = SHIFT_SEED,
    mean_gain_floor: float = 25,
    shift_gain_floor: float = 20,
    maximum_size_bytes: int = 40_000_000,
    require_smaller_size: bool = True,
    latency_ceiling: float = 1.0,
    validation_name: str = "CropFit interaction-only compaction validation v0.12 candidate",
    protocol_champion: str = "v0.11.0, six range-relative features, 40 Extra Trees, min_samples_leaf=1",
    protocol_candidate: str = "two transparent interaction features, 60 Extra Trees, min_samples_leaf=2",
    candidate_features: list[str] = INTERACTION_FEATURE_NAMES,
    selection: str | None = None,
) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    sizes = None
    for seed in confirmation_seeds + final_seeds:
        models, x, y, groups, indices = fit_pair_fn(profiles, seed)
        validation, test = indices
        item = {
            "seed": seed,
            "phase": "confirmation" if seed in confirmation_seeds else "final",
            "testProfiles": len(np.unique(groups[test])),
        }
        for name in ("championV011", "interactionCandidate"):
            model = models[name]["model"]
            columns = models[name]["columns"]
            feature_x = x[:, columns]
            predictions = model.predict(feature_x[test])
            deployed_errors = np.abs(np.minimum(predictions, y[test]) - y[test])
            item[name] = {
                **error_metrics(y[test], predictions),
                "deployedMaximumAbsoluteError": round(float(np.max(deployed_errors)), 5),
                "fitSeconds": models[name]["fitSeconds"],
                "apiBatchLatencyMs": prediction_latency_ms(model, feature_x[test[:132]]),
                "calibration": calibrated_coverage(model, feature_x, y, validation, test),
                "activeCalibration": active_calibrated_coverage(model, feature_x, y, validation, test),
            }
        if sizes is None:
            sizes = {name: serialized_size(models[name]["model"]) for name in models}
        item["gains"] = relative_gains(item["championV011"], item["interactionCandidate"])
        item["latencyRatio"] = round(
            item["interactionCandidate"]["apiBatchLatencyMs"] / item["championV011"]["apiBatchLatencyMs"], 3,
        )
        candidate = item["interactionCandidate"]
        champion_active = item["championV011"]["activeCalibration"]
        candidate_active = candidate["activeCalibration"]
        item["passedPerSeedGate"] = (
            item["gains"]["maePercent"] > 0
            and item["gains"]["p90Percent"] > 0
            and candidate["deployedMaximumAbsoluteError"] < item["championV011"]["deployedMaximumAbsoluteError"]
            and .77 <= candidate_active["coverage80"] <= .83
            and .87 <= candidate_active["coverage90"] <= .93
            and candidate_active["meanRadius80"] < champion_active["meanRadius80"]
            and candidate_active["meanRadius90"] < champion_active["meanRadius90"]
        )
        results.append(item)
        print(json.dumps(item), flush=True)

    assert sizes is not None
    final = [item for item in results if item["phase"] == "final"]
    mean_gain = lambda rows, name: float(np.mean([item["gains"][name] for item in rows]))
    all_mae_gain = mean_gain(results, "maePercent")
    all_p90_gain = mean_gain(results, "p90Percent")
    final_mae_gain = mean_gain(final, "maePercent")
    final_p90_gain = mean_gain(final, "p90Percent")
    latency_ratio = float(np.mean([item["latencyRatio"] for item in results]))

    shift_models, shift_x, shift_y, shift_groups, shift_indices = fit_pair_fn(profiles, shift_seed)
    shift_validation, shift_test = shift_indices
    shifted_x, shifted_y, irrigated = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=shift_seed,
    )
    shifted = {}
    for name in ("championV011", "interactionCandidate"):
        columns = shift_models[name]["columns"]
        shifted[name] = model_metrics(
            shift_models[name]["model"], shifted_x[:, columns], shifted_y, irrigated,
        )
    candidate_model = shift_models["interactionCandidate"]["model"]
    candidate_shift_x = shift_x[:, shift_models["interactionCandidate"]["columns"]]
    quantiles = validation_quantiles(
        candidate_model, candidate_shift_x, shift_y, shift_validation, active_only=True,
    )
    active_shift = shifted_y > 0
    shifted_coverage = coverage(
        shifted["interactionCandidate"]["errors"], shifted["interactionCandidate"]["treeStd"],
        active_shift, quantiles,
    )
    frozen_trees = np.asarray([
        tree.predict(candidate_shift_x[shift_test]) for tree in candidate_model.estimators_
    ])
    frozen_errors = np.abs(frozen_trees.mean(axis=0) - shift_y[shift_test])
    frozen_coverage = coverage(
        frozen_errors, frozen_trees.std(axis=0), shift_y[shift_test] > 0, quantiles,
    )
    shift_gains = relative_gains(shifted["championV011"], shifted["interactionCandidate"])
    shift_gate = (
        min(shift_gains.values()) >= shift_gain_floor
        and shifted["interactionCandidate"]["deployedMaximumAbsoluteError"]
        < shifted["championV011"]["deployedMaximumAbsoluteError"]
        and all(
            shifted["interactionCandidate"]["subgroups"][name]["mae"]
            < shifted["championV011"]["subgroups"][name]["mae"]
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

    size_passed = (
        sizes["interactionCandidate"] <= maximum_size_bytes
        and (
            not require_smaller_size
            or sizes["interactionCandidate"] < sizes["championV011"]
        )
    )
    size_rule = (
        f"compressed size must be smaller than v0.11 and <={maximum_size_bytes / 1_000_000:g} MB"
        if require_smaller_size
        else f"compressed size must be <={maximum_size_bytes / 1_000_000:g} MB (a measured size increase is allowed)"
    )
    gate = {
        "passed": (
            all(item["passedPerSeedGate"] for item in results)
            and all_mae_gain >= mean_gain_floor and all_p90_gain >= mean_gain_floor
            and final_mae_gain >= mean_gain_floor and final_p90_gain >= mean_gain_floor
            and latency_ratio <= latency_ceiling
            and size_passed
            and shift_gate
        ),
        "rule": (
            "Every fresh grouped seed must improve MAE, p90, and deployed maximum error; preserve "
            "API-served active 80%/90% coverage within 3 points; and tighten both active intervals. "
            f"All-seed and final-only mean MAE/p90 gains must each be >={mean_gain_floor:g}%; mean API latency must "
            f"be <={latency_ceiling:g}x; {size_rule}. A separate "
            f"Latin-hypercube shift must improve raw MAE, raw p90, and deployed MAE by >={shift_gain_floor:g}%, "
            "improve irrigated/rainfed/active MAE and deployed maximum error, and preserve active "
            "coverage within 2 points of nominal."
        ),
    }
    return {
        "name": validation_name,
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": protocol_champion,
            "candidate": protocol_candidate,
            "candidateFeatures": candidate_features,
            "selection": selection or (
                "Development seeds 20270201-20270203 compared two-feature forests with 32-60 trees "
                "and leaf sizes 1-3. The 60-tree/leaf-2 candidate was the strongest option that "
                "improved mean and tail error while remaining substantially smaller. Seeds in this "
                "report were reserved until after that choice."
            ),
            "fixedEvaluation": "Both models use identical fitting, validation, held-out profiles, and scenario rows.",
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
            "championSerializedSizeBytes": sizes["championV011"],
            "candidateSerializedSizeBytes": sizes["interactionCandidate"],
            "sizeReductionPercent": round(
                100 * (sizes["championV011"] - sizes["interactionCandidate"]) / sizes["championV011"], 2,
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


def markdown(
    report: dict,
    introduction: str = "The candidate keeps only the two transparent interaction features and uses leaf smoothing to improve tail safety. Training density and evaluation rows are unchanged from v0.11.",
    report_title: str = "CropFit interaction-only compaction validation",
) -> str:
    lines = [
        f"# {report_title}", "",
        introduction, "",
        "| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Max deployed error | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        candidate = item["interactionCandidate"]
        active = candidate["activeCalibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV011"]["mae"]:.5f} | '
            f'{candidate["mae"]:.5f} | {item["gains"]["maePercent"]:.2f}% | '
            f'{item["gains"]["p90Percent"]:.2f}% | {candidate["deployedMaximumAbsoluteError"]:.3f} | '
            f'{active["coverage80"]:.1%} | {active["coverage90"]:.1%} |'
        )
    summary, shift = report["summary"], report["independentShift"]
    size_change = summary["sizeReductionPercent"]
    size_description = (
        f"{size_change:.1f}% smaller"
        if size_change >= 0
        else f"{-size_change:.1f}% larger"
    )
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Final-only gains are **{summary["finalMeanMaeImprovementPercent"]:.2f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.2f}% p90**.',
        "", f'The forest is **{summary["candidateSerializedSizeBytes"] / 1_000_000:.1f} MB** ({size_description}) with **{summary["meanApiBatchLatencyRatio"]:.2f}x** batch latency.',
        "", "## Independent shift", "",
        f'Fresh-shift gains are **{shift["gains"]["maePercent"]:.2f}% raw MAE**, **{shift["gains"]["p90Percent"]:.2f}% raw p90**, and **{shift["gains"]["deployedMaePercent"]:.2f}% deployed MAE**.',
        "", f'Active shifted coverage is **{shift["activeCoverage"]["independentShift"]["p80"]:.1%} / {shift["activeCoverage"]["independentShift"]["p90"]:.1%}**.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> The retained inputs contain no crop identity, target score, held-out label, or observed yield.", "",
        "> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(
    report: dict,
    output: Path,
    figure_title: str = "CropFit v0.12 candidate rejected · one deployed-tail regression",
    heldout_title: str = "Two-feature held-out gains",
    calibration_title: str = "Candidate active calibration",
    tail_title: str = "Tail gate fails on seed 18",
) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    axes[0].plot(x, [item["gains"]["maePercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["gains"]["p90Percent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    mean_floor = float(report["gate"]["rule"].split("mean MAE/p90 gains must each be >=", 1)[1].split("%", 1)[0])
    axes[0].axhline(mean_floor, color="#d98352", linestyle="--", label="mean gate")
    axes[0].set(xticks=x, xticklabels=labels, xlabel="fresh seed suffix", ylabel="Error reduction (%)", title=heldout_title)
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["interactionCandidate"]["activeCalibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["interactionCandidate"]["activeCalibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.75, .95), xlabel="fresh seed suffix", ylabel="Coverage", title=calibration_title)
    axes[1].legend(); axes[1].grid(alpha=.18)
    width = .38
    champion_max = [item["championV011"]["deployedMaximumAbsoluteError"] for item in results]
    candidate_max = [item["interactionCandidate"]["deployedMaximumAbsoluteError"] for item in results]
    axes[2].bar(x - width / 2, champion_max, width, color="#8fae82", label="v0.11")
    axes[2].bar(x + width / 2, candidate_max, width, color="#315d49", label="candidate")
    axes[2].set(xticks=x, xticklabels=labels, xlabel="fresh seed suffix", ylabel="Maximum deployed error", title=tail_title)
    axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    figure.suptitle(figure_title, fontweight="bold")
    figure.text(.5, .01, "Unseen crop profiles · no crop identity or target feature · not observed yield accuracy", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, .94))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/interaction-compaction-validation-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/interaction-compaction-validation-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/interaction-compaction-validation-v0.12.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["gate"], indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Interaction-only compaction gate did not pass")


if __name__ == "__main__":
    main()
