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
prediction = requests.post(f"{base}/predict", json=payload, timeout=30)
prediction.raise_for_status()
assert prediction.json()["observedYieldEvidence"]["county"] == "Fort Bend County"
invalid = requests.post(f"{base}/predict", json={**payload, "climate": climate[:11]}, timeout=10)
assert invalid.status_code == 422
print(f'CropFit HTTP verified: API {health["apiVersion"]}, local fallback, USDA evidence, input bounds')
PY
