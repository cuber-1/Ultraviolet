#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_port="${CROPFIT_TEST_PORT:-}"
service_log="$(mktemp)"
service_pid=""

if [[ -z "${test_port}" ]]; then
  test_port="$("${repo_root}/machine-learning/.venv/bin/python" - <<'PY'
import socket

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
fi

cleanup() {
  if [[ -n "${service_pid}" ]]; then
    kill "${service_pid}" 2>/dev/null || true
    wait "${service_pid}" 2>/dev/null || true
  fi
  rm -f "${service_log}"
}
trap cleanup EXIT

CROPFIT_PORT="${test_port}" "${repo_root}/scripts/runCropFitLocal.sh" >"${service_log}" 2>&1 &
service_pid="$!"
for ((attempt = 0; attempt < 30; attempt++)); do
  if curl --fail --silent "http://127.0.0.1:${test_port}/health" >/dev/null; then
    break
  fi
  if ! kill -0 "${service_pid}" 2>/dev/null; then
    cat "${service_log}" >&2
    exit 1
  fi
  sleep 1
done

if ! curl --fail --silent "http://127.0.0.1:${test_port}/health" >/dev/null; then
  cat "${service_log}" >&2
  echo "CropFit HTTP service did not become ready." >&2
  exit 1
fi

"${repo_root}/machine-learning/.venv/bin/python" - "${test_port}" <<'PY'
import sys

import requests

port = int(sys.argv[1])
base = f"http://127.0.0.1:{port}"
months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
climate = [{"month": month, "temperatureC": 22, "precipitationMmDay": 3, "solarMjM2Day": 18} for month in months]
payload = {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "soilPh": 6.5, "irrigated": True, "climate": climate, "climateHistory": [climate] * 10}
health = requests.get(f"{base}/health", timeout=10).json()
assert health["status"] == "ok" and health["requestLimits"]["historyYearsMax"] == 20
assert health["revision"].startswith(f'{health["apiVersion"]}:')
assert health["model"] == "CropFit EcoCrop surrogate v0.6"
assert health["metrics"]["mae"] == .0894
atlas = health["evidence"]["historicalYieldAtlas"]
assert atlas["name"] == "USDA county yield atlas v3"
assert atlas["predictionMethod"]["halfLifeYears"] == 3.0 and atlas["predictionMethod"]["recencyWeight"] == .8
assert atlas["validation"]["spearman"] == .7914 and atlas["uncertaintyValidation"]["gate"]["passed"]
assert health["climateHistory"] == {"source": "NASA POWER Agroclimatology", "startYear": 2016, "endYear": 2025, "years": 10}
prediction = requests.post(f"{base}/predict", json=payload, timeout=30)
prediction.raise_for_status()
prediction_body = prediction.json()
assert prediction_body["observedYieldEvidence"]["county"] == "Fort Bend County"
assert prediction_body["confidence"] == .8
assert prediction_body["expectedAbsoluteError"]["p80"] <= prediction_body["expectedAbsoluteError"]["p90"]
boundary = requests.post(f"{base}/predict", json={**payload, "climate": [{**item, "solarMjM2Day": 34} for item in climate]}, timeout=30)
boundary.raise_for_status()
assert boundary.json()["score"] == 0, "hard EcoCrop solar boundary was not enforced"
representatives = {
    "basil": "Ocimum basilicum",
    "kale": "Brassica oleracea var. acephala",
    "common bean": "Phaseolus vulgaris",
    "melon": "Cucumis melo",
    "onion": "Allium cepa",
    "sunflower": "Helianthus annuus",
}
for crop, scientific_name in representatives.items():
    response = requests.post(f"{base}/predict", json={**payload, "crop": crop}, timeout=30)
    response.raise_for_status()
    assert response.json()["profile"]["scientific_name"] == scientific_name
invalid = requests.post(f"{base}/predict", json={**payload, "climate": climate[:11]}, timeout=10)
assert invalid.status_code == 422
print(f'CropFit HTTP verified: API {health["apiVersion"]}, model v0.6, atlas v3 recency prior, seasonal boundary ceiling, 2016-2025 climate window, 16-choice coverage, USDA evidence, input bounds')
PY
