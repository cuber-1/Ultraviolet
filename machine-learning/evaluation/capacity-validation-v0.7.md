# CropFit v0.7 capacity validation

A 200-tree Extra Trees candidate was compared with the 120-tree v0.6 champion on identical grouped crop-profile splits. This measures EcoCrop-teacher fidelity, not observed yield accuracy.

| Phase | Seed | v0.6 MAE | v0.7 MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 20261210 | 0.08770 | 0.08399 | 4.23% | 3.54% | 80.8% | 90.5% | 1.64x |
| development | 20261211 | 0.09050 | 0.08791 | 2.86% | 2.96% | 80.2% | 89.8% | 1.88x |
| development | 20261212 | 0.09340 | 0.09076 | 2.83% | 5.14% | 80.3% | 90.2% | 1.73x |
| confirmation | 20261213 | 0.08551 | 0.08312 | 2.79% | 1.18% | 80.1% | 89.9% | 1.77x |
| confirmation | 20261214 | 0.09526 | 0.09303 | 2.34% | 1.43% | 79.8% | 89.9% | 1.72x |
| final | 20261215 | 0.09060 | 0.08816 | 2.69% | 4.20% | 80.0% | 89.9% | 1.63x |
| final | 20261216 | 0.08226 | 0.08040 | 2.26% | 3.19% | 79.9% | 90.0% | 1.76x |
| final | 20261217 | 0.08780 | 0.08523 | 2.93% | 1.15% | 80.4% | 90.3% | 1.61x |
| final | 20261218 | 0.09260 | 0.08955 | 3.29% | 5.84% | 80.2% | 89.9% | 2.00x |
| final | 20261219 | 0.09069 | 0.08823 | 2.71% | 2.69% | 79.1% | 89.6% | 1.00x |

Locked-seed wins: **7/7**. Mean locked MAE improved **2.72%** and p90 improved **2.81%**.

Locked mean calibrated coverage was **79.9% / 89.9%**. The candidate is **124.9 MB** compressed and its mean API-batch latency ratio is **1.64x**.

Promotion gate: **PASS**.

> Suitability remains an agroclimatic screening score. More trees improve approximation fidelity; they do not turn CropFit into a field-yield model.
