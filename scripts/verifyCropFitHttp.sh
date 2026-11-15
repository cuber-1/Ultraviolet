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
import math
import sys

import requests

port = int(sys.argv[1])
base = f"http://127.0.0.1:{port}"
months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
climate = [{"month": month, "temperatureC": 22, "precipitationMmDay": 3, "solarMjM2Day": 18} for month in months]
payload = {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "soilPh": 6.5, "irrigated": True, "climate": climate, "climateHistory": [climate] * 10}
health = requests.get(f"{base}/health", timeout=10).json()
assert health["status"] == "ok" and health["requestLimits"]["historyYearsMax"] == 20
assert health["apiVersion"] == "0.17.0"
assert health["revision"].startswith(f'{health["apiVersion"]}:')
assert health["model"] == "CropFit EcoCrop surrogate v0.9.1"
assert len(health["artifactSha256"]) == 64
assert health["revision"].endswith(health["artifactSha256"][:12])
assert health["metrics"]["mae"] == .0145
atlas = health["evidence"]["historicalYieldAtlas"]
assert atlas["name"] == "USDA county yield atlas v9"
assert atlas["predictionMethod"]["halfLifeYears"] == 3.0 and atlas["predictionMethod"]["recencyWeight"] == .8
assert atlas["validation"]["spearman"] == .7914 and atlas["uncertaintyValidation"]["gate"]["passed"]
assert atlas["spatialTransferValidation"]["gate"]["passed"]
assert atlas["spatialTransferValidation"]["selectedNeighborhood"] == {"maxNeighbors": 8, "distancePower": 2.0, "distanceOffsetKm": 5.0}
assert atlas["spatialTransferValidation"]["finalSignal"]["regionalNeighborhood"]["spearman"] == .806
production_blend = atlas["spatialTransferValidation"]["productionBlend"]
assert production_blend["selectedWeights"] == {"regionalNeighborhoodByRegion": {
    "Northeast": 0.0, "Midwest": .15, "South": .15, "West": 0.0,
}}
assert all(
    item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0
    for item in (*production_blend["perRegionConfirmation"], *production_blend["perRegionFinalSignal"])
)
assert atlas["spatialTransferValidation"]["productionBlend"]["gate"]["passed"]
assert atlas["spatialTransferValidation"]["productionBlend"]["intervalCalibration"]["meanWidth90Reduction"] >= .04
assert atlas["spatialTransferValidation"]["productionBlend"]["intervalCalibration"]["selectedRegionalScales"]["West"] == {"scale80": 1.45, "scale90": 1.45}
subtype_atlas = health["evidence"]["cropSubtypeYieldAtlas"]
assert subtype_atlas["name"] == "USDA crop-subtype yield atlas v1"
assert subtype_atlas["records"] == 690 and subtype_atlas["crops"] == ["silage corn", "spring wheat"]
assert subtype_atlas["validation"]["gate"]["passed"]
assert subtype_atlas["validation"]["selectedNeighborhoods"]["silage corn"] == {"maxNeighbors": 5, "distancePower": 2.0, "historyPower": 1.0, "distanceOffsetKm": 5.0}
assert subtype_atlas["validation"]["selectedRecencyWeights"] == {"silage corn": .25, "spring wheat": .8}
assert subtype_atlas["predictionMethod"]["recencyWeightByCrop"] == {"silage corn": .25, "spring wheat": .8}
assert subtype_atlas["validation"]["selectedDisagreementAlphas"] == {"silage corn": 0.0, "spring wheat": 5.0}
assert subtype_atlas["validation"]["selectedCalibrationScopes"] == {"silage corn": "pooled", "spring wheat": "region-conditioned"}
expected_history_depth = {
    "silage corn": {"region": "Midwest", "beta": -.02},
    "spring wheat": {"region": "West", "beta": -.02},
}
assert subtype_atlas["validation"]["selectedHistoryDepth"] == expected_history_depth
assert subtype_atlas["spatialTransferValidation"]["selectedHistoryDepthByCrop"] == expected_history_depth
silage_validation = next(item for item in subtype_atlas["validation"]["perCrop"] if item["crop"] == "silage corn")
assert all(silage_validation["historyReliabilityComparison"][block]["spearmanGain"] > 0 for block in ("development", "stability", "final"))
assert silage_validation["temporalComparison"]["final"]["spearmanGain"] > 0
assert silage_validation["temporalComparison"]["final"]["maeReduction"] > 0
assert silage_validation["temporalComparison"]["finalSpearmanGainBootstrap95"][0] > 0
assert subtype_atlas["validation"]["selectedRegionalScales"]["spring wheat"]["West"] == {"scale80": 1.1, "scale90": 1.0}
assert subtype_atlas["validation"]["supportedRegionsByCrop"]["silage corn"] == ["Midwest", "Northeast"]
assert health["climateHistory"] == {"source": "NASA POWER Agroclimatology", "startYear": 2016, "endYear": 2025, "years": 10}
prediction = requests.post(f"{base}/predict", json=payload, timeout=30)
prediction.raise_for_status()
prediction_body = prediction.json()
assert prediction_body["observedYieldEvidence"]["county"] == "Fort Bend County"
assert prediction_body["observedYieldEvidence"]["yieldUnit"] == "bu/acre"
assert prediction_body["observedYieldEvidence"]["history"][0]["yieldPerAcre"] > 0
assert prediction_body["observedYieldEvidence"]["observedYieldPrior"]["intervalMethod"] == "local-regional-blend-conformal"
assert prediction_body["observedYieldEvidence"]["observedYieldPrior"]["distanceBucket"] == "25-50"
assert 1 <= prediction_body["observedYieldEvidence"]["observedYieldPrior"]["neighborCount"] <= 9
assert len(prediction_body["observedYieldEvidence"]["regionalNeighbors"]) == prediction_body["observedYieldEvidence"]["observedYieldPrior"]["neighborCount"] == 6
assert prediction_body["confidence"] == .8
assert prediction_body["expectedAbsoluteError"]["p80"] <= prediction_body["expectedAbsoluteError"]["p90"]
boundary = requests.post(f"{base}/predict", json={**payload, "climate": [{**item, "solarMjM2Day": 34} for item in climate]}, timeout=30)
boundary.raise_for_status()
assert boundary.json()["score"] == 0, "hard EcoCrop solar boundary was not enforced"
assert boundary.json()["expectedAbsoluteError"] == {"p80": 0.0, "p90": 0.0}
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
for crop, latitude, longitude, unit in (
    ("spring wheat", 46.8, -100.8, "bu/acre"),
    ("silage corn", 43.0, -89.0, "tons/acre"),
):
    response = requests.post(f"{base}/predict", json={**payload, "crop": crop, "latitude": latitude, "longitude": longitude}, timeout=30)
    response.raise_for_status()
    evidence = response.json()["observedYieldEvidence"]
    assert evidence["yieldUnit"] == unit and evidence["meanYieldPerAcre"] > 0
    expected_method = "region-conditioned-disagreement-scaled-spatial-conformal" if crop == "spring wheat" else "history-scaled-spatial-neighborhood-conformal"
    assert evidence["observedYieldPrior"]["intervalMethod"] == expected_method
    assert evidence["observedYieldPrior"]["neighborCount"] == 5
    assert abs(sum(item["weight"] for item in evidence["regionalNeighbors"]) - 1) < .0001
western_wheat = requests.post(f"{base}/predict", json={**payload, "crop": "spring wheat", "latitude": 43.451477, "longitude": -116.244376}, timeout=30)
western_wheat.raise_for_status()
western_evidence = western_wheat.json()["observedYieldEvidence"]
assert western_evidence["state"] == "ID"
assert western_evidence["observedYieldPrior"]["intervalMethod"] == "history-scaled-region-conditioned-disagreement-scaled-spatial-conformal"
assert western_evidence["observedYieldPrior"]["disagreementAlpha"] == 5.0
assert western_evidence["observedYieldPrior"]["calibrationRegion"] == "West"
assert western_evidence["observedYieldPrior"]["neighborDisagreement"] >= 0
western_prior = western_evidence["observedYieldPrior"]
assert western_prior["historyDepthRegion"] == "West"
assert western_prior["historyDepthBeta"] == -.02
western_group = next(item for item in subtype_atlas["spatialTransferValidation"]["groups"] if item["crop"] == "spring wheat" and item["region"] == "West" and item["historyBucket"] == western_prior["effectiveHistoryBucket"])
western_history_factor = math.exp(western_group["historyDepthBeta"]
    * (western_prior["effectiveHistoryCount"] - western_group["historyCenter"]))
assert western_prior["historyDepthFactor"] == round(western_history_factor, 6)
western_radius90 = (western_group["normalizedErrorP90"]
    * subtype_atlas["validation"]["selectedRegionalScales"]["spring wheat"]["West"]["scale90"]
    * (1 + western_group["disagreementAlpha"] * western_prior["neighborDisagreement"])
    * western_history_factor)
assert western_prior["interval90"] == [
    round(max(0, western_prior["expectedPercentile"] - western_radius90), 4),
    round(min(1, western_prior["expectedPercentile"] + western_radius90), 4),
]
unsupported_silage = requests.post(f"{base}/predict", json={**payload, "crop": "silage corn", "latitude": 43.451477, "longitude": -116.244376}, timeout=30)
unsupported_silage.raise_for_status()
assert unsupported_silage.json()["observedYieldEvidence"] is None
invalid = requests.post(f"{base}/predict", json={**payload, "climate": climate[:11]}, timeout=10)
assert invalid.status_code == 422
print(f'CropFit HTTP verified: API {health["apiVersion"]}, model v0.9.1, artifact identity, atlas v9 plus unit-safe subtype atlas, seasonal boundary ceiling, 2016-2025 climate window, USDA evidence, input bounds')
PY
