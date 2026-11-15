from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.neighbors import BallTree

from .crop_expansion_validation import candidate_rows, metric_summary
from .yield_atlas import conformal_quantile, history_bucket, observed_prior_prediction


YEARS = tuple(range(2010, 2026))
CALIBRATION_YEARS = tuple(range(2011, 2018))
DEVELOPMENT_YEARS = (2018, 2019, 2020)
STABILITY_YEARS = (2021, 2022)
FINAL_YEARS = (2023, 2024, 2025)
SCALE_CANDIDATES = (1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.33, 1.4, 1.5)
CROP_METADATA = {
    "silage corn": {"yieldUnit": "tons/acre", "usdaUnit": "TONS / ACRE"},
    "spring wheat": {"yieldUnit": "bu/acre", "usdaUnit": "BU / ACRE"},
}


def subtype_rows(data: Path) -> list[dict]:
    return [{
        **row,
        "yieldPerAcre": row["yield"],
        "yieldPercentileWithinCropYear": row["percentile"],
    } for row in candidate_rows(data) if row["crop"] in CROP_METADATA]


def spatial_transfer_examples(rows: list[dict]) -> list[dict]:
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for items in histories.values():
        items.sort(key=lambda item: item["year"])
    examples = []
    for year in YEARS[1:]:
        for crop in CROP_METADATA:
            sources = []
            for (source_crop, fips), items in histories.items():
                if source_crop != crop:
                    continue
                earlier = [item for item in items if item["year"] < year]
                if earlier:
                    latest = earlier[-1]
                    sources.append({
                        "fips": fips, "latitude": latest["latitude"], "longitude": latest["longitude"],
                        "prediction": observed_prior_prediction(earlier, year), "historyCount": len(earlier),
                    })
            targets = [row for row in rows if row["crop"] == crop and row["year"] == year]
            if len(sources) < 2 or not targets:
                continue
            tree = BallTree(np.radians([[item["latitude"], item["longitude"]] for item in sources]), metric="haversine")
            distances, indices = tree.query(
                np.radians([[item["latitude"], item["longitude"]] for item in targets]),
                k=min(2, len(sources)),
            )
            for target, target_distances, target_indices in zip(targets, distances, indices, strict=True):
                neighbors = [
                    (float(distance * 6371.0), sources[int(index)])
                    for distance, index in zip(target_distances, target_indices, strict=True)
                    if sources[int(index)]["fips"] != target["fips"]
                ]
                if not neighbors or neighbors[0][0] > 100:
                    continue
                distance, source = neighbors[0]
                examples.append({
                    **target, "prediction": source["prediction"], "historyCount": source["historyCount"],
                    "distanceKm": distance,
                    "absoluteError": abs(source["prediction"] - target["yieldPercentileWithinCropYear"]),
                })
    return examples


def interval_metrics(items: list[dict], table: dict[tuple[str, str], dict], scales: dict[str, dict]) -> dict:
    hits80, hits90, widths80, widths90 = [], [], [], []
    for item in items:
        calibration = table[(item["crop"], history_bucket(item["historyCount"]))]
        crop_scales = scales[item["crop"]]
        radius80 = calibration["absoluteErrorP80"] * crop_scales["scale80"]
        radius90 = calibration["absoluteErrorP90"] * crop_scales["scale90"]
        interval80 = (max(0.0, item["prediction"] - radius80), min(1.0, item["prediction"] + radius80))
        interval90 = (max(0.0, item["prediction"] - radius90), min(1.0, item["prediction"] + radius90))
        actual = item["yieldPercentileWithinCropYear"]
        hits80.append(interval80[0] <= actual <= interval80[1])
        hits90.append(interval90[0] <= actual <= interval90[1])
        widths80.append(interval80[1] - interval80[0])
        widths90.append(interval90[1] - interval90[0])
    return {
        "observations": len(items),
        "coverage80": round(float(np.mean(hits80)), 4),
        "coverage90": round(float(np.mean(hits90)), 4),
        "meanWidth80": round(float(np.mean(widths80)), 4),
        "meanWidth90": round(float(np.mean(widths90)), 4),
    }


def build(data: Path) -> tuple[dict, dict]:
    rows = subtype_rows(data)
    examples = spatial_transfer_examples(rows)
    calibration_examples = [item for item in examples if item["year"] in CALIBRATION_YEARS]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for item in calibration_examples:
        grouped[(item["crop"], history_bucket(item["historyCount"]))].append(item["absoluteError"])
    table = {
        key: {
            "crop": key[0], "historyBucket": key[1], "examples": len(errors),
            "absoluteErrorP80": round(conformal_quantile(errors, .8), 4),
            "absoluteErrorP90": round(conformal_quantile(errors, .9), 4),
        }
        for key, errors in grouped.items()
    }

    unit_scales = {crop: {"scale80": 1.0, "scale90": 1.0} for crop in CROP_METADATA}
    selection = []
    for crop in CROP_METADATA:
        crop_candidates = []
        for scale in SCALE_CANDIDATES:
            scales = {**unit_scales, crop: {"scale80": scale, "scale90": scale}}
            development = interval_metrics([item for item in examples if item["crop"] == crop and item["year"] in DEVELOPMENT_YEARS], table, scales)
            stability = interval_metrics([item for item in examples if item["crop"] == crop and item["year"] in STABILITY_YEARS], table, scales)
            crop_candidates.append({"scale": scale, "development": development, "stability": stability})
        scale80 = next(item["scale"] for item in crop_candidates if item["development"]["coverage80"] >= .78 and item["stability"]["coverage80"] >= .78)
        scale90 = next(item["scale"] for item in crop_candidates if item["development"]["coverage90"] >= .88 and item["stability"]["coverage90"] >= .88)
        unit_scales[crop] = {"scale80": scale80, "scale90": scale90}
        selection.append({"crop": crop, "candidates": crop_candidates, "selected": unit_scales[crop]})

    per_crop = []
    for crop in CROP_METADATA:
        crop_examples = [item for item in examples if item["crop"] == crop]
        final_examples = [item for item in crop_examples if item["year"] in FINAL_YEARS]
        published = sum(1 for row in rows if row["crop"] == crop and row["year"] in FINAL_YEARS)
        signal = metric_summary(final_examples, published)
        item = {
            "crop": crop,
            "signal": signal,
            "development": interval_metrics([item for item in crop_examples if item["year"] in DEVELOPMENT_YEARS], table, unit_scales),
            "stability": interval_metrics([item for item in crop_examples if item["year"] in STABILITY_YEARS], table, unit_scales),
            "final": interval_metrics(final_examples, table, unit_scales),
        }
        item["passed"] = (
        item["signal"]["observations"] >= 100
        and item["signal"]["spearman"] >= .5
        and item["signal"]["bootstrap95"][0] > .3
        and item["development"]["coverage80"] >= .78 and item["development"]["coverage90"] >= .88
        and item["stability"]["coverage80"] >= .78 and item["stability"]["coverage90"] >= .88
        and .75 <= item["final"]["coverage80"] <= .9
        and .87 <= item["final"]["coverage90"] <= .96
        and item["final"]["meanWidth90"] <= .8
        )
        per_crop.append(item)
    accepted_crops = [item["crop"] for item in per_crop if item["passed"]]
    gate_passed = accepted_crops == ["spring wheat"]
    report = {
        "name": "USDA crop-subtype yield atlas v1 validation",
        "calibrationYears": list(CALIBRATION_YEARS), "developmentYears": list(DEVELOPMENT_YEARS),
        "stabilityYears": list(STABILITY_YEARS), "finalTestYears": list(FINAL_YEARS),
        "calibrationExamples": len(calibration_examples),
        "calibrationGroups": [table[key] for key in sorted(table)],
        "scaleSelection": selection, "selectedScales": unit_scales, "perCrop": per_crop,
        "acceptedCrops": accepted_crops,
        "gate": {
            "passed": gate_passed,
            "rule": "Leave-one-county-out transfer within 100 km needs final N >=100, Spearman >=0.50 with grouped-bootstrap lower >0.30; pre-final development/stability coverage >=78%/88%; locked 2023-2025 coverage 75-90%/87-96%; mean final 90% width <=0.80.",
        },
        "interpretation": "Nearby-county subtype ordering and uncertainty only; not parcel yield, revenue, or purchase returns.",
    }
    if not gate_passed:
        raise RuntimeError("Crop-subtype atlas promotion gate failed; no atlas was produced.")

    records = []
    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        histories[(row["crop"], row["fips"])].append(row)
    for (crop, fips), items in sorted(histories.items()):
        if crop not in accepted_crops:
            continue
        items.sort(key=lambda item: item["year"])
        latest = items[-1]
        values = np.asarray([item["yieldPerAcre"] for item in items])
        percentiles = np.asarray([item["yieldPercentileWithinCropYear"] for item in items])
        expected = observed_prior_prediction(items, 2026)
        calibration = table[(crop, history_bucket(len(items)))]
        scales = unit_scales[crop]
        records.append({
            "crop": crop, "fips": fips, "state": latest["state"], "county": latest["county"],
            "latitude": latest["latitude"], "longitude": latest["longitude"],
            "yieldUnit": CROP_METADATA[crop]["yieldUnit"], "usdaUnit": CROP_METADATA[crop]["usdaUnit"],
            "years": [item["year"] for item in items], "observations": len(items),
            "meanPercentile": round(float(np.mean(percentiles)), 4),
            "p10Percentile": round(float(np.quantile(percentiles, .1)), 4),
            "p90Percentile": round(float(np.quantile(percentiles, .9)), 4),
            "meanYieldPerAcre": round(float(np.mean(values)), 2),
            "observedYieldPrior": {
                "expectedPercentile": round(expected, 4),
                "interval80": [round(max(0.0, expected - calibration["absoluteErrorP80"] * scales["scale80"]), 4), round(min(1.0, expected + calibration["absoluteErrorP80"] * scales["scale80"]), 4)],
                "interval90": [round(max(0.0, expected - calibration["absoluteErrorP90"] * scales["scale90"]), 4), round(min(1.0, expected + calibration["absoluteErrorP90"] * scales["scale90"]), 4)],
                "historyBucket": history_bucket(len(items)), "calibrationExamples": calibration["examples"],
                "intervalMethod": "spatial-neighborhood-conformal", "neighborCount": 1,
            },
            "history": [{"year": item["year"], "yieldPerAcre": item["yieldPerAcre"], "percentile": round(item["yieldPercentileWithinCropYear"], 4)} for item in items],
            "latest": {"year": latest["year"], "yieldPerAcre": latest["yieldPerAcre"]},
        })
    atlas = {
        "name": "USDA crop-subtype yield atlas v1", "evidenceGrade": "observed-subtype-county-calibrated",
        "scope": "contiguous U.S. counties excluding California; non-durum spring wheat; 2010-2025",
        "source": "USDA NASS Quick Stats published county yields", "crops": accepted_crops,
        "years": list(YEARS), "records": records, "validation": report,
        "spatialTransferValidation": {
            "method": "Leave one reporting county out and use the nearest other county with earlier history within 100 km.",
            "selectedNeighborhood": {"maxNeighbors": 1, "distancePower": 0.0, "distanceOffsetKm": 5.0},
            "groups": [{
                **table[(crop, bucket)],
                "absoluteErrorP80": round(table[(crop, bucket)]["absoluteErrorP80"] * unit_scales[crop]["scale80"], 4),
                "absoluteErrorP90": round(table[(crop, bucket)]["absoluteErrorP90"] * unit_scales[crop]["scale90"], 4),
            } for crop in accepted_crops for bucket in ("1", "2-3", "4+")],
            "gate": report["gate"],
        },
        "predictionMethod": {"name": "shrunken exponential recency prior", "forecastYear": 2026, "halfLifeYears": 3.0, "recencyWeight": .8, "longHistoryWeight": .2},
        "disclaimer": "Observed subtype-specific county prior with split-conformal uncertainty; not a parcel yield forecast, causal estimate, or purchase recommendation.",
    }
    return atlas, report


def markdown(report: dict, records: int) -> str:
    lines = [
        "# USDA crop-subtype yield atlas v1", "",
        report["gate"]["rule"], "",
        "| Crop subtype | Locked N | Transfer ρ | 95% lower | 80% coverage | 90% coverage | Decision |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["perCrop"]:
        signal, final = item["signal"], item["final"]
        lines.append(f'| {item["crop"]} | {signal["observations"]:,} | {signal["spearman"]:.3f} | {signal["bootstrap95"][0]:.3f} | {final["coverage80"]:.1%} | {final["coverage90"]:.1%} | {"PROMOTE" if item["passed"] else "REJECT"} |')
    lines += [
        "", f'Promotion gate: **{"PASS" if report["gate"]["passed"] else "NOT PASSED"}**. Atlas records: **{records:,}**.', "",
        "Scales were selected on 2018-2020 development and 2021-2022 stability blocks. The 2023-2025 outcomes remained locked until final evaluation. Silage corn retains an own-county persistence signal but fails the spatial-transfer rank floor and is not served as property evidence.", "",
        "> " + report["interpretation"], "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    crops = [item["crop"] for item in report["perCrop"]]
    colors = ["#315d49" if item["passed"] else "#d98352" for item in report["perCrop"]]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    x = np.arange(len(crops)); width = .32
    coverage80 = [item["final"]["coverage80"] * 100 for item in report["perCrop"]]
    coverage90 = [item["final"]["coverage90"] * 100 for item in report["perCrop"]]
    axes[0].bar(x - width / 2, coverage80, width, color=colors, alpha=.65, label="80% interval")
    axes[0].bar(x + width / 2, coverage90, width, color=colors, label="90% interval")
    axes[0].axhline(80, color="#78a55a", linestyle=":"); axes[0].axhline(90, color="#315d49", linestyle=":")
    axes[0].set(xticks=x, xticklabels=crops, ylim=(70, 100), ylabel="locked outcome coverage (%)", title="2023-2025 calibrated reliability")
    axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    correlations = [item["signal"]["spearman"] for item in report["perCrop"]]
    lowers = [item["signal"]["bootstrap95"][0] for item in report["perCrop"]]
    uppers = [item["signal"]["bootstrap95"][1] for item in report["perCrop"]]
    for position, correlation, lower, upper, color, item in zip(x, correlations, lowers, uppers, colors, report["perCrop"], strict=True):
        axes[1].errorbar([position], [correlation], yerr=[[correlation - lower], [upper - correlation]], fmt="o", markersize=10, capsize=6, color=color)
        axes[1].annotate("PROMOTE" if item["passed"] else "REJECT", (position, correlation), xytext=(0, 16), textcoords="offset points", ha="center", color=color, fontweight="bold", fontsize=9)
    axes[1].axhline(.5, color="#d98352", linestyle="--", label="promotion floor")
    axes[1].set(xticks=x, xticklabels=crops, ylim=(.25, .9), ylabel="Spearman rank correlation", title="Locked county ordering signal")
    axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("CropFit subtype atlas · held-out spatial-transfer evidence", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .06, 1, .94)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--atlas", type=Path, default=root / "evaluation/yield-atlas-subtypes-v1.json")
    parser.add_argument("--validation", type=Path, default=root / "evaluation/yield-atlas-subtypes-validation-v1.json")
    args = parser.parse_args()
    atlas, report = build(args.data)
    args.atlas.write_text(json.dumps(atlas, separators=(",", ":")) + "\n")
    args.validation.write_text(json.dumps(report, indent=2) + "\n")
    args.validation.with_suffix(".md").write_text(markdown(report, len(atlas["records"])))
    plot(report, args.validation.with_suffix(".png"))
    print(json.dumps({"records": len(atlas["records"]), "gate": report["gate"], "perCrop": report["perCrop"]}, indent=2))


if __name__ == "__main__":
    main()
