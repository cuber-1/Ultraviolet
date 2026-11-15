from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

from .estimator_validation import split_indices
from .profiles import load_profiles
from .scenario_shift_validation import coverage, model_metrics, shifted_examples, validation_quantiles
from .training import generate_examples


SEED = 20261114
EVALUATION_DENSITY = 72
CHAMPION_DENSITY = 120
CHAMPION_TREES = 70
CANDIDATE_DENSITY = 240
CANDIDATE_TREES = 32


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, SEED)
    train, validation, test = split_indices(x, y, groups, SEED)
    training_x, training_y, training_groups = generate_examples(profiles, CHAMPION_DENSITY, SEED)
    fitting_groups = np.unique(groups[train])
    fitting_indices = np.flatnonzero(np.isin(training_groups, fitting_groups))
    champion = ExtraTreesRegressor(
        n_estimators=CHAMPION_TREES,
        min_samples_leaf=1,
        max_features=1.0,
        n_jobs=-1,
        random_state=SEED,
    ).fit(training_x[fitting_indices], training_y[fitting_indices])
    candidate_x, candidate_y, candidate_groups = generate_examples(profiles, CANDIDATE_DENSITY, SEED)
    candidate_indices = np.flatnonzero(np.isin(candidate_groups, fitting_groups))
    candidate = ExtraTreesRegressor(
        n_estimators=CANDIDATE_TREES,
        min_samples_leaf=1,
        max_features=1.0,
        n_jobs=-1,
        random_state=SEED,
    ).fit(candidate_x[candidate_indices], candidate_y[candidate_indices])
    shifted_x, shifted_y, irrigated = shifted_examples(profiles, np.unique(groups[test]))
    old = model_metrics(champion, shifted_x, shifted_y, irrigated)
    new = model_metrics(candidate, shifted_x, shifted_y, irrigated)
    active = shifted_y > 0
    quantiles = validation_quantiles(candidate, x, y, validation, active_only=True)
    shifted_coverage = coverage(new["errors"], new["treeStd"], active, quantiles)
    frozen_trees = np.asarray([tree.predict(x[test]) for tree in candidate.estimators_])
    frozen_errors = np.abs(frozen_trees.mean(axis=0) - y[test])
    frozen_coverage = coverage(
        frozen_errors, frozen_trees.std(axis=0), y[test] > 0, quantiles,
    )
    frozen_coverage = {"p80": frozen_coverage["p80"], "p90": frozen_coverage["p90"]}
    gains = {
        "maePercent": round(100 * (old["mae"] - new["mae"]) / old["mae"], 2),
        "p90Percent": round(100 * (old["p90AbsoluteError"] - new["p90AbsoluteError"]) / old["p90AbsoluteError"], 2),
        "deployedMaePercent": round(100 * (old["deployedMae"] - new["deployedMae"]) / old["deployedMae"], 2),
        "deployedP90Percent": round(100 * (old["deployedP90AbsoluteError"] - new["deployedP90AbsoluteError"]) / old["deployedP90AbsoluteError"], 2),
    }
    gate = {
        "passed": (
            min(gains.values()) >= 5
            and all(
                new["subgroups"][name]["mae"] < old["subgroups"][name]["mae"]
                for name in ("irrigated", "rainfed", "active")
            )
            and abs(frozen_coverage["p80"] - .8) <= .02
            and abs(frozen_coverage["p90"] - .9) <= .02
            and abs(shifted_coverage["p80"] - .8) <= .02
            and abs(shifted_coverage["p90"] - .9) <= .02
        ),
        "rule": (
            "Against the exact v0.9.1 estimator, all raw and deployed error gains must be >=5% "
            "on independently generated Latin-hypercube scenarios; irrigated, rainfed, and active "
            "MAE must each improve; active coverage must remain within 2 points of nominal on both "
            "frozen-random and shifted tests."
        ),
    }
    for item in (old, new):
        item.pop("treeStd")
        item.pop("errors")
    return {
        "name": "CropFit v0.10 independent density-shift validation",
        "target": "EcoCrop mechanistic screening teacher; not observed yield",
        "protocol": {
            "profiles": len(np.unique(groups[test])),
            "scenariosPerProfile": 64,
            "examples": len(shifted_y),
            "generator": "Independently seeded scipy LatinHypercube over the same physical support; not the training generator.",
            "champion": "v0.9.1 reconstructed with 120 fitting scenarios per crop and 70 Extra Trees",
            "candidate": "v0.10 candidate reconstructed with 240 fitting scenarios per crop and 32 Extra Trees",
            "heldOutPolicy": "Production-seed test crop profiles only; candidate selected without this shifted set.",
            "declaredGate": gate["rule"],
        },
        "championV09": old,
        "candidateV010": new,
        "gains": gains,
        "activeCoverage": {
            "frozenRandom": frozen_coverage,
            "independentShift": shifted_coverage,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    old, new, gains = report["championV09"], report["candidateV010"], report["gains"]
    coverage_report = report["activeCoverage"]
    lines = [
        "# CropFit v0.10 independent density-shift validation", "",
        "The v0.10 candidate was selected on frozen random development splits. This report tests it against v0.9.1 on a separately seeded Latin-hypercube scenario generator over the same held-out crop profiles.", "",
        "| Metric | v0.9.1 | v0.10 | Gain |", "|---|---:|---:|---:|",
        f'| Raw MAE | {old["mae"]:.5f} | {new["mae"]:.5f} | {gains["maePercent"]:.2f}% |',
        f'| Raw p90 error | {old["p90AbsoluteError"]:.5f} | {new["p90AbsoluteError"]:.5f} | {gains["p90Percent"]:.2f}% |',
        f'| Deployed MAE | {old["deployedMae"]:.5f} | {new["deployedMae"]:.5f} | {gains["deployedMaePercent"]:.2f}% |',
        f'| Deployed p90 error | {old["deployedP90AbsoluteError"]:.5f} | {new["deployedP90AbsoluteError"]:.5f} | {gains["deployedP90Percent"]:.2f}% |',
        "", f'Active conditional coverage is **{coverage_report["independentShift"]["p80"]:.1%} / {coverage_report["independentShift"]["p90"]:.1%}** on shifted scenarios and **{coverage_report["frozenRandom"]["p80"]:.1%} / {coverage_report["frozenRandom"]["p90"]:.1%}** on frozen-random held-out scenarios.',
        "", f'Gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> This validates mechanistic-teacher fidelity under scenario shift. It does not validate observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    gains = report["gains"]
    coverage_report = report["activeCoverage"]
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    names = ["raw MAE", "raw p90", "deployed MAE", "deployed p90"]
    values = [gains["maePercent"], gains["p90Percent"], gains["deployedMaePercent"], gains["deployedP90Percent"]]
    axes[0].bar(names, values, color=["#315d49", "#6f9551", "#315d49", "#6f9551"])
    axes[0].axhline(5, color="#d98352", linestyle="--", label="promotion floor")
    axes[0].set(ylabel="Error reduction (%)", title="Independent scenario-shift gain")
    axes[0].tick_params(axis="x", rotation=18); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    x = np.arange(2); width = .32
    axes[1].bar(x - width / 2, [coverage_report["frozenRandom"]["p80"], coverage_report["independentShift"]["p80"]], width, color="#d98352", label="80% interval")
    axes[1].bar(x + width / 2, [coverage_report["frozenRandom"]["p90"], coverage_report["independentShift"]["p90"]], width, color="#315d49", label="90% interval")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=x, xticklabels=["frozen random", "independent shift"], ylim=(.75, .95), ylabel="Active-case coverage", title="Conditional uncertainty transfers")
    axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.10 candidate · independent shift rejects promotion", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/density-shift-validation-v0.10.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/density-shift-validation-v0.10.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"gains": report["gains"], "activeCoverage": report["activeCoverage"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
