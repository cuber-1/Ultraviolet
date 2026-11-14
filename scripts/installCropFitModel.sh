#!/usr/bin/env bash
set -euo pipefail

release_url="https://github.com/cuber-1/Ultraviolet/releases/download/cropfit-v0.4/ultraviolet-cropfit-v0.4.tar.gz"
expected_sha256="9b15bfbe3a0641add1bace244ad17aa51aa544f9bd80cf344420973e6ddcf671"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_tmp="$(mktemp -d)"
trap 'rm -rf "${bundle_tmp}"' EXIT

echo "Downloading CropFit v0.4 model bundle..."
if command -v gh >/dev/null 2>&1; then
  gh release download cropfit-v0.4 --repo cuber-1/Ultraviolet --pattern ultraviolet-cropfit-v0.4.tar.gz --output "${bundle_tmp}/cropfit.tar.gz"
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  curl --fail --location --retry 3 --header "Authorization: Bearer ${GITHUB_TOKEN}" --output "${bundle_tmp}/cropfit.tar.gz" "${release_url}"
else
  echo "This repository is private. Install and authenticate GitHub CLI (brew install gh; gh auth login), or set GITHUB_TOKEN." >&2
  exit 1
fi

actual_sha256="$(python3 - "${bundle_tmp}/cropfit.tar.gz" <<'PY'
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
python3 -m venv "${repo_root}/machine-learning/.venv"
"${repo_root}/machine-learning/.venv/bin/python" -m pip install -r "${repo_root}/machine-learning/requirements-inference.txt"

echo "CropFit v0.4 is installed. Start it with: npm run ml:serve"
