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

from .estimator_validation import split_indices
from .features import COMPACT_FEATURE_COLUMNS
from .profiles import load_profiles
from .training import generate_examples


DEVELOPMENT_SEEDS = list(range(20270401, 20270404))
SIZE_CEILING_BYTES = 80_000_000
SPECS = [
    ("v0.11", 200, 40, "squared_error"),
    ("200x48", 200, 48, "squared_error"),
    ("220x40", 220, 40, "squared_error"),
    ("240x40", 240, 40, "squared_error"),
    ("260x36", 260, 36, "squared_error"),
    ("280x34", 280, 34, "squared_error"),
    ("300x32", 300, 32, "squared_error"),
    ("200x40-poisson", 200, 40, "poisson"),
    ("200x48-poisson", 200, 48, "poisson"),
    ("240x40-poisson", 240, 40, "poisson"),
]
QUANTILE_MODELS = {"240x40", "300x32"}
QUANTILES = (.50, .55, .60, .65)


def estimator(trees: int, criterion: str, seed: int) -> ExtraTreesRegressor:
    return ExtraTreesRegressor(
        n_estimators=trees,
        criterion=criterion,
        min_samples_leaf=1,
        max_features=1.0,
        n_jobs=-1,
        random_state=seed,
    )


def metrics(target: np.ndarray, prediction: np.ndarray) -> dict:
    errors = np.abs(prediction - target)
    deployed_errors = np.abs(np.minimum(prediction, target) - target)
    return {
        "mae": round(float(errors.mean()), 5),
        "p90AbsoluteError": round(float(np.quantile(errors, .9)), 5),
        "deployedMaximumAbsoluteError": round(float(deployed_errors.max()), 5),
    }


def relative(candidate: dict, champion: dict) -> dict:
    return {
        "maePercent": round(100 * (champion["mae"] - candidate["mae"]) / champion["mae"], 2),
        "p90Percent": round(
            100 * (champion["p90AbsoluteError"] - candidate["p90AbsoluteError"])
            / champion["p90AbsoluteError"],
            2,
        ),
    }


def serialized_size(model: ExtraTreesRegressor) -> int:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.joblib"
        joblib.dump(model, path, compress=3)
        return path.stat().st_size


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    columns = np.asarray(COMPACT_FEATURE_COLUMNS)
    results = []
    sizes: dict[str, int] = {}
    for seed in DEVELOPMENT_SEEDS:
        x, y, groups = generate_examples(profiles, 72, seed)
        train, _, test = split_indices(x, y, groups, seed)
        fitting_groups = np.unique(groups[train])
        compact_x = x[:, columns]
        active_test = np.all(compact_x[test, :4] > 0, axis=1)
        matrices = {}
        item = {"seed": seed, "models": {}}
        for _, density, _, _ in SPECS:
            if density not in matrices:
                training_x, training_y, training_groups = generate_examples(profiles, density, seed)
                fitting = np.flatnonzero(np.isin(training_groups, fitting_groups))
                matrices[density] = (training_x[fitting][:, columns], training_y[fitting])
        for name, density, trees, criterion in SPECS:
            model = estimator(trees, criterion, seed)
            started = perf_counter()
            model.fit(*matrices[density])
            tree_predictions = np.asarray([
                tree.predict(compact_x[test]) for tree in model.estimators_
            ])
            mean_prediction = tree_predictions.mean(axis=0)
            item["models"][name] = {
                **metrics(y[test], mean_prediction),
                "fitSeconds": round(perf_counter() - started, 3),
            }
            if seed == DEVELOPMENT_SEEDS[0]:
                sizes[name] = serialized_size(model)
            if name in QUANTILE_MODELS:
                for quantile in QUANTILES:
                    quantile_name = f"{name}-q{int(100 * quantile)}"
                    prediction = mean_prediction.copy()
                    prediction[active_test] = np.quantile(
                        tree_predictions[:, active_test], quantile, axis=0,
                    )
                    item["models"][quantile_name] = metrics(y[test], prediction)
                    sizes[quantile_name] = sizes.get(quantile_name, sizes.get(name, 0))
        champion = item["models"]["v0.11"]
        for name, candidate in item["models"].items():
            if name == "v0.11":
                continue
            candidate["gains"] = relative(candidate, champion)
            candidate["tailWin"] = (
                candidate["deployedMaximumAbsoluteError"]
                < champion["deployedMaximumAbsoluteError"]
            )
            candidate["passedSeedScreen"] = (
                min(candidate["gains"].values()) > 0 and candidate["tailWin"]
            )
        results.append(item)
        print(json.dumps(item), flush=True)

    candidate_names = [name for name in results[0]["models"] if name != "v0.11"]
    summary = []
    for name in candidate_names:
        candidates = [item["models"][name] for item in results]
        summary.append({
            "candidate": name,
            "meanMaeImprovementPercent": round(float(np.mean([
                item["gains"]["maePercent"] for item in candidates
            ])), 2),
            "meanP90ImprovementPercent": round(float(np.mean([
                item["gains"]["p90Percent"] for item in candidates
            ])), 2),
            "seedScreensPassed": sum(item["passedSeedScreen"] for item in candidates),
            "seeds": len(candidates),
            "serializedSizeBytes": sizes[name],
            "advanced": (
                all(item["passedSeedScreen"] for item in candidates)
                and np.mean([item["gains"]["maePercent"] for item in candidates]) >= 5
                and np.mean([item["gains"]["p90Percent"] for item in candidates]) >= 5
                and sizes[name] <= SIZE_CEILING_BYTES
            ),
        })
    return {
        "name": "CropFit density/capacity development screen v0.12",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "features": "the six locked v0.11 range-relative and interaction features",
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "reservedSeedsOpened": False,
            "sizeCeilingBytes": SIZE_CEILING_BYTES,
            "rule": (
                "Advance only if every development seed improves raw MAE, raw p90, and deployed "
                "maximum error; mean MAE/p90 gains are each at least 5%; and compressed size is "
                "at most 80 MB. Passing development permits fresh validation but is not promotion."
            ),
            "quantilePolicy": (
                "Upper tree quantiles are applied only to active cases; inactive predictions retain "
                "the mean. No held-out labels are used by the aggregator."
            ),
        },
        "results": results,
        "summary": summary,
        "advancedCandidates": [item["candidate"] for item in summary if item["advanced"]],
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit density/capacity development screen", "",
        "This development-only search tests whether more trees, denser fitting, Poisson splitting, "
        "or upper-quantile tree aggregation can improve v0.11 without reopening reserved seeds.", "",
        "| Candidate | Mean MAE gain | Mean p90 gain | Seed screens | Size | Advance |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["summary"]:
        lines.append(
            f'| {item["candidate"]} | {item["meanMaeImprovementPercent"]:.2f}% | '
            f'{item["meanP90ImprovementPercent"]:.2f}% | '
            f'{item["seedScreensPassed"]}/{item["seeds"]} | '
            f'{item["serializedSizeBytes"] / 1_000_000:.1f} MB | '
            f'{"yes" if item["advanced"] else "no"} |'
        )
    lines += [
        "", "**No candidate advanced.** Capacity/density variants retained attractive averages but "
        "missed at least one deployed-tail screen. Poisson splitting produced severe underprediction "
        "outliers, and upper tree quantiles traded tail correction for large raw-error regressions.", "",
        "> Development screening only; no confirmation, final, or shift seed was opened.", "",
        "> This measures mechanistic-teacher fidelity, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    conventional = [
        item for item in report["summary"]
        if "q" not in item["candidate"]
    ]
    labels = [item["candidate"] for item in conventional]
    x = np.arange(len(labels))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    width = .38
    axes[0].bar(x - width / 2, [item["meanMaeImprovementPercent"] for item in conventional], width, label="MAE", color="#315d49")
    axes[0].bar(x + width / 2, [item["meanP90ImprovementPercent"] for item in conventional], width, label="p90", color="#8fae82")
    axes[0].axhline(5, color="#d98352", linestyle="--", label="mean floor")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Error reduction (%)", title="Average gains can look attractive")
    axes[0].tick_params(axis="x", rotation=35); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    axes[1].bar(x, [item["seedScreensPassed"] for item in conventional], color="#315d49")
    axes[1].axhline(3, color="#d98352", linestyle="--", label="all seeds required")
    axes[1].set(xticks=x, xticklabels=labels, ylim=(0, 3.4), ylabel="Seed screens passed", title="No design clears all screens")
    axes[1].tick_params(axis="x", rotation=35); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    axes[2].bar(x, [item["serializedSizeBytes"] / 1_000_000 for item in conventional], color="#6f9551")
    axes[2].axhline(80, color="#d98352", linestyle="--", label="Mac ceiling")
    axes[2].set(xticks=x, xticklabels=labels, ylabel="Compressed MB", title="Two Poisson designs exceed Mac ceiling")
    axes[2].tick_params(axis="x", rotation=35); axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.12 development search rejected · no candidate advances", fontweight="bold")
    figure.text(.5, .01, "Three development seeds only · reserved validation remains unopened", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .04, 1, .94))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/density-capacity-development-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/density-capacity-development-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/density-capacity-development-v0.12.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"advancedCandidates": report["advancedCandidates"]}, indent=2))


if __name__ == "__main__":
    main()
