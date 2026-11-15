# CropFit density/capacity development screen

This development-only search tests whether more trees, denser fitting, Poisson splitting, or upper-quantile tree aggregation can improve v0.11 without reopening reserved seeds.

| Candidate | Mean MAE gain | Mean p90 gain | Seed screens | Size | Advance |
|---|---:|---:|---:|---:|---:|
| 200x48 | 5.14% | 3.37% | 2/3 | 77.4 MB | no |
| 220x40 | 4.62% | 5.57% | 2/3 | 70.5 MB | no |
| 240x40 | 9.32% | 13.26% | 2/3 | 76.5 MB | no |
| 240x40-q50 | -49.56% | -53.81% | 0/3 | 76.5 MB | no |
| 240x40-q55 | -58.57% | -63.36% | 0/3 | 76.5 MB | no |
| 240x40-q60 | -79.52% | -86.29% | 0/3 | 76.5 MB | no |
| 240x40-q65 | -110.45% | -119.58% | 0/3 | 76.5 MB | no |
| 260x36 | 8.49% | 10.08% | 1/3 | 75.0 MB | no |
| 280x34 | 9.13% | 10.32% | 2/3 | 76.2 MB | no |
| 300x32 | 11.65% | 14.05% | 2/3 | 76.7 MB | no |
| 300x32-q50 | -35.01% | -41.06% | 0/3 | 76.7 MB | no |
| 300x32-q55 | -46.12% | -55.02% | 0/3 | 76.7 MB | no |
| 300x32-q60 | -61.69% | -68.80% | 0/3 | 76.7 MB | no |
| 300x32-q65 | -90.06% | -101.78% | 0/3 | 76.7 MB | no |
| 200x40-poisson | -4.72% | -0.36% | 0/3 | 68.0 MB | no |
| 200x48-poisson | 0.42% | 5.74% | 0/3 | 81.6 MB | no |
| 240x40-poisson | 8.03% | 8.62% | 0/3 | 80.9 MB | no |

**No candidate advanced.** Capacity/density variants retained attractive averages but missed at least one deployed-tail screen. Poisson splitting produced severe underprediction outliers, and upper tree quantiles traded tail correction for large raw-error regressions.

> Development screening only; no confirmation, final, or shift seed was opened.

> This measures mechanistic-teacher fidelity, not observed yield, revenue, or property value.
