# USDA observed-prior crop expansion v2

Gate: Both the 2018–2025 forward test and locked 2023–2025 block need >=100 observations, Spearman >=0.50, grouped-bootstrap lower bound >0.30, and >=50% published-row coverage.

| Crop | Forward N | All-year ρ | Final N | Final ρ | Final 95% interval | Final MAE | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| beans (current excl chickpeas) | 81 | 0.318 | 44 | -0.019 | -0.405 to 0.331 | 0.276 | REJECT |
| beans (legacy incl chickpeas) | 57 | 0.779 | 0 | n/a | n/a | n/a | REJECT |
| dry peas | 162 | 0.578 | 48 | 0.530 | 0.195 to 0.741 | 0.190 | REJECT |
| durum wheat | 160 | 0.720 | 47 | 0.797 | 0.605 to 0.897 | 0.137 | REJECT |
| potato | 4 | 0.400 | 0 | n/a | n/a | n/a | REJECT |
| silage corn | 1,544 | 0.597 | 576 | 0.551 | 0.469 to 0.617 | 0.194 | ACCEPT |
| spring wheat | 1,023 | 0.779 | 257 | 0.762 | 0.670 to 0.830 | 0.138 | ACCEPT |
| sunflower | 135 | 0.272 | 37 | 0.354 | -0.108 to 0.690 | 0.230 | REJECT |
| sunflower (non-oil) | 1 | n/a | 0 | n/a | n/a | n/a | REJECT |

Accepted crops: **silage corn, spring wheat**.

## Data-definition guard

- USDA NASS changed the dry-edible-bean definition in 2019: the current category excludes chickpeas.
- Legacy and current bean definitions are evaluated separately and are never joined as one time series.
- Winter, non-durum spring, and durum wheat remain separate definitions; their percentiles are never pooled.
- Grain and silage corn, and oil and non-oil sunflower, remain separate definitions and units.
- Source: [USDA NASS Crop Production 2019 Summary](https://www.nass.usda.gov/Publications/Todays_Reports/reports/cropan20.pdf)

> Passing supports county-level regional ordering only, not parcel yield or purchase returns.
