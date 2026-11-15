# USDA county-prior trend development

Development gate: **PASS**.

The selected development candidate uses a **8-year** lookback and **30%** of a clipped county-rank trend correction.
Pooled Spearman delta: **+0.0009**; percentile-MAE delta: **-0.0006**.

| Crop | N | Rank delta | MAE delta |
|---|---:|---:|---:|
| corn | 4,219 | +0.0019 | -0.0010 |
| soybean | 3,705 | +0.0001 | -0.0006 |
| wheat | 2,438 | +0.0000 | +0.0000 |

Advance rule: At least one crop must enable; gated development pooled Spearman and MAE must improve; no crop or development year may regress either metric. Only then may fixed parameters advance to a separately committed confirmation/final protocol.

> Observed county-rank ordering only; not parcel yield, revenue, or property value.
