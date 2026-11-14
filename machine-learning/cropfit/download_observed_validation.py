from __future__ import annotations

import argparse
import json
from pathlib import Path

import certifi
import requests


CA_YIELD_URLS = {
    2018: "https://www.nass.usda.gov/sites/default/files/Statistics_by_State/California/Publications/AgComm/2018/2018cactbsErrata.csv",
    2019: "https://www.nass.usda.gov/sites/default/files/Statistics_by_State/California/Publications/AgComm/2019/201908cropyear.csv",
    2020: "https://www.nass.usda.gov/sites/default/files/Statistics_by_State/California/Publications/AgComm/2020/main_data_table.csv",
    2021: "https://www.nass.usda.gov/sites/default/files/Statistics_by_State/California/Publications/AgComm/2021/CAC_2021_data_by_commodity_20240417.csv",
    2022: "https://www.nass.usda.gov/sites/default/files/Statistics_by_State/California/Publications/AgComm/2022/County_Ag_Commissioner_Report_2022_data_by_commodity.csv",
}
COUNTIES_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2022_Gazetteer/2022_Gaz_counties_national.zip"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
PARAMETERS = ("T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN")
TILES = ((32, 42, -125, -115), (32, 42, -116, -114))


def download(session: requests.Session, url: str, destination: Path) -> None:
    if destination.exists():
        return
    response = session.get(url, timeout=120, verify=certifi.where())
    response.raise_for_status()
    destination.write_bytes(response.content)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / "data/raw/observed-validation")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for year, url in CA_YIELD_URLS.items():
        download(session, url, args.output / f"ca-county-ag-{year}.csv")
    download(session, COUNTIES_URL, args.output / "2022_Gaz_counties_national.zip")
    for year in CA_YIELD_URLS:
        for parameter in PARAMETERS:
            for index, (lat_min, lat_max, lon_min, lon_max) in enumerate(TILES):
                destination = args.output / f"nasa-power-{year}-{parameter.lower()}-{index}.json"
                if destination.exists():
                    continue
                response = session.get(
                    POWER_URL,
                    params={
                        "latitude-min": lat_min, "latitude-max": lat_max,
                        "longitude-min": lon_min, "longitude-max": lon_max,
                        "parameters": parameter, "community": "AG", "format": "JSON",
                        "start": year, "end": year,
                    },
                    timeout=120,
                    verify=certifi.where(),
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("features"):
                    raise RuntimeError(f"NASA POWER returned no features for {year} {parameter} tile {index}: {payload.get('messages')}")
                destination.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
