# CropFit v0.6 estimator validation

Extra Trees and the production Random Forest use identical 23-feature inputs, 120 trees, generated scenarios, and grouped crop-profile splits. This measures EcoCrop-teacher fidelity, not observed yield accuracy.

| Phase | Seed | RF MAE | Extra Trees MAE | MAE gain | p90 gain | 80% cov. | 90% cov. | Latency ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 20261210 | 0.1517 | 0.0877 | 42.2% | 47.4% | 80.5% | 90.3% | 1.86× |
| development | 20261211 | 0.1535 | 0.0905 | 41.0% | 46.2% | 80.2% | 90.1% | 1.03× |
| development | 20261212 | 0.1627 | 0.0934 | 42.6% | 47.2% | 80.3% | 90.2% | 0.90× |
| confirmation | 20261213 | 0.1500 | 0.0855 | 43.0% | 46.9% | 80.2% | 89.9% | 1.10× |
| confirmation | 20261214 | 0.1627 | 0.0953 | 41.4% | 49.2% | 79.7% | 90.2% | 0.99× |
| final | 20261215 | 0.1599 | 0.0906 | 43.4% | 49.1% | 80.3% | 90.2% | 0.62× |
| final | 20261216 | 0.1473 | 0.0823 | 44.1% | 48.5% | 79.9% | 90.1% | 0.97× |
| final | 20261217 | 0.1539 | 0.0878 | 43.0% | 47.9% | 80.3% | 90.4% | 1.00× |
| final | 20261218 | 0.1609 | 0.0926 | 42.5% | 45.3% | 80.2% | 90.0% | 1.06× |
| final | 20261219 | 0.1593 | 0.0907 | 43.1% | 47.1% | 79.1% | 89.8% | 1.59× |

Locked-seed wins: **7/7**. On the five final seeds, mean MAE improved **43.2%** and p90 improved **47.6%**.

Locked mean calibrated coverage was **80.0% / 90.1%**. Mean API-sized batch latency was **1.05×** the Random Forest.

Promotion gate: **PASS**.

> Suitability remains an agroclimatic screening score. This estimator change does not make it a yield forecast or property recommendation.
