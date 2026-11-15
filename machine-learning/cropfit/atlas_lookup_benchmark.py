from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from .yield_atlas import atlas_spatial_index, haversine_km, load_atlas, nearest_evidence


QUERIES = ((29.76, -95.37), (40.12, -88.24), (46.81, -100.78), (35.47, -97.52))


def brute_lookup(crop: str, latitude: float, longitude: float, path: Path) -> dict | None:
    atlas = load_atlas(str(path.resolve()))
    candidates = [record for record in atlas["records"] if record["crop"] == crop]
    if not candidates:
        return None
    return min(candidates, key=lambda item: haversine_km(latitude, longitude, item["latitude"], item["longitude"]))


def timed(function, crop: str, atlas: Path, iterations: int) -> float:
    samples = []
    for _ in range(5):
        started = perf_counter()
        for index in range(iterations):
            latitude, longitude = QUERIES[index % len(QUERIES)]
            function(crop, latitude, longitude, atlas)
        samples.append((perf_counter() - started) * 1000 / iterations)
    return median(samples)


def benchmark(atlas: Path, iterations: int) -> dict:
    load_atlas.cache_clear(); atlas_spatial_index.cache_clear()
    nearest_evidence("corn", *QUERIES[0], atlas, max_distance_km=10_000)
    for crop in ("corn", "soybean", "wheat"):
        for latitude, longitude in QUERIES:
            brute = brute_lookup(crop, latitude, longitude, atlas)
            indexed = nearest_evidence(crop, latitude, longitude, atlas, max_distance_km=10_000)
            if brute is None or indexed is None or brute["fips"] != indexed["fips"]:
                raise AssertionError(f"indexed lookup disagrees with brute force for {crop}")
    cases = []
    for crop, label in (("corn", "supported crop"), ("tomato", "unsupported crop")):
        brute_ms = timed(brute_lookup, crop, atlas, iterations)
        indexed_ms = timed(lambda name, lat, lon, path: nearest_evidence(name, lat, lon, path, max_distance_km=10_000), crop, atlas, iterations)
        cases.append({
            "case": label, "crop": crop, "iterationsPerRound": iterations,
            "bruteMillisecondsPerLookup": round(brute_ms, 6),
            "indexedMillisecondsPerLookup": round(indexed_ms, 6),
            "speedup": round(brute_ms / indexed_ms, 2),
        })
    return {
        "name": "USDA atlas lookup benchmark v1",
        "method": "Median of five warm-cache rounds across four fixed U.S. coordinates; exact nearest-county identity checked for all supported crops.",
        "atlasRecords": len(load_atlas(str(atlas.resolve()))["records"]),
        "cases": cases,
    }


def markdown(report: dict) -> str:
    lines = [
        "# USDA atlas lookup benchmark v1", "", report["method"], "",
        "| Case | Crop | Brute ms/lookup | Indexed ms/lookup | Speedup |",
        "|---|---|---:|---:|---:|",
    ]
    for item in report["cases"]:
        lines.append(f'| {item["case"]} | {item["crop"]} | {item["bruteMillisecondsPerLookup"]:.4f} | {item["indexedMillisecondsPerLookup"]:.4f} | **{item["speedup"]:.1f}x** |')
    lines += ["", f'Atlas records: {report["atlasRecords"]:,}. Results are machine-dependent; the correctness check is deterministic.', ""]
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-v11.json")
    parser.add_argument("--output", type=Path, default=root / "evaluation/atlas-lookup-benchmark-v1.json")
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    report = benchmark(args.atlas, args.iterations)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
