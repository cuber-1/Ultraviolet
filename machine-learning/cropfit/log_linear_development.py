from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from time import perf_counter

import joblib
import matplotlib.pyplot as plt
import numpy as np

from .density_refinement_validation import estimator
from .estimator_validation import prediction_latency_ms, split_indices
from .features import COMPACT_FEATURE_COLUMNS, COMPACT_FEATURE_NAMES
from .log_linear import LogLinearCropFitRegressor
from .profiles import load_profiles
from .training import conformal_quantile, generate_examples


EVALUATION_DENSITY = 72
FITTING_DENSITY = 200
CHAMPION_TREES = 40
DEVELOPMENT_SEEDS = list(range(20270501, 20270504))
MEMBERSHIP_FEATURE_NAMES = COMPACT_FEATURE_NAMES[:4]
MEMBERSHIP_COLUMNS = np.asarray(COMPACT_FEATURE_COLUMNS[:4])
COMPACT_COLUMNS = np.asarray(COMPACT_FEATURE_COLUMNS)


def serialized_size(model) -> int:
    with tempfile.NamedTemporaryFile(suffix=".joblib") as output:
        joblib.dump({"model": model}, output.name, compress=3)
        return Path(output.name).stat().st_size


def direct_calibrated_coverage(
    model: LogLinearCropFitRegressor,
    x: np.ndarray,
    y: np.ndarray,
    validation: np.ndarray,
    test: np.ndarray,
) -> dict:
    validation_active = np.all(x[validation] > 0, axis=1)
    test_active = np.all(x[test] > 0, axis=1)
    validation_errors = np.abs(model.predict(x[validation]) - y[validation])
    test_errors = np.abs(model.predict(x[test]) - y[test])
    quantiles = {
        "p80": conformal_quantile(validation_errors[validation_active], .8),
        "p90": conformal_quantile(validation_errors[validation_active], .9),
    }
    return {
        "method": "active absolute-residual split conformal",
        "validationExamples": int(np.sum(validation_active)),
        "testExamples": int(np.sum(test_active)),
        "absoluteErrorQuantiles": {name: round(float(value), 8) for name, value in quantiles.items()},
        "coverage80": round(float(np.mean(test_errors[test_active] <= quantiles["p80"])), 4),
        "coverage90": round(float(np.mean(test_errors[test_active] <= quantiles["p90"])), 4),
        "inactiveExact": bool(np.all(test_errors[~test_active] == 0)),
    }


def fit_pair(profiles: list, seed: int) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x, y, groups = generate_examples(profiles, EVALUATION_DENSITY, seed)
    train, validation, test = split_indices(x, y, groups, seed)
    training_x, training_y, training_groups = generate_examples(profiles, FITTING_DENSITY, seed)
    fitting = np.flatnonzero(np.isin(training_groups, np.unique(groups[train])))
    champion = estimator(CHAMPION_TREES, seed)
    champion_started = perf_counter()
    champion.fit(training_x[fitting][:, COMPACT_COLUMNS], training_y[fitting])
    champion_seconds = perf_counter() - champion_started
    candidate = LogLinearCropFitRegressor()
    candidate_started = perf_counter()
    candidate.fit(training_x[fitting][:, MEMBERSHIP_COLUMNS], training_y[fitting])
    candidate_seconds = perf_counter() - candidate_started
    return {
        "championV011": {"model": champion, "columns": COMPACT_COLUMNS, "fitSeconds": champion_seconds},
        "logLinearCandidate": {"model": candidate, "columns": MEMBERSHIP_COLUMNS, "fitSeconds": candidate_seconds},
    }, x, y, groups, np.asarray([validation, test], dtype=object)


def gains(champion: dict, candidate: dict) -> dict:
    return {
        key: round(100 * (champion[source] - candidate[source]) / champion[source], 4)
        for source, key in (("mae", "maePercent"), ("p90AbsoluteError", "p90Percent"))
    }


def fidelity_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    errors = np.abs(predicted - actual)
    return {
        "mae": round(float(np.mean(errors)), 8),
        "p90AbsoluteError": round(float(np.quantile(errors, .9)), 8),
    }


def seed_result(profiles: list, seed: int) -> tuple[dict, dict]:
    models, x, y, _, indices = fit_pair(profiles, seed)
    validation, test = indices
    item = {"seed": seed, "testExamples": len(test)}
    sizes = {}
    for name, fitted in models.items():
        model, columns = fitted["model"], fitted["columns"]
        predictions = model.predict(x[test][:, columns])
        errors = np.abs(predictions - y[test])
        deployed_errors = np.abs(np.minimum(predictions, y[test]) - y[test])
        item[name] = {
            **fidelity_metrics(y[test], predictions),
            "maximumAbsoluteError": round(float(np.max(errors)), 8),
            "deployedMaximumAbsoluteError": round(float(np.max(deployed_errors)), 8),
            "fitSeconds": round(float(fitted["fitSeconds"]), 4),
            "apiBatchLatencyMs": prediction_latency_ms(model, x[test[:132]][:, columns]),
        }
        sizes[name] = serialized_size(model)
    candidate = models["logLinearCandidate"]["model"]
    item["logLinearCandidate"]["coefficients"] = {
        name: round(float(value), 8)
        for name, value in zip(MEMBERSHIP_FEATURE_NAMES, candidate.coef_, strict=True)
    }
    item["logLinearCandidate"]["intercept"] = round(float(candidate.intercept_), 8)
    item["logLinearCandidate"]["calibration"] = direct_calibrated_coverage(
        candidate, x[:, MEMBERSHIP_COLUMNS], y, validation, test,
    )
    item["gains"] = gains(item["championV011"], item["logLinearCandidate"])
    return item, sizes


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results, sizes = [], None
    for seed in DEVELOPMENT_SEEDS:
        item, seed_sizes = seed_result(profiles, seed)
        results.append(item)
        sizes = sizes or seed_sizes
        print(json.dumps(item), flush=True)
    assert sizes is not None
    coefficient_matrix = np.asarray([
        list(item["logLinearCandidate"]["coefficients"].values()) for item in results
    ])
    coefficient_spread = np.ptp(coefficient_matrix, axis=0)
    mean_mae_gain = float(np.mean([item["gains"]["maePercent"] for item in results]))
    mean_p90_gain = float(np.mean([item["gains"]["p90Percent"] for item in results]))
    latency_ratio = float(np.mean([
        item["logLinearCandidate"]["apiBatchLatencyMs"] / item["championV011"]["apiBatchLatencyMs"]
        for item in results
    ]))
    checks = {
        "allSeedsImproveMaeAndP90": all(min(item["gains"].values()) > 99 for item in results),
        "allSeedsImproveDeployedTail": all(
            item["logLinearCandidate"]["deployedMaximumAbsoluteError"]
            < item["championV011"]["deployedMaximumAbsoluteError"]
            for item in results
        ),
        "maximumErrorBelow0_001": all(
            item["logLinearCandidate"]["maximumAbsoluteError"] <= .001 for item in results
        ),
        "coefficientSpreadBelow0_001": bool(np.max(coefficient_spread) <= .001),
        "activeCoverage": all(
            abs(item["logLinearCandidate"]["calibration"]["coverage80"] - .8) <= .02
            and abs(item["logLinearCandidate"]["calibration"]["coverage90"] - .9) <= .02
            and item["logLinearCandidate"]["calibration"]["inactiveExact"]
            for item in results
        ),
        "sizeBelow50KB": sizes["logLinearCandidate"] <= 50_000,
        "latencyBelowChampion": latency_ratio < 1,
    }
    return {
        "name": "CropFit log-linear development screen v0.12",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.11.0, six features, 40 Extra Trees",
            "candidate": "ordinary least squares in log space over four range-membership features; structural zero when any membership is zero",
            "candidateFeatures": MEMBERSHIP_FEATURE_NAMES,
            "selection": "One structurally matched log-linear model was evaluated on development seeds only; no capacity or coefficient was selected on reserved rows.",
            "developmentSeeds": DEVELOPMENT_SEEDS,
            "reservedSeedsOpened": False,
            "reservedValidation": {
                "confirmationSeeds": list(range(20270510, 20270515)),
                "finalSeeds": list(range(20270515, 20270520)),
                "shiftSeed": 20270520,
            },
            "advanceRule": "Advance only if every development seed improves MAE and p90 by >99%, improves deployed maximum error, keeps maximum raw error <=0.001, learns coefficients stable within 0.001, preserves active 80%/90% coverage within two points with exact inactive zeros, serializes below 50 KB, and is faster than v0.11.",
        },
        "results": results,
        "summary": {
            "meanMaeImprovementPercent": round(mean_mae_gain, 4),
            "meanP90ImprovementPercent": round(mean_p90_gain, 4),
            "meanApiBatchLatencyRatio": round(latency_ratio, 4),
            "championSerializedSizeBytes": sizes["championV011"],
            "candidateSerializedSizeBytes": sizes["logLinearCandidate"],
            "coefficientRange": {
                name: [round(float(np.min(coefficient_matrix[:, index])), 8), round(float(np.max(coefficient_matrix[:, index])), 8)]
                for index, name in enumerate(MEMBERSHIP_FEATURE_NAMES)
            },
        },
        "gate": {"passed": all(checks.values()), "checks": checks},
    }


def markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# CropFit log-linear development screen", "",
        "A four-feature log-linear regression learns the multiplicative EcoCrop response from fitting rows. It does not receive crop identity, coordinates, the target score, or observed yield as an input. The teacher is structurally log-linear in these memberships, which explains the near-zero fidelity error but does not imply near-zero real-world crop error.", "",
        "| Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        candidate = item["logLinearCandidate"]
        calibration = candidate["calibration"]
        lines.append(
            f'| {item["seed"]} | {item["championV011"]["mae"]:.5f} | {candidate["mae"]:.8f} | '
            f'{item["gains"]["maePercent"]:.3f}% | {item["gains"]["p90Percent"]:.3f}% | '
            f'{candidate["maximumAbsoluteError"]:.8f} | {calibration["coverage80"]:.1%} | {calibration["coverage90"]:.1%} |'
        )
    lines += [
        "", f'Mean development gains: **{summary["meanMaeImprovementPercent"]:.3f}% MAE** and **{summary["meanP90ImprovementPercent"]:.3f}% p90**.',
        "", f'The candidate serializes to **{summary["candidateSerializedSizeBytes"] / 1000:.1f} KB** versus **{summary["championSerializedSizeBytes"] / 1_000_000:.1f} MB**, with **{summary["meanApiBatchLatencyRatio"]:.3f}x** batch latency.',
        "", f'Development gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. Fresh confirmation, final, and shift seeds remain unopened.',
        "", "> This measures fidelity to the declared mechanistic teacher, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results, summary = report["results"], report["summary"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    width = .36
    axes[0].bar(x - width / 2, [item["championV011"]["mae"] for item in results], width, label="v0.11", color="#8fae82")
    axes[0].bar(x + width / 2, [item["logLinearCandidate"]["mae"] for item in results], width, label="log-linear", color="#315d49")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Held-out MAE", title="Development error collapses")
    axes[0].set_yscale("log")
    axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    coefficient_names = list(summary["coefficientRange"])
    coefficient_means = [np.mean(summary["coefficientRange"][name]) for name in coefficient_names]
    axes[1].bar(["temp", "water", "pH", "solar"], coefficient_means, color="#315d49")
    axes[1].set(ylabel="Learned elasticity", title="Stable interpretable coefficients")
    axes[1].grid(axis="y", alpha=.18)
    axes[2].bar(["v0.11", "log-linear"], [summary["championSerializedSizeBytes"] / 1_000_000, summary["candidateSerializedSizeBytes"] / 1_000_000], color=["#8fae82", "#315d49"])
    axes[2].set(ylabel="Serialized model (MB)", title="Mac-ready artifact size")
    axes[2].set_yscale("log")
    axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.12 development candidate · trained multiplicative regression", fontweight="bold")
    figure.text(.5, .01, "Development seeds only · fresh validation remains sealed · not observed yield accuracy", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/log-linear-development-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/log-linear-development-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/log-linear-development-v0.12.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Log-linear development gate did not pass")


if __name__ == "__main__":
    main()
