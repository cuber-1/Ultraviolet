from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import matplotlib.pyplot as plt

from .inference import MONTHS, CropFitPredictor, sha256_file
from .profiles import resolve_profile


def climate(offset: float) -> list[dict]:
    return [{
        "month": month,
        "temperatureC": 18 + offset + index * .35,
        "precipitationMmDay": 2.2 + index % 4 * .3,
        "solarMjM2Day": 12 + index % 6 * 1.4,
    } for index, month in enumerate(MONTHS)]


def timed(function, rounds: int) -> float:
    samples = []
    for _ in range(rounds):
        started = perf_counter(); function(); samples.append((perf_counter() - started) * 1000)
    return median(samples)


def benchmark_one(artifact: Path, profiles: Path, rounds: int) -> dict:
    predictor = CropFitPredictor(artifact, profiles)
    profile = resolve_profile("tomato", predictor.profiles)
    history = [climate(offset) for offset in (-3, -2, -1, 0, .5, 1, 1.5, 2, 3, 4)]
    series = [climate(.25)] + [year + (history[index + 1] if index + 1 < len(history) else climate(.25)) for index, year in enumerate(history)]
    legacy = lambda: [predictor.curve(profile, values, 6.5, True) for values in series]
    batched = lambda: predictor.curves(profile, series, 6.5, True)
    if legacy() != batched():
        raise AssertionError("batched reliability inference changed prediction output")
    legacy_ms = timed(legacy, rounds)
    batched_ms = timed(batched, rounds)
    return {
        "model": predictor.metadata["model"],
        "artifactSha256": sha256_file(artifact),
        "artifactBytes": artifact.stat().st_size,
        "scenarios": len(series),
        "scenarioLoopMilliseconds": round(legacy_ms, 4),
        "batchedMilliseconds": round(batched_ms, 4),
        "batchingSpeedup": round(legacy_ms / batched_ms, 2),
        "outputsIdentical": True,
    }


def benchmark(
    artifact: Path, profiles: Path, rounds: int,
    champion_artifact: Path | None = None, champion_profiles: Path | None = None,
) -> dict:
    production = benchmark_one(artifact, profiles, rounds)
    champion = benchmark_one(champion_artifact, champion_profiles or profiles, rounds) if champion_artifact else None
    checks = {"productionBatchEquality": production["outputsIdentical"]}
    if champion:
        checks.update({
            "championBatchEquality": champion["outputsIdentical"],
            "productionFaster": production["batchedMilliseconds"] < champion["batchedMilliseconds"],
            "productionAtMostOnePercentSize": production["artifactBytes"] <= .01 * champion["artifactBytes"],
        })
    return {
        "name": "CropFit reliability inference benchmark v5",
        "method": f"Median of {rounds} warm runs over one baseline plus ten historical climate scenarios on the same host; each model must produce exact nested equality between its scenario loop and batched path.",
        "production": production,
        "championV011": champion,
        "productionVsChampion": ({
            "batchedSpeedup": round(champion["batchedMilliseconds"] / production["batchedMilliseconds"], 2),
            "latencyReductionPercent": round(100 * (1 - production["batchedMilliseconds"] / champion["batchedMilliseconds"]), 2),
            "artifactSizeReductionPercent": round(100 * (1 - production["artifactBytes"] / champion["artifactBytes"]), 4),
        } if champion else None),
        "gate": {"passed": all(checks.values()), "checks": checks},
        "interpretation": "Warm local CPU timing is machine-dependent; exact output equality, artifact hashes, and byte sizes are deterministic.",
    }


def markdown(report: dict) -> str:
    production = report["production"]
    lines = [
        "# CropFit reliability inference benchmark v5", "",
        report["method"], "",
        "| Model | Artifact | Scenario loop | Batched | Internal speedup |", "|---|---:|---:|---:|---:|",
        f'| v0.12.1 production | {production["artifactBytes"] / 1000:.1f} KB | {production["scenarioLoopMilliseconds"]:.3f} ms | {production["batchedMilliseconds"]:.3f} ms | {production["batchingSpeedup"]:.2f}x |',
    ]
    champion = report["championV011"]
    if champion:
        lines.append(f'| v0.11 champion | {champion["artifactBytes"] / 1_000_000:.1f} MB | {champion["scenarioLoopMilliseconds"]:.3f} ms | {champion["batchedMilliseconds"]:.3f} ms | {champion["batchingSpeedup"]:.2f}x |')
        comparison = report["productionVsChampion"]
        lines += ["", f'Production batched inference is **{comparison["batchedSpeedup"]:.2f}x faster** ({comparison["latencyReductionPercent"]:.1f}% lower latency), with a **{comparison["artifactSizeReductionPercent"]:.4f}%** smaller artifact.']
    lines += ["", f'Gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. {report["interpretation"]}', ""]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    production = report["production"]
    champion = report["championV011"]
    models = ["v0.12.1"] + (["v0.11"] if champion else [])
    rows = [production] + ([champion] if champion else [])
    colors = ["#315d49", "#d98352"][:len(rows)]
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    latency = axes[0].bar(models, [item["batchedMilliseconds"] for item in rows], color=colors)
    axes[0].bar_label(latency, fmt="%.3f ms", padding=3)
    axes[0].set(title="Full reliability request", ylabel="median warm latency (ms)")
    size = axes[1].bar(models, [item["artifactBytes"] for item in rows], color=colors)
    axes[1].set_yscale("log"); axes[1].set(title="Released artifact size", ylabel="bytes (log scale)")
    axes[1].bar_label(size, labels=[
        f'{item["artifactBytes"] / 1000:.1f} KB' if item["artifactBytes"] < 1_000_000
        else f'{item["artifactBytes"] / 1_000_000:.1f} MB'
        for item in rows
    ], padding=3)
    for axis in axes:
        axis.grid(axis="y", alpha=.18)
    figure.suptitle("CropFit v0.12.1 · exact output, smaller local inference", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--champion-artifact", type=Path)
    parser.add_argument("--champion-profiles", type=Path)
    parser.add_argument("--output", type=Path, default=root / "evaluation/inference-benchmark-v5.json")
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()
    report = benchmark(
        args.artifact, args.profiles, args.rounds,
        args.champion_artifact, args.champion_profiles,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
