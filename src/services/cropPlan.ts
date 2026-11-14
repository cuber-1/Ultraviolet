import type { CropModelInfo, CropPrediction, CropProfileInput } from './vexcel';

// Onboarding brief, crop profiles, and climate-based timing.
// Timing is a transparent crop calendar: a month is "growable" when the NASA POWER
// monthly mean temperature sits inside the crop's range. A start month works when
// every month of the crop's growing period is growable.

export type Scale = 'urban' | 'rural';

export type Crop = {
  id: string;
  name: string;
  scale: Scale | 'both';
  sunHours: number;
  tempMinC: number;
  tempMaxC: number;
  growMonths: number;
  note: string;
};

export const CROPS: Crop[] = [
  { id: 'greens', name: 'Leafy greens', scale: 'both', sunHours: 4, tempMinC: 7, tempMaxC: 24, growMonths: 2, note: 'Lettuce, spinach, chard' },
  { id: 'herbs', name: 'Herbs', scale: 'urban', sunHours: 6, tempMinC: 15, tempMaxC: 30, growMonths: 2, note: 'Basil, cilantro, mint' },
  { id: 'microgreens', name: 'Microgreens', scale: 'urban', sunHours: 3, tempMinC: 13, tempMaxC: 27, growMonths: 1, note: 'Fast 2–3 week cycles' },
  { id: 'tomatoes', name: 'Tomatoes', scale: 'both', sunHours: 8, tempMinC: 16, tempMaxC: 30, growMonths: 3, note: 'Needs full sun' },
  { id: 'peppers', name: 'Peppers', scale: 'both', sunHours: 8, tempMinC: 18, tempMaxC: 31, growMonths: 3, note: 'Heat-loving' },
  { id: 'strawberries', name: 'Strawberries', scale: 'both', sunHours: 6, tempMinC: 10, tempMaxC: 26, growMonths: 3, note: 'Cool nights help' },
  { id: 'kale', name: 'Kale & brassicas', scale: 'both', sunHours: 5, tempMinC: 5, tempMaxC: 24, growMonths: 2, note: 'Frost-tolerant' },
  { id: 'beans', name: 'Beans', scale: 'both', sunHours: 6, tempMinC: 16, tempMaxC: 30, growMonths: 2, note: 'Fixes nitrogen' },
  { id: 'cucumbers', name: 'Cucumbers & squash', scale: 'both', sunHours: 7, tempMinC: 18, tempMaxC: 32, growMonths: 2, note: 'Vining, warm season' },
  { id: 'corn', name: 'Corn', scale: 'rural', sunHours: 8, tempMinC: 16, tempMaxC: 32, growMonths: 4, note: 'Row crop' },
  { id: 'soybeans', name: 'Soybeans', scale: 'rural', sunHours: 7, tempMinC: 18, tempMaxC: 30, growMonths: 4, note: 'Row crop' },
  { id: 'wheat', name: 'Wheat', scale: 'rural', sunHours: 6, tempMinC: 3, tempMaxC: 24, growMonths: 4, note: 'Cool-season grain' },
  { id: 'potatoes', name: 'Potatoes', scale: 'rural', sunHours: 6, tempMinC: 10, tempMaxC: 24, growMonths: 4, note: 'Cool-season tuber' },
  { id: 'melons', name: 'Melons', scale: 'rural', sunHours: 8, tempMinC: 20, tempMaxC: 34, growMonths: 3, note: 'Long hot season' },
  { id: 'onions', name: 'Onions', scale: 'rural', sunHours: 6, tempMinC: 10, tempMaxC: 27, growMonths: 4, note: 'Long-day or short-day' },
  { id: 'sunflowers', name: 'Sunflowers', scale: 'rural', sunHours: 7, tempMinC: 16, tempMaxC: 32, growMonths: 3, note: 'Drought-tolerant' },
];

export const URBAN_AREAS = [
  { id: 'houston', label: 'Houston', detail: 'Texas Gulf Coast', value: 'Houston, Texas', lat: 29.76, lon: -95.37 },
  { id: 'los-angeles', label: 'Los Angeles', detail: 'Southern California', value: 'Los Angeles, California', lat: 34.05, lon: -118.24 },
  { id: 'stockton', label: 'Stockton', detail: 'Central Valley, California', value: 'Stockton, California', lat: 37.96, lon: -121.29 },
] as const;

export const RURAL_REGIONS = [
  { id: 'central-valley', label: 'Central Valley', detail: 'California', lat: 36.6, lon: -120.2, places: ['Fresno, California', 'Bakersfield, California', 'Modesto, California', 'Salinas, California'] },
  { id: 'southwest', label: 'Desert Southwest', detail: 'Arizona · New Mexico', lat: 32.6, lon: -112.3, places: ['Yuma, Arizona', 'Las Cruces, New Mexico', 'El Centro, California'] },
  { id: 'texas', label: 'Texas', detail: 'Rio Grande · Plains', lat: 30.4, lon: -99.1, places: ['McAllen, Texas', 'Lubbock, Texas', 'Waco, Texas'] },
  { id: 'midwest', label: 'Corn Belt', detail: 'Iowa · Illinois · Nebraska', lat: 40.8, lon: -92.8, places: ['Des Moines, Iowa', 'Champaign, Illinois', 'Lincoln, Nebraska'] },
  { id: 'southeast', label: 'Southeast', detail: 'Georgia · Carolinas · Florida', lat: 32.3, lon: -81.5, places: ['Tifton, Georgia', 'Raleigh, North Carolina', 'Gainesville, Florida'] },
  { id: 'northwest', label: 'Pacific Northwest', detail: 'Washington · Oregon · Idaho', lat: 45.0, lon: -119.9, places: ['Yakima, Washington', 'Salem, Oregon', 'Boise, Idaho'] },
] as const;

export type Brief = {
  scale: Scale;
  areaSqft: number;
  crops: string[];
  urbanArea?: string;
  ruralRegions?: string[];
  preferredMonth: number; // 0-11
};

export const ACRE_SQFT = 43_560;
export const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const MONTH_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export const scaleForArea = (areaSqft: number): Scale => areaSqft >= ACRE_SQFT ? 'rural' : 'urban';
export const cropById = (id: string) => CROPS.find((crop) => crop.id === id);
export const briefCrops = (brief: Brief) => brief.crops.map(cropById).filter((crop): crop is Crop => Boolean(crop));

export function formatArea(areaSqft: number) {
  if (areaSqft >= ACRE_SQFT) return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(areaSqft / ACRE_SQFT)} acres`;
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(areaSqft)} ft²`;
}

export type MonthlyClimate = {
  query: string; name: string; region: string; lat: number; lon: number;
  temperatureC: number[]; solarMjM2Day: number[]; precipitationMmDay: number[];
  annual: { temperatureC: number; solarMjM2Day: number; precipitationMmDay: number };
  source: string;
};

export async function fetchMonthlyClimate(locations: string[], signal?: AbortSignal) {
  const response = await fetch('/api/climate/monthly', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ locations }), signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Climate lookup failed.');
  return payload as { results: MonthlyClimate[]; errors: Array<{ location: string; error: string }> };
}

export type CropTiming = {
  crop: Crop;
  growable: boolean[];
  startMonth: number | null;
  harvestMonth: number | null;
  waitMonths: number | null; // months after the preferred month
  seasonMonths: number;
  suitability?: number;
};

export function cropTiming(crop: Crop, climate: MonthlyClimate, preferredMonth: number): CropTiming {
  const growable = climate.temperatureC.map((t) => t >= crop.tempMinC && t <= crop.tempMaxC);
  const windowWorks = (start: number) => Array.from({ length: crop.growMonths }, (_, i) => growable[(start + i) % 12]).every(Boolean);
  for (let wait = 0; wait < 12; wait += 1) {
    const start = (preferredMonth + wait) % 12;
    if (windowWorks(start)) {
      return { crop, growable, startMonth: start, harvestMonth: (start + crop.growMonths - 1) % 12, waitMonths: wait, seasonMonths: growable.filter(Boolean).length };
    }
  }
  return { crop, growable, startMonth: null, harvestMonth: null, waitMonths: null, seasonMonths: growable.filter(Boolean).length };
}

export type LocationPlan = {
  climate: MonthlyClimate;
  timings: CropTiming[];
  moveInMonth: number | null;
  score: number;
  reasons: string[];
};

export function planForLocation(brief: Brief, climate: MonthlyClimate): LocationPlan {
  const crops = briefCrops(brief);
  const timings = crops.map((crop) => cropTiming(crop, climate, brief.preferredMonth));
  const suited = timings.filter((timing) => timing.startMonth !== null);
  const moveIn = suited.length ? suited.reduce((best, timing) => timing.waitMonths! < best.waitMonths! ? timing : best).startMonth : null;
  // Score: share of crops that fit, how soon they can start, season length, and solar resource.
  const fitShare = crops.length ? suited.length / crops.length : 0;
  const promptness = suited.length ? suited.reduce((sum, timing) => sum + (1 - timing.waitMonths! / 11), 0) / suited.length : 0;
  const season = timings.length ? timings.reduce((sum, timing) => sum + timing.seasonMonths / 12, 0) / timings.length : 0;
  const solar = Math.max(0, Math.min(1, (climate.annual.solarMjM2Day - 12) / 10));
  const score = Math.round(100 * (0.45 * fitShare + 0.25 * promptness + 0.15 * season + 0.15 * solar));
  const reasons = [
    `${suited.length} of ${crops.length} crops fit the local temperature calendar`,
    `${climate.annual.solarMjM2Day.toFixed(1)} MJ/m²/day average solar`,
    `${climate.annual.temperatureC.toFixed(1)}°C annual mean · ${climate.annual.precipitationMmDay.toFixed(1)} mm/day rain`,
  ];
  return { climate, timings, moveInMonth: moveIn, score, reasons };
}

/** Next calendar date (YYYY-MM-15) for a month index, from today. */
export function nextMonthDate(month: number, now = new Date()) {
  const year = month >= now.getMonth() ? now.getFullYear() : now.getFullYear() + 1;
  return `${year}-${String(month + 1).padStart(2, '0')}-15`;
}

/** Agent inputs for an urban brief: sun need, area, and two season dates. */
export function urbanAgentCriteria(brief: Brief, plan: LocationPlan | null) {
  const crops = briefCrops(brief);
  const targetHours = Math.min(10, Math.max(3, ...crops.map((crop) => crop.sunHours)));
  const start = plan?.moveInMonth ?? brief.preferredMonth;
  const longest = Math.max(1, ...crops.map((crop) => crop.growMonths));
  const mid = (start + Math.max(1, Math.floor(longest / 2))) % 12;
  const startDate = nextMonthDate(start);
  const midYear = Number(startDate.slice(0, 4)) + (mid < start ? 1 : 0);
  const dates = [startDate, `${midYear}-${String(mid + 1).padStart(2, '0')}-15`];
  const cropNames = crops.map((crop) => crop.name.toLowerCase()).join(', ');
  const area = urbanAreaLabel(brief);
  const goal = `Find rooftops in ${area} with at least ${Math.round(brief.areaSqft).toLocaleString('en-US')} square feet getting ${targetHours} hours of direct sun to grow ${cropNames}, starting ${MONTH_LONG[start]}.`;
  return { targetHours, targetAreaSqft: Math.max(100, Math.round(brief.areaSqft)), dates, goal, startMonth: start };
}

export const urbanAreaLabel = (brief: Brief) => URBAN_AREAS.find((area) => area.value === brief.urbanArea)?.label ?? brief.urbanArea ?? 'available coverage';

export function ruralPlaces(brief: Brief) {
  return [...new Set((brief.ruralRegions ?? []).flatMap((id) => RURAL_REGIONS.find((region) => region.id === id)?.places ?? []))].slice(0, 20);
}

const BRIEF_KEY = 'ultraviolet.brief';
export function saveBrief(brief: Brief) { try { sessionStorage.setItem(BRIEF_KEY, JSON.stringify(brief)); } catch { /* storage unavailable */ } }
export function loadBrief(): Brief | null {
  try { const raw = sessionStorage.getItem(BRIEF_KEY); return raw ? JSON.parse(raw) as Brief : null; } catch { return null; }
}

// ---- Crop model (see machine-learning/INTEGRATION.md) ----

export const cropProfiles = (brief: Brief): CropProfileInput[] => briefCrops(brief).map(({ id, name, sunHours, tempMinC, tempMaxC, growMonths }) => ({ id, name, sunHours, tempMinC, tempMaxC, growMonths }));

export async function fetchRegionPredictions(brief: Brief, climates: MonthlyClimate[], signal?: AbortSignal) {
  const response = await fetch('/api/ml/predict', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({
      crops: cropProfiles(brief), preferredMonth: brief.preferredMonth, targetAreaSqft: brief.areaSqft,
      targetSunHours: Math.max(...briefCrops(brief).map((crop) => crop.sunHours)),
      sites: climates.map((climate) => ({ id: climate.query, kind: 'region', lat: climate.lat, lon: climate.lon, climate: { temperatureC: climate.temperatureC, solarMjM2Day: climate.solarMjM2Day, precipitationMmDay: climate.precipitationMmDay }, roof: null })),
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Crop model request failed.');
  return payload as { model: CropModelInfo; predictions: CropPrediction[] };
}

/** Use trained-model timing and suitability for a region when the model answered; otherwise keep the calendar plan. */
export function applyModel(plan: LocationPlan, predictions: CropPrediction[], preferredMonth: number): LocationPlan {
  const mine = predictions.filter((item) => item.siteId === plan.climate.query && item.source === 'ml');
  if (!mine.length) return plan;
  const timings = plan.timings.map((timing) => {
    const hit = mine.find((item) => item.cropId === timing.crop.id);
    if (!hit) return timing;
    return { ...timing, startMonth: hit.plantMonth, harvestMonth: hit.harvestMonth, waitMonths: hit.plantMonth === null ? null : (hit.plantMonth - preferredMonth + 12) % 12, suitability: hit.suitability };
  });
  const suitability = mine.reduce((sum, item) => sum + item.suitability, 0) / mine.length;
  const started = timings.filter((timing) => timing.waitMonths !== null);
  const moveInMonth = started.length ? started.reduce((best, timing) => timing.waitMonths! < best.waitMonths! ? timing : best).startMonth : null;
  return { ...plan, timings, moveInMonth, score: Math.round(100 * suitability), reasons: [`Crop model suitability ${Math.round(100 * suitability)}%`, ...plan.reasons] };
}

export type MlCapabilities = { strict: boolean; configured: boolean; api: 'contract' | 'cropfit' | null; supportedCrops: string[] | null };
export async function fetchMlCapabilities(signal?: AbortSignal): Promise<MlCapabilities | null> {
  try { const response = await fetch('/api/ml/capabilities', { signal }); return response.ok ? await response.json() as MlCapabilities : null; } catch { return null; }
}

/** Where the loading map should look for a brief: a city, or the chosen farming regions. */
export function briefFocus(brief: Brief): Array<{ lat: number; lon: number }> {
  if (brief.scale === 'urban') { const area = URBAN_AREAS.find((item) => item.value === brief.urbanArea); return area ? [{ lat: area.lat, lon: area.lon }] : []; }
  return (brief.ruralRegions ?? []).flatMap((id) => { const region = RURAL_REGIONS.find((item) => item.id === id); return region ? [{ lat: region.lat, lon: region.lon }] : []; });
}
