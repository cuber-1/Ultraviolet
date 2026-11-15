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
FINAL_YEARS = (2023, 2024, 2025)
CANDIDATE_SPECS = {
    ("BEANS", "DRY EDIBLE, INCL CHICKPEAS", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "beans (legacy incl chickpeas)",
    ("BEANS", "DRY EDIBLE, (EXCL CHICKPEAS)", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "beans (current excl chickpeas)",
    ("CORN", "ALL CLASSES", "SILAGE", "TONS / ACRE"): "silage corn",
    ("PEAS", "DRY EDIBLE", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "dry peas",
    ("SUNFLOWER", "OIL TYPE", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "sunflower",
    ("SUNFLOWER", "NON-OIL TYPE", "ALL UTILIZATION PRACTICES", "LB / ACRE"): "sunflower (non-oil)",
    ("POTATOES", "ALL CLASSES", "ALL UTILIZATION PRACTICES", "CWT / ACRE"): "potato",
    ("WHEAT", "SPRING, (EXCL DURUM)", "ALL UTILIZATION PRACTICES", "BU / ACRE"): "spring wheat",
    ("WHEAT", "SPRING, DURUM", "ALL UTILIZATION PRACTICES", "BU / ACRE"): "durum wheat",
}


def candidate_rows(data: Path) -> list[dict]:
    points = county_points(data / "2022_Gaz_counties_national.zip", state=None)
    rows = []
    with (data / "quickstats-county-yield-2010-2025-expanded-v4.tsv").open(newline="", encoding="utf-8") as source:
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


def forward_examples(rows: list[dict], crop: str) -> tuple[list[dict], dict[int, int]]:
    examples = []
    published = {}
    for year in TEST_YEARS:
        history: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row["crop"] == crop and row["year"] < year:
                history[row["fips"]].append(row["percentile"])
        test = [row for row in rows if row["crop"] == crop and row["year"] == year]
        published[year] = len(test)
        for row in test:
            values = history.get(row["fips"], [])
            if values:
                examples.append({**row, "prediction": float(np.mean(values))})
    return examples, published


def optional_round(value: float) -> float | None:
    return round(float(value), 4) if np.isfinite(value) else None


def metric_summary(examples: list[dict], published: int) -> dict:
    actual = np.asarray([item["percentile"] for item in examples])
    predicted = np.asarray([item["prediction"] for item in examples])
    groups = np.asarray([item["fips"] for item in examples])
    correlation = float(spearmanr(predicted, actual).statistic) if len(examples) >= 2 else float("nan")
    interval = bootstrap_interval(predicted, actual, groups) if len(examples) >= 2 else (float("nan"), float("nan"))
    return {
        "published": published,
        "observations": len(examples),
        "coverage": round(len(examples) / published, 4) if published else 0.0,
        "spearman": optional_round(correlation),
        "bootstrap95": [optional_round(value) for value in interval],
        "maePercentile": optional_round(float(np.mean(np.abs(predicted - actual)))) if len(examples) else None,
    }


def validate(data: Path) -> dict:
    rows = candidate_rows(data)
    candidates = []
    for crop in sorted(set(CANDIDATE_SPECS.values())):
        examples, published_by_year = forward_examples(rows, crop)
        overall = metric_summary(examples, sum(published_by_year.values()))
        final_examples = [item for item in examples if item["year"] in FINAL_YEARS]
        final = metric_summary(final_examples, sum(published_by_year[year] for year in FINAL_YEARS))
        per_year = []
        for year in TEST_YEARS:
            year_rows = [item for item in examples if item["year"] == year]
            if len(year_rows) >= 2:
                rho = float(spearmanr([item["prediction"] for item in year_rows], [item["percentile"] for item in year_rows]).statistic)
            else:
                rho = float("nan")
            per_year.append({"year": year, "observations": len(year_rows), "spearman": round(rho, 4) if np.isfinite(rho) else None})
        passed = (
            overall["observations"] >= 100 and overall["spearman"] is not None and overall["spearman"] >= .5
            and overall["bootstrap95"][0] is not None and overall["bootstrap95"][0] > .3 and overall["coverage"] >= .5
            and final["observations"] >= 100 and final["spearman"] is not None and final["spearman"] >= .5
            and final["bootstrap95"][0] is not None and final["bootstrap95"][0] > .3 and final["coverage"] >= .5
        )
        candidates.append({
            "crop": crop, **overall, "finalTest": final,
            "perYear": per_year, "passed": passed,
        })
    return {
        "name": "USDA observed-prior crop expansion v2",
        "historyYears": list(range(2010, 2026)), "testYears": list(TEST_YEARS),
        "finalTestYears": list(FINAL_YEARS),
        "candidates": candidates,
        "acceptedCrops": [item["crop"] for item in candidates if item["passed"]],
        "gate": {
            "rule": "Both the 2018–2025 forward test and locked 2023–2025 block need >=100 observations, Spearman >=0.50, grouped-bootstrap lower bound >0.30, and >=50% published-row coverage.",
        },
        "dataNotes": [
            "USDA NASS changed the dry-edible-bean definition in 2019: the current category excludes chickpeas.",
            "Legacy and current bean definitions are evaluated separately and are never joined as one time series.",
            "Winter, non-durum spring, and durum wheat remain separate definitions; their percentiles are never pooled.",
            "Grain and silage corn, and oil and non-oil sunflower, remain separate definitions and units.",
        ],
        "definitionSource": "https://www.nass.usda.gov/Publications/Todays_Reports/reports/cropan20.pdf",
        "interpretation": "Passing supports county-level regional ordering only, not parcel yield or purchase returns.",
    }


def markdown(report: dict) -> str:
    lines = [
        "# USDA observed-prior crop expansion v2", "",
        f'Gate: {report["gate"]["rule"]}', "",
        "| Crop | Forward N | All-year ρ | Final N | Final ρ | Final 95% interval | Final MAE | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["candidates"]:
        final = item["finalTest"]
        all_rho = "n/a" if item["spearman"] is None else f'{item["spearman"]:.3f}'
        final_rho = "n/a" if final["spearman"] is None else f'{final["spearman"]:.3f}'
        final_interval = "n/a" if final["bootstrap95"][0] is None else f'{final["bootstrap95"][0]:.3f} to {final["bootstrap95"][1]:.3f}'
        final_mae = "n/a" if final["maePercentile"] is None else f'{final["maePercentile"]:.3f}'
        lines.append(f'| {item["crop"]} | {item["observations"]:,} | {all_rho} | {final["observations"]:,} | {final_rho} | {final_interval} | {final_mae} | {"ACCEPT" if item["passed"] else "REJECT"} |')
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
        "beans (current excl chickpeas)": "beans · current",
        "beans (legacy incl chickpeas)": "beans · legacy",
        "sunflower (non-oil)": "sunflower · non-oil",
    }
    labels = [label_map.get(item["crop"], item["crop"]) for item in candidates]
    colors = ["#315d49" if item["passed"] else "#d98352" for item in candidates]
    figure, axes = plt.subplots(1, 2, figsize=(14, 7))
    correlations = np.asarray([item["finalTest"]["spearman"] or 0 for item in candidates])
    intervals = np.asarray([
        item["finalTest"]["bootstrap95"] if item["finalTest"]["bootstrap95"][0] is not None else [0, 0]
        for item in candidates
    ])
    errors = np.vstack((correlations - intervals[:, 0], intervals[:, 1] - correlations))
    bars = axes[0].barh(labels, correlations, xerr=errors, capsize=5, color=colors)
    axes[0].bar_label(bars, labels=["n/a" if item["finalTest"]["spearman"] is None else f'{item["finalTest"]["spearman"]:.3f}' for item in candidates], padding=8)
    axes[0].axvline(.5, color="#777", linestyle="--", label="correlation floor")
    axes[0].set(xlim=(-.65, 1.05), xlabel="2023–2025 Spearman (95% county bootstrap)", title="Locked recent county rank persistence")
    axes[0].legend(loc="lower right"); axes[0].grid(axis="x", alpha=.18)
    final_observations = [item["finalTest"]["observations"] for item in candidates]
    bars = axes[1].barh(labels, final_observations, color=colors)
    axes[1].bar_label(bars, labels=[f'{item["finalTest"]["observations"]}  ({item["finalTest"]["coverage"]:.0%})' for item in candidates], padding=4)
    axes[1].axvline(100, color="#777", linestyle="--", label="sample floor")
    axes[1].set(xlim=(0, max(155, max(final_observations) * 1.2)), xlabel="final observations (coverage in labels)", title="Locked recent evidence volume")
    axes[1].legend(loc="lower right"); axes[1].grid(axis="x", alpha=.18)
    axes[0].invert_yaxis(); axes[1].invert_yaxis()
    figure.suptitle("USDA observed-prior crop expansion v2 · 2018–2025 test", fontweight="bold")
    figure.text(.5, .01, report["interpretation"], ha="center", color="#555", fontsize=9)
    figure.tight_layout(rect=(0, .06, 1, .94)); figure.savefig(output, dpi=180); plt.close(figure)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/raw/observed-validation/national")
    parser.add_argument("--output", type=Path, default=root / "evaluation/crop-expansion-validation-v2.json")
    args = parser.parse_args()
    report = validate(args.data)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    plot(report, args.output.with_suffix(".png"))
    print(json.dumps({"acceptedCrops": report["acceptedCrops"], "candidates": report["candidates"]}, indent=2))


if __name__ == "__main__":
    main()
