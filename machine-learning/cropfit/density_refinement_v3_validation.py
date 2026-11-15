from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .density_refinement_validation import estimator
from .estimator_validation import split_indices
from .features import COMPACT_FEATURE_COLUMNS, COMPACT_FEATURE_NAMES
from .interaction_compaction_validation import evaluate, markdown, plot
from .profiles import load_profiles
from .training import generate_examples


CONFIRMATION_SEEDS = list(range(20270320, 20270325))
FINAL_SEEDS = list(range(20270325, 20270330))
SHIFT_SEED = 20270330


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, 72, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    fitting_groups = np.unique(groups[train])
    columns = np.asarray(COMPACT_FEATURE_COLUMNS)
    models = {}
    for name, density, trees in (("championV011", 200, 40), ("interactionCandidate", 300, 28)):
        training_x, training_y, training_groups = generate_examples(profiles, density, seed)
        fitting_indices = np.flatnonzero(np.isin(training_groups, fitting_groups))
        model = estimator(trees, seed)
        started = perf_counter()
        model.fit(training_x[fitting_indices][:, columns], training_y[fitting_indices])
        models[name] = {"model": model, "columns": columns, "fitSeconds": round(perf_counter() - started, 3)}
    return models, x, y, groups, np.asarray([validation, test], dtype=object)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/density-refinement-v3-validation-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/density-refinement-v3-validation-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/density-refinement-v3-validation-v0.12.png")
    args = parser.parse_args()
    report = evaluate(
        args.profiles,
        fit_pair_fn=fit_pair,
        confirmation_seeds=CONFIRMATION_SEEDS,
        final_seeds=FINAL_SEEDS,
        shift_seed=SHIFT_SEED,
        mean_gain_floor=5,
        shift_gain_floor=5,
        maximum_size_bytes=70_000_000,
        require_smaller_size=False,
        latency_ceiling=1.05,
        validation_name="CropFit compact-feature density refinement v3 validation v0.12 candidate",
        protocol_candidate="six v0.11 features, 300 fitting scenarios per crop, 28 Extra Trees",
        candidate_features=COMPACT_FEATURE_NAMES,
        selection=(
            "Development seeds 20270201-20270203 compared 220/36, 240/32, 260/30, and 300/28 "
            "density/tree configurations against v0.11's 200/40 design. The 300/28 option was the "
            "only candidate with material frozen and shifted error gains, sharper calibrated bands, "
            "and non-worse worst shifted tail. All report seeds were reserved after that choice."
        ),
    )
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(
        report,
        "The candidate retains all six v0.11 features and increases fitting density while reducing tree count. Validation and held-out rows remain frozen.",
        report_title="CropFit density-refinement v3 validation",
    ))
    plot(
        report,
        args.plot,
        figure_title="CropFit v0.12 density candidate rejected · unstable tails",
        heldout_title="Density-refined held-out gains",
        calibration_title="Density-candidate active calibration",
        tail_title="Deployed-tail regressions remain",
    )
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["gate"], indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Density-refinement v3 promotion gate did not pass")


if __name__ == "__main__":
    main()
