import type { IncomingMessage, ServerResponse } from 'node:http';

// Crop-suitability model client. See ml/CONTRACT.md for the wire format.
// When ML_MODEL_URL is unset or the model fails, predictions come from the
// built-in crop calendar and are labelled source "calendar-fallback".

export type MlCrop = { id: string; name: string; sunHours: number; tempMinC: number; tempMaxC: number; growMonths: number };
export type MlClimate = { temperatureC: number[]; solarMjM2Day: number[]; precipitationMmDay: number[] };
export type MlSite = {
  id: string;
  kind: 'roof' | 'region';
  lat: number;
  lon: number;
  climate: MlClimate | null;
  roof?: { roofAreaSqft: number | null; sharedAreaSqft: number | null; meanSunHours: number | null; obstructionCount: number; buildingHeightM: number | null } | null;
};
export type MlRequest = { crops: MlCrop[]; preferredMonth: number; targetAreaSqft: number; targetSunHours: number; sites: MlSite[] };
export type MlPrediction = {
  siteId: string;
  cropId: string;
  suitability: number;
  plantMonth: number | null;
  harvestMonth: number | null;
  confidence: number | null;
  expectedYield: { value: number; unit: string } | null;
  notes: string | null;
  source: 'ml' | 'calendar-fallback';
};
export type MlResponse = { model: { name: string; version: string | null; source: 'ml' | 'calendar-fallback'; error: string | null }; predictions: MlPrediction[] };

const modelUrl = () => process.env.ML_MODEL_URL?.trim().replace(/\/$/, '') || null;
const modelTimeoutMs = () => Number(process.env.ML_MODEL_TIMEOUT_MS) || 15_000;
const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const isMonth = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 0 && Number(value) <= 11;

export function mlModelStatus() {
  const url = modelUrl();
  return { configured: Boolean(url), url, fallback: 'calendar' };
}

/** Transparent crop-calendar estimate used when the trained model is unavailable. */
export function calendarPrediction(site: MlSite, crop: MlCrop, preferredMonth: number): MlPrediction {
  const temperatures = site.climate?.temperatureC ?? null;
  let plantMonth: number | null = null;
  let wait: number | null = null;
  if (temperatures) {
    const growable = temperatures.map((t) => t >= crop.tempMinC && t <= crop.tempMaxC);
    for (let offset = 0; offset < 12; offset += 1) {
      const start = (preferredMonth + offset) % 12;
      if (Array.from({ length: crop.growMonths }, (_, i) => growable[(start + i) % 12]).every(Boolean)) { plantMonth = start; wait = offset; break; }
    }
  }
  const climateFit = temperatures === null ? 0.5 : plantMonth === null ? 0 : 0.7 + 0.3 * (1 - wait! / 11);
  const solar = site.climate ? site.climate.solarMjM2Day.reduce((sum, value) => sum + value, 0) / 12 : null;
  const sunFit = site.roof?.meanSunHours != null
    ? clamp01(site.roof.meanSunHours / crop.sunHours)
    : solar !== null ? clamp01((solar - 12) / 10) : 0.5;
  return {
    siteId: site.id,
    cropId: crop.id,
    suitability: Number((0.6 * climateFit + 0.4 * sunFit).toFixed(3)),
    plantMonth,
    harvestMonth: plantMonth === null ? null : (plantMonth + crop.growMonths - 1) % 12,
    confidence: null,
    expectedYield: null,
    notes: temperatures === null ? 'No climate data; sunlight only.' : plantMonth === null ? 'No full growing season at this location.' : null,
    source: 'calendar-fallback',
  };
}

function calendarResponse(request: MlRequest, error: string | null): MlResponse {
  return {
    model: { name: 'crop-calendar', version: null, source: 'calendar-fallback', error },
    predictions: request.sites.flatMap((site) => request.crops.map((crop) => calendarPrediction(site, crop, request.preferredMonth))),
  };
}

function parsePrediction(value: unknown): Omit<MlPrediction, 'source'> | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as Record<string, unknown>;
  const suitability = Number(item.suitability);
  if (typeof item.siteId !== 'string' || typeof item.cropId !== 'string' || !Number.isFinite(suitability)) return null;
  const yieldValue = item.expectedYield as Record<string, unknown> | null | undefined;
  return {
    siteId: item.siteId,
    cropId: item.cropId,
    suitability: clamp01(suitability),
    plantMonth: isMonth(item.plantMonth) ? item.plantMonth : null,
    harvestMonth: isMonth(item.harvestMonth) ? item.harvestMonth : null,
    confidence: Number.isFinite(Number(item.confidence)) && item.confidence !== null ? clamp01(Number(item.confidence)) : null,
    expectedYield: yieldValue && Number.isFinite(Number(yieldValue.value)) && typeof yieldValue.unit === 'string' ? { value: Number(yieldValue.value), unit: yieldValue.unit } : null,
    notes: typeof item.notes === 'string' ? item.notes : null,
  };
}

/** Ask the trained model; fill any gaps (or everything, on failure) from the crop calendar. */
export async function predictCropSuitability(request: MlRequest): Promise<MlResponse> {
  const url = modelUrl();
  if (!url || !request.sites.length || !request.crops.length) return calendarResponse(request, url ? null : 'ML_MODEL_URL is not set.');
  try {
    const response = await fetch(`${url}/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(modelTimeoutMs()),
    });
    if (!response.ok) throw new Error(`Model returned HTTP ${response.status}.`);
    const payload = await response.json() as { model?: { name?: unknown; version?: unknown }; predictions?: unknown[] };
    const parsed = (payload.predictions ?? []).map(parsePrediction).filter((item): item is NonNullable<typeof item> => Boolean(item));
    if (!parsed.length) throw new Error('Model returned no usable predictions.');
    const byKey = new Map(parsed.map((item) => [`${item.siteId}::${item.cropId}`, item]));
    const predictions = request.sites.flatMap((site) => request.crops.map((crop): MlPrediction => {
      const hit = byKey.get(`${site.id}::${crop.id}`);
      return hit ? { ...hit, source: 'ml' } : calendarPrediction(site, crop, request.preferredMonth);
    }));
    return {
      model: { name: typeof payload.model?.name === 'string' ? payload.model.name : 'crop-model', version: typeof payload.model?.version === 'string' ? payload.model.version : null, source: 'ml', error: null },
      predictions,
    };
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : 'Model request failed.';
    console.warn(`Crop model unavailable, using crop calendar: ${message}`);
    return calendarResponse(request, message);
  }
}

/** Mean suitability per site across the requested crops. */
export function siteSuitability(response: MlResponse) {
  const totals = new Map<string, { sum: number; count: number }>();
  for (const item of response.predictions) {
    const entry = totals.get(item.siteId) ?? { sum: 0, count: 0 };
    entry.sum += item.suitability; entry.count += 1;
    totals.set(item.siteId, entry);
  }
  return new Map([...totals].map(([id, { sum, count }]) => [id, sum / count]));
}

/** Combined rank score: 60% how much of the target area gets the needed sun, 40% model suitability. */
export function combinedRoofScore(sharedAreaSqft: number | null, targetAreaSqft: number, suitability: number | null) {
  const areaFit = sharedAreaSqft === null ? 0 : clamp01(sharedAreaSqft / Math.max(1, targetAreaSqft));
  return 0.6 * areaFit + 0.4 * (suitability ?? 0.5);
}

async function readJson(req: IncomingMessage) {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>;
}

function isCrop(value: unknown): value is MlCrop {
  const item = value as MlCrop;
  return Boolean(item) && typeof item.id === 'string' && typeof item.name === 'string' && [item.sunHours, item.tempMinC, item.tempMaxC, item.growMonths].every(Number.isFinite);
}

/** POST /api/ml/predict: browser-facing proxy so the model URL stays server-side. */
export async function handleMlRoute(pathname: string, req: IncomingMessage, res: ServerResponse) {
  if (pathname === '/api/ml/status') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(mlModelStatus())); return true; }
  if (pathname !== '/api/ml/predict' || req.method !== 'POST') return false;
  const input = await readJson(req);
  const crops = (Array.isArray(input.crops) ? input.crops : []).filter(isCrop).slice(0, 8);
  const sites = (Array.isArray(input.sites) ? input.sites : []).filter((site): site is MlSite => Boolean(site) && typeof (site as MlSite).id === 'string' && Number.isFinite((site as MlSite).lat) && Number.isFinite((site as MlSite).lon)).slice(0, 40);
  res.setHeader('Content-Type', 'application/json');
  if (!crops.length || !sites.length) { res.statusCode = 400; res.end(JSON.stringify({ error: 'Send at least one crop and one site.' })); return true; }
  const result = await predictCropSuitability({
    crops, sites,
    preferredMonth: isMonth(input.preferredMonth) ? input.preferredMonth : new Date().getMonth(),
    targetAreaSqft: Number(input.targetAreaSqft) || 0,
    targetSunHours: Number(input.targetSunHours) || 6,
  });
  res.end(JSON.stringify(result));
  return true;
}
