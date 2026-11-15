from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


EXPECTED_MEMBERS = {
    "machine-learning/artifacts/cropfit.joblib",
    "machine-learning/artifacts/cropfit.metadata.json",
    "machine-learning/data/raw/ecocrop.csv",
}


def validate_bundle(path: Path) -> None:
    with tarfile.open(path, "r:gz") as bundle:
        members = bundle.getmembers()
    names = {member.name for member in members}
    if len(members) != len(EXPECTED_MEMBERS):
        raise ValueError("CropFit bundle contains duplicate or unexpected members.")
    if names != EXPECTED_MEMBERS:
        raise ValueError("CropFit bundle member paths do not match the release contract.")
    if not all(member.isfile() for member in members):
        raise ValueError("CropFit bundle members must be regular files.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        validate_bundle(args.archive)
    except (OSError, tarfile.TarError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
