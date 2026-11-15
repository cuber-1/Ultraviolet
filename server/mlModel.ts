import type { IncomingMessage, ServerResponse } from 'node:http';
import { createHash } from 'node:crypto';

// Crop-suitability model client. See machine-learning/INTEGRATION.md for the wire format.
// Failover order: ML_MODEL_URL -> ML_MODEL_FALLBACK_URL -> built-in calendar.
// Calendar predictions are labelled source "calendar-fallback".

export type MlCrop = { id: string; name: string; sunHours: number; tempMinC: number; tempMaxC: number; growMonths: number };
export type MlClimateYear = { year: number; temperatureC: number[]; solarMjM2Day: number[]; precipitationMmDay: number[] };
export type MlClimate = { temperatureC: number[]; solarMjM2Day: number[]; precipitationMmDay: number[]; history?: MlClimateYear[] };
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
  /** Full model detail when the model provides it (CropFit). Month indexes are 0-11. */
  curve?: Array<{ month: number; score: number; uncertainty: number | null; errorP80: number | null; errorP90: number | null; historicalP10: number | null; historicalMedian: number | null; historicalP90: number | null; reliability: number | null; components: Record<string, number> | null }>;
  suitableMonths?: number[];
  growingDays?: { min: number; max: number } | null;
  limitingFactors?: Array<{ factor: string; score: number }>;
  profile?: { scientificName: string | null; tempOptC: [number, number] | null; rainOptMm: [number, number] | null; phOpt: [number, number] | null } | null;
  evidenceGrade?: string | null;
  plantingReliability?: { years: number; successRate: number; p10Score: number; medianScore: number; p90Score: number; threshold: number } | null;
  observedYieldEvidence?: { county: string; state: string; distanceKm: number; years: number[]; observations: number; meanPercentile: number; p10Percentile: number; p90Percentile: number; meanYieldBushelsPerAcre: number; observedYieldPrior?: { expectedPercentile: number; interval80: [number, number]; interval90: [number, number]; historyBucket: string; calibrationExamples: number }; history: Array<{ year: number; yieldBushelsPerAcre: number; percentile: number }>; evidenceGrade: string; source: string; disclaimer: string } | null;
};
export type MlResponse = { model: { name: string; version: string | null; source: 'ml' | 'calendar-fallback'; error: string | null }; predictions: MlPrediction[] };

const cleanUrl = (value: string | undefined) => value?.trim().replace(/\/$/, '') || null;
// Primary model: ML_MODEL_URL, or CROPFIT_URL (docker compose / npm run ml:serve).
const explicitModelUrl = () => cleanUrl(process.env.ML_MODEL_URL || process.env.CROPFIT_URL);
const fallbackModelUrl = () => cleanUrl(process.env.ML_MODEL_FALLBACK_URL);
const modelUrls = () => [...new Set([explicitModelUrl(), fallbackModelUrl()].filter((url): url is string => Boolean(url)))];
/** Base URL for raw CropFit proxies; defaults to the local `npm run ml:serve` port. */
export const modelBaseUrl = () => explicitModelUrl() ?? 'http://127.0.0.1:8100';
const modelTimeoutMs = () => Number(process.env.ML_MODEL_TIMEOUT_MS) || 15_000;
const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const isMonth = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 0 && Number(value) <= 11;
const modelIdentity = (value: string) => { const match = value.match(/^(.*)\s+(v\d+(?:\.\d+)*)$/i); return match ? { name: match[1], version: match[2] } : { name: value }; };

/** ML_STRICT=1: never substitute the crop calendar. Unsupported crops get no prediction; model failures surface as errors. */
export const mlStrict = () => ['1', 'true', 'yes'].includes(String(process.env.ML_STRICT ?? '').toLowerCase());

export function mlModelStatus() {
  const url = explicitModelUrl();
  const backupUrl = fallbackModelUrl();
  return { configured: Boolean(url || backupUrl), url, backupUrl, fallback: mlStrict() ? (backupUrl ? 'model' : 'none') : backupUrl ? 'model-then-calendar' : 'calendar', strict: mlStrict() };
}

/** Ping the model's /health endpoint and time it. */
export async function mlModelHealth() {
  const urls = modelUrls();
  if (!urls.length) return { configured: false, online: false, latencyMs: null, model: null, error: 'No model URL is set.' };
  const errors: string[] = [];
  for (const [index, url] of urls.entries()) {
    const started = Date.now();
    try {
      const response = await fetch(`${url}/health`, { signal: AbortSignal.timeout(4_000) });
      const payload = await response.json().catch(() => ({})) as { apiVersion?: string; revision?: string; model?: string | { name?: string; version?: string }; metrics?: Record<string, number>; evidence?: unknown };
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const model = typeof payload.model === 'string' ? modelIdentity(payload.model) : payload.model ?? null;
      return { configured: true, online: true, latencyMs: Date.now() - started, model, apiVersion: payload.apiVersion ?? null, revision: payload.revision ?? null, metrics: payload.metrics ?? null, evidence: payload.evidence ?? null, error: null, url, role: index === 0 ? 'primary' : 'backup', primaryError: index ? errors[0] : null };
    } catch (reason) {
      errors.push(`${index === 0 ? 'primary' : 'backup'}: ${reason instanceof Error ? reason.message : 'unreachable'}`);
    }
  }
  return { configured: true, online: false, latencyMs: null, model: null, error: errors.join('; ') };
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

// ---- CropFit adapter -------------------------------------------------------
// CropFit (EcoCrop surrogate) takes one crop per call:
//   POST /predict { crop, latitude, longitude, soilPh, irrigated }
//   -> { score 0-100, bestPlantingMonth, suitableMonths[], confidence, growingDays{min,max},
//        limitingFactors[{factor, score}], monthlyCurve[{month, score, uncertainty, temperatureC}] }
// Detected from GET /health ("model": "CropFit ...") or forced with ML_MODEL_API=cropfit.

const CROPFIT_NAMES: Record<string, string> = {
  greens: 'lettuce', tomatoes: 'tomato', peppers: 'pepper', strawberries: 'strawberry', cucumbers: 'cucumber',
  corn: 'corn', soybeans: 'soybean', wheat: 'wheat', potatoes: 'potato', microgreens: 'lettuce',
  herbs: 'basil', kale: 'kale', beans: 'common bean', melons: 'melon', onions: 'onion', sunflowers: 'sunflower',
};
const CROPFIT_REPRESENTATIVES: Record<string, string> = {
  greens: 'lettuce', herbs: 'basil', microgreens: 'lettuce', kale: 'kale', beans: 'common bean',
  cucumbers: 'cucumber', melons: 'rock melon',
};
/** Crops the model scores natively (microgreens borrows lettuce, so it is excluded in strict mode). */
export const cropFitCropIds = () => Object.keys(CROPFIT_NAMES).filter((id) => !(mlStrict() && id === 'microgreens'));
export const cropFitModelName = (cropId: string) => CROPFIT_NAMES[cropId] ?? null;

export async function mlCapabilities() {
  const url = explicitModelUrl() ?? fallbackModelUrl();
  return { strict: mlStrict(), configured: Boolean(url), api: url ? await modelApiKind(url) : null, supportedCrops: url && await modelApiKind(url) === 'cropfit' ? cropFitCropIds() : null };
}
const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const monthIndex = (value: unknown) => {
  if (Number.isInteger(value)) { const n = Number(value); return n >= 1 && n <= 12 ? n - 1 : n >= 0 && n <= 11 ? n : null; }
  const key = String(value ?? '').trim().slice(0, 3).toLowerCase();
  const index = MONTH_KEYS.indexOf(key);
  return index >= 0 ? index : null;
};
type CropFitResult = {
  score?: number; bestPlantingMonth?: unknown; bestReliablePlantingMonth?: unknown; suitableMonths?: unknown[]; confidence?: number;
  growingDays?: { min?: number; max?: number }; limitingFactors?: Array<{ factor?: string; score?: number }>;
  plantingReliability?: { years?: number; successRate?: number; p10Score?: number; medianScore?: number; p90Score?: number; threshold?: number } | null;
  monthlyCurve?: Array<{ month?: unknown; score?: number; uncertainty?: number; expectedAbsoluteErrorP80?: number; expectedAbsoluteErrorP90?: number; historicalP10?: number; historicalMedian?: number; historicalP90?: number; reliability?: number; components?: Record<string, number> }>;
  profile?: Record<string, unknown>; evidenceGrade?: string;
  observedYieldEvidence?: { county?: unknown; state?: unknown; distanceKm?: number; years?: unknown[]; observations?: number; meanPercentile?: number; p10Percentile?: number; p90Percentile?: number; meanYieldBushelsPerAcre?: number; observedYieldPrior?: { expectedPercentile?: number; interval80?: unknown[]; interval90?: unknown[]; historyBucket?: unknown; calibrationExamples?: number }; history?: Array<{ year?: number; yieldBushelsPerAcre?: number; percentile?: number }>; evidenceGrade?: unknown; source?: unknown; disclaimer?: unknown } | null;
};
const apiKindCache = new Map<string, { kind: 'contract' | 'cropfit'; expires: number }>();
export class BoundedExpiringCache<T> {
  private readonly entries = new Map<string, { expires: number; value: T }>();
  readonly maxEntries: number;
  constructor(maxEntries: number) {
    if (!Number.isInteger(maxEntries) || maxEntries < 1) throw new Error('Cache capacity must be a positive integer.');
    this.maxEntries = maxEntries;
  }
  get size() { return this.entries.size; }
  get(key: string, now = Date.now()) {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    if (entry.expires <= now) { this.entries.delete(key); return undefined; }
    this.entries.delete(key); this.entries.set(key, entry);
    return entry.value;
  }
  set(key: string, value: T, expires: number) {
    this.entries.delete(key); this.entries.set(key, { expires, value });
    while (this.entries.size > this.maxEntries) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
  }
  delete(key: string) { return this.entries.delete(key); }
}

export const CROPFIT_CACHE_MAX_ENTRIES = 2_048;
export const cropFitRequestCacheKey = (url: string, revision: string, payload: object) => `${url}:${revision}:${createHash('sha256').update(JSON.stringify(payload)).digest('base64url')}`;
const cropFitCache = new BoundedExpiringCache<Promise<CropFitResult>>(CROPFIT_CACHE_MAX_ENTRIES);

async function modelApiKind(url: string): Promise<'contract' | 'cropfit'> {
  const forced = process.env.ML_MODEL_API?.trim().toLowerCase();
  if (forced === 'cropfit' || forced === 'contract') return forced;
  const cached = apiKindCache.get(url);
  if (cached && cached.expires > Date.now()) return cached.kind;
  try {
    const response = await fetch(`${url}/health`, { signal: AbortSignal.timeout(4_000) });
    if (!response.ok) throw new Error(`Model health returned HTTP ${response.status}.`);
    const health = await response.json() as { model?: unknown };
    const kind: 'contract' | 'cropfit' = typeof health.model === 'string' && /cropfit/i.test(health.model) ? 'cropfit' : 'contract';
    apiKindCache.set(url, { kind, expires: Date.now() + 300_000 });
    return kind;
  } catch {
    apiKindCache.delete(url);
    return 'contract';
  }
}

function cropFitCall(url: string, revision: string | null, crop: string, lat: number, lon: number, climate: MlClimate | null) {
  const payload = {
    crop, latitude: Number(lat.toFixed(4)), longitude: Number(lon.toFixed(4)), soilPh: Number(process.env.ML_SOIL_PH) || 6.5, irrigated: process.env.ML_IRRIGATED !== 'false',
    climate: climate ? MONTH_KEYS.map((month, index) => ({ month: month.toUpperCase(), temperatureC: climate.temperatureC[index], precipitationMmDay: climate.precipitationMmDay[index], solarMjM2Day: climate.solarMjM2Day[index] })) : undefined,
    climateHistory: climate?.history?.map((year) => MONTH_KEYS.map((month, index) => ({ month: month.toUpperCase(), temperatureC: year.temperatureC[index], precipitationMmDay: year.precipitationMmDay[index], solarMjM2Day: year.solarMjM2Day[index], year: year.year }))),
  };
  const key = revision ? cropFitRequestCacheKey(url, revision, payload) : null;
  const cached = key ? cropFitCache.get(key) : undefined;
  if (cached) return cached;
  const value = fetch(`${url}/predict`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(modelTimeoutMs()),
    body: JSON.stringify(payload),
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({})) as CropFitResult & { detail?: unknown };
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `CropFit HTTP ${response.status}`);
    return payload;
  });
  if (key) {
    cropFitCache.set(key, value, Date.now() + 3_600_000);
    value.catch(() => cropFitCache.delete(key));
  }
  return value;
}

function fromCropFit(site: MlSite, crop: MlCrop, preferredMonth: number, result: CropFitResult): MlPrediction {
  const curve = new Map((result.monthlyCurve ?? []).flatMap((item) => { const m = monthIndex(item.month); return m === null || !Number.isFinite(item.score) ? [] : [[m, Number(item.score)] as const]; }));
  const suitable = (result.suitableMonths ?? []).map(monthIndex).filter((m): m is number => m !== null);
  // First workable month on or after the user's preferred month; else CropFit's best month.
  let plant: number | null = null;
  for (let offset = 0; offset < 12 && plant === null; offset += 1) if (suitable.includes((preferredMonth + offset) % 12)) plant = (preferredMonth + offset) % 12;
  plant ??= monthIndex(result.bestReliablePlantingMonth ?? result.bestPlantingMonth);
  // Harvest at the middle of CropFit's growing range (its max alone runs long, e.g. 150 d for tomato).
  const minDays = Number(result.growingDays?.min); const maxDays = Number(result.growingDays?.max);
  const days = Number.isFinite(minDays) && Number.isFinite(maxDays) ? (minDays + maxDays) / 2 : maxDays || crop.growMonths * 30;
  const score = plant !== null && curve.has(plant) ? curve.get(plant)! : Number(result.score ?? 0);
  const limiting = [...(result.limitingFactors ?? [])].filter((item) => Number.isFinite(item.score)).sort((a, b) => Number(a.score) - Number(b.score))[0];
  const reliability = result.plantingReliability;
  const observed = result.observedYieldEvidence;
  const successRate = Number(reliability?.successRate);
  const reliableMonth = monthIndex(result.bestReliablePlantingMonth);
  const reliabilityNote = Number.isFinite(successRate) ? `Risk-adjusted ${reliableMonth === null ? 'best' : MONTH_KEYS[reliableMonth].toUpperCase()} window cleared the threshold in ${Math.round(successRate * 100)}% of ${Number(reliability?.years) || 0} historical years.` : null;
  const limitingNote = limiting?.factor && Number(limiting.score) < 90 ? `Most limited by ${limiting.factor.replace(/_/g, ' ')} (${Math.round(Number(limiting.score))}/100).` : limiting?.factor ? 'No strong limiting factor.' : null;
  const representativeNote = CROPFIT_REPRESENTATIVES[crop.id] ? `Representative EcoCrop profile for ${crop.name}: ${CROPFIT_REPRESENTATIVES[crop.id]}.` : null;
  const observedNote = observed && typeof observed.county === 'string' && Number.isFinite(observed.meanPercentile) ? `USDA observed prior near ${observed.county}, ${String(observed.state)}: ${Math.round(Number(observed.observedYieldPrior?.expectedPercentile ?? observed.meanPercentile) * 100)}th percentile from ${Number(observed.observations)} published years (${Math.round(Number(observed.distanceKm))} km away).` : null;
  return {
    siteId: site.id, cropId: crop.id,
    suitability: clamp01(score / 100),
    plantMonth: suitable.length || plant !== null ? plant : null,
    harvestMonth: plant === null ? null : (plant + Math.max(1, Math.round(days / 30)) - 1) % 12,
    confidence: Number.isFinite(result.confidence) ? clamp01(Number(result.confidence)) : null,
    expectedYield: null,
    notes: [representativeNote, reliabilityNote, observedNote, limitingNote].filter(Boolean).join(' ') || null,
    source: 'ml',
    curve: (result.monthlyCurve ?? []).flatMap((item) => {
      const month = monthIndex(item.month);
      return month === null || !Number.isFinite(item.score) ? [] : [{ month, score: Number(item.score), uncertainty: Number.isFinite(item.uncertainty) ? Number(item.uncertainty) : null, errorP80: Number.isFinite(item.expectedAbsoluteErrorP80) ? Number(item.expectedAbsoluteErrorP80) : null, errorP90: Number.isFinite(item.expectedAbsoluteErrorP90) ? Number(item.expectedAbsoluteErrorP90) : null, historicalP10: Number.isFinite(item.historicalP10) ? Number(item.historicalP10) : null, historicalMedian: Number.isFinite(item.historicalMedian) ? Number(item.historicalMedian) : null, historicalP90: Number.isFinite(item.historicalP90) ? Number(item.historicalP90) : null, reliability: Number.isFinite(item.reliability) ? Number(item.reliability) : null, components: item.components ?? null }];
    }).sort((a, b) => a.month - b.month),
    suitableMonths: suitable,
    growingDays: Number.isFinite(minDays) && Number.isFinite(maxDays) ? { min: minDays, max: maxDays } : null,
    limitingFactors: (result.limitingFactors ?? []).filter((item) => item.factor && Number.isFinite(item.score)).map((item) => ({ factor: String(item.factor), score: Number(item.score) })),
    profile: result.profile ? {
      scientificName: typeof result.profile.scientific_name === 'string' ? result.profile.scientific_name : null,
      tempOptC: pair(result.profile.temp_opt_min, result.profile.temp_opt_max),
      rainOptMm: pair(result.profile.rain_opt_min, result.profile.rain_opt_max),
      phOpt: pair(result.profile.ph_opt_min, result.profile.ph_opt_max),
    } : null,
    evidenceGrade: typeof result.evidenceGrade === 'string' ? result.evidenceGrade : null,
    plantingReliability: reliability && [reliability.years, reliability.successRate, reliability.p10Score, reliability.medianScore, reliability.p90Score, reliability.threshold].every((value) => Number.isFinite(Number(value))) ? { years: Number(reliability.years), successRate: Number(reliability.successRate), p10Score: Number(reliability.p10Score), medianScore: Number(reliability.medianScore), p90Score: Number(reliability.p90Score), threshold: Number(reliability.threshold) } : null,
    observedYieldEvidence: observed && typeof observed.county === 'string' && typeof observed.state === 'string' && Array.isArray(observed.years) && [observed.distanceKm, observed.observations, observed.meanPercentile, observed.p10Percentile, observed.p90Percentile, observed.meanYieldBushelsPerAcre].every((value) => Number.isFinite(Number(value))) ? {
      county: observed.county, state: observed.state, distanceKm: Number(observed.distanceKm), years: observed.years.map(Number).filter(Number.isFinite), observations: Number(observed.observations), meanPercentile: Number(observed.meanPercentile), p10Percentile: Number(observed.p10Percentile), p90Percentile: Number(observed.p90Percentile), meanYieldBushelsPerAcre: Number(observed.meanYieldBushelsPerAcre), observedYieldPrior: observed.observedYieldPrior && Number.isFinite(observed.observedYieldPrior.expectedPercentile) && Array.isArray(observed.observedYieldPrior.interval80) && observed.observedYieldPrior.interval80.length === 2 && observed.observedYieldPrior.interval80.every((value) => Number.isFinite(Number(value))) && Array.isArray(observed.observedYieldPrior.interval90) && observed.observedYieldPrior.interval90.length === 2 && observed.observedYieldPrior.interval90.every((value) => Number.isFinite(Number(value))) ? { expectedPercentile: Number(observed.observedYieldPrior.expectedPercentile), interval80: observed.observedYieldPrior.interval80.map(Number) as [number, number], interval90: observed.observedYieldPrior.interval90.map(Number) as [number, number], historyBucket: String(observed.observedYieldPrior.historyBucket ?? ''), calibrationExamples: Number(observed.observedYieldPrior.calibrationExamples) } : undefined, history: (observed.history ?? []).flatMap((item) => [item.year, item.yieldBushelsPerAcre, item.percentile].every((value) => Number.isFinite(Number(value))) ? [{ year: Number(item.year), yieldBushelsPerAcre: Number(item.yieldBushelsPerAcre), percentile: Number(item.percentile) }] : []), evidenceGrade: String(observed.evidenceGrade ?? 'historical-county-context'), source: String(observed.source ?? 'USDA NASS Quick Stats'), disclaimer: String(observed.disclaimer ?? 'Historical county context; not a parcel yield forecast.'),
    } : null,
  };
}
const pair = (a: unknown, b: unknown): [number, number] | null => Number.isFinite(Number(a)) && Number.isFinite(Number(b)) ? [Number(a), Number(b)] : null;

async function predictViaCropFit(url: string, request: MlRequest): Promise<MlResponse> {
  const strict = mlStrict();
  let health: { model?: string; apiVersion?: string; revision?: string } | null = null;
  try {
    const response = await fetch(`${url}/health`, { signal: AbortSignal.timeout(3_000) });
    if (response.ok) health = await response.json() as { model?: string; apiVersion?: string; revision?: string };
  } catch { /* prediction can proceed uncached when health is transiently unavailable */ }
  const revision = typeof health?.revision === 'string' && health.revision ? health.revision
    : health ? createHash('sha256').update(JSON.stringify({ apiVersion: health.apiVersion ?? null, model: health.model ?? null })).digest('base64url') : null;
  const pairs = request.sites.flatMap((site) => request.crops.map((crop) => ({ site, crop, name: strict && crop.id === 'microgreens' ? undefined : CROPFIT_NAMES[crop.id] })));
  const errors: string[] = [];
  const predictions: MlPrediction[] = [];
  for (let i = 0; i < pairs.length; i += 6) {
    const batch = await Promise.all(pairs.slice(i, i + 6).map(async ({ site, crop, name }) => {
      if (!name) return strict ? null : calendarPrediction(site, crop, request.preferredMonth);
      try { return fromCropFit(site, crop, request.preferredMonth, await cropFitCall(url, revision, name, site.lat, site.lon, site.climate)); }
      catch (reason) {
        const message = reason instanceof Error ? reason.message : 'CropFit failed';
        if (strict) throw new Error(`CropFit failed for ${crop.name}: ${message}`);
        errors.push(message); return calendarPrediction(site, crop, request.preferredMonth);
      }
    }));
    predictions.push(...batch.filter((item): item is MlPrediction => item !== null));
  }
  if (!predictions.some((item) => item.source === 'ml')) throw new Error(errors[0] ?? 'CropFit returned no predictions for these crops.');
  if (errors.length) console.warn(`CropFit failed for ${errors.length} pair(s): ${errors[0]}`);
  let name = 'CropFit';
  let version: string | null = null;
  if (health?.model) { const identity = modelIdentity(health.model); name = identity.name; version = identity.version ?? null; }
  return { model: { name, version, source: 'ml', error: errors.length ? `${errors.length} pair(s) used the crop calendar: ${errors[0]}` : null }, predictions };
}

async function predictFromUrl(url: string, request: MlRequest): Promise<MlResponse> {
  if (await modelApiKind(url) === 'cropfit') return await predictViaCropFit(url, request);
  const response = await fetch(`${url}/predict`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal: AbortSignal.timeout(modelTimeoutMs()),
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
}

/** Ask primary, then backup; fill everything from the crop calendar if both fail. */
export async function predictCropSuitability(request: MlRequest): Promise<MlResponse> {
  const urls = modelUrls();
  if (mlStrict() && !urls.length) throw new Error('Strict live mode: no model URL is set.');
  if (!request.sites.length || !request.crops.length) return calendarResponse(request, null);
  if (!urls.length) return calendarResponse(request, 'No model URL is set.');
  const errors: string[] = [];
  for (const [index, url] of urls.entries()) {
    try {
      const result = await predictFromUrl(url, request);
      if (index) console.warn(`Primary crop model unavailable; backup model answered: ${errors[0]}`);
      return result;
    } catch (reason) {
      errors.push(`${index === 0 ? 'primary' : 'backup'}: ${reason instanceof Error ? reason.message : 'model request failed'}`);
    }
  }
  const message = errors.join('; ');
  if (mlStrict()) throw new Error(message);
  console.warn(`Crop models unavailable, using crop calendar: ${message}`);
  return calendarResponse(request, message);
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
  if (pathname === '/api/ml/capabilities') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(await mlCapabilities())); return true; }
  if (pathname === '/api/ml/health') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(await mlModelHealth())); return true; }
  if (pathname !== '/api/ml/predict' || req.method !== 'POST') return false;
  const input = await readJson(req);
  const crops = (Array.isArray(input.crops) ? input.crops : []).filter(isCrop).slice(0, 8);
  const sites = (Array.isArray(input.sites) ? input.sites : []).filter((site): site is MlSite => Boolean(site) && typeof (site as MlSite).id === 'string' && Number.isFinite((site as MlSite).lat) && Number.isFinite((site as MlSite).lon)).slice(0, 40);
  res.setHeader('Content-Type', 'application/json');
  if (!crops.length || !sites.length) { res.statusCode = 400; res.end(JSON.stringify({ error: 'Send at least one crop and one site.' })); return true; }
  let result: MlResponse;
  try {
  result = await predictCropSuitability({
    crops, sites,
    preferredMonth: isMonth(input.preferredMonth) ? input.preferredMonth : new Date().getMonth(),
    targetAreaSqft: Number(input.targetAreaSqft) || 0,
    targetSunHours: Number(input.targetSunHours) || 6,
  });
  } catch (reason) { res.statusCode = 502; res.end(JSON.stringify({ error: reason instanceof Error ? reason.message : 'Crop model failed.' })); return true; }
  res.end(JSON.stringify(result));
  return true;
}
