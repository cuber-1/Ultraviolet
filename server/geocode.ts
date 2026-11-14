import type { IncomingMessage, ServerResponse } from 'node:http';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Street addresses for roof coordinates via OpenStreetMap Nominatim (no key).
//   GET /api/geo/reverse?lat=..&lon=..  ->  { street, area, label } | 404
// Nominatim's usage policy allows ~1 request/second with an identifying User-Agent, so
// requests are queued and every answer is cached in memory and runtime/geocode-cache.json.

type Address = { street: string | null; area: string | null; label: string };
const cache = new Map<string, Address | null>();
let loaded = false;
let queue: Promise<unknown> = Promise.resolve();
let last = 0;

const keyFor = (lat: number, lon: number) => `${lat.toFixed(5)},${lon.toFixed(5)}`;

async function load(file: string) {
  if (loaded) return;
  loaded = true;
  try { Object.entries(JSON.parse(await readFile(file, 'utf8')) as Record<string, Address | null>).forEach(([key, value]) => cache.set(key, value)); } catch { /* no cache yet */ }
}

async function persist(file: string) {
  try { await mkdir(resolve(file, '..'), { recursive: true }); await writeFile(file, JSON.stringify(Object.fromEntries(cache))); } catch { /* best effort */ }
}

async function lookup(lat: number, lon: number): Promise<Address | null> {
  const wait = Math.max(0, last + 1100 - Date.now());
  if (wait) await new Promise((done) => setTimeout(done, wait));
  last = Date.now();
  const params = new URLSearchParams({ format: 'jsonv2', lat: String(lat), lon: String(lon), zoom: '18', addressdetails: '1' });
  const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`, {
    headers: { 'User-Agent': 'Ultraviolet rooftop-farming prototype (hackathon demo)', 'Accept-Language': 'en' },
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) throw new Error(`Reverse geocoding failed (${response.status}).`);
  const payload = await response.json() as { address?: Record<string, string> };
  const a = payload.address ?? {};
  const road = a.road ?? a.pedestrian ?? a.footway ?? null;
  const street = road ? [a.house_number, road].filter(Boolean).join(' ') : a.building ?? a.amenity ?? null;
  const area = [a.neighbourhood ?? a.suburb ?? a.quarter, a.city ?? a.town ?? a.village ?? a.county, a.state].filter(Boolean).slice(0, 3).join(', ') || null;
  if (!street && !area) return null;
  return { street, area, label: [street, area].filter(Boolean).join(', ') };
}

/** Returns true when the request was handled. */
export async function handleGeoRoute(pathname: string, url: URL, res: ServerResponse, root: string, _req?: IncomingMessage) {
  if (pathname !== '/api/geo/reverse') return false;
  const lat = Number(url.searchParams.get('lat')); const lon = Number(url.searchParams.get('lon'));
  res.setHeader('Content-Type', 'application/json');
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) { res.statusCode = 400; res.end(JSON.stringify({ error: 'lat and lon are required.' })); return true; }
  const file = resolve(root, 'runtime/geocode-cache.json');
  await load(file);
  const key = keyFor(lat, lon);
  if (!cache.has(key)) {
    const job = queue.then(() => lookup(lat, lon));
    queue = job.catch(() => undefined);
    try { cache.set(key, await job); void persist(file); }
    catch (reason) { res.statusCode = 502; res.end(JSON.stringify({ error: reason instanceof Error ? reason.message : 'Lookup failed.' })); return true; }
  }
  const value = cache.get(key);
  if (!value) { res.statusCode = 404; res.end(JSON.stringify({ error: 'No address here.' })); return true; }
  res.end(JSON.stringify(value));
  return true;
}
