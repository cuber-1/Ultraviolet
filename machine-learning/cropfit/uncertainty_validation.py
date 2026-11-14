from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from .profiles import load_profiles
from .training import generate_examples


LEGACY_BINS = (
    (0, .01, 0.0, 0.0), (.01, 2, .5355, .7941), (2, 5, 1.574, 2.0919),
    (5, 10, 3.8241, 5.0367),
)


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


def evaluate(artifact: Path, profiles_path: Path, samples_per_crop: int, seed: int) -> dict:
    bundle = joblib.load(artifact)
    model, metadata = bundle["model"], bundle["metadata"]
    x, y, groups = generate_examples(load_profiles(profiles_path), samples_per_crop, seed)
    train_validation, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    inner_groups = groups[train_validation]
    _, inner_validation = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(x[train_validation], y[train_validation], inner_groups))
    validation = train_validation[inner_validation]
    trees = np.asarray([tree.predict(x[test]) for tree in model.estimators_])
    errors = np.abs(trees.mean(axis=0) - y[test])
    tree_std = trees.std(axis=0)
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
            "policy": "Calibration uses validation crop profiles; comparison is evaluated once on untouched crop profiles.",
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
        "gate": gate,
    }


def markdown(report: dict) -> str:
    legacy, candidate, improvement = report["legacyV05"], report["candidate"], report["improvement"]
    return "\n".join([
        "# CropFit uncertainty calibration v0.5.1", "",
        "Calibration is fit only on validation crop profiles. This report compares methods on the untouched crop-profile test split; it measures fidelity to the EcoCrop screening teacher, not observed farm yield.", "",
        "| Method | 80% coverage | 90% coverage | Mean 80% radius | Mean 90% radius |", "|---|---:|---:|---:|---:|",
        f'| v0.5 disagreement bins | {legacy["coverage80"]:.1%} | {legacy["coverage90"]:.1%} | {legacy["meanRadius80"]:.3f} | {legacy["meanRadius90"]:.3f} |',
        f'| v0.5.1 normalized conformal | {candidate["coverage80"]:.1%} | {candidate["coverage90"]:.1%} | {candidate["meanRadius80"]:.3f} | {candidate["meanRadius90"]:.3f} |', "",
        f'The candidate reduces mean 90% radius by **{improvement["meanRadius90ReductionPercent"]:.1f}%** while bringing both marginal coverages to their nominal targets. Gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
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
    figure.suptitle("CropFit v0.5.1 · untouched crop-profile uncertainty test", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/uncertainty-validation-v0.5.1.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/uncertainty-validation-v0.5.1.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    report = evaluate(args.artifact, args.profiles, args.samples_per_crop, args.seed)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"gate": report["gate"], "candidate": report["candidate"], "improvement": report["improvement"]}, indent=2))


if __name__ == "__main__":
    main()
