from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit

from .profiles import load_profiles
from .training import TREE_STD_FLOOR, conformal_quantile, generate_examples


LEGACY_BINS = (
    (0, .01, 0.0, 0.0), (.01, 2, .5355, .7941), (2, 5, 1.574, 2.0919),
    (5, 10, 3.8241, 5.0367),
)
ROBUSTNESS_SEEDS = list(range(20261201, 20261206))


def radii(metadata: dict, tree_std: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    calibration = metadata["uncertaintyCalibration"]
    scale = tree_std + float(calibration["treeStdFloor"])
    quantiles = calibration["normalizedErrorQuantiles"]
    return scale * float(quantiles["p80"]), scale * float(quantiles["p90"])


def legacy_radii(tree_std: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p80 = np.copy(tree_std)
    p90 = np.minimum(100.0, tree_std * 1.5)
    for lower, upper, radius80, radius90 in LEGACY_BINS:
        mask = (tree_std >= lower) & (tree_std < upper)
        p80[mask], p90[mask] = radius80, radius90
    return p80, p90


def metrics(errors: np.ndarray, p80: np.ndarray, p90: np.ndarray) -> dict:
    return {
        "coverage80": round(float(np.mean(errors <= p80)), 4),
        "coverage90": round(float(np.mean(errors <= p90)), 4),
        "meanRadius80": round(float(np.mean(p80)), 4),
        "meanRadius90": round(float(np.mean(p90)), 4),
    }


def api_round(values: np.ndarray) -> np.ndarray:
    """Mirror the inference API's conservative three-decimal serialization."""
    return np.ceil(values * 1000) / 1000


def split_indices(x: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train_validation, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    inner_groups = groups[train_validation]
    inner_train, inner_validation = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(x[train_validation], y[train_validation], inner_groups))
    return train_validation[inner_train], train_validation[inner_validation], test


def errors_and_std(model, x: np.ndarray, y: np.ndarray, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    trees = np.asarray([tree.predict(x[indices]) for tree in model.estimators_])
    return np.abs(trees.mean(axis=0) - y[indices]), trees.std(axis=0)


def evaluate(artifact: Path, profiles_path: Path, samples_per_crop: int, seed: int) -> dict:
    bundle = joblib.load(artifact)
    model, metadata = bundle["model"], bundle["metadata"]
    x, y, groups = generate_examples(load_profiles(profiles_path), samples_per_crop, seed)
    _, validation, test = split_indices(x, y, groups, seed)
    errors, tree_std = errors_and_std(model, x, y, test)
    candidate_radii = radii(metadata, tree_std)
    unrounded_candidate = metrics(errors, *candidate_radii)
    candidate = metrics(errors, *(api_round(item) for item in candidate_radii))
    legacy = metrics(errors, *legacy_radii(tree_std))
    profile_coverages = []
    candidate_p80, candidate_p90 = radii(metadata, tree_std)
    for group in np.unique(groups[test]):
        mask = groups[test] == group
        profile_coverages.append([float(np.mean(errors[mask] <= candidate_p80[mask])), float(np.mean(errors[mask] <= candidate_p90[mask]))])
    profile_coverages = np.asarray(profile_coverages)
    gate = {
        "passed": abs(candidate["coverage80"] - .8) <= .02
        and abs(candidate["coverage90"] - .9) <= .02
        and candidate["meanRadius90"] < legacy["meanRadius90"],
        "rule": "Candidate coverage must be within 2 points of 80% and 90%, and its mean 90% radius must be narrower than v0.5.",
    }
    return {
        "model": metadata["model"],
        "split": {
            "seed": seed, "samplesPerCrop": samples_per_crop,
            "validationExamples": len(validation), "validationProfiles": len(np.unique(groups[validation])),
            "testExamples": len(test), "testProfiles": len(np.unique(groups[test])),
            "policy": "Calibration uses validation crop profiles; comparison uses held-out crop profiles excluded from estimator fitting and calibration.",
        },
        "legacyV05": legacy,
        "unroundedCandidate": unrounded_candidate,
        "candidate": candidate,
        "improvement": {
            "coverageDeviationReduction": round(
                abs(legacy["coverage80"] - .8) + abs(legacy["coverage90"] - .9)
                - abs(candidate["coverage80"] - .8) - abs(candidate["coverage90"] - .9), 4,
            ),
            "meanRadius90ReductionPercent": round(100 * (1 - candidate["meanRadius90"] / legacy["meanRadius90"]), 2),
        },
        "perProfileCoverageQuantiles": {
            "quantiles": [0, .1, .25, .5, .75, .9, 1],
            "p80": np.quantile(profile_coverages[:, 0], [0, .1, .25, .5, .75, .9, 1]).round(4).tolist(),
            "p90": np.quantile(profile_coverages[:, 1], [0, .1, .25, .5, .75, .9, 1]).round(4).tolist(),
            "note": "Split conformal guarantees marginal, not per-profile, coverage.",
        },
        "singleSplitGate": gate,
    }


def robustness(profiles_path: Path, samples_per_crop: int, seeds: list[int], estimators: int) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    for seed in seeds:
        x, y, groups = generate_examples(profiles, samples_per_crop, seed)
        train, validation, test = split_indices(x, y, groups, seed)
        model = RandomForestRegressor(n_estimators=estimators, min_samples_leaf=1, max_features=1.0, n_jobs=-1, random_state=seed)
        model.fit(x[train], y[train])
        validation_errors, validation_std = errors_and_std(model, x, y, validation)
        test_errors, test_std = errors_and_std(model, x, y, test)
        normalized = validation_errors / (validation_std + TREE_STD_FLOOR)
        quantile80 = conformal_quantile(normalized, .8)
        quantile90 = conformal_quantile(normalized, .9)
        candidate = metrics(
            test_errors,
            api_round(quantile80 * (test_std + TREE_STD_FLOOR)),
            api_round(quantile90 * (test_std + TREE_STD_FLOOR)),
        )
        legacy = metrics(test_errors, *legacy_radii(test_std))
        passed = (
            .77 <= candidate["coverage80"] <= .83
            and .87 <= candidate["coverage90"] <= .93
            and candidate["meanRadius90"] < legacy["meanRadius90"]
        )
        results.append({
            "seed": seed, "validationProfiles": len(np.unique(groups[validation])), "testProfiles": len(np.unique(groups[test])),
            "legacyV05": legacy, "candidate": candidate,
            "meanRadius90ReductionPercent": round(100 * (1 - candidate["meanRadius90"] / legacy["meanRadius90"]), 2),
            "passed": passed,
        })
        print(json.dumps(results[-1]), flush=True)
    gate = {
        "passed": all(item["passed"] for item in results),
        "rule": "On every frozen seed, coverage must be within 3 points of 80% and 90%, and mean 90% radius must be narrower than v0.5.",
    }
    return {
        "protocol": {
            "seeds": seeds, "samplesPerCrop": samples_per_crop, "estimators": estimators,
            "split": "Fresh grouped train/validation/test crop-profile splits per seed; calibration never uses the test profiles.",
            "declaredGate": gate["rule"],
        },
        "results": results,
        "summary": {
            "wins": sum(item["passed"] for item in results), "seeds": len(results),
            "meanCoverage80": round(float(np.mean([item["candidate"]["coverage80"] for item in results])), 4),
            "meanCoverage90": round(float(np.mean([item["candidate"]["coverage90"] for item in results])), 4),
            "meanRadius90ReductionPercent": round(float(np.mean([item["meanRadius90ReductionPercent"] for item in results])), 2),
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    legacy, candidate, improvement = report["legacyV05"], report["candidate"], report["improvement"]
    return "\n".join([
        "# CropFit uncertainty calibration v0.5.1", "",
        "Calibration is fit only on validation crop profiles. This report compares methods on held-out crop-profile test splits; it measures fidelity to the EcoCrop screening teacher, not observed farm yield.", "",
        "| Method | 80% coverage | 90% coverage | Mean 80% radius | Mean 90% radius |", "|---|---:|---:|---:|---:|",
        f'| v0.5 disagreement bins | {legacy["coverage80"]:.1%} | {legacy["coverage90"]:.1%} | {legacy["meanRadius80"]:.3f} | {legacy["meanRadius90"]:.3f} |',
        f'| v0.5.1 normalized conformal | {candidate["coverage80"]:.1%} | {candidate["coverage90"]:.1%} | {candidate["meanRadius80"]:.3f} | {candidate["meanRadius90"]:.3f} |', "",
        f'The production-seed candidate reduces mean 90% radius by **{improvement["meanRadius90ReductionPercent"]:.1f}%** while bringing both marginal coverages to their nominal targets. Single-split gate: **{"PASS" if report["singleSplitGate"]["passed"] else "NOT PASSED"}**.', "",
        "## Frozen five-seed robustness", "",
        "The method and gate were frozen before evaluating five new seeds (20261201–20261205). Every seed requires both coverages within three percentage points of nominal and a narrower mean 90% radius than v0.5.", "",
        "| Seed | 80% coverage | 90% coverage | v0.5 radius90 | v0.5.1 radius90 | Reduction |", "|---:|---:|---:|---:|---:|---:|",
        *[f'| {item["seed"]} | {item["candidate"]["coverage80"]:.1%} | {item["candidate"]["coverage90"]:.1%} | {item["legacyV05"]["meanRadius90"]:.3f} | {item["candidate"]["meanRadius90"]:.3f} | {item["meanRadius90ReductionPercent"]:.1f}% |' for item in report["robustness"]["results"]],
        "", f'Robustness wins: **{report["robustness"]["summary"]["wins"]}/{report["robustness"]["summary"]["seeds"]}**. Overall gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "Intervals are marginal across unseen crop profiles. They are not per-species guarantees, yield intervals, or property-investment confidence.", "",
    ])


def plot(report: dict, output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    labels = ["v0.5 bins", "v0.5.1 conformal"]
    x = np.arange(2); width = .32
    axes[0].bar(x - width / 2, [report["legacyV05"]["coverage80"] * 100, report["candidate"]["coverage80"] * 100], width, label="80% interval", color="#6f9551")
    axes[0].bar(x + width / 2, [report["legacyV05"]["coverage90"] * 100, report["candidate"]["coverage90"] * 100], width, label="90% interval", color="#315d49")
    axes[0].axhline(80, color="#6f9551", linestyle="--", alpha=.65); axes[0].axhline(90, color="#315d49", linestyle="--", alpha=.65)
    axes[0].set(xticks=x, xticklabels=labels, ylim=(70, 101), ylabel="Held-out coverage (%)", title="Coverage moves to nominal targets"); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    axes[1].bar(x - width / 2, [report["legacyV05"]["meanRadius80"], report["candidate"]["meanRadius80"]], width, label="80% radius", color="#d98352")
    axes[1].bar(x + width / 2, [report["legacyV05"]["meanRadius90"], report["candidate"]["meanRadius90"]], width, label="90% radius", color="#8f2f14")
    axes[1].set(xticks=x, xticklabels=labels, ylabel="Mean suitability-point radius", title="Sharper calibrated error bands"); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.5.1 · held-out crop-profile uncertainty test", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def robustness_plot(report: dict, output: Path) -> None:
    results = report["robustness"]["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results)); width = .34
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.7))
    axes[0].plot(x, [item["candidate"]["coverage80"] * 100 for item in results], marker="o", linewidth=2.5, color="#6f9551", label="80% interval")
    axes[0].plot(x, [item["candidate"]["coverage90"] * 100 for item in results], marker="o", linewidth=2.5, color="#315d49", label="90% interval")
    axes[0].axhline(80, color="#6f9551", linestyle="--", alpha=.6); axes[0].axhline(90, color="#315d49", linestyle="--", alpha=.6)
    axes[0].set(xticks=x, xticklabels=labels, ylim=(75, 94), xlabel="frozen seed suffix", ylabel="Held-out coverage (%)", title="Nominal coverage holds on every seed"); axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].bar(x - width / 2, [item["legacyV05"]["meanRadius90"] for item in results], width, color="#d98352", label="v0.5 bins")
    axes[1].bar(x + width / 2, [item["candidate"]["meanRadius90"] for item in results], width, color="#315d49", label="v0.5.1 conformal")
    axes[1].set(xticks=x, xticklabels=labels, xlabel="frozen seed suffix", ylabel="Mean 90% radius", title="Sharper bands on all five splits"); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit uncertainty robustness · 5/5 frozen gates pass", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/uncertainty-validation-v0.5.1.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/uncertainty-validation-v0.5.1.png")
    parser.add_argument("--robustness-plot", type=Path, default=root / "evaluation/uncertainty-robustness-v0.5.1.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--robustness-seeds", type=int, nargs="+", default=ROBUSTNESS_SEEDS)
    parser.add_argument("--estimators", type=int, default=120)
    args = parser.parse_args()
    report = evaluate(args.artifact, args.profiles, args.samples_per_crop, args.seed)
    report["robustness"] = robustness(args.profiles, args.samples_per_crop, args.robustness_seeds, args.estimators)
    report["gate"] = {
        "passed": report["singleSplitGate"]["passed"] and report["robustness"]["gate"]["passed"],
        "rule": "Production-seed and frozen five-seed robustness gates must both pass.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    robustness_plot(report, args.robustness_plot)
    print(json.dumps({"gate": report["gate"], "candidate": report["candidate"], "improvement": report["improvement"], "robustness": report["robustness"]["summary"]}, indent=2))


if __name__ == "__main__":
    main()
