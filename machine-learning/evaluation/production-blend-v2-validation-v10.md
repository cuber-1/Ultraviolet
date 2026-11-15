# USDA observed-prior crop-specific blend validation

Select per-crop weights on 2018-2020, enable crop-region probes only when rank and MAE both improve there, veto each crop unless 2021-2022 rank and MAE both improve, then require positive locked pooled rank/MAE gains with grouped-bootstrap rank lower >0; no crop, year, or region may regress. Recalibrated intervals must retain all v9 coverage gates and mean 90% width within 0.002 of v9.

Only **wheat** survives the stability veto. Corn and soybean retain their exact v9 policy.

On 8,881 locked 2023–2025 county-years, Spearman changes from **0.83764** to **0.83786** and percentile MAE from **0.12039** to **0.12034**. The grouped-bootstrap rank-gain interval is **+0.000128 to +0.000315**.

Wheat gains **+0.00103** Spearman and reduces MAE by **0.00033**.

Recalibrated intervals cover **84.5% / 93.0%** with mean 90% width **0.5113**.

Promotion gate: **PASS**.

> Observed county-rank evidence; not parcel yield, revenue, or property value.
