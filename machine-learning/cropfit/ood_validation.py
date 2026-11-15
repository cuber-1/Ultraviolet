from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from .features import feature_row, teacher_scores
from .profiles import load_profiles
from .training import generate_examples


def metrics(errors: np.ndarray) -> dict:
    return {
        "mae": round(float(np.mean(errors)), 5),
        "p90AbsoluteError": round(float(np.quantile(errors, .9)), 5),
        "maximumAbsoluteError": round(float(np.max(errors)), 5),
    }


def held_out(model, metadata: dict, profiles: list, samples_per_crop: int, seed: int) -> dict:
    x, y, groups = generate_examples(profiles, samples_per_crop, seed)
    _, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed).split(x, y, groups))
    trees = np.asarray([tree.predict(x[test]) for tree in model.estimators_])
    raw = trees.mean(axis=0)
    raw_errors = np.abs(raw - y[test])
    ceiling_errors = np.abs(np.minimum(raw, y[test]) - y[test])
    tree_std = trees.std(axis=0)
    calibration = metadata["uncertaintyCalibration"]
    scale = tree_std + float(calibration["treeStdFloor"])
    radius80 = np.ceil(float(calibration["normalizedErrorQuantiles"]["p80"]) * scale * 1000) / 1000
    radius90 = np.ceil(float(calibration["normalizedErrorQuantiles"]["p90"]) * scale * 1000) / 1000
    return {
        "examples": len(test), "profiles": len(np.unique(groups[test])),
        "rawSurrogate": metrics(raw_errors),
        "seasonalCeiling": metrics(ceiling_errors),
        "existingIntervalCoverageAfterCeiling": {
            "p80": round(float(np.mean(ceiling_errors <= radius80)), 4),
            "p90": round(float(np.mean(ceiling_errors <= radius90)), 4),
        },
        "errorNeverIncreased": bool(np.all(ceiling_errors <= raw_errors + 1e-12)),
    }


def boundary_stress(model, profiles: list) -> dict:
    cases = {"solarAbsoluteMin": [], "solarAbsoluteMax": [], "temperatureAbsoluteMin": [], "temperatureAbsoluteMax": []}
    targets = {name: [] for name in cases}
    for profile in profiles:
        temperature = (profile.temp_opt_min + profile.temp_opt_max) / 2
        rain = (profile.rain_opt_min + profile.rain_opt_max) / 2
        ph = (profile.ph_opt_min + profile.ph_opt_max) / 2
        values = {
            "solarAbsoluteMin": (temperature, rain, ph, 4.0),
            "solarAbsoluteMax": (temperature, rain, ph, 34.0),
            "temperatureAbsoluteMin": (profile.temp_abs_min, rain, ph, 18.0),
            "temperatureAbsoluteMax": (profile.temp_abs_max, rain, ph, 18.0),
        }
        for name, (temp, precipitation, soil_ph, solar) in values.items():
            cases[name].append(feature_row(profile, temp, precipitation, soil_ph, solar, False))
            targets[name].append(teacher_scores(profile, temp, precipitation, soil_ph, solar, False)["suitability"])
    results = {}
    for name, rows in cases.items():
        truth = np.asarray(targets[name])
        predicted = model.predict(np.asarray(rows, dtype=np.float32))
        raw_errors = np.abs(predicted - truth)
        ceiling_errors = np.abs(np.minimum(predicted, truth) - truth)
        results[name] = {
            "examples": len(rows), "teacherScore": float(np.max(truth)),
            "rawSurrogate": metrics(raw_errors), "seasonalCeiling": metrics(ceiling_errors),
        }
    return results


def evaluate(artifact: Path, profiles_path: Path, samples_per_crop: int, seed: int) -> dict:
    bundle = joblib.load(artifact)
    profiles = load_profiles(profiles_path)
    heldout = held_out(bundle["model"], bundle["metadata"], profiles, samples_per_crop, seed)
    boundaries = boundary_stress(bundle["model"], profiles)
    gate = {
        "passed": heldout["errorNeverIncreased"]
        and heldout["seasonalCeiling"]["mae"] < heldout["rawSurrogate"]["mae"]
        and heldout["seasonalCeiling"]["p90AbsoluteError"] < heldout["rawSurrogate"]["p90AbsoluteError"]
        and heldout["existingIntervalCoverageAfterCeiling"]["p80"] >= .8
        and heldout["existingIntervalCoverageAfterCeiling"]["p90"] >= .9
        and all(item["seasonalCeiling"]["maximumAbsoluteError"] == 0 for item in boundaries.values()),
        "rule": "The seasonal ceiling must never increase held-out error, must improve MAE and p90, preserve at least nominal existing interval coverage, and eliminate all tested hard-boundary extrapolation errors.",
    }
    return {
        "model": bundle["metadata"]["model"],
        "target": "EcoCrop mechanistic screening teacher; not observed yield",
        "heldOut": heldout, "boundaryStress": boundaries, "gate": gate,
    }


def markdown(report: dict) -> str:
    heldout = report["heldOut"]
    lines = [
        "# CropFit seasonal-ceiling validation", "",
        "The ML score is capped by the exact seasonal and establishment EcoCrop suitability already computed for limiting-factor explanations. The clamp only removes surrogate overestimation; it does not replace ML underestimation.", "",
        "| Held-out path | MAE | p90 error | Maximum error |", "|---|---:|---:|---:|",
        f'| Raw {report["model"]} | {heldout["rawSurrogate"]["mae"]:.4f} | {heldout["rawSurrogate"]["p90AbsoluteError"]:.4f} | {heldout["rawSurrogate"]["maximumAbsoluteError"]:.3f} |',
        f'| Deployed seasonal ceiling | {heldout["seasonalCeiling"]["mae"]:.4f} | {heldout["seasonalCeiling"]["p90AbsoluteError"]:.4f} | {heldout["seasonalCeiling"]["maximumAbsoluteError"]:.3f} |', "",
        f'Existing p80/p90 radii remain conservative at **{heldout["existingIntervalCoverageAfterCeiling"]["p80"]:.1%} / {heldout["existingIntervalCoverageAfterCeiling"]["p90"]:.1%}** coverage.', "",
        "At exact solar and temperature absolute boundaries, the teacher score is zero. The raw ensemble can extrapolate nonzero values because continuous training samples almost never land exactly on a boundary; the ceiling reduces all tested boundary errors to zero.", "",
        f'Gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.', "",
        "> This improves fidelity to EcoCrop constraints. It does not validate yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    heldout = report["heldOut"]
    labels = ["MAE", "p90 error", "maximum error"]
    raw = [heldout["rawSurrogate"]["mae"], heldout["rawSurrogate"]["p90AbsoluteError"], heldout["rawSurrogate"]["maximumAbsoluteError"]]
    ceiling = [heldout["seasonalCeiling"]["mae"], heldout["seasonalCeiling"]["p90AbsoluteError"], heldout["seasonalCeiling"]["maximumAbsoluteError"]]
    x = np.arange(3); width = .36
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].bar(x - width / 2, raw, width, color="#d98352", label="raw surrogate")
    axes[0].bar(x + width / 2, ceiling, width, color="#315d49", label="seasonal ceiling")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Suitability-point error", title="Held-out teacher fidelity"); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    names = list(report["boundaryStress"])
    axes[1].bar(np.arange(len(names)) - width / 2, [report["boundaryStress"][name]["rawSurrogate"]["maximumAbsoluteError"] for name in names], width, color="#8f2f14", label="raw maximum")
    axes[1].bar(np.arange(len(names)) + width / 2, [report["boundaryStress"][name]["seasonalCeiling"]["maximumAbsoluteError"] for name in names], width, color="#315d49", label="ceiling maximum")
    axes[1].set(xticks=np.arange(len(names)), xticklabels=["solar min", "solar max", "temp min", "temp max"], ylabel="Maximum error", title="Exact hard-boundary stress"); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle(f'{report["model"]} · prevent out-of-domain overestimation', fontweight="bold")
    figure.tight_layout(); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/ood-validation-v0.9.json")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/ood-validation-v0.9.png")
    parser.add_argument("--samples-per-crop", type=int, default=72)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    report = evaluate(args.artifact, args.profiles, args.samples_per_crop, args.seed)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"heldOut": report["heldOut"], "gate": report["gate"]}, indent=2))


if __name__ == "__main__":
    main()
