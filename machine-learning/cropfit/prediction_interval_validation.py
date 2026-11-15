from __future__ import annotations

import argparse
import json
from pathlib import Path

from .national_observed_validation import CROP_NAMES
from .prediction_interval_development import (
    block_summary,
    conditional_radii,
    evaluate as development_evaluate,
    interval_metrics,
    prepare,
)
from .yield_atlas import CENSUS_REGIONS, STATE_TO_CENSUS_REGION


FINAL_YEARS = (2023, 2024, 2025)
SELECTED_CUTS = (.33, .67)
SELECTED_BLEND = .75
MIN_CROP_REGION_EXAMPLES = 100


def evaluate(data: Path) -> dict:
    development = development_evaluate(data)
    selected = development["selectedCandidate"]
    assert tuple(selected["cuts"]) == SELECTED_CUTS and selected["blend"] == SELECTED_BLEND
    items, base, scales = prepare(data)
    conditional = conditional_radii(items, SELECTED_CUTS)
    final_items = [item for item in items if item["year"] in FINAL_YEARS]
    champion = block_summary(final_items, base, scales)
    candidate = block_summary(final_items, base, scales, SELECTED_CUTS, conditional, SELECTED_BLEND)
    crop_regions = []
    for crop in sorted(CROP_NAMES.values()):
        for region in CENSUS_REGIONS:
            group = [item for item in final_items if item["crop"] == crop and STATE_TO_CENSUS_REGION[item["state"]] == region]
            if group:
                crop_regions.append({"crop": crop, "region": region, **interval_metrics(group, base, scales, SELECTED_CUTS, conditional, SELECTED_BLEND)})
    per_year = [{"year": year, **interval_metrics([item for item in final_items if item["year"] == year], base, scales, SELECTED_CUTS, conditional, SELECTED_BLEND)} for year in FINAL_YEARS]
    reduction90 = round(1 - candidate["pooled"]["meanWidth90"] / champion["pooled"]["meanWidth90"], 4)
    checks = {
        "sealedCandidateMatches": tuple(selected["cuts"]) == SELECTED_CUTS and selected["blend"] == SELECTED_BLEND,
        "developmentGatePassed": development["gate"]["passed"],
        "pooledFinalCoverage": .80 <= candidate["pooled"]["coverage80"] <= .87 and .90 <= candidate["pooled"]["coverage90"] <= .95,
        "cropFinalCoverage": all(item["coverage90"] >= .88 for item in candidate["perCrop"]),
        "regionFinalCalibration": all(item["coverage80"] >= .75 and .85 <= item["coverage90"] <= .98 and item["meanWidth90"] <= .70 for item in candidate["perRegion"]),
        "cropRegionFinalCoverage": all(item["observations"] < MIN_CROP_REGION_EXAMPLES or item["coverage90"] >= .85 for item in crop_regions),
        "perYearFinalCoverage": all(item["coverage90"] >= .88 for item in per_year),
        "meanWidth90ReductionAtLeast1Percent": reduction90 >= .01,
        "eightyPercentIntervalsUnchanged": candidate["pooled"]["meanWidth80"] == champion["pooled"]["meanWidth80"] and candidate["pooled"]["coverage80"] == champion["pooled"]["coverage80"],
    }
    return {
        "name": "Atlas v12 prediction-stratified interval locked validation",
        "protocol": {"sealedCuts": list(SELECTED_CUTS), "sealedBlend": SELECTED_BLEND, "finalYears": list(FINAL_YEARS), "minimumCropRegionExamples": MIN_CROP_REGION_EXAMPLES},
        "developmentEvidence": {"widthReduction90": selected["widthReduction90"], "gate": development["gate"]},
        "championV11": champion, "candidate": candidate, "perCropRegionFinal": crop_regions, "perYearFinal": per_year,
        "meanWidth90Reduction": reduction90, "gate": {"passed": all(checks.values()), "checks": checks},
        "decision": "promote prediction-stratified intervals to atlas v12" if all(checks.values()) else "reject; retain atlas v11",
        "interpretation": "Observed county-rank uncertainty; not parcel yield, revenue, or property value.",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(); parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national"); parser.add_argument("--output", type=Path, default=root / "evaluation/prediction-interval-validation-v12.json")
    args = parser.parse_args(); report = evaluate(args.data); args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"candidate": report["candidate"]["pooled"], "meanWidth90Reduction": report["meanWidth90Reduction"], "gate": report["gate"], "decision": report["decision"]}, indent=2))
    if not report["gate"]["passed"]: raise SystemExit("Prediction-stratified interval promotion gate did not pass")


if __name__ == "__main__": main()
