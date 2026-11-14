from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import spearmanr

from .inference import CropFitPredictor
from .observed_validation import climate, power_grids
from .yield_atlas import forward_examples, rows_from_quickstats


DEVELOPMENT_YEARS = (2018, 2019, 2020)
CONFIRMATION_YEARS = (2021, 2022)
FINAL_TEST_YEARS = (2023, 2024, 2025)
CANDIDATE_CLIMATE_WEIGHTS = (0.0, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0)


def score_cache(data: Path, artifact: Path, profiles: Path) -> list[dict]:
    model_version = joblib.load(artifact)["metadata"]["model"].rsplit(" ", 1)[-1]
    destination = data / f"cropfit-{model_version}-ranking-scores-2018-2025.json"
    existing = data / f"cropfit-{model_version}-scores.json"
    scores = json.loads(destination.read_text()) if destination.exists() else json.loads(existing.read_text()) if existing.exists() else []
    by_key = {(item["year"], item["crop"], item["fips"]): item for item in scores}
    rows = rows_from_quickstats(data)
    wanted = [row for row in rows if row["year"] in (*DEVELOPMENT_YEARS, *CONFIRMATION_YEARS, *FINAL_TEST_YEARS)]
    missing_by_year: dict[int, list[dict]] = defaultdict(list)
    for row in wanted:
        if (row["year"], row["crop"], row["fips"]) not in by_key:
            missing_by_year[row["year"]].append(row)
    if missing_by_year:
        predictor = CropFitPredictor(artifact, profiles)
        completed = 0
        for year in sorted(missing_by_year):
            grids = power_grids(data, year)
            for row in missing_by_year[year]:
                result = predictor.predict(row["crop"], row["latitude"], row["longitude"], 6.5, False, climate(grids, row["latitude"], row["longitude"], year))
                by_key[(year, row["crop"], row["fips"])] = {
                    "year": year, "crop": row["crop"], "fips": row["fips"],
                    "state": row["state"], "county": row["county"],
                    "cropFitScore": result["score"],
                }
                completed += 1
                if completed % 500 == 0:
                    print(f"scored {completed} new county-year rows", flush=True)
        scores = [by_key[key] for key in sorted(by_key)]
        destination.write_text(json.dumps(scores, separators=(",", ":")) + "\n")
    elif destination.exists():
        scores = json.loads(destination.read_text())
    return scores


def joined_examples(data: Path, scores: list[dict]) -> list[dict]:
    rows = rows_from_quickstats(data)
    forward, _ = forward_examples(rows, tuple(range(2010, 2026)), 2010)
    prior_by_key = {(item["year"], item["crop"], item["fips"]): item for item in forward}
    examples = []
    for item in scores:
        key = (item["year"], item["crop"], item["fips"])
        prior = prior_by_key.get(key)
        if prior is None or item["year"] not in (*DEVELOPMENT_YEARS, *CONFIRMATION_YEARS, *FINAL_TEST_YEARS):
            continue
        examples.append({
            **item,
            "actual": prior["yieldPercentileWithinCropYear"],
            "observedPrior": prior["prediction"],
            "climateScore": item["cropFitScore"] / 100.0,
        })
    return examples


def summary(examples: list[dict], climate_weight: float) -> dict:
    actual = np.asarray([item["actual"] for item in examples])
    prior = np.asarray([item["observedPrior"] for item in examples])
    hybrid = (1.0 - climate_weight) * prior + climate_weight * np.asarray([item["climateScore"] for item in examples])
    prior_rho = float(spearmanr(prior, actual).statistic)
    hybrid_rho = float(spearmanr(hybrid, actual).statistic)
    return {
        "observations": len(examples),
        "priorSpearman": round(prior_rho, 4),
        "hybridSpearman": round(hybrid_rho, 4),
        "spearmanDelta": round(hybrid_rho - prior_rho, 4),
        "priorMaePercentile": round(float(np.mean(np.abs(prior - actual))), 4),
        "hybridMaePercentile": round(float(np.mean(np.abs(hybrid - actual))), 4),
    }


def paired_bootstrap_delta(examples: list[dict], climate_weight: float, seed: int = 20261114) -> list[float]:
    actual = np.asarray([item["actual"] for item in examples])
    prior = np.asarray([item["observedPrior"] for item in examples])
    hybrid = (1.0 - climate_weight) * prior + climate_weight * np.asarray([item["climateScore"] for item in examples])
    groups = np.asarray([f'{item["crop"]}:{item["fips"]}' for item in examples])
    unique, inverse = np.unique(groups, return_inverse=True)
    indices = [np.flatnonzero(inverse == index) for index in range(len(unique))]
    random = np.random.default_rng(seed)
    deltas = []
    for _ in range(2000):
        sampled = random.integers(0, len(unique), len(unique))
        selection = np.concatenate([indices[index] for index in sampled])
        deltas.append(float(spearmanr(hybrid[selection], actual[selection]).statistic - spearmanr(prior[selection], actual[selection]).statistic))
    return [round(float(value), 4) for value in np.quantile(deltas, [.025, .975])]


def validate(data: Path, artifact: Path, profiles: Path) -> dict:
    examples = joined_examples(data, score_cache(data, artifact, profiles))
    development = [item for item in examples if item["year"] in DEVELOPMENT_YEARS]
    candidates = [{"climateWeight": weight, **summary(development, weight)} for weight in CANDIDATE_CLIMATE_WEIGHTS]
    selected = max(candidates, key=lambda item: item["hybridSpearman"])
    climate_weight = selected["climateWeight"]
    confirmation = [item for item in examples if item["year"] in CONFIRMATION_YEARS]
    final_test = [item for item in examples if item["year"] in FINAL_TEST_YEARS]
    confirmation_summary = summary(confirmation, climate_weight)
    final_summary = summary(final_test, climate_weight)
    final_summary["spearmanDeltaBootstrap95"] = paired_bootstrap_delta(final_test, climate_weight)
    per_crop = [{"crop": crop, **summary([item for item in final_test if item["crop"] == crop], climate_weight)} for crop in ("corn", "soybean", "wheat")]
    per_year = [{"year": year, **summary([item for item in final_test if item["year"] == year], climate_weight)} for year in FINAL_TEST_YEARS]
    passed = (
        final_summary["spearmanDelta"] > 0
        and final_summary["spearmanDeltaBootstrap95"][0] > 0
        and all(item["spearmanDelta"] >= 0 for item in per_crop)
        and sum(item["spearmanDelta"] > 0 for item in per_year) >= 2
    )
    climate_only = summary(final_test, 1.0)
    climate_delta_interval = paired_bootstrap_delta(final_test, 1.0)
    prior_vs_climate = {
        "observations": climate_only["observations"],
        "priorSpearman": climate_only["priorSpearman"],
        "climateSpearman": climate_only["hybridSpearman"],
        "priorAdvantage": round(-climate_only["spearmanDelta"], 4),
        "priorAdvantageBootstrap95": [-climate_delta_interval[1], -climate_delta_interval[0]],
        "perCrop": [],
    }
    for crop in ("corn", "soybean", "wheat"):
        item = summary([example for example in final_test if example["crop"] == crop], 1.0)
        prior_vs_climate["perCrop"].append({
            "crop": crop, "observations": item["observations"],
            "priorSpearman": item["priorSpearman"], "climateSpearman": item["hybridSpearman"],
            "priorAdvantage": round(-item["spearmanDelta"], 4),
        })
    prior_gate = (
        prior_vs_climate["priorAdvantage"] > 0
        and prior_vs_climate["priorAdvantageBootstrap95"][0] > 0
        and all(item["priorAdvantage"] > 0 for item in prior_vs_climate["perCrop"])
    )
    return {
        "name": "CropFit observed-ranking blend v1",
        "model": joblib.load(artifact)["metadata"]["model"],
        "target": "USDA county yield percentile within crop and year",
        "weights": {"observedCountyPrior": round(1 - climate_weight, 2), "agroclimaticScore": climate_weight},
        "developmentYears": list(DEVELOPMENT_YEARS), "candidateSelection": candidates,
        "confirmationYears": list(CONFIRMATION_YEARS), "confirmation": confirmation_summary,
        "finalTestYears": list(FINAL_TEST_YEARS), "finalTest": final_summary,
        "perCropFinalTest": per_crop, "perYearFinalTest": per_year,
        "blendGate": {
            "passed": passed,
            "rule": "On untouched 2023–2025 rows: pooled rank delta and grouped-bootstrap lower bound > 0, every crop non-negative, and at least two of three years positive.",
        },
        "priorVsClimateFinalTest": prior_vs_climate,
        "productionGate": {
            "passed": prior_gate,
            "rule": "On 2023–2025 rows, the observed prior must beat the current agroclimatic-only rank pooled with a grouped-bootstrap lower bound > 0 and separately for every supported crop.",
            "decision": "Use the observed prior only for supported crops in rural regional ranking; keep agroclimatic suitability for planting timing and unsupported crops. Do not promote the failed blend.",
        },
        "interpretation": "This validates ordering counties for supported crops. It does not validate parcel yield, revenue, or purchase returns.",
    }


def markdown(report: dict) -> str:
    final = report["finalTest"]
    lines = [
        "# CropFit observed-ranking blend v1", "",
        f'**Blend gate: {"PASS" if report["blendGate"]["passed"] else "NOT PASSED"}**', "",
        f'The selected blend uses {report["weights"]["observedCountyPrior"]:.0%} observed county prior and {report["weights"]["agroclimaticScore"]:.0%} agroclimatic score. Candidate weight was selected on 2018–2020 only.', "",
        f'On untouched 2023–2025 outcomes ({final["observations"]:,} rows), Spearman changed from **{final["priorSpearman"]:.4f}** to **{final["hybridSpearman"]:.4f}** (delta {final["spearmanDelta"]:+.4f}; county-crop grouped-bootstrap 95% interval {final["spearmanDeltaBootstrap95"][0]:+.4f} to {final["spearmanDeltaBootstrap95"][1]:+.4f}).', "",
        "| Crop | N | Prior ρ | Hybrid ρ | Delta |", "|---|---:|---:|---:|---:|",
    ]
    for item in report["perCropFinalTest"]:
        lines.append(f'| {item["crop"]} | {item["observations"]:,} | {item["priorSpearman"]:.4f} | {item["hybridSpearman"]:.4f} | {item["spearmanDelta"]:+.4f} |')
    lines += ["", "| Year | N | Prior ρ | Hybrid ρ | Delta |", "|---:|---:|---:|---:|---:|"]
    for item in report["perYearFinalTest"]:
        lines.append(f'| {item["year"]} | {item["observations"]:,} | {item["priorSpearman"]:.4f} | {item["hybridSpearman"]:.4f} | {item["spearmanDelta"]:+.4f} |')
    prior = report["priorVsClimateFinalTest"]
    lines += [
        "", f'Blend gate rule: {report["blendGate"]["rule"]}', "",
        "## Production ranking decision", "",
        f'On the same untouched rows, the observed prior scored **{prior["priorSpearman"]:.4f}** versus **{prior["climateSpearman"]:.4f}** for the current agroclimatic-only ranking (advantage {prior["priorAdvantage"]:+.4f}; grouped-bootstrap 95% interval {prior["priorAdvantageBootstrap95"][0]:+.4f} to {prior["priorAdvantageBootstrap95"][1]:+.4f}). Production gate: **{"PASS" if report["productionGate"]["passed"] else "NOT PASSED"}**.', "",
        f'{report["productionGate"]["decision"]}', "", f'> {report["interpretation"]}', "",
    ]
    return "\n".join(lines)


def plot(report: dict, destination: Path) -> None:
    import matplotlib.pyplot as plt

    candidates = report["candidateSelection"]
    years = report["perYearFinalTest"]
    crops = report["perCropFinalTest"]
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    axes[0].plot([item["climateWeight"] * 100 for item in candidates], [item["hybridSpearman"] for item in candidates], marker="o", color="#315d49")
    axes[0].axvline(report["weights"]["agroclimaticScore"] * 100, color="#d98352", linestyle="--", label="selected on 2018–2020")
    axes[0].set(xlabel="agroclimatic weight (%)", ylabel="development Spearman", title="Observed outcomes dominate the blend")
    axes[0].grid(alpha=.18); axes[0].legend()
    labels = [str(item["year"]) for item in years] + [item["crop"] for item in crops]
    deltas = [item["spearmanDelta"] for item in years] + [item["spearmanDelta"] for item in crops]
    colors = ["#315d49" if value >= 0 else "#d98352" for value in deltas]
    bars = axes[1].bar(labels, deltas, color=colors)
    axes[1].bar_label(bars, fmt="%+.4f", padding=3, fontsize=8)
    axes[1].axhline(0, color="#777", linewidth=.8)
    axes[1].set(ylabel="hybrid − prior Spearman", title="Untouched 2023–2025 rank gain")
    axes[1].grid(axis="y", alpha=.18)
    prior = report["priorVsClimateFinalTest"]
    comparison = prior["perCrop"]
    positions = np.arange(len(comparison)); width = .36
    axes[2].bar(positions - width / 2, [item["priorSpearman"] for item in comparison], width, color="#315d49", label="USDA prior")
    axes[2].bar(positions + width / 2, [item["climateSpearman"] for item in comparison], width, color="#d98352", label="climate-only")
    axes[2].set(xticks=positions, xticklabels=[item["crop"] for item in comparison], ylim=(-.1, .95), ylabel="final-test Spearman", title="Production choice · observed prior wins")
    axes[2].grid(axis="y", alpha=.18); axes[2].legend()
    axes[2].text(.03, .91, f'Pooled: {prior["priorSpearman"]:.3f} vs {prior["climateSpearman"]:.3f}', transform=axes[2].transAxes, color="#315d49", fontsize=9)
    figure.suptitle("CropFit observed-ranking blend v1", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(destination, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/ranking-validation-v1.json")
    args = parser.parse_args()
    report = validate(args.data, args.artifact, args.profiles)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"weights": report["weights"], "finalTest": report["finalTest"], "blendGate": report["blendGate"], "priorVsClimateFinalTest": report["priorVsClimateFinalTest"], "productionGate": report["productionGate"]}, indent=2))


if __name__ == "__main__":
    main()
