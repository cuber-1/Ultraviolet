# USDA observed-prior crop expansion v1

Gate: Each crop needs >=100 forward observations, Spearman >=0.50, grouped-bootstrap lower bound >0.30, and >=50% published-row coverage.

| Crop | Published | Forward N | Coverage | Spearman | 95% interval | Percentile MAE | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| beans (current excl chickpeas) | 110 | 81 | 73.6% | 0.318 | 0.004 to 0.545 | 0.233 | REJECT |
| beans (legacy incl chickpeas) | 59 | 57 | 96.6% | 0.779 | 0.665 to 0.847 | 0.159 | REJECT |
| potato | 4 | 4 | 100.0% | 0.400 | -1.000 to 1.000 | 0.252 | REJECT |
| sunflower | 142 | 135 | 95.1% | 0.272 | 0.029 to 0.458 | 0.241 | REJECT |

Accepted crops: **none**.

## Data-definition guard

- USDA NASS changed the dry-edible-bean definition in 2019: the current category excludes chickpeas.
- Legacy and current bean definitions are evaluated separately and are never joined as one time series.
- Source: [USDA NASS Crop Production 2019 Summary](https://www.nass.usda.gov/Publications/Todays_Reports/reports/cropan20.pdf)

> Passing supports county-level regional ordering only, not parcel yield or purchase returns.
