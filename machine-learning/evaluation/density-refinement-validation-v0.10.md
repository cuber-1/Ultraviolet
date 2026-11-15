# CropFit v0.10 density-refinement validation

The candidate doubles fitting-only scenario density while reducing tree count. Validation and held-out crop profiles and rows remain identical. This measures EcoCrop-teacher fidelity, not observed yield.

| Phase | Seed | v0.9.1 MAE | Candidate MAE | MAE gain | p90 gain | Active 80% | Active 90% | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 20261210 | 0.01464 | 0.01368 | 6.56% | 6.32% | 81.4% | 90.6% | 0.97x |
| development | 20261211 | 0.01454 | 0.01334 | 8.25% | 9.89% | 80.6% | 89.7% | 0.97x |
| development | 20261212 | 0.01517 | 0.01362 | 10.22% | 15.35% | 80.4% | 91.0% | 1.03x |
| confirmation | 20261213 | 0.01465 | 0.01264 | 13.72% | 14.65% | 81.0% | 91.4% | 1.02x |
| confirmation | 20261214 | 0.01660 | 0.01452 | 12.53% | 7.62% | 80.9% | 90.1% | 0.95x |
| final | 20261215 | 0.01539 | 0.01376 | 10.59% | 9.25% | 80.6% | 90.7% | 0.97x |
| final | 20261216 | 0.01390 | 0.01260 | 9.35% | 10.74% | 80.6% | 91.0% | 1.07x |
| final | 20261217 | 0.01445 | 0.01252 | 13.36% | 14.53% | 81.1% | 91.3% | 0.99x |
| final | 20261218 | 0.01510 | 0.01424 | 5.70% | 5.11% | 81.7% | 91.0% | 1.00x |
| final | 20261219 | 0.01619 | 0.01440 | 11.06% | 10.32% | 79.6% | 90.5% | 1.10x |

Locked-seed wins: **7/7**. Mean locked MAE improved **10.90%** and p90 improved **10.32%**.

Final-only mean gains were **10.01% MAE** and **9.99% p90**. Active coverage was **80.8% / 90.9%**.

The candidate is **63.7 MB**, **9.5% smaller**, with a **1.01x** latency ratio.

Promotion gate: **PASS**.

> Suitability remains an agroclimatic screening score, not a yield forecast or property recommendation.
