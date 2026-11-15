# CropFit v0.8 interaction-feature validation

Two input-derived agroclimatic interactions let a 120-tree candidate represent the multiplicative EcoCrop structure more efficiently than the 200-tree v0.7 champion. This is mechanistic-teacher fidelity, not observed-yield accuracy.

| Phase | Seed | v0.7 MAE | v0.8 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 20261210 | 0.08399 | 0.01692 | 79.86% | 80.03% | 81.0% | 90.4% | 0.57x |
| development | 20261211 | 0.08791 | 0.01810 | 79.41% | 79.45% | 80.7% | 90.1% | 0.59x |
| development | 20261212 | 0.09076 | 0.01772 | 80.48% | 79.86% | 80.9% | 90.6% | 0.56x |
| confirmation | 20261213 | 0.08312 | 0.01754 | 78.90% | 79.68% | 80.3% | 90.5% | 0.57x |
| confirmation | 20261214 | 0.09303 | 0.01849 | 80.12% | 78.86% | 79.9% | 90.2% | 0.57x |
| final | 20261215 | 0.08816 | 0.01718 | 80.51% | 79.39% | 80.6% | 90.3% | 0.60x |
| final | 20261216 | 0.08040 | 0.01580 | 80.35% | 79.13% | 80.2% | 90.0% | 0.58x |
| final | 20261217 | 0.08523 | 0.01642 | 80.73% | 80.20% | 80.6% | 90.2% | 0.58x |
| final | 20261218 | 0.08955 | 0.01791 | 80.00% | 78.92% | 80.7% | 90.2% | 0.60x |
| final | 20261219 | 0.08823 | 0.01816 | 79.42% | 78.59% | 79.5% | 89.6% | 0.54x |

Locked-seed wins: **7/7**. Mean locked MAE improved **80.00%** and p90 improved **79.25%**.

Locked calibrated coverage was **80.2% / 90.1%**. The candidate is **72.5 MB** compressed with a **0.58x** latency ratio.

The two features contain no final suitability value: they separately combine temperature with water and pH with solar. The forest must still learn their joint response on crop profiles excluded from fitting.

Promotion gate: **PASS**.
