#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${repo_root}/machine-learning/.venv/bin/python"
host="${CROPFIT_HOST:-127.0.0.1}"
port="${CROPFIT_PORT:-8100}"

if [[ ! -x "${python_bin}" ]]; then
  echo "CropFit is not installed. Run ./scripts/installCropFitModel.sh first." >&2
  exit 1
fi
if [[ ! -f "${repo_root}/machine-learning/artifacts/cropfit.joblib" ]]; then
  echo "CropFit model artifact is missing. Run ./scripts/installCropFitModel.sh again." >&2
  exit 1
fi
if [[ ! -f "${repo_root}/machine-learning/artifacts/cropfit.metadata.json" ]]; then
  echo "CropFit model metadata is missing. Run ./scripts/installCropFitModel.sh again." >&2
  exit 1
fi
if [[ ! -f "${repo_root}/machine-learning/data/raw/ecocrop.csv" ]]; then
  echo "CropFit EcoCrop profiles are missing. Run ./scripts/installCropFitModel.sh again." >&2
  exit 1
fi

export PYTHONPATH="${repo_root}/machine-learning"
exec "${python_bin}" -m uvicorn cropfit.trained_api:app --host "${host}" --port "${port}"
