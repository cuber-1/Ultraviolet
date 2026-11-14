# How Ultraviolet calls the crop model

> **CropFit is supported directly.** If the model's `GET /health` returns a
> `model` string containing "CropFit" (or `ML_MODEL_API=cropfit`), the app calls
> CropFit's own API instead: one `POST /predict` per site × crop with
> `{ crop, latitude, longitude, soilPh, irrigated }`, and maps `monthlyCurve`,
> `suitableMonths`, `growingDays`, `confidence`, and `limitingFactors` onto the
> prediction fields below. Crop ids map to EcoCrop names (greens→lettuce,
> tomatoes→tomato, peppers→pepper, strawberries→strawberry, cucumbers→cucumber,
> corn, soybeans→soybean, wheat, potatoes→potato); other crops use the calendar.
> Optional: `ML_SOIL_PH` (default 6.5), `ML_IRRIGATED` (default true).

Ultraviolet calls the crop-suitability model over HTTP from its server. Implement
these two endpoints and set `ML_MODEL_URL` (or `CROPFIT_URL`) in the app's `.env`.

```bash
ML_MODEL_URL="http://127.0.0.1:8765"   # no trailing slash
ML_MODEL_TIMEOUT_MS=15000              # optional, default 15000
```

Restart Vite after changing either value. If the variable is unset, the model is
unreachable, times out, or returns no usable predictions, the app falls back to a
crop calendar (NASA monthly temperature within each crop's range) and labels the
results "Crop calendar · model offline". The UI and Deep Agent keep working.

CropFit (this folder) is the production model; the generic contract below is
for any other model you want to plug in.

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
| `sites[].climate` | NASA POWER monthly climatology, 12 values each, January first. `null` if the lookup failed. |
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
