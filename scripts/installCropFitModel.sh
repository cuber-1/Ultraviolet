#!/usr/bin/env bash
set -euo pipefail

release_url="https://github.com/cuber-1/Ultraviolet/releases/download/cropfit-v0.9.1/ultraviolet-cropfit-v0.9.1.tar.gz"
expected_sha256="31bbd8142cd1cf809d707e5b12d5deb1c3545a86fc6c81a35cc2eb5008bea67f"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_tmp="$(mktemp -d)"
trap 'rm -rf "${bundle_tmp}"' EXIT
python_bin="${CROPFIT_PYTHON:-python3}"

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "Python was not found. Install Python 3.10+ (for example: brew install python@3.12)." >&2
  exit 1
fi
if ! "${python_bin}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "CropFit requires Python 3.10 or newer. Set CROPFIT_PYTHON to a compatible interpreter." >&2
  exit 1
fi

echo "Downloading CropFit v0.9.1 model bundle..."
if command -v gh >/dev/null 2>&1; then
  gh release download cropfit-v0.9.1 --repo cuber-1/Ultraviolet --pattern ultraviolet-cropfit-v0.9.1.tar.gz --output "${bundle_tmp}/cropfit.tar.gz"
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  curl --fail --location --retry 3 --header "Authorization: Bearer ${GITHUB_TOKEN}" --output "${bundle_tmp}/cropfit.tar.gz" "${release_url}"
else
  echo "This repository is private. Install and authenticate GitHub CLI (brew install gh; gh auth login), or set GITHUB_TOKEN." >&2
  exit 1
fi

actual_sha256="$("${python_bin}" - "${bundle_tmp}/cropfit.tar.gz" <<'PY'
import hashlib
import pathlib
import sys

digest = hashlib.sha256()
with pathlib.Path(sys.argv[1]).open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
  echo "CropFit bundle checksum mismatch." >&2
  exit 1
fi

tar -xzf "${bundle_tmp}/cropfit.tar.gz" -C "${repo_root}"
"${python_bin}" -m venv "${repo_root}/machine-learning/.venv"
"${repo_root}/machine-learning/.venv/bin/python" -m pip install --upgrade pip
"${repo_root}/machine-learning/.venv/bin/python" -m pip install -r "${repo_root}/machine-learning/requirements-inference.txt"
PYTHONPATH="${repo_root}/machine-learning" "${repo_root}/machine-learning/.venv/bin/python" -m cropfit.verify_inference

echo "CropFit v0.9.1 is installed and verified."
echo "Local Mac fallback: npm run ml:serve:local"
echo "Tailscale/LAN service: npm run ml:serve"
