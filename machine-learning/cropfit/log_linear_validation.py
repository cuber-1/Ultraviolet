from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .log_linear_development import (
    MEMBERSHIP_COLUMNS,
    MEMBERSHIP_FEATURE_NAMES,
    direct_calibrated_coverage,
    fit_pair,
    gains,
    seed_result,
    serialized_size,
)
from .profiles import load_profiles
from .scenario_shift_validation import shifted_examples
from .training import conformal_quantile


CONFIRMATION_SEEDS = list(range(20270510, 20270515))
FINAL_SEEDS = list(range(20270515, 20270520))
SHIFT_SEED = 20270520


def prediction_metrics(prediction: np.ndarray, target: np.ndarray, irrigated: np.ndarray | None = None) -> dict:
    errors = np.abs(prediction - target)
    deployed_errors = np.abs(np.minimum(prediction, target) - target)
    result = {
        "examples": len(target),
        "mae": round(float(np.mean(errors)), 8),
        "p90AbsoluteError": round(float(np.quantile(errors, .9)), 8),
        "maximumAbsoluteError": round(float(np.max(errors)), 8),
        "deployedMae": round(float(np.mean(deployed_errors)), 8),
        "deployedMaximumAbsoluteError": round(float(np.max(deployed_errors)), 8),
    }
    if irrigated is not None:
        result["subgroups"] = {}
        for name, mask in (
            ("irrigated", irrigated), ("rainfed", ~irrigated),
            ("active", target > 0), ("hardZero", target == 0),
        ):
            result["subgroups"][name] = {
                "examples": int(np.sum(mask)),
                "mae": round(float(np.mean(errors[mask])), 8),
                "p90AbsoluteError": round(float(np.quantile(errors[mask], .9)), 8),
            }
    return result


def relative_shift_gains(champion: dict, candidate: dict) -> dict:
    return {
        key: round(100 * (champion[source] - candidate[source]) / champion[source], 4)
        for source, key in (
            ("mae", "maePercent"),
            ("p90AbsoluteError", "p90Percent"),
            ("deployedMae", "deployedMaePercent"),
        )
    }


def shifted_coverage(model, validation_x: np.ndarray, validation_y: np.ndarray, validation: np.ndarray, shifted_x: np.ndarray, shifted_y: np.ndarray) -> dict:
    validation_active = np.all(validation_x[validation] > 0, axis=1)
    validation_errors = np.abs(model.predict(validation_x[validation]) - validation_y[validation])
    quantiles = {
        "p80": conformal_quantile(validation_errors[validation_active], .8),
        "p90": conformal_quantile(validation_errors[validation_active], .9),
    }
    shifted_active = np.all(shifted_x > 0, axis=1)
    errors = np.abs(model.predict(shifted_x) - shifted_y)
    return {
        "coverage80": round(float(np.mean(errors[shifted_active] <= quantiles["p80"])), 4),
        "coverage90": round(float(np.mean(errors[shifted_active] <= quantiles["p90"])), 4),
        "absoluteErrorQuantiles": {name: round(float(value), 8) for name, value in quantiles.items()},
        "inactiveExact": bool(np.all(errors[~shifted_active] == 0)),
    }


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results, sizes = [], None
    for seed in CONFIRMATION_SEEDS + FINAL_SEEDS:
        item, seed_sizes = seed_result(profiles, seed)
        item["phase"] = "confirmation" if seed in CONFIRMATION_SEEDS else "final"
        candidate = item["logLinearCandidate"]
        calibration = candidate["calibration"]
        item["passedPerSeedGate"] = (
            min(item["gains"].values()) >= 99
            and candidate["maximumAbsoluteError"] <= .001
            and candidate["deployedMaximumAbsoluteError"] < item["championV011"]["deployedMaximumAbsoluteError"]
            and abs(calibration["coverage80"] - .8) <= .02
            and abs(calibration["coverage90"] - .9) <= .02
            and calibration["inactiveExact"]
        )
        results.append(item)
        sizes = sizes or seed_sizes
        print(json.dumps(item), flush=True)
    assert sizes is not None

    final = [item for item in results if item["phase"] == "final"]
    mean_gain = lambda rows, key: float(np.mean([item["gains"][key] for item in rows]))
    all_mae_gain = mean_gain(results, "maePercent")
    all_p90_gain = mean_gain(results, "p90Percent")
    final_mae_gain = mean_gain(final, "maePercent")
    final_p90_gain = mean_gain(final, "p90Percent")
    latency_ratio = float(np.mean([
        item["logLinearCandidate"]["apiBatchLatencyMs"] / item["championV011"]["apiBatchLatencyMs"]
        for item in results
    ]))
    coefficient_matrix = np.asarray([
        list(item["logLinearCandidate"]["coefficients"].values()) for item in results
    ])

    shift_models, shift_x, shift_y, shift_groups, shift_indices = fit_pair(profiles, SHIFT_SEED)
    shift_validation, shift_test = shift_indices
    shifted_x, shifted_y, irrigated = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=SHIFT_SEED,
    )
    shifted = {}
    for name, fitted in shift_models.items():
        prediction = fitted["model"].predict(shifted_x[:, fitted["columns"]])
        shifted[name] = prediction_metrics(prediction, shifted_y, irrigated)
    shift_gains = relative_shift_gains(shifted["championV011"], shifted["logLinearCandidate"])
    candidate_model = shift_models["logLinearCandidate"]["model"]
    random_calibration = direct_calibrated_coverage(
        candidate_model, shift_x[:, MEMBERSHIP_COLUMNS], shift_y, shift_validation, shift_test,
    )
    shift_calibration = shifted_coverage(
        candidate_model, shift_x[:, MEMBERSHIP_COLUMNS], shift_y, shift_validation,
        shifted_x[:, MEMBERSHIP_COLUMNS], shifted_y,
    )
    shift_gate = (
        min(shift_gains.values()) >= 99
        and shifted["logLinearCandidate"]["maximumAbsoluteError"] <= .001
        and shifted["logLinearCandidate"]["deployedMaximumAbsoluteError"]
        < shifted["championV011"]["deployedMaximumAbsoluteError"]
        and all(
            shifted["logLinearCandidate"]["subgroups"][name]["mae"]
            < shifted["championV011"]["subgroups"][name]["mae"]
            for name in ("irrigated", "rainfed", "active")
        )
        and shifted["logLinearCandidate"]["subgroups"]["hardZero"]["mae"] == 0
        and abs(random_calibration["coverage80"] - .8) <= .02
        and abs(random_calibration["coverage90"] - .9) <= .02
        and abs(shift_calibration["coverage80"] - .8) <= .02
        and abs(shift_calibration["coverage90"] - .9) <= .02
        and random_calibration["inactiveExact"] and shift_calibration["inactiveExact"]
    )

    coefficient_spread = np.ptp(coefficient_matrix, axis=0)
    checks = {
        "everySeedPasses": all(item["passedPerSeedGate"] for item in results),
        "allSeedMeanGains": all_mae_gain >= 99 and all_p90_gain >= 99,
        "finalMeanGains": final_mae_gain >= 99 and final_p90_gain >= 99,
        "coefficientStability": bool(np.max(coefficient_spread) <= .001),
        "positiveUnitSumElasticities": bool(np.all(coefficient_matrix > 0) and np.all(np.abs(np.sum(coefficient_matrix, axis=1) - 1) <= .01)),
        "artifactSize": sizes["logLinearCandidate"] <= 50_000 and sizes["logLinearCandidate"] <= .01 * sizes["championV011"],
        "batchLatency": latency_ratio <= .25,
        "independentShift": shift_gate,
    }
    return {
        "name": "CropFit log-linear validation v0.12",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.11.0, six features, 40 Extra Trees",
            "candidate": "ordinary least squares in log space over four range-membership features; structural zero when any membership is zero",
            "candidateFeatures": MEMBERSHIP_FEATURE_NAMES,
            "selection": "The candidate and every threshold were fixed after development seeds 20270501-20270503. Confirmation, final, and independent-shift seeds below were reserved until this protocol was committed.",
            "fixedEvaluation": "Both models use identical fitting profiles, validation profiles, held-out profiles, and scenario rows.",
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "shiftSeed": SHIFT_SEED,
            "declaredGate": (
                "Every seed must improve MAE/p90 by >=99%, improve deployed maximum error, keep maximum raw error <=0.001, preserve active 80%/90% coverage within two points, and produce exact inactive zeros. All-seed and final-only mean gains must be >=99%; learned elasticities must remain positive, sum within 0.01 of one, and vary by <=0.001; compressed size must be <=50 KB and <=1% of v0.11; batch latency <=0.25x. The independent Latin-hypercube shift must meet the same accuracy, tail, subgroup, zero, and coverage requirements."
            ),
        },
        "results": results,
        "summary": {
            "seedWins": sum(item["passedPerSeedGate"] for item in results),
            "seeds": len(results),
            "allMeanMaeImprovementPercent": round(all_mae_gain, 4),
            "allMeanP90ImprovementPercent": round(all_p90_gain, 4),
            "finalMeanMaeImprovementPercent": round(final_mae_gain, 4),
            "finalMeanP90ImprovementPercent": round(final_p90_gain, 4),
            "meanApiBatchLatencyRatio": round(latency_ratio, 4),
            "championSerializedSizeBytes": sizes["championV011"],
            "candidateSerializedSizeBytes": sizes["logLinearCandidate"],
            "coefficientRange": {
                name: [round(float(np.min(coefficient_matrix[:, index])), 8), round(float(np.max(coefficient_matrix[:, index])), 8)]
                for index, name in enumerate(MEMBERSHIP_FEATURE_NAMES)
            },
        },
        "independentShift": {
            "seed": SHIFT_SEED,
            "profiles": len(np.unique(shift_groups[shift_test])),
            "examples": len(shifted_y),
            **shifted,
            "gains": shift_gains,
            "activeCoverage": {"frozenRandom": random_calibration, "independentShift": shift_calibration},
            "passed": shift_gate,
        },
        "gate": {"passed": all(checks.values()), "checks": checks},
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit log-linear validation", "",
        "The candidate learns a multiplicative response from four transparent range-membership features. It receives no crop identity, coordinates, target score, or observed yield feature. Its structural match to the mechanistic teacher explains the near-zero fidelity error; this is not a claim of near-zero real-world crop error.", "",
        "| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        candidate = item["logLinearCandidate"]
        calibration = candidate["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV011"]["mae"]:.5f} | {candidate["mae"]:.8f} | '
            f'{item["gains"]["maePercent"]:.3f}% | {item["gains"]["p90Percent"]:.3f}% | '
            f'{candidate["maximumAbsoluteError"]:.8f} | {calibration["coverage80"]:.1%} | {calibration["coverage90"]:.1%} |'
        )
    summary, shift = report["summary"], report["independentShift"]
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Final-only gains are **{summary["finalMeanMaeImprovementPercent"]:.3f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.3f}% p90**.',
        "", f'The regressor is **{summary["candidateSerializedSizeBytes"] / 1000:.1f} KB** versus **{summary["championSerializedSizeBytes"] / 1_000_000:.1f} MB**, with **{summary["meanApiBatchLatencyRatio"]:.3f}x** batch latency.',
        "", "## Independent shift", "",
        f'Fresh-shift gains are **{shift["gains"]["maePercent"]:.2f}% raw MAE**, **{shift["gains"]["p90Percent"]:.2f}% raw p90**, and **{shift["gains"]["deployedMaePercent"]:.2f}% deployed MAE**.',
        "", f'Active shifted coverage is **{shift["activeCoverage"]["independentShift"]["coverage80"]:.1%} / {shift["activeCoverage"]["independentShift"]["coverage90"]:.1%}**.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.',
        "", "> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results, summary = report["results"], report["summary"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    axes[0].plot(x, [item["gains"]["maePercent"] for item in results], marker="o", label="MAE gain", color="#315d49")
    axes[0].plot(x, [item["gains"]["p90Percent"] for item in results], marker="o", label="p90 gain", color="#6f9551")
    axes[0].axhline(99, color="#d98352", linestyle="--", label="promotion floor")
    axes[0].set(xticks=x, xticklabels=labels, ylim=(98.5, 100.1), xlabel="fresh seed suffix", ylabel="Error reduction (%)", title="Held-out gains")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["logLinearCandidate"]["calibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["logLinearCandidate"]["calibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.6); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.6)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.76, .94), xlabel="fresh seed suffix", ylabel="Coverage", title="Direct conformal calibration")
    axes[1].legend(); axes[1].grid(alpha=.18)
    axes[2].bar(["v0.11", "v0.12"], [summary["championSerializedSizeBytes"] / 1_000_000, summary["candidateSerializedSizeBytes"] / 1_000_000], color=["#8fae82", "#315d49"])
    axes[2].set(ylabel="Serialized model (MB)", title="Mac-ready model size")
    axes[2].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.12 candidate · interpretable log-linear regression", fontweight="bold")
    figure.text(.5, .01, "Fresh unseen crop profiles · independent scenario shift · not observed yield accuracy", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/log-linear-validation-v0.12.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/log-linear-validation-v0.12.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/log-linear-validation-v0.12.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "independentShift": {"gains": report["independentShift"]["gains"], "activeCoverage": report["independentShift"]["activeCoverage"]}, "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Log-linear promotion gate did not pass")


if __name__ == "__main__":
    main()
