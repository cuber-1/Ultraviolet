from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from .inference import MONTHS, CropFitPredictor
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


def benchmark(artifact: Path, profiles: Path, rounds: int) -> dict:
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
        "name": "CropFit reliability inference benchmark v4",
        "method": f"Median of {rounds} warm runs over one baseline plus ten historical climate scenarios; exact nested output equality required.",
        "scenarios": len(series),
        "legacyMilliseconds": round(legacy_ms, 4),
        "batchedMilliseconds": round(batched_ms, 4),
        "speedup": round(legacy_ms / batched_ms, 2),
        "outputsIdentical": True,
    }


def markdown(report: dict) -> str:
    return "\n".join([
        "# CropFit reliability inference benchmark v4", "",
        report["method"], "",
        "| Path | Median latency |", "|---|---:|",
        f'| One forest pass per scenario | {report["legacyMilliseconds"]:.2f} ms |',
        f'| Batched forest pass | {report["batchedMilliseconds"]:.2f} ms |',
        "", f'**Speedup: {report["speedup"]:.2f}x. Outputs identical: {str(report["outputsIdentical"]).lower()}.**',
        "", "Timing is machine-dependent; exact output equality is deterministic.", "",
    ])


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--output", type=Path, default=root / "evaluation/inference-benchmark-v4.json")
    parser.add_argument("--rounds", type=int, default=30)
    args = parser.parse_args()
    report = benchmark(args.artifact, args.profiles, args.rounds)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
