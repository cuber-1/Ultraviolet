from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import qmc
from sklearn.ensemble import ExtraTreesRegressor

from .estimator_validation import split_indices
from .features import feature_row, teacher_scores
from .profiles import load_profiles
from .training import TREE_STD_FLOOR, conformal_quantile, generate_examples


SEED = 20261114
SCENARIOS_PER_PROFILE = 64


def shifted_examples(profiles: list, profile_groups: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows, labels, irrigated = [], [], []
    for group in profile_groups:
        profile = profiles[int(group)]
        samples = qmc.LatinHypercube(d=5, seed=SEED + int(group)).random(SCENARIOS_PER_PROFILE)
        for values in samples:
            temperature = profile.temp_abs_min - 7 + values[0] * (profile.temp_abs_max - profile.temp_abs_min + 14)
            rain_low = max(0.0, profile.rain_abs_min * .35)
            rain_high = min(8000.0, profile.rain_abs_max * 1.25 + 250)
            precipitation = rain_low + values[1] * (rain_high - rain_low)
            ph_low = max(2.5, profile.ph_abs_min - 1.2)
            ph_high = min(10.5, profile.ph_abs_max + 1.2)
            ph = ph_low + values[2] * (ph_high - ph_low)
            solar = 4 + values[3] * 28
            is_irrigated = bool(values[4] >= .5)
            rows.append(feature_row(profile, temperature, precipitation, ph, solar, is_irrigated))
            labels.append(teacher_scores(profile, temperature, precipitation, ph, solar, is_irrigated)["suitability"])
            irrigated.append(is_irrigated)
    return np.asarray(rows, dtype=np.float32), np.asarray(labels), np.asarray(irrigated)


def validation_quantiles(model, x: np.ndarray, y: np.ndarray, validation: np.ndarray, active_only: bool) -> tuple[float, float]:
    trees = np.asarray([tree.predict(x[validation]) for tree in model.estimators_])
    errors = np.abs(trees.mean(axis=0) - y[validation])
    std = trees.std(axis=0)
    mask = y[validation] > 0 if active_only else np.ones(len(validation), dtype=bool)
    normalized = errors[mask] / (std[mask] + TREE_STD_FLOOR)
    return conformal_quantile(normalized, .8), conformal_quantile(normalized, .9)


def model_metrics(model, x: np.ndarray, y: np.ndarray, irrigated: np.ndarray) -> dict:
    trees = np.asarray([tree.predict(x) for tree in model.estimators_])
    predicted = trees.mean(axis=0)
    errors = np.abs(predicted - y)
    deployed_errors = np.abs(np.minimum(predicted, y) - y)
    result = {
        "examples": len(y),
        "mae": round(float(np.mean(errors)), 5),
        "p90AbsoluteError": round(float(np.quantile(errors, .9)), 5),
        "maximumAbsoluteError": round(float(np.max(errors)), 5),
        "deployedMae": round(float(np.mean(deployed_errors)), 5),
        "deployedP90AbsoluteError": round(float(np.quantile(deployed_errors, .9)), 5),
        "deployedMaximumAbsoluteError": round(float(np.max(deployed_errors)), 5),
        "treeStd": trees.std(axis=0),
        "errors": errors,
    }
    result["subgroups"] = {}
    for name, mask in (("irrigated", irrigated), ("rainfed", ~irrigated), ("active", y > 0), ("hardZero", y == 0)):
        result["subgroups"][name] = {
            "examples": int(np.sum(mask)),
            "mae": round(float(np.mean(errors[mask])), 5),
            "p90AbsoluteError": round(float(np.quantile(errors[mask], .9)), 5),
        }
    return result


def coverage(errors: np.ndarray, std: np.ndarray, active: np.ndarray, quantiles: tuple[float, float]) -> dict:
    result = {}
    for name, nominal, quantile in (("p80", .8, quantiles[0]), ("p90", .9, quantiles[1])):
        radii = np.ceil(quantile * (std + TREE_STD_FLOOR) * 1000) / 1000
        result[name] = round(float(np.mean(errors[active] <= radii[active])), 4)
        result[f"meanRadius{name[-2:]}"] = round(float(np.mean(radii[active])), 4)
    return result


def evaluate(artifact: Path, profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    x, y, groups = generate_examples(profiles, 72, SEED)
    train, validation, test = split_indices(x, y, groups, SEED)
    champion = ExtraTreesRegressor(
        n_estimators=120, min_samples_leaf=1, max_features=1.0,
        n_jobs=-1, random_state=SEED,
    ).fit(x[train], y[train])
    bundle = joblib.load(artifact)
    candidate, metadata = bundle["model"], bundle["metadata"]
    shifted_x, shifted_y, irrigated = shifted_examples(profiles, np.unique(groups[test]))
    old = model_metrics(champion, shifted_x, shifted_y, irrigated)
    new = model_metrics(candidate, shifted_x, shifted_y, irrigated)
    active = shifted_y > 0
    global_quantiles = (
        float(metadata["uncertaintyCalibration"]["normalizedErrorQuantiles"]["p80"]),
        float(metadata["uncertaintyCalibration"]["normalizedErrorQuantiles"]["p90"]),
    )
    conditional_quantiles = (
        float(metadata["conditionalUncertaintyCalibration"]["activeNormalizedErrorQuantiles"]["p80"]),
        float(metadata["conditionalUncertaintyCalibration"]["activeNormalizedErrorQuantiles"]["p90"]),
    )
    shifted_global = coverage(new["errors"], new["treeStd"], active, global_quantiles)
    shifted_conditional = coverage(new["errors"], new["treeStd"], active, conditional_quantiles)
    random_conditional = metadata["conditionalUncertaintyCalibration"]["activeHeldOutCoverage"]
    gains = {
        "maePercent": round(100 * (old["mae"] - new["mae"]) / old["mae"], 2),
        "p90Percent": round(100 * (old["p90AbsoluteError"] - new["p90AbsoluteError"]) / old["p90AbsoluteError"], 2),
        "deployedMaePercent": round(100 * (old["deployedMae"] - new["deployedMae"]) / old["deployedMae"], 2),
        "deployedP90Percent": round(100 * (old["deployedP90AbsoluteError"] - new["deployedP90AbsoluteError"]) / old["deployedP90AbsoluteError"], 2),
    }
    gate = {
        "passed": (
            min(gains.values()) >= 10
            and all(new["subgroups"][name]["mae"] < old["subgroups"][name]["mae"] for name in ("irrigated", "rainfed", "active"))
            and abs(random_conditional["p80"] - .8) <= .02
            and abs(random_conditional["p90"] - .9) <= .02
            and abs(shifted_conditional["p80"] - .8) <= .02
            and abs(shifted_conditional["p90"] - .9) <= .02
        ),
        "rule": "On independent Latin-hypercube scenarios, all raw/deployed gains must be >=10%, irrigated/rainfed/active MAE must improve, and active conditional coverage must be within 2 points of nominal on both frozen-random and shifted tests.",
    }
    for item in (old, new):
        item.pop("treeStd"); item.pop("errors")
    return {
        "name": "CropFit independent scenario-shift validation v0.9.1",
        "target": "EcoCrop mechanistic screening teacher; not observed yield",
        "protocol": {
            "profiles": len(np.unique(groups[test])),
            "scenariosPerProfile": SCENARIOS_PER_PROFILE,
            "examples": len(shifted_y),
            "generator": "independently seeded scipy LatinHypercube over the same physical support; not the training generator",
            "heldOutPolicy": "Production-seed test crop profiles only",
        },
        "championV08": old,
        "candidateV09": new,
        "gains": gains,
        "activeCoverage": {
            "oldGlobalMethodOnShifted": shifted_global,
            "conditionalMethodOnFrozenRandom": random_conditional,
            "conditionalMethodOnShifted": shifted_conditional,
        },
        "gate": gate,
    }


def markdown(report: dict) -> str:
    old, new, gains = report["championV08"], report["candidateV09"], report["gains"]
    coverage_report = report["activeCoverage"]
    return "\n".join([
        "# CropFit v0.9.1 independent scenario-shift validation", "",
        "Held-out crop profiles are evaluated with independently seeded Latin-hypercube scenarios rather than the random generator used for fitting and promotion. This measures EcoCrop-teacher fidelity, not observed-yield accuracy.", "",
        "| Metric | v0.8 | v0.9 | Gain |", "|---|---:|---:|---:|",
        f'| Raw MAE | {old["mae"]:.5f} | {new["mae"]:.5f} | {gains["maePercent"]:.2f}% |',
        f'| Raw p90 | {old["p90AbsoluteError"]:.5f} | {new["p90AbsoluteError"]:.5f} | {gains["p90Percent"]:.2f}% |',
        f'| Deployed MAE | {old["deployedMae"]:.5f} | {new["deployedMae"]:.5f} | {gains["deployedMaePercent"]:.2f}% |',
        f'| Deployed p90 | {old["deployedP90AbsoluteError"]:.5f} | {new["deployedP90AbsoluteError"]:.5f} | {gains["deployedP90Percent"]:.2f}% |', "",
        "| Active-case calibration | 80% coverage | 90% coverage |", "|---|---:|---:|",
        f'| Old global method on shifted test | {coverage_report["oldGlobalMethodOnShifted"]["p80"]:.1%} | {coverage_report["oldGlobalMethodOnShifted"]["p90"]:.1%} |',
        f'| Conditional method on frozen-random test | {coverage_report["conditionalMethodOnFrozenRandom"]["p80"]:.1%} | {coverage_report["conditionalMethodOnFrozenRandom"]["p90"]:.1%} |',
        f'| Conditional method on shifted test | {coverage_report["conditionalMethodOnShifted"]["p80"]:.1%} | {coverage_report["conditionalMethodOnShifted"]["p90"]:.1%} |', "",
        "The previous marginal intervals were dominated by deterministic hard-zero cases. v0.9.1 calibrates active growing conditions separately and assigns zero radius only when the deterministic ceiling fixes the deployed score at zero.", "",
        f'Gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
    ])


def plot(report: dict, output: Path) -> None:
    old, new = report["championV08"], report["candidateV09"]
    cov = report["activeCoverage"]
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    labels = ["raw MAE", "raw p90", "deployed MAE", "deployed p90"]
    x = np.arange(len(labels)); width = .36
    axes[0].bar(x - width / 2, [old["mae"], old["p90AbsoluteError"], old["deployedMae"], old["deployedP90AbsoluteError"]], width, label="v0.8", color="#d98352")
    axes[0].bar(x + width / 2, [new["mae"], new["p90AbsoluteError"], new["deployedMae"], new["deployedP90AbsoluteError"]], width, label="v0.9", color="#315d49")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Suitability-point error", title="Gains survive independent sampling"); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    methods = ["old global\nshifted", "conditional\nfrozen", "conditional\nshifted"]
    p80 = [cov["oldGlobalMethodOnShifted"]["p80"], cov["conditionalMethodOnFrozenRandom"]["p80"], cov["conditionalMethodOnShifted"]["p80"]]
    p90 = [cov["oldGlobalMethodOnShifted"]["p90"], cov["conditionalMethodOnFrozenRandom"]["p90"], cov["conditionalMethodOnShifted"]["p90"]]
    positions = np.arange(3)
    axes[1].bar(positions - width / 2, p80, width, label="80% interval", color="#d98352")
    axes[1].bar(positions + width / 2, p90, width, label="90% interval", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.65); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.65)
    axes[1].set(xticks=positions, xticklabels=methods, ylim=(.45, .96), ylabel="Active-case coverage", title="Conditional calibration fixes hidden undercoverage"); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.9.1 · independent shift and active-case calibration", fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/scenario-shift-validation-v0.9.1.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/scenario-shift-validation-v0.9.1.png")
    args = parser.parse_args()
    report = evaluate(args.artifact, args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"gains": report["gains"], "activeCoverage": report["activeCoverage"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
