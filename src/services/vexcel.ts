export type RoofProperty = {
  parcelGeometry: GeoJSON.Geometry;
  roofWkt: string | null;
  roofAreaSqft: number | null;
  roofShape: string | null;
  roofMaterial: string | null;
  objectCounts: { ac: number; vents: number; skylights: number };
  collection: string | null;
  captureDate: string | null;
};

export type SearchResult = {
  id: string;
  rank: number;
  lat: number;
  lon: number;
  score: number;
  matchReason: string;
  tileGeometry: GeoJSON.Geometry;
  property: RoofProperty | null;
  costar: CostarProperty | null;
  imageryUrl: string;
};

export type CostarProperty = {
  propertyId: number;
  matchDistanceM: number;
  buildingName: string | null;
  address: string;
  propertyType: string;
  buildingClass: string | null;
  buildingRating: number | null;
  grossBuildingAreaSqft: number | null;
  rentableBuildingAreaSqft: number | null;
  stories: number | null;
  yearBuilt: number | null;
  lotSize: number | null;
  lotSizeUnit: string | null;
  zoning: string | null;
  photoUrl: string | null;
  listing: null | { count: number; types: string[]; statuses: string[]; active: boolean; brokerages: string[]; certifiedFreshDate: string | null };
  apartment: null | { units: number | null; availableUnits: number; minRent: number | null; maxRent: number | null; management: string | null };
  matterport: Array<{ modelId: string; caption: string; thumbnailUrl: string | null }>;
  source: string;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
  source: string;
};

export async function searchVexcel(input: { query: string }, signal?: AbortSignal) {
  const response = await fetch('/api/vexcel/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Vexcel search failed.');
  return payload as SearchResponse;
}
export type ElevationSample = { lat: number; lon: number; dsmM: number | null; dtmM: number | null };
export type ElevationResponse = { samples: ElevationSample[]; dsmCollection: string[]; dsmLayer: string[]; dtmCollection: string[]; dtmLayer: string[] };

export async function fetchElevations(points: Array<{ lat: number; lon: number }>, signal?: AbortSignal) {
  const response = await fetch('/api/vexcel/elevation', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ points }), signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Elevation sampling failed.');
  return payload as ElevationResponse;
}

export type GeometryEvidence = {
  candidateId: string;
  available: boolean;
  roofAreaSqft: number | null;
  buildingHeightM: number | null;
  validSamples: number;
  obstructionCount: number;
  dsmCollections: string[];
  dtmCollections: string[];
  reason: string | null;
};

export type SunlightEvidence = {
  candidateId: string;
  dates: string[];
  targetHours: number;
  targetAreaSqft: number;
  sharedAreaSqft: number | null;
  perDate: Array<{ date: string; areaMeetingTargetSqft: number | null; meanHours: number | null }>;
  geometry: GeometryEvidence;
};

export type AgentComparison = {
  mode: 'deep-agent' | 'direct';
  model?: string;
  dates: string[];
  targetHours: number;
  targetAreaSqft: number;
  candidates: SearchResult[];
  simulations: SunlightEvidence[];
  narrative?: null | {
    summary: string;
    criteria: { location: string; targetAreaSqft: number; targetHours: number; dates: string[] };
    explanations: Array<{ candidateId: string; explanation: string }>;
    unknowns: string[];
  };
};

export type ComparisonInput = {
  goal: string;
  followUp?: string;
  location: string;
  lat: number;
  lon: number;
  radiusM: number;
  dates: string[];
  targetHours: number;
  targetAreaSqft: number;
};

export type AgentProgress = { stage: 'planning' | 'imagery' | 'property' | 'geometry' | 'sunlight' | 'ranking'; message: string };

export type PhotonWatchInput = ComparisonInput & { platform: 'imessage' | 'sms' | 'telegram' | 'email' | 'whatsapp_business'; handle: string };

export async function createPhotonWatch(input: PhotonWatchInput, signal?: AbortSignal) {
  const response = await fetch('/api/vexcel/watch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Photon watch setup failed.');
  return payload as { id: string; status: 'watching'; messageStatus: string; checkedEveryMinutes: number };
}

async function directComparison(input: ComparisonInput, signal?: AbortSignal) {
  const response = await fetch('/api/vexcel/compare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...input, query: input.goal }), signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Roof comparison failed.');
  return payload as AgentComparison;
}

export async function runAgentComparison(input: ComparisonInput, onProgress: (progress: AgentProgress) => void, signal?: AbortSignal): Promise<AgentComparison> {
  const response = await fetch('/api/vexcel/agent', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal });
  if (response.status === 503) {
    onProgress({ stage: 'planning', message: 'Model unavailable; running the same comparison directly' });
    return directComparison(input, signal);
  }
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || 'Deep Agents comparison failed.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: AgentComparison | null = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    for (const event of events) {
      const line = event.split('\n').find((item) => item.startsWith('data: '));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.type === 'progress') onProgress(payload as AgentProgress);
      if (payload.type === 'error') throw new Error(payload.error || 'Deep Agents comparison failed.');
      if (payload.type === 'result') result = payload as AgentComparison;
    }
  }
  if (!result) throw new Error('The agent finished without a comparison result.');
  return result;
}
