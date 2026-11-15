# How Ultraviolet calls the crop model

> **CropFit is supported directly.** If the model's `GET /health` returns a
> `model` string containing "CropFit" (or `ML_MODEL_API=cropfit`), the app calls
> CropFit's own API instead: one `POST /predict` per site × crop with
> `{ crop, latitude, longitude, soilPh, irrigated, climate, climateHistory }`, and maps `monthlyCurve`,
> `plantingReliability`, `suitableMonths`, `growingDays`, `confidence`, and `limitingFactors` onto the
> prediction fields below. Crop ids map to EcoCrop names (greens→lettuce,
> herbs→basil, tomatoes→tomato, peppers→pepper, strawberries→strawberry,
> kale→kale, beans→common bean, cucumbers→cucumber, corn, soybeans→soybean,
> wheat, potatoes→potato, melons→rock melon, onions→onion,
> sunflowers→sunflower). Microgreens use lettuce only in resilient mode and
> remain excluded in strict mode.
> Optional: `ML_SOIL_PH` (default 6.5), `ML_IRRIGATED` (default true).

For grain corn, soybean, winter wheat, silage corn, and non-durum spring wheat,
CropFit API v0.18.0 also returns optional
`observedYieldEvidence` from nearby USDA reporting counties within 100 km.
Atlas v9 includes 2010–2025 history plus a calibrated observed-yield percentile
prior with 80% and 90% uncertainty intervals. The prior blends 80% exponential
recency weighting (three-year half-life) with 20% of the stable long-history
mean. For regional ranking it adds 15% from up to eight surrounding counties
in the Midwest and South, where both development rank and MAE improved; the
Northeast and West retain 100% of the local prior. Returned intervals use
production-blend errors from 2011–2017, conditional on crop and effective
history depth, then selects the smallest regional safety scales that meet
nominal coverage in both 2018–2020 and 2021–2022. This preserves 84.4% / 92.9%
later coverage while narrowing the mean 90% band 4.3% relative to transfer
radii. It does not modify the underlying
EcoCrop suitability and is not a parcel yield forecast. Exact `spring wheat`
and `silage corn` requests use a separate 690-record subtype atlas. A
development-only search selected five inverse-distance neighbors, then passed
leave-one-county-out stability and locked 2023–2025 gates for both crops.
Silage corn additionally weights neighbors by their history counts; spring
wheat remains distance-only because development selection did not support the
extra weighting.
Silage uses 25% exponential recency plus 75% long-history mean after that blend
cleared a +0.005 development-rank floor and improved rank and MAE again in
stability years. Spring wheat retains the generic 80% recency blend.
Spring-wheat uncertainty expands with disagreement among its five neighbors;
the scaling parameter is retained only after clearing a 1% development-width
reduction floor and stability coverage gates. Silage uncertainty remains
disagreement-neutral because it did not clear that floor.
Spring wheat also uses region-conditioned pre-2018 conformal groups only after
every region/history cell reaches 50 errors, the groups clear a separate 1%
development-width floor, and they preserve stability coverage.
Silage retains pooled calibration because its regional candidate is wider.
Within each coarse history bucket, a development-selected continuous factor
narrows intervals when the contributing counties provide deeper evidence. It
uses β=-0.02 for Western spring wheat and Midwest silage only; both candidates
cleared a 1% development-width floor and all locked pooled and regional gates.
`observedYieldPrior.calibrationRegion` reports the exact group used (`Midwest`,
`West`, or `all`), and returned interval endpoints are reconstructed from the
reported expected percentile, neighbor disagreement, effective history count,
`historyDepthBeta`, and `historyCenter` without hidden precision.
Its region-specific interval multipliers were selected on development and
stability years before the final block was opened. Only crop-region pairs with
at least 50 examples in all three blocks are published. Yield history carries
explicit `bu/acre` or `tons/acre` units. Generic `corn` and `wheat` retain their
original atlas-v9 definitions.
Nearest-county retrieval uses a cached exact haversine spatial index; it returns
the same county as brute force while avoiding a full atlas scan per request.
Caller-supplied climate accepts 12 or 24 ordered monthly records and at most 20
12-month history years. Invalid shapes, non-finite coordinates, geographic or
soil ranges, and non-boolean irrigation values are rejected inside the
predictor as well as at the HTTP boundary. Invalid caller input returns HTTP
422. `/health` exposes the full artifact SHA-256 and incorporates its prefix in
the service revision.
The Ultraviolet server caches successful CropFit calls for one hour using a
SHA-256 key over the complete request (including climate, soil, irrigation,
coordinates, model URL, API version, and training run) and caps the LRU at
2,048 entries. Each browser prediction checks `/health` once; an API deployment
or retrained artifact therefore invalidates prior entries without a web-server
restart. If health is transiently unavailable, predictions proceed uncached.

For `kind: "region"` results, the Ultraviolet client uses that observed prior
to rank corn, soybean, and wheat locations while retaining CropFit suitability
for planting timing and unsupported crops. The validated blend was not used;
urban roof ranking remains based on sunlit area and agroclimatic suitability.

The app supplies a 2016–2025 NASA POWER monthly history. CropFit scores every
planting month in every year and returns p10/median/p90 suitability plus the
fraction of years scoring at least 55. `bestReliablePlantingMonth` maximizes the
historical downside (p10) before median fit. If the caller omits climate data,
the standalone CropFit service fetches the same history itself, so Mac-only
inference returns the same fields when the Spark is offline. Growing cycles
crossing December continue into the following historical year; the final 2025
start year uses the ten-year baseline for its 2026 continuation.

Ultraviolet calls the crop-suitability model over HTTP from its server. Implement
these two endpoints and set `ML_MODEL_URL` (or `CROPFIT_URL`) in the app's `.env`.

```bash
ML_MODEL_URL="http://127.0.0.1:8765"   # no trailing slash
ML_MODEL_FALLBACK_URL="https://backup.example.com" # optional second model
ML_MODEL_TIMEOUT_MS=15000              # optional, default 15000
```

Restart Vite after changing these values. If the primary model fails, the app
tries `ML_MODEL_FALLBACK_URL`. If neither model answers, it falls back to a crop
calendar (NASA monthly temperature within each crop's range) and labels the
results "Crop calendar · model offline". The UI and Deep Agent keep working.
Failed health probes are not cached, so a recovered primary is redetected as
CropFit on the next request rather than receiving the generic API payload.

CropFit API v0.18.0 with the v0.10.0 production model artifact is the supported
runtime; the generic contract below is for any other model you want to plug in.

## `GET /health`

Return `200` with any JSON body, for example `{"ok": true}`.

## `POST /predict`

### Request

```json
{
  "crops": [
    { "id": "tomatoes", "name": "Tomatoes", "sunHours": 8, "tempMinC": 16, "tempMaxC": 30, "growMonths": 3 }
  ],
  "preferredMonth": 3,
  "targetAreaSqft": 5000,
  "targetSunHours": 8,
  "sites": [
    {
      "id": "29.684712,-95.347183",
      "kind": "roof",
      "lat": 29.684712,
      "lon": -95.347183,
      "climate": {
        "temperatureC": [10.3, 12.5, 16.5, 20.4, 24.6, 28.0, 28.5, 29.0, 26.2, 21.4, 15.9, 11.7],
        "solarMjM2Day": [10.5, 12.0, 16.1, 19.1, 21.6, 22.7, 22.0, 21.1, 18.1, 15.9, 12.0, 9.5],
        "precipitationMmDay": [2.9, 2.6, 2.9, 2.8, 3.9, 4.8, 3.4, 3.7, 3.9, 3.8, 2.9, 3.2]
      },
      "roof": {
        "roofAreaSqft": 202358,
        "sharedAreaSqft": 8510,
        "meanSunHours": 13.1,
        "obstructionCount": 4,
        "buildingHeightM": 9.2
      }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `crops[]` | The user's crops (1–6). `sunHours` is daily direct sun needed; `tempMinC`/`tempMaxC` the growing range for monthly mean temperature; `growMonths` the season length. |
| `preferredMonth` | Month the user wants to start, `0` = January … `11` = December. |
| `targetAreaSqft` | Growing area the user needs. Rural sites send the land size. |
| `targetSunHours` | The most demanding crop's daily sun need. |
| `sites[].kind` | `"roof"` for urban rooftops, `"region"` for rural farming towns. |
| `sites[].climate` | NASA POWER 2016–2025 monthly mean, 12 values each, January first. `null` if the lookup failed. |
| `sites[].climate.history` | Ten annual monthly series (2016–2025), used for planting reliability and p10–p90 bands. |
| `sites[].climate.temperatureC` | Monthly mean air temperature at 2 m, °C. |
| `sites[].climate.solarMjM2Day` | Monthly mean all-sky surface shortwave, MJ/m²/day. |
| `sites[].climate.precipitationMmDay` | Monthly mean precipitation, mm/day. |
| `sites[].roof` | Roofs only (`null` for regions). Measured from Vexcel geometry and the app's sun simulator. |
| `roof.sharedAreaSqft` | Roof area that gets at least `targetSunHours` on every simulated date. `null` if geometry was missing. |
| `roof.meanSunHours` | Mean daily direct-sun hours across the roof, averaged over the simulated dates. |
| `roof.obstructionCount` | Raised features (HVAC, parapets) found on the roof. |
| `roof.buildingHeightM` | Roof height above ground, metres. |

### Response

```json
{
  "model": { "name": "crop-xgb", "version": "2026-11-14" },
  "predictions": [
    {
      "siteId": "29.684712,-95.347183",
      "cropId": "tomatoes",
      "suitability": 0.82,
      "plantMonth": 3,
      "harvestMonth": 5,
      "confidence": 0.7,
      "expectedYield": { "value": 4.1, "unit": "lb/ft²/season" },
      "notes": "Hot July may stress fruit set."
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `siteId`, `cropId` | yes | Echo the ids from the request. Return one prediction per site × crop. |
| `suitability` | yes | `0`–`1`. How well the crop suits the site. |
| `plantMonth`, `harvestMonth` | no | `0`–`11`, or `null` when no season works. Shown as the planting window. |
| `confidence` | no | `0`–`1`. |
| `expectedYield` | no | `{ value, unit }`. |
| `notes` | no | One short sentence shown on hover. |

Missing site × crop pairs are filled from the crop calendar. Values outside the
ranges are clamped; malformed entries are dropped.

## How the app uses the predictions

- **Deep Agent (urban):** tool `predict_crop_suitability` runs after the
  sunlight simulation. Roofs are ranked by
  `0.6 × min(1, sharedAreaSqft ÷ targetAreaSqft) + 0.4 × mean suitability`.
  The server scores any roof the agent skipped, so every roof has a score.
- **Rural:** `POST /api/ml/predict` (server proxy) scores each town. When the
  model answers, a town's fit is its mean suitability and planting windows come
  from the model.
- **Status:** `GET /api/ml/status` and `GET /api/vexcel/status` (`ml` field) show
  whether `ML_MODEL_URL` is set.

## Try it

```bash
npm run ml:serve                     # CropFit on 0.0.0.0:8100
curl -s localhost:8100/health
```

Or point at the DGX Spark over Tailscale: `ML_MODEL_URL=http://100.119.73.13:8100`.
