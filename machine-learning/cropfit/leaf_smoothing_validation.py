from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .density_refinement_validation import estimator
from .features import COMPACT_FEATURE_COLUMNS, COMPACT_FEATURE_NAMES
from .interaction_compaction_validation import evaluate, markdown, plot
from .profiles import load_profiles
from .training import generate_examples
from .estimator_validation import split_indices


CONFIRMATION_SEEDS = list(range(20270301, 20270306))
FINAL_SEEDS = list(range(20270306, 20270311))
SHIFT_SEED = 20270311


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, 72, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    training_x, training_y, training_groups = generate_examples(profiles, 200, seed)
    fitting_indices = np.flatnonzero(np.isin(training_groups, np.unique(groups[train])))
    columns = np.asarray(COMPACT_FEATURE_COLUMNS)
    models = {}
    for name, trees, leaf in (("championV011", 40, 1), ("interactionCandidate", 72, 2)):
        model = estimator(trees, seed)
        model.set_params(min_samples_leaf=leaf)
        started = perf_counter()
        model.fit(training_x[fitting_indices][:, columns], training_y[fitting_indices])
        models[name] = {"model": model, "columns": columns, "fitSeconds": round(perf_counter() - started, 3)}
    return models, x, y, groups, np.asarray([validation, test], dtype=object)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/leaf-smoothing-validation-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/leaf-smoothing-validation-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/leaf-smoothing-validation-v0.12.png")
    args = parser.parse_args()
    report = evaluate(
        args.profiles,
        fit_pair_fn=fit_pair,
        confirmation_seeds=CONFIRMATION_SEEDS,
        final_seeds=FINAL_SEEDS,
        shift_seed=SHIFT_SEED,
        mean_gain_floor=3,
        shift_gain_floor=5,
        maximum_size_bytes=60_000_000,
        latency_ceiling=1.0,
        validation_name="CropFit six-feature leaf-smoothing validation v0.12 candidate",
        protocol_candidate="six v0.11 features, 72 Extra Trees, min_samples_leaf=2",
        candidate_features=COMPACT_FEATURE_NAMES,
        selection=(
            "Development seeds 20270201-20270203 compared 48-72 smoothed six-feature trees and "
            "a 60-tree leaf-3 option. The 72-tree/leaf-2 candidate was the only Pareto option "
            "that improved mean frozen and shifted error, worst shifted tail, size, and latency. "
            "All seeds in this report were reserved until after that choice."
        ),
    )
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(
        report,
        "The candidate retains all six v0.11 features and smooths leaves while increasing tree count. Training density and evaluation rows are unchanged from v0.11.",
    ))
    plot(
        report,
        args.plot,
        figure_title="CropFit v0.12 smoothing candidate rejected · unstable tails",
        heldout_title="Leaf-smoothed held-out gains",
        tail_title="Deployed-tail regressions remain",
    )
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["gate"], indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Leaf-smoothing promotion gate did not pass")


if __name__ == "__main__":
    main()
