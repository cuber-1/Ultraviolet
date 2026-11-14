import type { Connect } from 'vite';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { geometryBounds, geometryRequiredRadius, insideMetricGeometry, metricPointToLonLat, roofWktToMetricGeometry, type MetricRoofGeometry } from '../src/services/roofGeometry';
import { sharedMeetingArea, simulate, type AreaSelection, type Obstruction } from '../src/services/sunSimulation';
import { handleMonthlyClimate, monthlyClimateAt } from './monthlyClimate';
import { handleRunsRoute } from './runStore';
import { combinedRoofScore, handleMlRoute, mlModelStatus, modelBaseUrl, predictCropSuitability, siteSuitability, type MlCrop } from './mlModel';
import { landLensAgentStatus, roofSites, runLandLensAgent, type AgentCandidate, type GeometryEvidence, type SunlightEvidence } from './landlensAgent';
import { createPhotonConversation, photonStatus, sendPhotonMessage, type PhotonPlatform } from './photon';

const API_ROOT = 'https://api.vexcelgroup.com/v2';
const LAYERS = 'urban,urban-r,wide-area,urban-g';
const CLIMATE_MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

type JsonRecord = Record<string, unknown>;
type RuralGoal = 'balanced' | 'sun' | 'low-irrigation';
type PhotonWatch = {
  id: string; goal: string; location: string; lat: number; lon: number; radiusM: number;
  dates: string[]; targetHours: number; targetAreaSqft: number; platform: PhotonPlatform;
  handle: string; spaceId: string; knownOpenings: string[]; createdAt: string; lastCheckedAt: string | null;
};

type CostarProperty = JsonRecord & {
  id: number;
  primaryAddress?: JsonRecord;
  attachments?: JsonRecord[];
  constructionEvents?: JsonRecord[];
};

const propertyTypeNames: Record<number, string> = { 1: 'Hospitality', 2: 'Industrial', 3: 'Land', 5: 'Office', 6: 'Retail', 7: 'Flex', 8: 'Sports & entertainment', 9: 'Mixed use', 10: 'Specialty', 11: 'Multifamily', 13: 'Healthcare', 15: 'Residential', 16: 'Homes' };
const listingTypeNames: Record<number, string> = { 1: 'Apartment community', 9: 'For sale', 12: 'Land for sale', 13: 'Portfolio for sale', 14: 'Space for lease', 16: 'Building park lease', 17: 'Shopping center lease', 18: 'Land for lease', 19: 'Sublease', 21: 'Coworking', 22: 'Auction', 23: 'Land auction' };
const listingStatusNames: Record<number, string> = { 1: 'Active', 2: 'Pending', 3: 'Off market', 7: 'Awaiting verification', 10: 'Confidential', 13: 'Draft' };

function readJsonLines(path: string) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as JsonRecord);
}

function costarIndex(root: string) {
  const directory = process.env.COSTAR_DATA_DIR || resolve(root, '../costar-hackathon-kit/data');
  const properties = readJsonLines(resolve(directory, 'commercial-property.jsonl')) as CostarProperty[];
  const listings = readJsonLines(resolve(directory, 'commercial-listing-summary.jsonl'));
  const apartments = readJsonLines(resolve(directory, 'apartment-listing.jsonl'));
  const listingsByProperty = new Map<number, JsonRecord[]>();
  const apartmentsByProperty = new Map<number, JsonRecord>();
  for (const listing of listings) {
    const propertyId = Number(listing.propertyId);
    if (!Number.isFinite(propertyId)) continue;
    listingsByProperty.set(propertyId, [...(listingsByProperty.get(propertyId) ?? []), listing]);
  }
  for (const apartment of apartments) apartmentsByProperty.set(Number(apartment.propertyId), apartment);
  return { available: properties.length > 0, properties, listingsByProperty, apartmentsByProperty };
}

function distanceMeters(lat: number, lon: number, address: JsonRecord) {
  const addressLat = Number(address.latitude);
  const addressLon = Number(address.longitude);
  if (!Number.isFinite(addressLat) || !Number.isFinite(addressLon)) return Number.POSITIVE_INFINITY;
  const x = (addressLon - lon) * 111_320 * Math.cos(lat * Math.PI / 180);
  const y = (addressLat - lat) * 111_320;
  return Math.hypot(x, y);
}

function addressLabel(address: JsonRecord) {
  const street = [address.streetNumber, address.streetDirection, address.streetName, address.streetType].filter(Boolean).join(' ');
  return [street, address.city, address.state, address.postcode].filter(Boolean).join(', ');
}

function matchCostar(index: ReturnType<typeof costarIndex>, lat: number, lon: number) {
  let match: CostarProperty | null = null;
  let matchDistance = Number.POSITIVE_INFINITY;
  for (const property of index.properties) {
    const distance = distanceMeters(lat, lon, property.primaryAddress ?? {});
    if (distance < matchDistance) { match = property; matchDistance = distance; }
  }
  if (!match || matchDistance > 125) return null;
  const address = match.primaryAddress ?? {};
  const listings = index.listingsByProperty.get(match.id) ?? [];
  const apartment = index.apartmentsByProperty.get(match.id);
  const tours = (match.attachments ?? []).filter((attachment) => [36, 234].includes(Number(attachment.videoExternalReferenceType)) && typeof attachment.videoKey === 'string');
  const completionYears = (match.constructionEvents ?? []).map((event) => Number(event.year)).filter(Number.isFinite);
  const listingTypes = [...new Set(listings.map((listing) => listingTypeNames[Number(listing.listingType)] ?? `Type ${listing.listingType}`))];
  const listingStatuses = [...new Set(listings.map((listing) => listingStatusNames[Number(listing.listingStatus)] ?? 'Unknown'))];
  return {
    propertyId: match.id,
    matchDistanceM: Math.round(matchDistance),
    buildingName: typeof match.buildingName === 'string' ? match.buildingName : null,
    address: addressLabel(address),
    propertyType: propertyTypeNames[Number(match.propertyType)] ?? 'Commercial property',
    buildingClass: Number(match.buildingClass) > 0 ? ['Unknown', 'A', 'B', 'C', 'F'][Number(match.buildingClass)] : null,
    buildingRating: Number(match.buildingRating) || null,
    grossBuildingAreaSqft: Number(match.grossBuildingAreaSquareFeet) || null,
    rentableBuildingAreaSqft: Number(match.rentableBuildingAreaSquareFeet) || null,
    stories: Number(match.numStoriesAboveGrade) || null,
    yearBuilt: completionYears.length ? Math.max(...completionYears) : null,
    lotSize: Number(match.lotSize) || null,
    lotSizeUnit: Number(match.lotSizeMeasurementType) === 2 ? 'acres' : Number(match.lotSizeMeasurementType) === 1 ? 'ft²' : null,
    zoning: typeof match.zoningDescription === 'string' && match.zoningDescription !== 'None' ? match.zoningDescription : null,
    photoUrl: typeof (match.primaryPhoto as JsonRecord | undefined)?.attachmentUri === 'string' ? (match.primaryPhoto as JsonRecord).attachmentUri : null,
    listing: listings.length ? {
      count: listings.length,
      types: listingTypes,
      statuses: listingStatuses,
      active: listings.some((listing) => Number(listing.listingStatus) === 1),
      brokerages: [...new Set(listings.map((listing) => listing.brokerageCompanyName).filter((value): value is string => typeof value === 'string'))].slice(0, 3),
      certifiedFreshDate: listings.map((listing) => String(listing.certifiedFreshDate ?? '')).filter(Boolean).sort().at(-1) || null,
    } : null,
    apartment: apartment ? {
      units: Number(apartment.totalActiveUnits ?? apartment.totalNumUnits) || null,
      availableUnits: Number(apartment.numUnitsAvailable) || 0,
      minRent: Number(apartment.minRent) || null,
      maxRent: Number(apartment.maxRent) || null,
      management: typeof apartment.propertyManagementCompanyName === 'string' ? apartment.propertyManagementCompanyName : null,
    } : null,
    matterport: tours.slice(0, 8).map((tour) => ({ modelId: String(tour.videoKey), caption: typeof tour.caption === 'string' ? tour.caption : 'Matterport scan', thumbnailUrl: typeof tour.attachmentUri === 'string' ? tour.attachmentUri : null })),
    source: 'CoStar hackathon dataset',
  };
}

function configuredKey(root: string) {
  if (process.env.VEXCEL_API_KEY) return process.env.VEXCEL_API_KEY;
  const paths = [resolve(root, '.env'), resolve(root, '../Vexcel_API_Hackathon_Tutorial_PDF_PY/.env')];
  for (const path of paths) {
    if (!existsSync(path)) continue;
    const match = readFileSync(path, 'utf8').match(/^VEXCEL_API_KEY=(.+)$/m);
    if (match?.[1] && !match[1].includes('paste-your')) return match[1].trim().replace(/^['"]|['"]$/g, '');
  }
  return undefined;
}

function square(lat: number, lon: number, radiusM: number) {
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos(lat * Math.PI / 180));
  return `POLYGON((${lon - dLon} ${lat - dLat},${lon + dLon} ${lat - dLat},${lon + dLon} ${lat + dLat},${lon - dLon} ${lat + dLat},${lon - dLon} ${lat - dLat}))`;
}

function coordinates(geometry: JsonRecord): number[][] {
  const raw = geometry.coordinates;
  if (!Array.isArray(raw)) return [];
  const values: number[][] = [];
  const visit = (node: unknown) => {
    if (Array.isArray(node) && node.length >= 2 && typeof node[0] === 'number' && typeof node[1] === 'number') values.push([node[0], node[1]]);
    else if (Array.isArray(node)) node.forEach(visit);
  };
  visit(raw);
  return values;
}

function centroid(geometry: JsonRecord) {
  const points = coordinates(geometry);
  return points.reduce((sum, point) => ({ lon: sum.lon + point[0] / points.length, lat: sum.lat + point[1] / points.length }), { lat: 0, lon: 0 });
}

function json(res: ServerResponse, status: number, value: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(value));
}

async function body(req: IncomingMessage) {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as JsonRecord;
}

const ruralClimateCache = new Map<string, { expires: number; value: unknown }>();
let embeddingCollectionCache: { expires: number; values: string[] } | null = null;
const embeddingSearchCache = new Map<string, { expires: number; features: Array<{ geometry: JsonRecord; properties: JsonRecord }> }>();
const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

async function geocodePlace(place: string) {
  const params = new URLSearchParams({ name: place, count: '1', language: 'en', format: 'json' });
  const response = await fetch(`https://geocoding-api.open-meteo.com/v1/search?${params}`);
  if (!response.ok) throw new Error(`Location search failed for ${place}.`);
  const payload = await response.json() as { results?: Array<JsonRecord> };
  const result = payload.results?.[0];
  if (!result || !Number.isFinite(Number(result.latitude)) || !Number.isFinite(Number(result.longitude))) throw new Error(`Could not locate ${place}.`);
  return {
    query: place,
    name: String(result.name || place),
    region: [result.admin2, result.admin1, result.country].filter(Boolean).map(String).join(', '),
    lat: Number(result.latitude),
    lon: Number(result.longitude),
    timezone: String(result.timezone || 'UTC'),
  };
}

async function ruralClimate(place: string, goal: RuralGoal) {
  const cacheKey = `${place.toLowerCase()}:${goal}`;
  const cached = ruralClimateCache.get(cacheKey);
  if (cached && cached.expires > Date.now()) return cached.value;
  const location = await geocodePlace(place);
  const params = new URLSearchParams({
    parameters: 'ALLSKY_SFC_SW_DWN,PRECTOTCORR,T2M,T2M_MAX,T2M_MIN', community: 'AG',
    longitude: String(location.lon), latitude: String(location.lat), format: 'JSON',
  });
  const response = await fetch(`https://power.larc.nasa.gov/api/temporal/climatology/point?${params}`);
  if (!response.ok) throw new Error(`NASA POWER climate lookup failed for ${place}.`);
  const payload = await response.json() as { header?: JsonRecord; properties?: { parameter?: Record<string, Record<string, number>> } };
  const values = payload.properties?.parameter ?? {};
  const solar = Number(values.ALLSKY_SFC_SW_DWN?.ANN);
  const precipitation = Number(values.PRECTOTCORR?.ANN);
  const temperature = Number(values.T2M?.ANN);
  const temperatureMax = Number(values.T2M_MAX?.ANN);
  const temperatureMin = Number(values.T2M_MIN?.ANN);
  if (![solar, precipitation, temperature].every(Number.isFinite)) throw new Error(`NASA POWER returned incomplete climate data for ${place}.`);
  const solarFit = clamp01((solar - 10) / 10);
  const temperatureFit = clamp01(1 - Math.abs(temperature - 20) / 15);
  const rainfallFit = clamp01(precipitation / 3);
  const weights = goal === 'sun' ? [0.6, 0.25, 0.15] : goal === 'low-irrigation' ? [0.25, 0.3, 0.45] : [0.4, 0.35, 0.25];
  const score = Math.round(100 * (solarFit * weights[0] + temperatureFit * weights[1] + rainfallFit * weights[2]));
  const value = {
    ...location, score, solarMjM2Day: solar, precipitationMmDay: precipitation,
    temperatureC: temperature, temperatureMaxC: temperatureMax, temperatureMinC: temperatureMin,
    reason: goal === 'sun' ? 'Weighted toward stronger year-round solar resource.' : goal === 'low-irrigation' ? 'Weighted toward precipitation and moderate growing temperatures.' : 'Balances solar resource, growing temperature, and precipitation.',
    period: String(payload.header?.range || 'NASA POWER climatology'),
    source: 'NASA POWER Agroclimatology', soilAssessed: false, parcelAssessed: false,
  };
  ruralClimateCache.set(cacheKey, { expires: Date.now() + 86_400_000, value });
  return value;
}

async function availableEmbeddingCollections(key: string) {
  if (embeddingCollectionCache && embeddingCollectionCache.expires > Date.now()) return embeddingCollectionCache.values;
  const response = await vexcel(key, 'embedding/collections?include=collection,layer,last-capture-date');
  const payload = await response.json() as { features?: Array<{ properties?: JsonRecord }> };
  const values = [...new Set((payload.features ?? []).flatMap((feature) => {
    const layer = String(feature.properties?.layer || '');
    const collection = feature.properties?.collection;
    return ['urban', 'urban-r', 'wide-area', 'urban-g'].includes(layer) && typeof collection === 'string' ? [collection] : [];
  }))];
  if (!values.length) throw new Error('Vexcel returned no searchable imagery collections.');
  embeddingCollectionCache = { expires: Date.now() + 10 * 60_000, values };
  return values;
}

function locationPhrase(query: string) {
  const match = query.match(/\b(?:near|around|in)\s+([a-z][a-z .'-]*(?:,\s*[a-z]{2,})?)(?=\s+(?:with|that|having|and|at least|over|under|for)\b|[.?!]|$)/i);
  return match?.[1]?.trim() || null;
}

async function vexcel(key: string, path: string, init: RequestInit = {}) {
  const response = await fetch(`${API_ROOT}/${path}`, {
    ...init,
    headers: { 'X-API-KEY': key, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${(await response.text()).slice(0, 180)}`);
  return response;
}

function parseElevationWkt(wkt: string) {
  const values: number[] = [];
  const coordinatePattern = /-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+(-?\d+(?:\.\d+)?)/g;
  for (const match of wkt.matchAll(coordinatePattern)) values.push(Number(match[1]));
  return values;
}

async function propertyAt(key: string, lat: number, lon: number) {
  const params = new URLSearchParams({ wkt: `POINT(${lon} ${lat})`, srid: '4326', layer: LAYERS, latest: 'true', include: 'precomputed', 'unit-system': 'imperial' });
  const response = await fetch(`${API_ROOT}/property/extract?${params}`, { headers: { 'X-API-KEY': key } });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`property/extract returned ${response.status}`);
  const payload = await response.json() as { features?: Array<{ geometry: JsonRecord; properties: JsonRecord }> };
  const feature = payload.features?.[0];
  if (!feature) return null;
  const structures = Array.isArray(feature.properties.structures) ? feature.properties.structures as JsonRecord[] : [];
  const primary = structures.find((item) => item['primary-structure'] === true) ?? structures.sort((a, b) => Number(b['footprint.area'] ?? 0) - Number(a['footprint.area'] ?? 0))[0];
  return {
    parcelGeometry: feature.geometry,
    roofWkt: typeof primary?.['footprint.wkt'] === 'string' ? primary['footprint.wkt'] : null,
    roofAreaSqft: Number(primary?.['footprint.area'] ?? 0) || null,
    roofShape: primary?.['roof-characteristics.shape.value'] ?? null,
    roofMaterial: primary?.['roof-characteristics.material.class'] ?? null,
    objectCounts: {
      ac: Number(primary?.['roof-objects.ac-unit.count'] ?? 0),
      vents: Number(primary?.['roof-objects.roof-vent.count'] ?? 0),
      skylights: Number(primary?.['roof-objects.skylight.count'] ?? 0),
    },
    collection: feature.properties['metadata.collection'] ?? null,
    captureDate: feature.properties['metadata.ortho-date-estimate'] ?? null,
  };
}

async function elevationsAt(key: string, points: Array<{ lat: number; lon: number }>) {
  const line = `LINESTRING(${points.map((point) => `${point.lon} ${point.lat}`).join(',')})`;
  const dsmParams = new URLSearchParams({ wkt: line, srid: '4326', layer: 'urban,wide-area', 'unit-system': 'metric' });
  const dtmParams = new URLSearchParams({ wkt: line, srid: '4326', 'dem-priority': 'vexcel-dtm,public-dtm', 'unit-system': 'metric' });
  const [dsmResponse, dtmResponse] = await Promise.all([vexcel(key, `dsm/elevation?${dsmParams}`), vexcel(key, `dtm/elevation?${dtmParams}`)]);
  const dsm = await dsmResponse.json() as { wkt: string; collection?: string[]; layer?: string[] };
  const dtm = await dtmResponse.json() as { wkt: string; collection?: string[]; layer?: string[] };
  const dsmValues = parseElevationWkt(dsm.wkt);
  const dtmValues = parseElevationWkt(dtm.wkt);
  return {
    samples: points.map((point, index) => ({ ...point, dsmM: dsmValues[index] ?? null, dtmM: dtmValues[index] ?? null })),
    dsmCollection: dsm.collection ?? [], dsmLayer: dsm.layer ?? [], dtmCollection: dtm.collection ?? [], dtmLayer: dtm.layer ?? [],
  };
}

async function searchCandidates(key: string, costar: ReturnType<typeof costarIndex>, input: { query: string; lat: number; lon: number; radiusM: number; location?: string }) {
  const explicitPlace = input.location?.trim();
  const allCoverage = explicitPlace && /^(?:all (?:available )?(?:areas|vexcel coverage)|available vexcel coverage)$/i.test(explicitPlace);
  const place = explicitPlace ? (allCoverage ? null : explicitPlace) : locationPhrase(input.query);
  let searchBody: JsonRecord;
  let searchDescription: string;
  if (place) {
    const location = await geocodePlace(place);
    searchBody = { wkt: square(location.lat, location.lon, 20_000), srid: 4326 };
    searchDescription = `within available coverage near ${location.name}, ${location.region}`;
  } else {
    const collections = await availableEmbeddingCollections(key);
    searchBody = { collection: collections };
    searchDescription = `across all ${collections.length} available standard imagery collections`;
  }
  const cacheKey = `${input.query.trim().toLowerCase()}:${place || 'all-coverage'}`;
  const cached = embeddingSearchCache.get(cacheKey);
  let features: Array<{ geometry: JsonRecord; properties: JsonRecord }>;
  if (cached && cached.expires > Date.now()) features = cached.features;
  else {
    const response = await vexcel(key, 'embedding/extract', { method: 'POST', body: JSON.stringify({
      ...searchBody, 'search-text': input.query,
      include: 'score,geometry,collection', 'total-records': 24, 'page-size': 24,
    }) });
    const payload = await response.json() as { features?: Array<{ geometry: JsonRecord; properties: JsonRecord }> };
    features = payload.features ?? [];
    embeddingSearchCache.set(cacheKey, { expires: Date.now() + 5 * 60_000, features });
  }
  const unique = new Map<string, { geometry: JsonRecord; properties: JsonRecord; center: { lat: number; lon: number } }>();
  for (const feature of features) {
    const center = centroid(feature.geometry);
    unique.set(`${center.lat.toFixed(4)}:${center.lon.toFixed(4)}`, { ...feature, center });
  }
  return Promise.all([...unique.values()].slice(0, 12).map(async (feature, rank) => {
    const property = await propertyAt(key, feature.center.lat, feature.center.lon).catch(() => null);
    const costarProperty = costar.available ? matchCostar(costar, feature.center.lat, feature.center.lon) : null;
    return {
      id: `${feature.center.lat.toFixed(6)},${feature.center.lon.toFixed(6)}`,
      rank: rank + 1,
      lat: feature.center.lat,
      lon: feature.center.lon,
      score: Number(feature.properties.score ?? 0),
      matchReason: `Vexcel imagery match for “${input.query}” ${searchDescription}`,
      tileGeometry: feature.geometry,
      property,
      costar: costarProperty,
      imageryUrl: `/api/vexcel/imagery?lat=${feature.center.lat}&lon=${feature.center.lon}`,
    };
  }));
}

type ResolvedGeometry = {
  evidence: GeometryEvidence;
  roofAreaSqft: number;
  roofWidthM: number;
  roofDepthM: number;
  roofGeometry: MetricRoofGeometry;
  roofBounds: { x: number; y: number; width: number; height: number };
  obstructions: Obstruction[];
};

async function resolveCandidateGeometry(key: string, candidate: AgentCandidate): Promise<ResolvedGeometry | null> {
  const roofAreaSqft = candidate.property?.roofAreaSqft ?? null;
  const roofWkt = candidate.property?.roofWkt ?? null;
  const missing = (reason: string): null => null;
  if (!roofAreaSqft || !roofWkt) return missing('Vexcel did not return a roof outline and area.');
  const uncenteredRoofGeometry = roofWktToMetricGeometry(roofWkt, candidate.lat, candidate.lon, 0);
  const imageRadiusM = Math.min(250, Math.max(55, Math.sqrt(roofAreaSqft * .092903) * .9, geometryRequiredRadius(uncenteredRoofGeometry)));
  const roofWidthM = imageRadiusM * 2;
  const roofDepthM = imageRadiusM * 2;
  const roofGeometry = roofWktToMetricGeometry(roofWkt, candidate.lat, candidate.lon, imageRadiusM);
  if (!roofGeometry.length) return missing('Roof outline could not be projected.');
  const roofBounds = geometryBounds(roofGeometry, roofWidthM);
  const size = 12;
  const cellWidth = roofBounds.width / size;
  const cellDepth = roofBounds.height / size;
  const cells: Array<{ x: number; y: number; lat: number; lon: number }> = [];
  for (let row = 0; row < size; row += 1) for (let column = 0; column < size; column += 1) {
    const x = roofBounds.x + (column + .5) * cellWidth;
    const y = roofBounds.y + (row + .5) * cellDepth;
    if (insideMetricGeometry(x, y, roofGeometry)) cells.push({ x, y, ...metricPointToLonLat({ x, y }, candidate.lat, candidate.lon, imageRadiusM) });
  }
  if (cells.length < 2) return null;
  const elevations = await elevationsAt(key, cells.map(({ lat, lon }) => ({ lat, lon })));
  const valid = elevations.samples.map((sample, index) => ({ sample, cell: cells[index] })).filter((item) => item.cell && item.sample.dsmM !== null && item.sample.dtmM !== null);
  if (valid.length < 2) return null;
  const median = (values: number[]) => { const sorted = [...values].sort((a, b) => a - b); return sorted[Math.floor(sorted.length / 2)]; };
  const roofPlaneM = median(valid.map((item) => item.sample.dsmM!));
  const groundM = median(valid.map((item) => item.sample.dtmM!));
  const obstructions = valid.filter((item) => item.sample.dsmM! - roofPlaneM >= .75).map((item) => ({ x: item.cell.x - cellWidth / 2, y: item.cell.y - cellDepth / 2, width: cellWidth, depth: cellDepth, heightM: item.sample.dsmM! - roofPlaneM }));
  const rawHeight = roofPlaneM - groundM;
  return {
    evidence: {
      candidateId: candidate.id, available: true, roofAreaSqft, buildingHeightM: rawHeight >= 1 ? rawHeight : null,
      validSamples: valid.length, obstructionCount: obstructions.length,
      dsmCollections: elevations.dsmCollection, dtmCollections: elevations.dtmCollection, reason: null,
    },
    roofAreaSqft, roofWidthM, roofDepthM, roofGeometry, roofBounds, obstructions,
  };
}

function unavailableGeometry(candidate: AgentCandidate, reason: string): GeometryEvidence {
  return { candidateId: candidate.id, available: false, roofAreaSqft: candidate.property?.roofAreaSqft ?? null, buildingHeightM: null, validSamples: 0, obstructionCount: 0, dsmCollections: [], dtmCollections: [], reason };
}

const timeZoneFor = (lon: number) => lon < -112 ? 'America/Los_Angeles' : lon < -100 ? 'America/Denver' : lon < -85 ? 'America/Chicago' : 'America/New_York';
function offsetForDate(date: string, timeZone: string) {
  const instant = new Date(`${date}T12:00:00Z`);
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(instant).map((part) => [part.type, part.value]));
  return (Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second)) - instant.getTime()) / 3_600_000;
}

async function simulateCandidate(key: string, candidate: AgentCandidate, dates: string[], targetHours: number, targetAreaSqft: number, resolved?: ResolvedGeometry | null): Promise<SunlightEvidence> {
  const geometry = resolved === undefined ? await resolveCandidateGeometry(key, candidate).catch(() => null) : resolved;
  if (!geometry) return { candidateId: candidate.id, dates, targetHours, targetAreaSqft, sharedAreaSqft: null, perDate: dates.map((date) => ({ date, areaMeetingTargetSqft: null, meanHours: null })), geometry: unavailableGeometry(candidate, 'Roof or DSM/DTM geometry is unavailable.') };
  const scale = Math.sqrt(Math.min(1, targetAreaSqft / geometry.roofAreaSqft));
  const selection: AreaSelection = { x: geometry.roofBounds.x + geometry.roofBounds.width * (1 - scale) / 2, y: geometry.roofBounds.y + geometry.roofBounds.height * (1 - scale) / 2, width: geometry.roofBounds.width * scale, height: geometry.roofBounds.height * scale };
  const results = dates.map((date) => simulate({
    date, minute: 720, timezoneOffsetHours: offsetForDate(date, timeZoneFor(candidate.lon)), lat: candidate.lat, lon: candidate.lon,
    roofAreaSqft: geometry.roofAreaSqft, roofWidthM: geometry.roofWidthM, roofDepthM: geometry.roofDepthM,
    roofGeometry: geometry.roofGeometry, selection, obstructions: geometry.obstructions, targetHours,
  }));
  return {
    candidateId: candidate.id, dates, targetHours, targetAreaSqft,
    sharedAreaSqft: sharedMeetingArea(results, targetHours),
    perDate: results.map((result, index) => ({ date: dates[index], areaMeetingTargetSqft: result.meetingTargetAreaSqft, meanHours: result.estimatedHours })),
    geometry: geometry.evidence,
  };
}

export function vexcelApiPlugin(root: string) {
  const costar = costarIndex(root);
  const watchDirectory = resolve(root, 'runtime');
  const watchPath = resolve(watchDirectory, 'photon-watches.json');
  const watches = new Map<string, PhotonWatch>((existsSync(watchPath) ? JSON.parse(readFileSync(watchPath, 'utf8')) as PhotonWatch[] : []).map((watch) => [watch.id, watch]));
  const saveWatches = () => { mkdirSync(watchDirectory, { recursive: true }); writeFileSync(watchPath, JSON.stringify([...watches.values()], null, 2)); };
  const openingFingerprint = (candidate: AgentCandidate) => `${candidate.id}:${candidate.costar?.listing?.active ? 'active' : 'inactive'}:${candidate.costar?.listing?.statuses.join('|') ?? ''}:${candidate.costar?.apartment?.availableUnits ?? 0}`;
  const isOpening = (candidate: AgentCandidate) => Boolean(candidate.costar?.listing?.active || (candidate.costar?.apartment?.availableUnits ?? 0) > 0);
  let scanning = false;
  const scanWatches = async () => {
    const key = configuredKey(root);
    if (!key || !photonStatus().configured || scanning || !watches.size) return;
    scanning = true;
    try {
      for (const watch of watches.values()) {
        try {
          const candidates = await searchCandidates(key, costar, { query: watch.goal, location: watch.location, lat: watch.lat, lon: watch.lon, radiusM: watch.radiusM });
          const currentOpenings = candidates.filter(isOpening);
          const known = new Set(watch.knownOpenings);
          const newOpenings = currentOpenings.filter((candidate) => !known.has(openingFingerprint(candidate)));
          watch.knownOpenings = currentOpenings.map(openingFingerprint);
          watch.lastCheckedAt = new Date().toISOString();
          if (!newOpenings.length) { saveWatches(); continue; }
          const geometryCache = new Map<string, Promise<ResolvedGeometry | null>>();
          const output = await runLandLensAgent({ goal: watch.goal, location: locationPhrase(watch.goal) || 'all available Vexcel coverage', dates: watch.dates, targetHours: watch.targetHours, targetAreaSqft: watch.targetAreaSqft, source: 'photon-watch' }, {
            search: async () => candidates,
            geometry: async (candidate) => { if (!geometryCache.has(candidate.id)) geometryCache.set(candidate.id, resolveCandidateGeometry(key, candidate).catch(() => null)); const resolved = await geometryCache.get(candidate.id)!; return resolved?.evidence ?? unavailableGeometry(candidate, 'Roof or DSM/DTM geometry is unavailable.'); },
            simulate: async (candidate, dates, hours, area) => { if (!geometryCache.has(candidate.id)) geometryCache.set(candidate.id, resolveCandidateGeometry(key, candidate).catch(() => null)); return simulateCandidate(key, candidate, dates, hours, area, await geometryCache.get(candidate.id)!); },
          }, () => {});
          const simulationById = new Map(output.simulations.map((item) => [item.candidateId, item]));
          for (const candidate of newOpenings) if (!simulationById.has(candidate.id)) simulationById.set(candidate.id, await simulateCandidate(key, candidate, watch.dates, watch.targetHours, watch.targetAreaSqft));
          const ranked = newOpenings.sort((a, b) => (simulationById.get(b.id)?.sharedAreaSqft ?? -1) - (simulationById.get(a.id)?.sharedAreaSqft ?? -1));
          const lines = ranked.slice(0, 3).map((candidate, index) => { const sunlight = simulationById.get(candidate.id)?.sharedAreaSqft; const name = candidate.costar?.buildingName || candidate.costar?.address || candidate.id; return `${index + 1}. ${name} — ${sunlight === null || sunlight === undefined ? 'sunlight not assessed' : `${Math.round(sunlight).toLocaleString()} ft² meets ${watch.targetHours} h on every date`}`; });
          await sendPhotonMessage(watch.spaceId, `LandLens found ${newOpenings.length} new opening${newOpenings.length === 1 ? '' : 's'} for your roof goal:\n\n${lines.join('\n')}\n\nOpen LandLens to review the roof outlines, listings, and sunlight evidence.`);
          saveWatches();
        } catch (error) { console.warn(`Photon watch ${watch.id} failed:`, error instanceof Error ? error.message : String(error)); }
      }
    } finally { scanning = false; }
  };
  const middleware: Connect.NextHandleFunction = async (req, res, next) => {
    if (!req.url) return next();
    const url = new URL(req.url, 'http://localhost');
    try {
      if (await handleMonthlyClimate(url.pathname, req, res)) return;
      if (await handleMlRoute(url.pathname, req, res)) return;
      if (await handleRunsRoute(url.pathname, req, res, root)) return;
      if (url.pathname === '/api/cropfit/status') {
        const response = await fetch(`${modelBaseUrl()}/health`, { signal: AbortSignal.timeout(3_000) });
        return json(res, response.status, await response.json());
      }
      if (url.pathname === '/api/cropfit/predict' && req.method === 'POST') {
        const input = await body(req);
        const latitude = Number(input.latitude); const longitude = Number(input.longitude);
        const climate = Number.isFinite(latitude) && Number.isFinite(longitude) ? await monthlyClimateAt(latitude, longitude).catch(() => null) : null;
        const response = await fetch(`${modelBaseUrl()}/predict`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...input,
            climate: climate ? CLIMATE_MONTHS.map((month, index) => ({ month: month.toUpperCase(), temperatureC: climate.temperatureC[index], precipitationMmDay: climate.precipitationMmDay[index], solarMjM2Day: climate.solarMjM2Day[index] })) : undefined,
            climateHistory: climate?.history.map((year) => CLIMATE_MONTHS.map((month, index) => ({ month: month.toUpperCase(), year: year.year, temperatureC: year.temperatureC[index], precipitationMmDay: year.precipitationMmDay[index], solarMjM2Day: year.solarMjM2Day[index] }))),
          }), signal: AbortSignal.timeout(35_000),
        });
        const payload = await response.json();
        return json(res, response.status, response.ok ? payload : { error: payload.detail || 'CropFit prediction failed.' });
      }
      if (url.pathname === '/api/cropfit/recommend' && req.method === 'POST') {
        const input = await body(req);
        const response = await fetch(`${modelBaseUrl()}/recommend`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal: AbortSignal.timeout(5_000),
        });
        const payload = await response.json();
        return json(res, response.status, response.ok ? payload : { error: payload.detail || 'CropFit recommendation failed.' });
      }
      if (url.pathname === '/api/rural/compare' && req.method === 'POST') {
        const input = await body(req);
        const goal = ['balanced', 'sun', 'low-irrigation'].includes(String(input.goal)) ? String(input.goal) as RuralGoal : 'balanced';
        const locations = (Array.isArray(input.locations) ? input.locations : String(input.locations || '').split(/[;\n]/))
          .map(String).map((location) => location.trim()).filter(Boolean).slice(0, 8);
        if (locations.length < 2) return json(res, 400, { error: 'Enter at least two places to compare.' });
        const settled = await Promise.allSettled(locations.map((location) => ruralClimate(location, goal)));
        const results = settled.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []);
        const errors = settled.flatMap((result, index) => result.status === 'rejected' ? [{ location: locations[index], error: result.reason instanceof Error ? result.reason.message : 'Lookup failed.' }] : []);
        if (results.length < 2) return json(res, 502, { error: 'Fewer than two places returned usable climate evidence.', details: errors });
        results.sort((a, b) => Number((b as JsonRecord).score) - Number((a as JsonRecord).score));
        return json(res, 200, { goal, results, errors, method: 'Climate-fit score from NASA POWER annual climatology. Parcel, ownership, water-rights, and soil suitability are not assessed.' });
      }
      if (!url.pathname.startsWith('/api/vexcel/')) return next();
      const key = configuredKey(root);
      if (!key) return json(res, 503, { error: 'Vexcel access is not configured on this server.' });
      if (url.pathname === '/api/vexcel/status') return json(res, 200, { configured: true, search: 'live', agent: landLensAgentStatus(), photon: photonStatus(), ml: mlModelStatus() });
      if (url.pathname === '/api/vexcel/watch' && req.method === 'POST') {
        if (!photonStatus().configured) return json(res, 503, { error: 'Photon is not configured. Add PHOTON_API_KEY, PHOTON_PROJECT_ID, and PHOTON_AGENT_USER_ID on the server.' });
        const input = await body(req);
        const platform = String(input.platform || '') as PhotonPlatform;
        const handle = String(input.handle || '').trim();
        const lat = Number(input.lat); const lon = Number(input.lon);
        const radiusM = Math.min(20_000, Math.max(500, Number(input.radiusM) || 8_000));
        const goal = String(input.goal || 'Find a suitable rooftop opening for urban agriculture.');
        const location = String(input.location || `${lat}, ${lon}`);
        const dates = Array.isArray(input.dates) ? input.dates.map(String).slice(0, 6) : ['2026-04-15', '2026-10-15'];
        const targetHours = Math.min(14, Math.max(1, Number(input.targetHours) || 6));
        const targetAreaSqft = Math.max(100, Number(input.targetAreaSqft) || 5_000);
        if (!['imessage', 'sms', 'telegram', 'email', 'whatsapp_business'].includes(platform) || !handle || !Number.isFinite(lat) || !Number.isFinite(lon)) return json(res, 400, { error: 'Platform, destination, and geographic scope are required.' });
        const current = await searchCandidates(key, costar, { query: goal, location, lat, lon, radiusM });
        const conversation = await createPhotonConversation(platform, handle);
        const watch: PhotonWatch = { id: `watch_${Date.now().toString(36)}`, goal, location, lat, lon, radiusM, dates, targetHours, targetAreaSqft, platform, handle, spaceId: conversation.spaceId, knownOpenings: current.filter(isOpening).map(openingFingerprint), createdAt: new Date().toISOString(), lastCheckedAt: null };
        const message = await sendPhotonMessage(conversation.spaceId, `LandLens is watching ${location} for new rooftop openings that match:\n\n${goal}\n\nNew listings will be checked with property records, roof geometry, and sunlight before you hear about them.`);
        watches.set(watch.id, watch); saveWatches();
        return json(res, 201, { id: watch.id, status: 'watching', messageStatus: message.status, checkedEveryMinutes: 15 });
      }
      if (url.pathname === '/api/vexcel/search' && req.method === 'POST') {
        const input = await body(req);
        const query = String(input.query || 'large flat unobstructed commercial rooftop');
        const searchLocation = typeof input.location === 'string' ? input.location.trim() : undefined;
        const hydrated = await searchCandidates(key, costar, { query, location: searchLocation, lat: 0, lon: 0, radiusM: 20_000 });
        return json(res, 200, { query, results: hydrated, source: costar.available ? 'Vexcel available embedding collections + property geometry + CoStar local property inventory' : 'Vexcel available embedding collections + property geometry' });
      }
      // One roof by coordinates, shaped like a search result (used by the home page showcase).
      if (url.pathname === '/api/vexcel/site' && req.method === 'GET') {
        const lat = Number(url.searchParams.get('lat')); const lon = Number(url.searchParams.get('lon'));
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return json(res, 400, { error: 'lat and lon are required.' });
        const property = await propertyAt(key, lat, lon).catch(() => null);
        return json(res, 200, {
          id: `${lat.toFixed(6)},${lon.toFixed(6)}`, rank: 1, lat, lon, score: 0, matchReason: 'Selected roof',
          property, costar: costar.available ? matchCostar(costar, lat, lon) : null,
          imageryUrl: `/api/vexcel/imagery?lat=${lat}&lon=${lon}`,
        });
      }
      if (url.pathname === '/api/vexcel/elevation' && req.method === 'POST') {
        const input = await body(req);
        const points = Array.isArray(input.points) ? input.points.slice(0, 196).map((point) => ({ lat: Number((point as JsonRecord).lat), lon: Number((point as JsonRecord).lon) })) : [];
        if (points.length < 2 || points.some((point) => !Number.isFinite(point.lat) || !Number.isFinite(point.lon))) return json(res, 400, { error: 'At least two valid sample points are required.' });
        return json(res, 200, await elevationsAt(key, points));
      }
      if (url.pathname === '/api/vexcel/compare' && req.method === 'POST') {
        const input = await body(req);
        const lat = Number(input.lat); const lon = Number(input.lon);
        const radiusM = Math.min(20_000, Math.max(500, Number(input.radiusM) || 8_000));
        const query = String(input.query || 'large flat commercial rooftop');
        const searchLocation = typeof input.location === 'string' ? input.location.trim() : undefined;
        const dates = Array.isArray(input.dates) ? input.dates.map(String).slice(0, 6) : ['2026-04-15', '2026-10-15'];
        const targetHours = Math.min(14, Math.max(1, Number(input.targetHours) || 6));
        const targetAreaSqft = Math.max(100, Number(input.targetAreaSqft) || 5_000);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return json(res, 400, { error: 'A valid search center is required.' });
        const candidates = await searchCandidates(key, costar, { query, location: searchLocation, lat, lon, radiusM });
        const simulations: SunlightEvidence[] = [];
        for (const candidate of candidates) simulations.push(await simulateCandidate(key, candidate, dates, targetHours, targetAreaSqft));
        const byId = new Map(candidates.map((candidate) => [candidate.id, candidate]));
        simulations.sort((a, b) => {
          const difference = (b.sharedAreaSqft ?? -1) - (a.sharedAreaSqft ?? -1);
          if (Math.abs(difference) <= 100) {
            const tourDifference = (byId.get(b.candidateId)?.costar?.matterport.length ?? 0) - (byId.get(a.candidateId)?.costar?.matterport.length ?? 0);
            if (tourDifference !== 0) return tourDifference;
          }
          return difference;
        });
        return json(res, 200, { mode: 'direct', query, dates, targetHours, targetAreaSqft, candidates, simulations });
      }
      if (url.pathname === '/api/vexcel/agent' && req.method === 'POST') {
        const input = await body(req);
        const lat = Number(input.lat); const lon = Number(input.lon);
        const radiusM = Math.min(20_000, Math.max(500, Number(input.radiusM) || 8_000));
        const goal = String(input.goal || 'Find a suitable rooftop for urban agriculture.');
        const searchLocation = typeof input.location === 'string' ? input.location.trim() : undefined;
        const dates = Array.isArray(input.dates) ? input.dates.map(String).slice(0, 6) : ['2026-04-15', '2026-10-15'];
        const targetHours = Math.min(14, Math.max(1, Number(input.targetHours) || 6));
        const targetAreaSqft = Math.max(100, Number(input.targetAreaSqft) || 5_000);
        const cropProfiles = (Array.isArray(input.cropProfiles) ? input.cropProfiles : []).filter((crop): crop is MlCrop => Boolean(crop) && typeof (crop as MlCrop).id === 'string' && typeof (crop as MlCrop).name === 'string' && [(crop as MlCrop).sunHours, (crop as MlCrop).tempMinC, (crop as MlCrop).tempMaxC, (crop as MlCrop).growMonths].every(Number.isFinite)).slice(0, 6);
        const preferredMonth = Number.isInteger(input.preferredMonth) && Number(input.preferredMonth) >= 0 && Number(input.preferredMonth) <= 11 ? Number(input.preferredMonth) : new Date().getMonth();
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return json(res, 400, { error: 'A valid search center is required.' });
        if (!landLensAgentStatus().configured) return json(res, 503, { error: 'Agent model access is not configured.', fallback: '/api/vexcel/compare' });
        res.statusCode = 200;
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache, no-transform');
        res.setHeader('Connection', 'keep-alive');
        const send = (value: unknown) => res.write(`data: ${JSON.stringify(value)}\n\n`);
        const geometryCache = new Map<string, Promise<ResolvedGeometry | null>>();
        const candidateCache = new Map<string, AgentCandidate>();
        const search = async (searchQuery: string) => {
          const results = await searchCandidates(key, costar, { query: searchQuery, location: searchLocation, lat, lon, radiusM });
          results.forEach((candidate) => candidateCache.set(candidate.id, candidate));
          return results;
        };
        const geometry = async (candidate: AgentCandidate) => {
          if (!geometryCache.has(candidate.id)) geometryCache.set(candidate.id, resolveCandidateGeometry(key, candidate).catch(() => null));
          const resolved = await geometryCache.get(candidate.id)!;
          return resolved?.evidence ?? unavailableGeometry(candidate, 'Roof or DSM/DTM geometry is unavailable.');
        };
        const sunlight = async (candidate: AgentCandidate, requestedDates: string[], requestedHours: number, requestedArea: number) => {
          if (!geometryCache.has(candidate.id)) geometryCache.set(candidate.id, resolveCandidateGeometry(key, candidate).catch(() => null));
          return simulateCandidate(key, candidate, requestedDates, requestedHours, requestedArea, await geometryCache.get(candidate.id)!);
        };
        try {
          const output = await runLandLensAgent({ goal, followUp: typeof input.followUp === 'string' ? input.followUp : undefined, location: searchLocation || locationPhrase(goal) || 'all available Vexcel coverage', dates, targetHours, targetAreaSqft, crops: Array.isArray(input.crops) ? input.crops.map(String).slice(0, 6) : undefined, cropProfiles, preferredMonth, source: input.source === 'guided' ? 'guided' : 'search' }, { search, geometry, simulate: sunlight }, (event) => send({ type: 'progress', ...event }), (event) => send({ type: 'trace', event }));
          const simulatedIds = new Set(output.simulations.map((item) => item.candidateId));
          for (const candidate of output.candidates) if (!simulatedIds.has(candidate.id)) output.simulations.push(await sunlight(candidate, dates, targetHours, targetAreaSqft));
          const byId = new Map(output.candidates.map((candidate) => [candidate.id, candidate]));
          // Every roof gets a crop-model score, even ones the agent did not ask about.
          const scored = new Set(output.predictions.map((item) => item.siteId));
          const unscored = output.candidates.filter((candidate) => !scored.has(candidate.id));
          if (cropProfiles.length && unscored.length) {
            try {
              const response = await predictCropSuitability({ crops: cropProfiles, preferredMonth, targetAreaSqft, targetSunHours: targetHours, sites: await roofSites(unscored, new Map(output.simulations.map((item) => [item.candidateId, item]))) });
              output.predictions.push(...response.predictions);
              output.mlModel ??= response.model;
            } catch (reason) {
              output.mlModel = { name: 'CropFit', version: null, source: 'ml', error: reason instanceof Error ? reason.message : 'Crop model failed.' };
            }
          }
          const suitability = siteSuitability({ model: output.mlModel ?? { name: 'none', version: null, source: 'ml', error: null }, predictions: output.predictions });
          const rankScore = (id: string, shared: number | null) => cropProfiles.length ? combinedRoofScore(shared, targetAreaSqft, suitability.get(id) ?? null) : null;
          output.simulations.sort((a, b) => {
            const scoreA = rankScore(a.candidateId, a.sharedAreaSqft);
            const scoreB = rankScore(b.candidateId, b.sharedAreaSqft);
            if (scoreA !== null && scoreB !== null && Math.abs(scoreB - scoreA) > 0.01) return scoreB - scoreA;
            const difference = (b.sharedAreaSqft ?? -1) - (a.sharedAreaSqft ?? -1);
            if (Math.abs(difference) <= 100) {
              const tourDifference = (byId.get(b.candidateId)?.costar?.matterport.length ?? 0) - (byId.get(a.candidateId)?.costar?.matterport.length ?? 0);
              if (tourDifference !== 0) return tourDifference;
            }
            return difference;
          });
          send({ type: 'result', mode: 'deep-agent', dates, targetHours, targetAreaSqft, ...output });
        } catch (error) {
          send({ type: 'error', error: error instanceof Error ? error.message : 'Agent comparison failed.' });
        } finally { res.end(); }
        return;
      }
      if (url.pathname === '/api/vexcel/imagery') {
        const lat = Number(url.searchParams.get('lat'));
        const lon = Number(url.searchParams.get('lon'));
        const bands = url.searchParams.get('bands') === 'irg' ? 'irg' : 'rgb';
        const radiusM = Math.min(250, Math.max(30, Number(url.searchParams.get('radiusM')) || 55));
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return json(res, 400, { error: 'Invalid coordinates.' });
        const area = square(lat, lon, radiusM);
        const response = await vexcel(key, 'ortho/extract', { method: 'POST', body: JSON.stringify({ wkt: area, srid: 4326, layer: LAYERS, bands, crop: 'bounding_box', 'destination-dimensions': '800,800', 'image-format': 'jpeg' }) });
        res.statusCode = 200;
        res.setHeader('Content-Type', response.headers.get('content-type') || 'image/jpeg');
        res.setHeader('X-LandLens-Bands', bands);
        res.setHeader('Cache-Control', 'private, max-age=3600');
        res.end(Buffer.from(await response.arrayBuffer()));
        return;
      }
      return json(res, 404, { error: 'Unknown Vexcel endpoint.' });
    } catch (error) {
      return json(res, 502, { error: error instanceof Error ? error.message : 'Vexcel request failed.' });
    }
  };

  return {
    name: 'landlens-vexcel-api',
    configureServer(server: { middlewares: { use: (handler: Connect.NextHandleFunction) => void }; httpServer?: { once: (event: string, listener: () => void) => void } }) { server.middlewares.use(middleware); const timer = setInterval(scanWatches, 15 * 60_000); timer.unref(); server.httpServer?.once('close', () => clearInterval(timer)); },
    configurePreviewServer(server: { middlewares: { use: (handler: Connect.NextHandleFunction) => void } }) { server.middlewares.use(middleware); },
  };
}
