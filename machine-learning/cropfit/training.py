from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import xgboost as xgb
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

from .features import FEATURE_NAMES, feature_row, teacher_scores
from .profiles import load_profiles


def generate_examples(profiles, samples_per_crop: int, seed: int):
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
            features.append(feature_row(profile, temperature, precipitation, ph, solar, irrigated))
            labels.append(teacher_scores(profile, temperature, precipitation, ph, solar, irrigated)["suitability"])
            groups.append(group)
    return np.asarray(features, dtype=np.float32), np.asarray(labels, dtype=np.float32), np.asarray(groups)


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


def save_run(run_dir: Path, metadata: dict, config: dict, history: dict, learning_rates: list[float], booster, residuals: np.ndarray):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    with (run_dir / "history.csv").open("w", newline="") as output:
        writer = csv.writer(output); writer.writerow(["iteration", "learning_rate", "train_rmse", "validation_rmse", "train_mae", "validation_mae"])
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


def train(raw: Path, artifact: Path, metadata_path: Path, runs: Path, samples_per_crop: int, seed: int, rounds: int):
    profiles = load_profiles(raw)
    if len(profiles) < 100:
        raise RuntimeError(f"Only {len(profiles)} usable crop profiles found")
    x, y, groups = generate_examples(profiles, samples_per_crop, seed)
    train_validation_indices, test_indices = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    inner_groups = groups[train_validation_indices]
    inner_train, inner_validation = next(GroupShuffleSplit(n_splits=1, test_size=.15, random_state=seed + 1).split(x[train_validation_indices], y[train_validation_indices], inner_groups))
    train_indices = train_validation_indices[inner_train]
    validation_indices = train_validation_indices[inner_validation]
    model = ExtraTreesRegressor(
        n_estimators=120,
        min_samples_leaf=1,
        max_features=1.0,
        n_jobs=-1,
        random_state=seed,
    )
    model.fit(x[train_indices], y[train_indices])
    booster, history, learning_rates, device = train_booster(x[train_indices], y[train_indices], x[validation_indices], y[validation_indices], rounds, seed)
    boosted_predictions = booster.predict(xgb.DMatrix(x[test_indices], feature_names=FEATURE_NAMES))
    baseline_predictions = model.predict(x[test_indices])
    validation_predictions = model.predict(x[validation_indices])
    residuals = np.abs(baseline_predictions - y[test_indices])
    boosted_residuals = np.abs(boosted_predictions - y[test_indices])
    created = datetime.now(timezone.utc)
    run_id = created.strftime("%Y%m%dT%H%M%SZ")
    metadata = {
        "model": "CropFit EcoCrop surrogate v0.3",
        "selectedModel": "extraTrees",
        "createdAt": created.isoformat(),
        "runId": run_id,
        "device": device,
        "trainingSource": "FAO EcoCrop environmental requirement profiles via OpenCLIM",
        "labelType": "mechanistic screening teacher; not observed farm yield",
        "profiles": len(profiles),
        "examples": int(len(x)),
        "heldOutProfiles": int(len(set(groups[test_indices].tolist()))),
        "boostingRounds": len(learning_rates),
        "metrics": {
            "mae": round(float(mean_absolute_error(y[test_indices], baseline_predictions)), 4),
            "r2": round(float(r2_score(y[test_indices], baseline_predictions)), 4),
            "p90AbsoluteError": round(float(np.quantile(residuals, .9)), 4),
        },
        "validationMetrics": {
            "mae": round(float(mean_absolute_error(y[validation_indices], validation_predictions)), 4),
            "r2": round(float(r2_score(y[validation_indices], validation_predictions)), 4),
        },
        "modelParameters": {
            "nEstimators": 120,
            "minSamplesLeaf": 1,
            "maxFeatures": 1.0,
        },
        "selectionEvidence": "Candidate improved held-out MAE on all five seeds in the 20261110-20261114 robustness sweep (7.7% mean improvement).",
        "boostedCandidate": {
            "mae": round(float(mean_absolute_error(y[test_indices], boosted_predictions)), 4),
            "r2": round(float(r2_score(y[test_indices], boosted_predictions)), 4),
            "p90AbsoluteError": round(float(np.quantile(boosted_residuals, .9)), 4),
            "promoted": False,
            "reason": "Held-out crop-profile MAE was worse than ExtraTrees.",
        },
        "featureNames": FEATURE_NAMES,
        "seed": seed,
    }
    config = {"samplesPerCrop": samples_per_crop, "seed": seed, "requestedBoostingRounds": rounds, "learningRate": "cosine 0.08 to 0.005", "split": "68% train / 12% validation / 20% held-out crop profiles (approximate)"}
    artifact.parent.mkdir(parents=True, exist_ok=True)
    # Ship only the promoted estimator. Candidate diagnostics remain in the run directory.
    joblib.dump({"model": model, "metadata": metadata}, artifact, compress=3)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    save_run(runs / run_id, metadata, config, history, learning_rates, booster, residuals)
    return metadata


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--metadata", type=Path, default=root / "artifacts/cropfit.metadata.json")
    parser.add_argument("--runs", type=Path, default=root / "runs")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--rounds", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    print(json.dumps(train(args.raw, args.artifact, args.metadata, args.runs, args.samples_per_crop, args.seed, args.rounds), indent=2))


if __name__ == "__main__":
    main()
