from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

from .observed_validation import bootstrap_interval, county_points, number


TEST_YEARS = tuple(range(2018, 2026))
CANDIDATE_SPECS = {
    ("BEANS", "DRY EDIBLE, INCL CHICKPEAS", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "beans (legacy incl chickpeas)",
    ("BEANS", "DRY EDIBLE, (EXCL CHICKPEAS)", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "beans (current excl chickpeas)",
    ("SUNFLOWER", "OIL TYPE", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "sunflower",
    ("POTATOES", "ALL CLASSES", "ALL UTILIZATION PRACTICES", "CWT / ACRE"): "potato",
}


def candidate_rows(data: Path) -> list[dict]:
    points = county_points(data / "2022_Gaz_counties_national.zip", state=None)
    rows = []
    with (data / "quickstats-county-yield-2010-2025-expanded-v3.tsv").open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            key = (row["COMMODITY_DESC"], row["CLASS_DESC"], row["UTIL_PRACTICE_DESC"], row["UNIT_DESC"])
            crop = CANDIDATE_SPECS.get(key)
            if crop is None or row["STATE_ALPHA"] in {"AK", "CA", "HI", "PR"} or not row["COUNTY_CODE"].strip():
                continue
            observed = number(row["VALUE"])
            fips = f"{int(row['STATE_FIPS_CODE']):02d}{int(row['COUNTY_CODE']):03d}"
            if observed is None or fips not in points:
                continue
            latitude, longitude, county = points[fips]
            rows.append({
                "year": int(row["YEAR"]), "crop": crop, "fips": fips,
                "state": row["STATE_ALPHA"], "county": county,
                "latitude": latitude, "longitude": longitude, "yield": observed,
            })
    by_crop_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        by_crop_year[(row["crop"], row["year"])].append(row)
    for group in by_crop_year.values():
        percentiles = rankdata([row["yield"] for row in group], method="average") / len(group)
        for row, percentile in zip(group, percentiles, strict=True):
            row["percentile"] = float(percentile)
    return rows


def forward_examples(rows: list[dict], crop: str) -> tuple[list[dict], int]:
    examples = []
    published = 0
    for year in TEST_YEARS:
        history: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row["crop"] == crop and row["year"] < year:
                history[row["fips"]].append(row["percentile"])
        test = [row for row in rows if row["crop"] == crop and row["year"] == year]
        published += len(test)
        for row in test:
            values = history.get(row["fips"], [])
            if values:
                examples.append({**row, "prediction": float(np.mean(values))})
    return examples, published


def validate(data: Path) -> dict:
    rows = candidate_rows(data)
    candidates = []
    for crop in sorted(set(CANDIDATE_SPECS.values())):
        examples, published = forward_examples(rows, crop)
        actual = np.asarray([item["percentile"] for item in examples])
        predicted = np.asarray([item["prediction"] for item in examples])
        groups = np.asarray([item["fips"] for item in examples])
        correlation = float(spearmanr(predicted, actual).statistic) if len(examples) >= 2 else float("nan")
        interval = bootstrap_interval(predicted, actual, groups) if len(examples) >= 2 else (float("nan"), float("nan"))
        per_year = []
        for year in TEST_YEARS:
            year_rows = [item for item in examples if item["year"] == year]
            if len(year_rows) >= 2:
                rho = float(spearmanr([item["prediction"] for item in year_rows], [item["percentile"] for item in year_rows]).statistic)
            else:
                rho = float("nan")
            per_year.append({"year": year, "observations": len(year_rows), "spearman": round(rho, 4) if np.isfinite(rho) else None})
        coverage = len(examples) / published if published else 0.0
        passed = len(examples) >= 100 and correlation >= .5 and interval[0] > .3 and coverage >= .5
        candidates.append({
            "crop": crop, "published": published, "observations": len(examples),
            "coverage": round(coverage, 4), "spearman": round(correlation, 4),
            "bootstrap95": list(interval),
            "maePercentile": round(float(np.mean(np.abs(predicted - actual))), 4),
            "perYear": per_year, "passed": passed,
        })
    return {
        "name": "USDA observed-prior crop expansion v1",
        "historyYears": list(range(2010, 2026)), "testYears": list(TEST_YEARS),
        "candidates": candidates,
        "acceptedCrops": [item["crop"] for item in candidates if item["passed"]],
        "gate": {
            "rule": "Each crop needs >=100 forward observations, Spearman >=0.50, grouped-bootstrap lower bound >0.30, and >=50% published-row coverage.",
        },
        "dataNotes": [
            "USDA NASS changed the dry-edible-bean definition in 2019: the current category excludes chickpeas.",
            "Legacy and current bean definitions are evaluated separately and are never joined as one time series.",
        ],
        "definitionSource": "https://www.nass.usda.gov/Publications/Todays_Reports/reports/cropan20.pdf",
        "interpretation": "Passing supports county-level regional ordering only, not parcel yield or purchase returns.",
    }


def markdown(report: dict) -> str:
    lines = [
        "# USDA observed-prior crop expansion v1", "",
        f'Gate: {report["gate"]["rule"]}', "",
        "| Crop | Published | Forward N | Coverage | Spearman | 95% interval | Percentile MAE | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["candidates"]:
        lines.append(f'| {item["crop"]} | {item["published"]:,} | {item["observations"]:,} | {item["coverage"]:.1%} | {item["spearman"]:.3f} | {item["bootstrap95"][0]:.3f} to {item["bootstrap95"][1]:.3f} | {item["maePercentile"]:.3f} | {"ACCEPT" if item["passed"] else "REJECT"} |')
    lines += [
        "", f'Accepted crops: **{", ".join(report["acceptedCrops"]) or "none"}**.', "",
        "## Data-definition guard", "",
        *[f"- {note}" for note in report["dataNotes"]],
        f'- Source: [USDA NASS Crop Production 2019 Summary]({report["definitionSource"]})',
        "", f'> {report["interpretation"]}', "",
    ]
    return "\n".join(lines)


def plot(report: dict, output: Path) -> None:
    import matplotlib.pyplot as plt

    candidates = report["candidates"]
    label_map = {
        "beans (current excl chickpeas)": "beans\ncurrent",
        "beans (legacy incl chickpeas)": "beans\nlegacy",
    }
    labels = [label_map.get(item["crop"], item["crop"]) for item in candidates]
    colors = ["#315d49" if item["passed"] else "#d98352" for item in candidates]
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    correlations = np.asarray([item["spearman"] for item in candidates])
    intervals = np.asarray([item["bootstrap95"] for item in candidates])
    errors = np.vstack((correlations - intervals[:, 0], intervals[:, 1] - correlations))
    bars = axes[0].bar(labels, correlations, yerr=errors, capsize=5, color=colors)
    axes[0].bar_label(bars, fmt="%.3f", padding=8); axes[0].axhline(.5, color="#777", linestyle="--", label="correlation floor")
    axes[0].set(ylim=(-.08, 1.05), ylabel="held-out Spearman (95% county bootstrap)", title="County rank persistence"); axes[0].legend(); axes[0].grid(axis="y", alpha=.18)
    bars = axes[1].bar(labels, [item["observations"] for item in candidates], color=colors)
    axes[1].bar_label(bars, labels=[f'{item["observations"]}  ({item["coverage"]:.0%})' for item in candidates], padding=4)
    axes[1].axhline(100, color="#777", linestyle="--", label="sample floor")
    axes[1].set(ylim=(0, 155), ylabel="forward observations (coverage in labels)", title="Evidence volume"); axes[1].legend(); axes[1].grid(axis="y", alpha=.18)
    figure.suptitle("USDA observed-prior crop expansion · 2018–2025 test", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .05, 1, 1)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--output", type=Path, default=root / "evaluation/crop-expansion-validation-v1.json")
    args = parser.parse_args()
    report = validate(args.data)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"acceptedCrops": report["acceptedCrops"], "candidates": report["candidates"]}, indent=2))


if __name__ == "__main__":
    main()
