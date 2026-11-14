import type { IncomingMessage, ServerResponse } from 'node:http';

// Monthly NASA POWER climatology for onboarding crop timing.
// POST /api/climate/monthly { locations: string[] } -> { results, errors }

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'] as const;
const cache = new Map<string, { expires: number; value: MonthlyClimate }>();

export type MonthlyClimate = {
  query: string;
  name: string;
  region: string;
  lat: number;
  lon: number;
  temperatureC: number[];
  solarMjM2Day: number[];
  precipitationMmDay: number[];
  annual: { temperatureC: number; solarMjM2Day: number; precipitationMmDay: number };
  source: string;
};

async function geocode(place: string) {
  const params = new URLSearchParams({ name: place.split(',')[0].trim(), count: '10', language: 'en', format: 'json' });
  const response = await fetch(`https://geocoding-api.open-meteo.com/v1/search?${params}`);
  if (!response.ok) throw new Error(`Location search failed for ${place}.`);
  const payload = await response.json() as { results?: Array<Record<string, unknown>> };
  const qualifier = place.split(',').slice(1).join(',').trim().toLowerCase();
  const results = payload.results ?? [];
  const match = (qualifier && results.find((item) => [item.admin1, item.country, item.country_code].some((value) => typeof value === 'string' && value.toLowerCase().startsWith(qualifier.slice(0, 4))))) || results[0];
  if (!match || !Number.isFinite(Number(match.latitude)) || !Number.isFinite(Number(match.longitude))) throw new Error(`Could not locate ${place}.`);
  return {
    query: place,
    name: String(match.name || place),
    region: [match.admin1, match.country].filter(Boolean).map(String).join(', '),
    lat: Number(match.latitude),
    lon: Number(match.longitude),
  };
}

export async function monthlyClimate(place: string): Promise<MonthlyClimate> {
  const key = place.trim().toLowerCase();
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return cached.value;
  const location = await geocode(place);
  const params = new URLSearchParams({
    parameters: 'T2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR', community: 'AG',
    longitude: String(location.lon), latitude: String(location.lat), format: 'JSON',
  });
  const response = await fetch(`https://power.larc.nasa.gov/api/temporal/climatology/point?${params}`);
  if (!response.ok) throw new Error(`NASA POWER climate lookup failed for ${place}.`);
  const payload = await response.json() as { properties?: { parameter?: Record<string, Record<string, number>> } };
  const values = payload.properties?.parameter ?? {};
  const series = (name: string) => MONTHS.map((month) => Number(values[name]?.[month]));
  const temperatureC = series('T2M');
  const solarMjM2Day = series('ALLSKY_SFC_SW_DWN');
  const precipitationMmDay = series('PRECTOTCORR');
  if (![...temperatureC, ...solarMjM2Day, ...precipitationMmDay].every(Number.isFinite)) throw new Error(`NASA POWER returned incomplete monthly data for ${place}.`);
  const value: MonthlyClimate = {
    ...location,
    temperatureC, solarMjM2Day, precipitationMmDay,
    annual: {
      temperatureC: Number(values.T2M?.ANN),
      solarMjM2Day: Number(values.ALLSKY_SFC_SW_DWN?.ANN),
      precipitationMmDay: Number(values.PRECTOTCORR?.ANN),
    },
    source: 'NASA POWER Agroclimatology monthly climatology',
  };
  cache.set(key, { expires: Date.now() + 86_400_000, value });
  return value;
}

async function readJson(req: IncomingMessage) {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>;
}

function send(res: ServerResponse, status: number, value: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(value));
}

/** Returns true when the request was handled. */
export async function handleMonthlyClimate(pathname: string, req: IncomingMessage, res: ServerResponse) {
  if (pathname !== '/api/climate/monthly' || req.method !== 'POST') return false;
  const input = await readJson(req);
  const locations = (Array.isArray(input.locations) ? input.locations : [])
    .map(String).map((item) => item.trim()).filter(Boolean).slice(0, 20);
  if (!locations.length) { send(res, 400, { error: 'Add at least one location.' }); return true; }
  const settled = await Promise.allSettled(locations.map((location) => monthlyClimate(location)));
  const results = settled.flatMap((item) => item.status === 'fulfilled' ? [item.value] : []);
  const errors = settled.flatMap((item, index) => item.status === 'rejected' ? [{ location: locations[index], error: item.reason instanceof Error ? item.reason.message : 'Lookup failed.' }] : []);
  if (!results.length) { send(res, 502, { error: 'No location returned usable climate data.', details: errors }); return true; }
  send(res, 200, { results, errors });
  return true;
}
