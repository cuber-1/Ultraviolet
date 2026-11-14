# CropFit compact-estimator validation

An 80-tree Extra Trees candidate was tested as a smaller Mac artifact against the 120-tree v0.6 champion on seven fresh grouped crop-profile splits.

| Seed | MAE regression | p90 regression | 80% cov. | 90% cov. | Pass |
|---:|---:|---:|---:|---:|:---:|
| 20261220 | +3.82% | +6.05% | 80.8% | 90.6% | no |
| 20261221 | +4.97% | +5.64% | 79.4% | 89.8% | no |
| 20261222 | +4.12% | +7.87% | 80.2% | 90.1% | no |
| 20261223 | +4.49% | +4.64% | 80.7% | 90.3% | no |
| 20261224 | +3.89% | +4.43% | 80.7% | 90.0% | no |
| 20261225 | +3.17% | +6.55% | 79.8% | 89.6% | no |
| 20261226 | +4.39% | +6.36% | 80.3% | 90.3% | no |

Seed wins: **0/7**. Mean MAE regression: **+4.12%**; mean p90 regression: **+5.93%**.

The candidate serialized to **66.7%** of the champion, but failed the accuracy gate. Decision: **retain the 120-tree v0.6 champion**.

Calibration remained valid, but calibration alone cannot justify a less accurate scorer.
