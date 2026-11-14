from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import product
from pathlib import Path
from urllib.parse import urljoin

import certifi
import requests

from .download_observed_validation import COUNTIES_URL, PARAMETERS, POWER_URL, download


DATASETS_PAGE = "https://www.nass.usda.gov/datasets"
YEARS = tuple(range(2018, 2026))
ATLAS_YEARS = tuple(range(2010, 2026))
ATLAS_CANDIDATES = {
    ("BEANS", "DRY EDIBLE, INCL CHICKPEAS", "ALL UTILIZATION PRACTICES", "LB / ACRE"),
    ("BEANS", "DRY EDIBLE, (EXCL CHICKPEAS)", "ALL UTILIZATION PRACTICES", "LB / ACRE"),
    ("SUNFLOWER", "OIL TYPE", "ALL UTILIZATION PRACTICES", "LB / ACRE"),
    ("POTATOES", "ALL CLASSES", "ALL UTILIZATION PRACTICES", "CWT / ACRE"),
}
LATITUDE_BANDS = ((24, 34), (34, 44), (44, 50))
LONGITUDE_BANDS = ((-125, -115), (-115, -105), (-105, -95), (-95, -85), (-85, -75), (-75, -66))


def latest_crops_url(session: requests.Session) -> str:
    response = session.get(DATASETS_PAGE, timeout=60, verify=certifi.where())
    response.raise_for_status()
    matches = re.findall(r'href="([^"]*/qs\.crops_\d+\.txt\.gz)"', response.text)
    if not matches:
        raise RuntimeError("Could not find the USDA NASS Quick Stats crops bulk file")
    return urljoin(DATASETS_PAGE, matches[-1])


def keep(row: dict[str, str], years: tuple[int, ...] = YEARS, include_atlas_candidates: bool = False) -> bool:
    if row["YEAR"] not in {str(year) for year in years}:
        return False
    if row["AGG_LEVEL_DESC"] != "COUNTY" or row["STATISTICCAT_DESC"] != "YIELD" or row["FREQ_DESC"] != "ANNUAL":
        return False
    if row["PRODN_PRACTICE_DESC"] != "ALL PRODUCTION PRACTICES" or row["DOMAIN_DESC"] != "TOTAL":
        return False
    crop = row["COMMODITY_DESC"]
    standard = (
        crop == "CORN" and row["CLASS_DESC"] == "ALL CLASSES" and row["UTIL_PRACTICE_DESC"] == "GRAIN" and row["UNIT_DESC"] == "BU / ACRE"
        or crop == "SOYBEANS" and row["CLASS_DESC"] == "ALL CLASSES" and row["UTIL_PRACTICE_DESC"] == "ALL UTILIZATION PRACTICES" and row["UNIT_DESC"] == "BU / ACRE"
        or crop == "WHEAT" and row["CLASS_DESC"] == "WINTER" and row["UTIL_PRACTICE_DESC"] == "ALL UTILIZATION PRACTICES" and row["UNIT_DESC"] == "BU / ACRE"
    )
    candidate = (crop, row["CLASS_DESC"], row["UTIL_PRACTICE_DESC"], row["UNIT_DESC"]) in ATLAS_CANDIDATES
    return standard or include_atlas_candidates and candidate


def extract(source: Path, destination: Path, years: tuple[int, ...] = YEARS, include_atlas_candidates: bool = False) -> int:
    if destination.exists():
        with destination.open(newline="") as existing:
            return max(0, sum(1 for _ in existing) - 1)
    selected = []
    with gzip.open(source, "rt", encoding="utf-8", errors="replace", newline="") as raw:
        reader = csv.DictReader(raw, delimiter="\t")
        fields = ["COMMODITY_DESC", "CLASS_DESC", "UTIL_PRACTICE_DESC", "UNIT_DESC", "STATE_FIPS_CODE", "STATE_ALPHA", "STATE_NAME", "COUNTY_CODE", "COUNTY_NAME", "YEAR", "VALUE", "CV_%"]
        for row in reader:
            if keep(row, years, include_atlas_candidates):
                selected.append({field: row[field].replace("\x00", "") for field in fields})
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(selected)
    return len(selected)


def fetch_power(task: tuple[Path, int, str, int, tuple[int, int], tuple[int, int]]) -> Path:
    destination, year, parameter, index, latitudes, longitudes = task
    if destination.exists():
        return destination
    for attempt in range(5):
        try:
            response = requests.get(
                POWER_URL,
                params={
                    "latitude-min": latitudes[0], "latitude-max": latitudes[1],
                    "longitude-min": longitudes[0], "longitude-max": longitudes[1],
                    "parameters": parameter, "community": "AG", "format": "JSON",
                    "start": year, "end": year,
                },
                timeout=120,
                verify=certifi.where(),
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("features"):
                raise RuntimeError(str(payload.get("messages")))
            destination.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
            return destination
        except (requests.RequestException, RuntimeError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / "data/raw/observed-validation/national")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    download(session, COUNTIES_URL, args.output / "2022_Gaz_counties_national.zip")
    filtered = args.output / "quickstats-county-yield-2018-2025.tsv"
    metadata_path = args.output / "download-metadata.json"
    if filtered.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        crops_url = metadata["quickStats"]
        with filtered.open(newline="") as existing:
            rows = max(0, sum(1 for _ in existing) - 1)
    else:
        crops_url = latest_crops_url(session)
        bulk = args.output / Path(crops_url).name
        download(session, crops_url, bulk)
        rows = extract(bulk, filtered)
    bulk = args.output / Path(crops_url).name
    if not bulk.exists():
        download(session, crops_url, bulk)
    atlas_filtered = args.output / "quickstats-county-yield-2010-2025.tsv"
    atlas_rows = extract(bulk, atlas_filtered, ATLAS_YEARS)
    expanded_filtered = args.output / "quickstats-county-yield-2010-2025-expanded-v3.tsv"
    expanded_rows = extract(bulk, expanded_filtered, ATLAS_YEARS, include_atlas_candidates=True)
    tasks = []
    for year in YEARS:
        for parameter in PARAMETERS:
            for index, (latitudes, longitudes) in enumerate(product(LATITUDE_BANDS, LONGITUDE_BANDS)):
                destination = args.output / f"nasa-power-{year}-{parameter.lower()}-{index}.json"
                tasks.append((destination, year, parameter, index, latitudes, longitudes))
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_power, task) for task in tasks]
        for future in as_completed(futures):
            future.result()
    metadata_path.write_text(json.dumps({
        "quickStats": crops_url,
        "filteredRows": rows,
        "years": YEARS,
        "atlasFilteredRows": atlas_rows,
        "atlasYears": ATLAS_YEARS,
        "expandedAtlasFilteredRows": expanded_rows,
    }, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "filteredRows": rows, "atlasFilteredRows": atlas_rows, "expandedAtlasFilteredRows": expanded_rows, "powerTiles": len(tasks)}, indent=2))


if __name__ == "__main__":
    main()
