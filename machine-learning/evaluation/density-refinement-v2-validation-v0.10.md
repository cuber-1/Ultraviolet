# CropFit v0.10 density-refinement v2 validation

The 200-scenario/40-tree candidate was selected only after the 240/32 candidate failed shift confirmation. This report uses ten new grouped seeds and a new independent scenario-shift seed.

| Phase | Seed | v0.9.1 MAE | Candidate MAE | MAE gain | p90 gain | Active 80% | Active 90% |
|---|---:|---:|---:|---:|---:|---:|---:|
| confirmation | 20261220 | 0.01522 | 0.01332 | 12.48% | 14.29% | 79.9% | 89.9% |
| confirmation | 20261221 | 0.01521 | 0.01407 | 7.50% | 8.62% | 79.9% | 90.3% |
| confirmation | 20261222 | 0.01415 | 0.01354 | 4.31% | 0.45% | 80.8% | 90.4% |
| confirmation | 20261223 | 0.01580 | 0.01431 | 9.43% | 12.81% | 79.9% | 89.8% |
| confirmation | 20261224 | 0.01405 | 0.01276 | 9.18% | 10.08% | 81.8% | 90.8% |
| final | 20261225 | 0.01495 | 0.01441 | 3.61% | 5.64% | 80.6% | 89.3% |
| final | 20261226 | 0.01541 | 0.01366 | 11.36% | 6.67% | 80.7% | 90.1% |
| final | 20261227 | 0.01557 | 0.01438 | 7.64% | 9.50% | 79.4% | 88.6% |
| final | 20261228 | 0.01527 | 0.01378 | 9.76% | 7.29% | 81.5% | 91.2% |
| final | 20261229 | 0.01478 | 0.01317 | 10.89% | 9.53% | 82.6% | 91.4% |

Seed wins: **10/10**. Final-only gains are **8.65% MAE** and **7.73% p90**.

The candidate is **65.9 MB** (6.3% smaller) with **0.95x** latency.

## Independent shift

Fresh-seed gains are **10.72% raw MAE**, **11.49% raw p90**, **10.43% deployed MAE**, and **100.00% deployed p90**.

Active shifted coverage is **80.7% / 90.8%**.

Promotion gate: **PASS**.

> This validates mechanistic-teacher fidelity, not observed yield, revenue, or property value.
