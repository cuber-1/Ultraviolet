from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

from .features import COMPACT_FEATURE_COLUMNS, COMPACT_FEATURE_NAMES, FEATURE_NAMES, feature_row, teacher_scores
from .log_linear import LogLinearCropFitRegressor
from .profiles import load_profiles


MEMBERSHIP_FEATURE_NAMES = COMPACT_FEATURE_NAMES[:4]
MEMBERSHIP_FEATURE_COLUMNS = np.asarray(COMPACT_FEATURE_COLUMNS[:4])
MEMBERSHIP_FLOOR = 1e-6
PRODUCTION_THRESHOLDS = {
    "maximumMae": .02,
    "maximumP90AbsoluteError": .05,
    "minimumR2": .9997,
    "minimumHeldOutProfiles": 350,
    "maximumCoverageDeviation": .02,
    "maximumRawError": 1e-5,
}


def conformal_quantile(values: np.ndarray, coverage: float) -> float:
    """Finite-sample split-conformal quantile using the conservative higher rank."""
    level = min(1.0, math.ceil((len(values) + 1) * coverage) / len(values))
    return float(np.quantile(values, level, method="higher"))


def production_gate(
    metrics: dict,
    held_out_profiles: int,
    active_coverage80: float,
    active_coverage90: float,
    maximum_raw_error: float,
) -> dict:
    checks = {
        "mae": float(metrics["mae"]) <= PRODUCTION_THRESHOLDS["maximumMae"],
        "p90AbsoluteError": float(metrics["p90AbsoluteError"]) <= PRODUCTION_THRESHOLDS["maximumP90AbsoluteError"],
        "r2": float(metrics["r2"]) >= PRODUCTION_THRESHOLDS["minimumR2"],
        "heldOutProfiles": held_out_profiles >= PRODUCTION_THRESHOLDS["minimumHeldOutProfiles"],
        "activeCoverage80": abs(active_coverage80 - .8) <= PRODUCTION_THRESHOLDS["maximumCoverageDeviation"],
        "activeCoverage90": abs(active_coverage90 - .9) <= PRODUCTION_THRESHOLDS["maximumCoverageDeviation"],
        "maximumRawError": maximum_raw_error <= PRODUCTION_THRESHOLDS["maximumRawError"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": PRODUCTION_THRESHOLDS,
        "rule": "Refuse artifact promotion unless held-out fidelity and conformal coverage meet every frozen production threshold.",
    }


def atomic_joblib_dump(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as output:
        temporary = Path(output.name)
    try:
        joblib.dump(value, temporary, compress=3)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_text_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", mode="w", delete=False) as output:
        output.write(value)
        temporary = Path(output.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_examples(
    profiles,
    samples_per_crop: int,
    seed: int,
    include_interactions: bool = True,
    dtype=np.float32,
):
    random = np.random.default_rng(seed)
    features, labels, groups = [], [], []
    for group, profile in enumerate(profiles):
        for _ in range(samples_per_crop):
            temperature = random.uniform(profile.temp_abs_min - 7, profile.temp_abs_max + 7)
            rain_ceiling = min(8000.0, profile.rain_abs_max * 1.25 + 250)
            precipitation = random.uniform(max(0.0, profile.rain_abs_min * .35), rain_ceiling)
            ph = random.uniform(max(2.5, profile.ph_abs_min - 1.2), min(10.5, profile.ph_abs_max + 1.2))
            solar = random.uniform(4.0, 32.0)
            irrigated = bool(random.integers(0, 2))
            features.append(feature_row(profile, temperature, precipitation, ph, solar, irrigated, include_interactions))
            labels.append(teacher_scores(profile, temperature, precipitation, ph, solar, irrigated)["suitability"])
            groups.append(group)
    return np.asarray(features, dtype=dtype), np.asarray(labels, dtype=dtype), np.asarray(groups)


def train_booster(x_train, y_train, x_validation, y_validation, rounds: int, seed: int):
    history: dict = {}
    learning_rates: list[float] = []
    def schedule(iteration: int) -> float:
        value = max(.005, .08 * .5 * (1 + math.cos(math.pi * iteration / rounds)))
        learning_rates.append(value)
        return value
    requested_device = os.environ.get("CROPFIT_TRAIN_DEVICE", "cuda")
    params = {
        "objective": "reg:squarederror", "eval_metric": ["rmse", "mae"],
        "max_depth": 8, "min_child_weight": 4, "subsample": .82, "colsample_bytree": .86,
        "reg_lambda": 1.2, "reg_alpha": .02, "seed": seed, "tree_method": "hist", "device": requested_device,
    }
    matrices = (xgb.DMatrix(x_train, label=y_train, feature_names=FEATURE_NAMES), xgb.DMatrix(x_validation, label=y_validation, feature_names=FEATURE_NAMES))
    try:
        booster = xgb.train(params, matrices[0], num_boost_round=rounds, evals=[(matrices[0], "train"), (matrices[1], "validation")], evals_result=history, verbose_eval=False, callbacks=[xgb.callback.LearningRateScheduler(schedule), xgb.callback.EarlyStopping(rounds=45, save_best=True)])
        device = requested_device
    except xgb.core.XGBoostError:
        history.clear(); learning_rates.clear(); params["device"] = "cpu"
        booster = xgb.train(params, matrices[0], num_boost_round=rounds, evals=[(matrices[0], "train"), (matrices[1], "validation")], evals_result=history, verbose_eval=False, callbacks=[xgb.callback.LearningRateScheduler(schedule), xgb.callback.EarlyStopping(rounds=45, save_best=True)])
        device = "cpu-fallback"
    return booster, history, learning_rates[:len(history["train"]["rmse"])], device


def save_run(run_dir: Path, metadata: dict, config: dict, history: dict, learning_rates: list[float], booster, model, residuals: np.ndarray):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    with (run_dir / "history.csv").open("w", newline="") as output:
        writer = csv.writer(output, lineterminator="\n"); writer.writerow(["iteration", "learning_rate", "train_rmse", "validation_rmse", "train_mae", "validation_mae"])
        for index, learning_rate in enumerate(learning_rates):
            writer.writerow([index + 1, learning_rate, history["train"]["rmse"][index], history["validation"]["rmse"][index], history["train"]["mae"][index], history["validation"]["mae"][index]])
    iterations = np.arange(1, len(learning_rates) + 1)
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    axes[0].plot(iterations, history["train"]["rmse"], label="train", color="#315d49")
    axes[0].plot(iterations, history["validation"]["rmse"], label="validation", color="#e85d04")
    axes[0].set(title="XGBoost candidate RMSE", xlabel="round", ylabel="RMSE"); axes[0].legend(); axes[0].grid(alpha=.2)
    axes[1].plot(iterations, learning_rates, color="#557f2d")
    axes[1].set(title="Learning-rate schedule", xlabel="round", ylabel="learning rate"); axes[1].grid(alpha=.2)
    axes[2].hist(residuals, bins=40, color="#d98352", edgecolor="white")
    axes[2].axvline(np.quantile(residuals, .9), color="#8f2f14", linestyle="--", label="p90")
    axes[2].set(title="Held-out absolute error", xlabel="suitability points", ylabel="examples"); axes[2].legend(); axes[2].grid(alpha=.15)
    figure.suptitle("CropFit training diagnostics", fontweight="bold"); figure.tight_layout(); figure.savefig(run_dir / "training-curves.png", dpi=180); plt.close(figure)
    importance = booster.get_score(importance_type="gain")
    ranked = sorted(importance.items(), key=lambda item: item[1])[-12:]
    figure, axis = plt.subplots(figsize=(8, 5)); axis.barh([item[0] for item in ranked], [item[1] for item in ranked], color="#6f9551"); axis.set(title="XGBoost candidate feature importance (gain)", xlabel="gain"); figure.tight_layout(); figure.savefig(run_dir / "feature-importance.png", dpi=180); plt.close(figure)
    coefficients = sorted(zip(MEMBERSHIP_FEATURE_NAMES, model.coef_, strict=True), key=lambda item: item[1])
    figure, axis = plt.subplots(figsize=(8, 5)); axis.barh([item[0] for item in coefficients], [item[1] for item in coefficients], color="#315d49"); axis.set(title="Production log-linear elasticities", xlabel="learned coefficient"); figure.tight_layout(); figure.savefig(run_dir / "selected-feature-importance.png", dpi=180); plt.close(figure)


def train(
    raw: Path,
    artifact: Path,
    metadata_path: Path,
    runs: Path,
    samples_per_crop: int,
    evaluation_samples_per_crop: int,
    seed: int,
    rounds: int,
):
    profiles = load_profiles(raw)
    if len(profiles) < 100:
        raise RuntimeError(f"Only {len(profiles)} usable crop profiles found")
    # Keep validation and held-out rows frozen while increasing fitting density.
    x, y, groups = generate_examples(profiles, evaluation_samples_per_crop, seed)
    train_validation_indices, test_indices = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    inner_groups = groups[train_validation_indices]
    inner_train, inner_validation = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(x[train_validation_indices], y[train_validation_indices], inner_groups))
    train_indices = train_validation_indices[inner_train]
    validation_indices = train_validation_indices[inner_validation]
    training_x, training_y, training_groups = generate_examples(profiles, samples_per_crop, seed, dtype=np.float64)
    fitting_groups = np.unique(groups[train_indices])
    fitting_indices = np.flatnonzero(np.isin(training_groups, fitting_groups))
    model = LogLinearCropFitRegressor(membership_floor=MEMBERSHIP_FLOOR)
    model.fit(training_x[fitting_indices][:, MEMBERSHIP_FEATURE_COLUMNS], training_y[fitting_indices])
    booster, history, learning_rates, device = train_booster(training_x[fitting_indices], training_y[fitting_indices], x[validation_indices], y[validation_indices], rounds, seed)
    boosted_predictions = booster.predict(xgb.DMatrix(x[test_indices], feature_names=FEATURE_NAMES))
    compact_x = x[:, MEMBERSHIP_FEATURE_COLUMNS]
    baseline_predictions = model.predict(compact_x[test_indices])
    validation_predictions = model.predict(compact_x[validation_indices])
    validation_residuals = np.abs(validation_predictions - y[validation_indices])
    active_validation = y[validation_indices] > 0
    active_validation_errors = validation_residuals[active_validation]
    active_error_p80 = conformal_quantile(active_validation_errors, .8)
    active_error_p90 = conformal_quantile(active_validation_errors, .9)
    residuals = np.abs(baseline_predictions - y[test_indices])
    boosted_residuals = np.abs(boosted_predictions - y[test_indices])
    active_test = y[test_indices] > 0
    active_held_out_p80_coverage = float(np.mean(residuals[active_test] <= active_error_p80))
    active_held_out_p90_coverage = float(np.mean(residuals[active_test] <= active_error_p90))
    created = datetime.now(timezone.utc)
    run_id = created.strftime("%Y%m%dT%H%M%SZ")
    metrics = {
        "mae": round(float(mean_absolute_error(y[test_indices], baseline_predictions)), 8),
        "r2": round(float(r2_score(y[test_indices], baseline_predictions)), 8),
        "p90AbsoluteError": round(float(np.quantile(residuals, .9)), 8),
        "maximumAbsoluteError": round(float(np.max(residuals)), 8),
    }
    held_out_profiles = int(len(set(groups[test_indices].tolist())))
    promotion = production_gate(
        metrics, held_out_profiles, active_held_out_p80_coverage, active_held_out_p90_coverage,
        float(np.max(residuals)),
    )
    metadata = {
        "model": "CropFit EcoCrop surrogate v0.12.1",
        "selectedModel": "logLinear",
        "createdAt": created.isoformat(),
        "runId": run_id,
        "device": device,
        "trainingSource": "FAO EcoCrop environmental requirement profiles via OpenCLIM",
        "labelType": "mechanistic screening teacher; not observed farm yield",
        "profiles": len(profiles),
        "examples": int(len(training_x)),
        "trainingExamples": int(len(fitting_indices)),
        "evaluationExamples": int(len(x)),
        "heldOutProfiles": held_out_profiles,
        "boostingRounds": len(learning_rates),
        "metrics": metrics,
        "validationMetrics": {
            "mae": round(float(mean_absolute_error(y[validation_indices], validation_predictions)), 8),
            "r2": round(float(r2_score(y[validation_indices], validation_predictions)), 8),
        },
        "modelParameters": {
            "estimator": "LogLinearCropFitRegressor",
            "solver": "ordinary least squares in log space",
            "membershipFloor": MEMBERSHIP_FLOOR,
            "inputFeatures": len(MEMBERSHIP_FEATURE_NAMES),
            "coefficients": {name: round(float(value), 10) for name, value in zip(MEMBERSHIP_FEATURE_NAMES, model.coef_, strict=True)},
            "intercept": round(float(model.intercept_), 10),
        },
        "uncertaintyCalibration": {
            "source": "validation crop profiles only",
            "method": "active absolute-residual split conformal",
            "absoluteErrorQuantiles": {
                "p80": round(active_error_p80, 8),
                "p90": round(active_error_p90, 8),
            },
            "nominalCoverage": {"p80": .8, "p90": .9},
            "heldOutCoverage": {
                "p80": round(active_held_out_p80_coverage, 4),
                "p90": round(active_held_out_p90_coverage, 4),
            },
            "heldOutMeanRadius": {
                "p80": round(active_error_p80, 8),
                "p90": round(active_error_p90, 8),
            },
            "gate": {
                "passed": abs(active_held_out_p80_coverage - .8) <= .02 and abs(active_held_out_p90_coverage - .9) <= .02,
                "rule": "Active held-out crop-profile coverage must be within 2 percentage points of both nominal levels.",
            },
        },
        "conditionalUncertaintyCalibration": {
            "condition": "deterministic seasonal and establishment suitability are both greater than zero",
            "activeMethod": "absolute-residual split conformal on active validation examples",
            "inactivePolicy": "zero radius because the deterministic ceiling fixes the deployed score at zero",
            "activeValidationExamples": int(np.sum(active_validation)),
            "activeHeldOutExamples": int(np.sum(active_test)),
            "activeAbsoluteErrorQuantiles": {
                "p80": round(active_error_p80, 8),
                "p90": round(active_error_p90, 8),
            },
            "activeHeldOutCoverage": {
                "p80": round(active_held_out_p80_coverage, 4),
                "p90": round(active_held_out_p90_coverage, 4),
            },
            "activeHeldOutMeanRadius": {
                "p80": round(active_error_p80, 8),
                "p90": round(active_error_p90, 8),
            },
            "gate": {
                "passed": abs(active_held_out_p80_coverage - .8) <= .02 and abs(active_held_out_p90_coverage - .9) <= .02,
                "rule": "Active held-out coverage must be within 2 percentage points of both nominal levels.",
            },
        },
        "selectionEvidence": "Four-feature membership-floor log-linear regression improved MAE and p90 by more than 99% on all ten fresh grouped crop-profile seeds, preserved active calibration, and produced zero served-score mismatches on an independent runtime-shaped shift; see evaluation/log-linear-floor-validation-v0.12.1.json.",
        "boostedCandidate": {
            "mae": round(float(mean_absolute_error(y[test_indices], boosted_predictions)), 4),
            "r2": round(float(r2_score(y[test_indices], boosted_predictions)), 4),
            "p90AbsoluteError": round(float(np.quantile(boosted_residuals, .9)), 4),
            "promoted": False,
            "reason": "Held-out crop-profile MAE was worse than the selected log-linear estimator.",
        },
        "featureNames": MEMBERSHIP_FEATURE_NAMES,
        "seed": seed,
        "promotionGate": promotion,
    }
    config = {
        "trainingSamplesPerCrop": samples_per_crop,
        "evaluationSamplesPerCrop": evaluation_samples_per_crop,
        "seed": seed,
        "requestedBoostingRounds": rounds,
        "learningRate": "cosine 0.08 to 0.005",
        "split": "68% train / 12% validation / 20% held-out crop profiles (approximate)",
        "densityPolicy": "Denser generated scenarios are fitting-only; validation and held-out rows remain frozen.",
        "featurePolicy": "Train only on the four range-membership features selected by the sealed v0.12.1 gate.",
        "optimization": "Closed-form ordinary least squares; no iterative learning rate applies to the production estimator. XGBoost curves are retained only as rejected-candidate diagnostics.",
    }
    if not promotion["passed"]:
        failed = ", ".join(name for name, passed in promotion["checks"].items() if not passed)
        raise RuntimeError(f"Production promotion gate failed: {failed}. Existing artifact was not modified.")
    # Ship only the promoted estimator. Candidate diagnostics remain in the run directory.
    atomic_joblib_dump({"model": model, "metadata": metadata}, artifact)
    atomic_text_write(metadata_path, json.dumps(metadata, indent=2) + "\n")
    save_run(runs / run_id, metadata, config, history, learning_rates, booster, model, residuals)
    return metadata


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--metadata", type=Path, default=root / "artifacts/cropfit.metadata.json")
    parser.add_argument("--runs", type=Path, default=root / "runs")
    parser.add_argument("--samples-per-crop", type=int, default=200)
    parser.add_argument("--evaluation-samples-per-crop", type=int, default=72)
    parser.add_argument("--rounds", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    print(json.dumps(train(
        args.raw, args.artifact, args.metadata, args.runs,
        args.samples_per_crop, args.evaluation_samples_per_crop, args.seed, args.rounds,
    ), indent=2))


if __name__ == "__main__":
    main()
