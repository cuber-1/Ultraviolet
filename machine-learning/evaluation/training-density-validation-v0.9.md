# CropFit v0.9 training-density validation

The candidate fits more generated scenarios per training crop but retains the exact v0.8 validation and test rows. It reduces the ensemble from 120 to 70 trees. This measures EcoCrop-teacher fidelity, not observed-yield accuracy.

| Phase | Seed | v0.8 MAE | v0.9 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 20261210 | 0.01692 | 0.01464 | 13.47% | 9.55% | 81.1% | 90.8% | 0.98x |
| development | 20261211 | 0.01810 | 0.01454 | 19.67% | 15.28% | 80.9% | 90.4% | 0.52x |
| development | 20261212 | 0.01772 | 0.01517 | 14.39% | 9.31% | 80.8% | 90.4% | 0.95x |
| confirmation | 20261213 | 0.01754 | 0.01465 | 16.48% | 17.22% | 80.3% | 90.8% | 1.12x |
| confirmation | 20261214 | 0.01849 | 0.01660 | 10.22% | 10.85% | 80.1% | 90.1% | 1.01x |
| final | 20261215 | 0.01718 | 0.01539 | 10.42% | 14.15% | 80.7% | 90.6% | 1.01x |
| final | 20261216 | 0.01580 | 0.01390 | 12.03% | 13.97% | 80.2% | 90.6% | 0.88x |
| final | 20261217 | 0.01642 | 0.01445 | 12.00% | 12.88% | 80.8% | 90.0% | 0.94x |
| final | 20261218 | 0.01791 | 0.01510 | 15.69% | 18.04% | 80.9% | 90.8% | 1.07x |
| final | 20261219 | 0.01816 | 0.01619 | 10.85% | 11.00% | 79.5% | 89.5% | 0.90x |

Locked-seed wins: **7/7**. Mean locked MAE improved **12.53%** and p90 improved **14.02%**.

Coverage was **80.4% / 90.3%**. The candidate is **70.4 MB** compressed with a **0.99x** latency ratio.

Promotion gate: **PASS**.
