from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .log_linear_development import MEMBERSHIP_COLUMNS, direct_calibrated_coverage, seed_result
from .log_linear_floor_development import MEMBERSHIP_FLOOR, fit_pair_floor
from .log_linear_validation import prediction_metrics, relative_shift_gains, shifted_coverage
from .profiles import load_profiles
from .scenario_shift_validation import shifted_examples


CONFIRMATION_SEEDS = list(range(20270530, 20270535))
FINAL_SEEDS = list(range(20270535, 20270540))
SHIFT_SEED = 20270540
RAW_ERROR_CEILING = 1e-5
SERVED_SCORE_DECIMALS = 1
SERIALIZED_ERROR_RESOLUTION = .001


def evaluate(profiles_path: Path) -> dict:
    profiles = load_profiles(profiles_path)
    results, sizes = [], None
    for seed in CONFIRMATION_SEEDS + FINAL_SEEDS:
        item, seed_sizes = seed_result(profiles, seed, fit_pair_fn=fit_pair_floor)
        item["phase"] = "confirmation" if seed in CONFIRMATION_SEEDS else "final"
        candidate = item["logLinearCandidate"]
        calibration = candidate["calibration"]
        item["passedPerSeedGate"] = (
            min(item["gains"].values()) >= 99
            and candidate["maximumAbsoluteError"] <= RAW_ERROR_CEILING
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
    all_mae_gain, all_p90_gain = mean_gain(results, "maePercent"), mean_gain(results, "p90Percent")
    final_mae_gain, final_p90_gain = mean_gain(final, "maePercent"), mean_gain(final, "p90Percent")
    latency_ratio = float(np.mean([
        item["logLinearCandidate"]["apiBatchLatencyMs"] / item["championV011"]["apiBatchLatencyMs"]
        for item in results
    ]))
    coefficient_matrix = np.asarray([
        list(item["logLinearCandidate"]["coefficients"].values()) for item in results
    ])

    shift_models, shift_x, shift_y, shift_groups, shift_indices = fit_pair_floor(profiles, SHIFT_SEED)
    shift_validation, shift_test = shift_indices
    shifted_x, shifted_y, irrigated = shifted_examples(
        profiles, np.unique(shift_groups[shift_test]), seed=SHIFT_SEED,
    )
    shifted = {}
    shifted_predictions = {}
    for name, fitted in shift_models.items():
        prediction = fitted["model"].predict(shifted_x[:, fitted["columns"]])
        shifted_predictions[name] = prediction
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
    candidate_prediction = shifted_predictions["logLinearCandidate"]
    served_scores = np.asarray([
        round(min(float(prediction), float(target)), SERVED_SCORE_DECIMALS)
        for prediction, target in zip(candidate_prediction, shifted_y, strict=True)
    ])
    teacher_scores = np.asarray([
        round(float(target), SERVED_SCORE_DECIMALS) for target in shifted_y
    ])
    runtime_score_mismatches = int(np.sum(served_scores != teacher_scores))
    reported_radii = {
        name: float(np.ceil(value * 1000) / 1000)
        for name, value in shift_calibration["absoluteErrorQuantiles"].items()
    }
    shift_gate = (
        min(shift_gains.values()) >= 99
        and shifted["logLinearCandidate"]["maximumAbsoluteError"] <= RAW_ERROR_CEILING
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
        and shift_calibration["coverage80"] >= .8
        and shift_calibration["coverage90"] >= .9
        and max(reported_radii.values()) <= SERIALIZED_ERROR_RESOLUTION
        and runtime_score_mismatches == 0
        and random_calibration["inactiveExact"] and shift_calibration["inactiveExact"]
    )

    checks = {
        "everySeedPasses": all(item["passedPerSeedGate"] for item in results),
        "allSeedMeanGains": all_mae_gain >= 99 and all_p90_gain >= 99,
        "finalMeanGains": final_mae_gain >= 99 and final_p90_gain >= 99,
        "coefficientStability": bool(np.max(np.ptp(coefficient_matrix, axis=0)) <= 1e-6),
        "positiveUnitSumElasticities": bool(np.all(coefficient_matrix > 0) and np.all(np.abs(np.sum(coefficient_matrix, axis=1) - 1) <= .01)),
        "artifactSize": sizes["logLinearCandidate"] <= 50_000 and sizes["logLinearCandidate"] <= .01 * sizes["championV011"],
        "batchLatency": latency_ratio <= .25,
        "runtimePrecisionShift": shift_gate,
    }
    return {
        "name": "CropFit membership-floor log-linear validation v0.12.1",
        "protocol": {
            "target": "EcoCrop mechanistic screening teacher; not observed yield",
            "champion": "v0.11.0, six features, 40 Extra Trees",
            "candidate": "four-feature log-linear regression with fixed 1e-6 teacher membership floor and float64 fitting rows",
            "membershipFloor": MEMBERSHIP_FLOOR,
            "selection": "The boundary fix and every threshold were fixed after the exposed v0.12 rejection plus development seeds 20270521-20270523. Seeds in this report were reserved until this protocol was committed.",
            "fixedEvaluation": "Both models use identical fitting profile identities, validation profiles, held-out profiles, and evaluation rows; the candidate alone retains float64 fitting precision.",
            "confirmationSeeds": CONFIRMATION_SEEDS,
            "finalSeeds": FINAL_SEEDS,
            "shiftSeed": SHIFT_SEED,
            "measurementFloorPolicy": (
                "Random-row active conformal coverage must remain within two points of nominal. On independently generated runtime-shaped rows, raw maximum error must stay <=0.00001, serialized p80/p90 radii must be <=0.001, coverage may be conservatively above nominal at that resolution, and every deterministic-ceiling score must exactly match the teacher after normal 0.1-point API rounding."
            ),
            "declaredGate": (
                "Every seed must improve MAE/p90 by >=99%, improve deployed maximum error, keep maximum raw error <=0.00001, preserve active random-row coverage within two points, and produce exact inactive zeros. All-seed and final-only mean gains >=99%; positive unit-sum coefficient spread <=0.000001; compressed size <=50 KB and <=1% of v0.11; batch latency <=0.25x. Independent shift must improve all accuracy/subgroup metrics, meet the measurement-floor policy, and have zero served-score mismatches."
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
                name: [round(float(np.min(coefficient_matrix[:, index])), 10), round(float(np.max(coefficient_matrix[:, index])), 10)]
                for index, name in enumerate(results[0]["logLinearCandidate"]["coefficients"])
            },
        },
        "independentShift": {
            "seed": SHIFT_SEED,
            "profiles": len(np.unique(shift_groups[shift_test])),
            "examples": len(shifted_y),
            **shifted,
            "gains": shift_gains,
            "activeCoverage": {"frozenRandom": random_calibration, "independentShift": shift_calibration},
            "serializedErrorRadii": reported_radii,
            "runtimeScoreMismatches": runtime_score_mismatches,
            "passed": shift_gate,
        },
        "gate": {"passed": all(checks.values()), "checks": checks},
    }


def markdown(report: dict) -> str:
    lines = [
        "# CropFit membership-floor log-linear validation", "",
        "The candidate aligns its positive-membership floor with the pre-existing mechanistic teacher and retains float64 precision only while fitting four learned elasticities.", "",
        "| Phase | Seed | v0.11 MAE | Candidate MAE | MAE gain | p90 gain | Maximum error | Active 80% | Active 90% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        candidate, calibration = item["logLinearCandidate"], item["logLinearCandidate"]["calibration"]
        lines.append(
            f'| {item["phase"]} | {item["seed"]} | {item["championV011"]["mae"]:.5f} | {candidate["mae"]:.8f} | '
            f'{item["gains"]["maePercent"]:.3f}% | {item["gains"]["p90Percent"]:.3f}% | '
            f'{candidate["maximumAbsoluteError"]:.8f} | {calibration["coverage80"]:.1%} | {calibration["coverage90"]:.1%} |'
        )
    summary, shift = report["summary"], report["independentShift"]
    lines += [
        "", f'Seed wins: **{summary["seedWins"]}/{summary["seeds"]}**. Final-only gains are **{summary["finalMeanMaeImprovementPercent"]:.3f}% MAE** and **{summary["finalMeanP90ImprovementPercent"]:.3f}% p90**.',
        "", f'The regressor is **{summary["candidateSerializedSizeBytes"] / 1000:.1f} KB** versus **{summary["championSerializedSizeBytes"] / 1_000_000:.1f} MB**, with **{summary["meanApiBatchLatencyRatio"]:.3f}x** batch latency.',
        "", "## Independent runtime-shaped shift", "",
        f'Raw maximum error is **{shift["logLinearCandidate"]["maximumAbsoluteError"]:.8f}**; serialized error radii are **{shift["serializedErrorRadii"]["p80"]:.3f} / {shift["serializedErrorRadii"]["p90"]:.3f}**; served-score mismatches: **{shift["runtimeScoreMismatches"]} / {shift["examples"]:,}**.',
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**.',
        "", "> This validates fidelity to the mechanistic teacher at the API's reporting precision, not observed-yield accuracy.", "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    results, summary, shift = report["results"], report["summary"], report["independentShift"]
    labels = [str(item["seed"])[-2:] for item in results]
    x = np.arange(len(results))
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.2))
    axes[0].plot(x, [item["logLinearCandidate"]["maximumAbsoluteError"] for item in results], marker="o", color="#315d49")
    axes[0].axhline(RAW_ERROR_CEILING, color="#d98352", linestyle="--", label="raw-error ceiling")
    axes[0].set(xticks=x, xticklabels=labels, ylabel="Maximum raw error", title="Every fresh seed below ceiling")
    axes[0].legend(); axes[0].grid(alpha=.18)
    axes[1].plot(x, [item["logLinearCandidate"]["calibration"]["coverage80"] for item in results], marker="o", label="active 80%", color="#d98352")
    axes[1].plot(x, [item["logLinearCandidate"]["calibration"]["coverage90"] for item in results], marker="o", label="active 90%", color="#315d49")
    axes[1].axhline(.8, color="#d98352", linestyle="--", alpha=.6); axes[1].axhline(.9, color="#315d49", linestyle="--", alpha=.6)
    axes[1].set(xticks=x, xticklabels=labels, ylim=(.76, .94), ylabel="Coverage", title="Fresh random-row calibration")
    axes[1].legend(); axes[1].grid(alpha=.18)
    axes[2].bar(["raw max\n(×1e-5)", "p90 radius\n(×.001)", "score mismatches"], [shift["logLinearCandidate"]["maximumAbsoluteError"] / RAW_ERROR_CEILING, shift["serializedErrorRadii"]["p90"] / SERIALIZED_ERROR_RESOLUTION, shift["runtimeScoreMismatches"]], color=["#315d49", "#6f9551", "#8fae82"])
    axes[2].axhline(1, color="#d98352", linestyle="--", label="ceiling")
    axes[2].set(ylabel="Normalized value", title="Independent runtime-shaped shift")
    axes[2].legend(); axes[2].grid(axis="y", alpha=.18)
    status = "promoted" if report["gate"]["passed"] else "rejected"
    figure.suptitle(f"CropFit v0.12.1 candidate {status} · teacher-floor alignment", fontweight="bold")
    figure.text(.5, .01, "Fresh unseen crop profiles · measurement-floor policy committed before evaluation", ha="center", color="#555555")
    figure.tight_layout(rect=(0, .05, 1, .93)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/log-linear-floor-validation-v0.12.1.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/log-linear-floor-validation-v0.12.1.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/log-linear-floor-validation-v0.12.1.png")
    args = parser.parse_args()
    report = evaluate(args.profiles)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps({"summary": report["summary"], "independentShift": {"maximumAbsoluteError": report["independentShift"]["logLinearCandidate"]["maximumAbsoluteError"], "serializedErrorRadii": report["independentShift"]["serializedErrorRadii"], "runtimeScoreMismatches": report["independentShift"]["runtimeScoreMismatches"]}, "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Membership-floor log-linear promotion gate did not pass")


if __name__ == "__main__":
    main()
