from __future__ import annotations

import argparse
import json
from pathlib import Path

from .feature_compaction_validation import evaluate, markdown, plot


CONFIRMATION_SEEDS = list(range(20270130, 20270135))
FINAL_SEEDS = list(range(20270135, 20270140))
SHIFT_SEED = 20270140


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    parser.add_argument("--json", type=Path, default=root / "evaluation/feature-compaction-v2-validation-v0.11.json")
    parser.add_argument("--markdown", type=Path, default=root / "evaluation/feature-compaction-v2-validation-v0.11.md")
    parser.add_argument("--plot", type=Path, default=root / "evaluation/feature-compaction-v2-validation-v0.11.png")
    args = parser.parse_args()
    report = evaluate(
        args.profiles,
        confirmation_seeds=CONFIRMATION_SEEDS,
        final_seeds=FINAL_SEEDS,
        shift_seed=SHIFT_SEED,
        gate_global_coverage=False,
        validation_name="CropFit compact-feature v2 validation v0.11 candidate",
    )
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    plot(report, args.plot)
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["gate"], indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit("Compact-feature v2 promotion gate did not pass")


if __name__ == "__main__":
    main()
