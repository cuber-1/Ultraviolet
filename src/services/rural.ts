export type RuralGoal = 'balanced' | 'sun' | 'low-irrigation';

export type RuralClimateResult = {
  query: string;
  name: string;
  region: string;
  lat: number;
  lon: number;
  timezone: string;
  score: number;
  solarMjM2Day: number;
  precipitationMmDay: number;
  temperatureC: number;
  temperatureMaxC: number;
  temperatureMinC: number;
  reason: string;
  period: string;
  source: string;
  soilAssessed: false;
  parcelAssessed: false;
};

export type RuralComparison = {
  goal: RuralGoal;
  results: RuralClimateResult[];
  errors: Array<{ location: string; error: string }>;
  method: string;
};

export async function compareRuralLocations(locations: string[], goal: RuralGoal, signal?: AbortSignal) {
  const response = await fetch('/api/rural/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locations, goal }),
    signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Rural comparison failed.');
  return payload as RuralComparison;
}
