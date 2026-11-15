# USDA county-prior crop-gated trend validation

Promotion gate: **NOT PASSED**.

The candidate was fixed before confirmation and final years were opened: 30% of a clipped eight-year county-rank trend for corn and soybean, with wheat exactly unchanged.

| Phase | N | Rank delta | MAE delta |
|---|---:|---:|---:|
| confirmation | 7,338 | -0.0010 | +0.0002 |
| final | 8,889 | -0.0009 | +0.0001 |

Final grouped-bootstrap 95% rank-delta interval: **-0.0013 to -0.0005**.

| Crop | N | Rank delta | MAE delta |
|---|---:|---:|---:|
| corn | 3,889 | -0.0013 | +0.0002 |
| soybean | 3,454 | -0.0011 | +0.0000 |
| wheat | 1,546 | +0.0000 | +0.0000 |

Gate rule: Confirmation and final pooled rank and MAE must improve; every crop and year must be non-regressing in both metrics; enabled crops must strictly improve both; wheat must remain exact; final grouped-bootstrap rank-delta lower bound must exceed zero.

> Observed county-rank ordering only; not parcel yield, revenue, or property value.
