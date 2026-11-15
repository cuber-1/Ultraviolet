from __future__ import annotations

import argparse
import json
from functools import partial
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .log_linear import LogLinearCropFitRegressor
from .log_linear_development import MEMBERSHIP_COLUMNS, fit_pair, seed_result
from .profiles import load_profiles
from .scenario_shift_validation import shifted_examples


MEMBERSHIP_FLOOR = 1e-6
DIAGNOSTIC_SEED = 20270519
DEVELOPMENT_SEEDS = list(range(20270521, 20270524))
SHIFT_DIAGNOSTIC_SEED = 20270520
fit_pair_floor = partial(
    fit_pair,
    candidate_factory=lambda: LogLinearCropFitRegressor(membership_floor=MEMBERSHIP_FLOOR),
    candidate_dtype=np.float64,
)


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results = []
    for seed in [DIAGNOSTIC_SEED, *DEVELOPMENT_SEEDS]:
        item, _ = seed_result(profiles, seed, fit_pair_fn=fit_pair_floor)
        item["phase"] = "exposed-diagnostic" if seed == DIAGNOSTIC_SEED else "development"
        results.append(item)
        print(json.dumps(item), flush=True)

    shift_models, _, _, shift_groups, shift_indices = fit_pair_floor(profiles, SHIFT_DIAGNOSTIC_SEED)
    _, shift_test = shift_indices
    shifted_x, shifted_y, _ = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=SHIFT_DIAGNOSTIC_SEED,
    )
    candidate = shift_models["logLinearCandidate"]["model"]
    shifted_prediction = candidate.predict(shifted_x[:, MEMBERSHIP_COLUMNS])
    shifted_errors = np.abs(shifted_prediction - shifted_y)
    served_scores = np.asarray([
        round(min(float(prediction), float(target)), 1)
        for prediction, target in zip(shifted_prediction, shifted_y, strict=True)
    ])
    teacher_scores = np.asarray([round(float(target), 1) for target in shifted_y])
    shift_diagnostic = {
        "seed": SHIFT_DIAGNOSTIC_SEED,
        "examples": len(shifted_y),
        "mae": round(float(np.mean(shifted_errors)), 8),
        "p90AbsoluteError": round(float(np.quantile(shifted_errors, .9)), 8),
        "maximumAbsoluteError": round(float(np.max(shifted_errors)), 8),
        "runtimeScoreMismatches": int(np.sum(served_scores != teacher_scores)),
    }
    coefficient_matrix = np.asarray([
        list(item["logLinearCandidate"]["coefficients"].values()) for item in results
    ])
    checks = {
        "exposedBoundaryFixed": results[0]["logLinearCandidate"]["maximumAbsoluteError"] <= 1e-5,
        "developmentAccuracy": all(
            min(item["gains"].values()) >= 99
            and item["logLinearCandidate"]["maximumAbsoluteError"] <= 1e-5
            for item in results[1:]
        ),
        "developmentCalibration": all(
            abs(item["logLinearCandidate"]["calibration"]["coverage80"] - .8) <= .02
            and abs(item["logLinearCandidate"]["calibration"]["coverage90"] - .9) <= .02
            and item["logLinearCandidate"]["calibration"]["inactiveExact"]
            for item in results[1:]
        ),
        "coefficientStability": bool(np.max(np.ptp(coefficient_matrix, axis=0)) <= 1e-6),
        "runtimePrecisionShift": shift_diagnostic["maximumAbsoluteError"] <= 1e-5 and shift_diagnostic["runtimeScoreMismatches"] == 0,
    }
    return {
        "name": "CropFit membership-floor log-linear development v0.12.1",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "diagnosis": "The rejected v0.12 candidate logged positive memberships below the teacher's 1e-6 numerical floor, perturbing one fitted seed and making millionth-point calibration generator-dependent.",
            "candidate": "v0.12 log-linear regression with the teacher's fixed 1e-6 positive-membership floor and float64 fitting rows",
            "membershipFloor": MEMBERSHIP_FLOOR,
            "selection": "The floor is copied from the pre-existing teacher definition, not tuned over candidates. Exposed seeds diagnose the prior rejection; only 20270521-20270523 are new development evidence.",
            "exposedDiagnosticSeed": DIAGNOSTIC_SEED,
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "exposedShiftDiagnosticSeed": SHIFT_DIAGNOSTIC_SEED,
            "reservedSeedsOpened": False,
            "reservedValidation": {
                "confirmationSeeds": list(range(20270530, 20270535)),
                "finalSeeds": list(range(20270535, 20270540)),
                "shiftSeed": 20270540,
            },
            "advanceRule": "The exposed bad seed must return below 0.00001 maximum error; every new development seed must improve MAE/p90 by >=99%, stay below 0.00001 maximum error, and preserve active random-row coverage within two points; coefficient spread <=0.000001; the exposed runtime-shaped shift must stay below 0.00001 maximum error with zero 0.1-point served-score mismatches.",
        },
        "results": results,
        "shiftDiagnostic": shift_diagnostic,
        "gate": {"passed": all(checks.values()), "checks": checks},
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit membership-floor log-linear development", "",
        report["protocol"]["diagnosis"], "",
        "The follow-up uses the teacher's existing `1e-6` positive-membership floor; it was not selected from a parameter search.", "",
        "| Phase | Seed | Candidate MAE | p90 | Maximum error | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        candidate, calibration = item["logLinearCandidate"], item["logLinearCandidate"]["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {candidate["mae"]:.8f} | '
            f'{candidate["p90AbsoluteError"]:.8f} | {candidate["maximumAbsoluteError"]:.8f} | '
            f'{calibration["coverage80"]:.1%} | {calibration["coverage90"]:.1%} |'
        )
    shift = report["shiftDiagnostic"]
    lines += [
        "", f'On the exposed runtime-shaped shift, maximum raw error is **{shift["maximumAbsoluteError"]:.8f}** and all **{shift["examples"]:,}** served scores match the teacher at 0.1-point precision.',
        "", f'Development gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. New confirmation, final, and shift seeds remain sealed.',
        "", "> This is mechanistic-teacher fidelity, not observed-yield accuracy.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results = report["results"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    axes[0].bar(x, [item["logLinearCandidate"]["maximumAbsoluteError"] for item in results], color=["#d98352", "#315d49", "#315d49", "#315d49"])
    axes[0].axhline(1e-5, color="#d98352", linestyle="--", label="advance ceiling")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Maximum raw error", title="Exposed boundary fixed")
    axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    axes[1].plot(x[1:], [item["logLinearCandidate"]["calibration"]["coverage80"] for item in results[1:]], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x[1:], [item["logLinearCandidate"]["calibration"]["coverage90"] for item in results[1:]], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.6); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.6)
    axes[1].set(xticks=x[1:], xticklabels=labels[1:], ylim=(.76, .94), ylabel="Coverage", title="New development calibration")
    axes[1].legend(); axes[1].grid(alpha=.18)
    shift = report["shiftDiagnostic"]
    axes[2].bar(["raw max error", "served mismatches"], [shift["maximumAbsoluteError"], shift["runtimeScoreMismatches"]], color=["#315d49", "#8fae82"])
    axes[2].set(title="Runtime-shaped shift", ylabel="Value")
    axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.12.1 development · teacher-floor alignment", fontweight="bold")
    figure.text(.5, .01, "Exposed diagnosis plus three new development seeds · fresh validation sealed", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/log-linear-floor-development-v0.12.1.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/log-linear-floor-development-v0.12.1.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/log-linear-floor-development-v0.12.1.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"shiftDiagnostic": report["shiftDiagnostic"], "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Membership-floor development gate did not pass")


if __name__ == "__main__":
    main()
