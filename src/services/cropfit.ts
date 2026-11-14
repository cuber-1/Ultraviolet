export type CropFitMonth = {
  month: string;
  monthIndex: number;
  score: number;
  uncertainty: number;
  temperatureC: number;
  precipitationMmDay: number;
  solarMjM2Day: number;
  components: { temperature: number; water: number; soil_ph: number; solar: number };
  historicalP10?: number;
  historicalMedian?: number;
  historicalP90?: number;
  reliability?: number;
};

export type CropFitPrediction = {
  crop: string;
  profile: { scientific_name: string; common_name: string; category: string; growing_days_min: number; growing_days_max: number };
  location: { latitude: number; longitude: number };
  score: number;
  confidence: number;
  bestPlantingMonth: string;
  bestReliablePlantingMonth: string;
  plantingReliability: { years: number; successRate: number; p10Score: number; medianScore: number; p90Score: number; threshold: number } | null;
  observedYieldEvidence: { county: string; state: string; distanceKm: number; years: number[]; observations: number; meanPercentile: number; p10Percentile: number; p90Percentile: number; meanYieldBushelsPerAcre: number; history: Array<{ year: number; yieldBushelsPerAcre: number; percentile: number }>; evidenceGrade: string; source: string; disclaimer: string } | null;
  suitableMonths: string[];
  growingDays: { min: number; max: number };
  limitingFactors: Array<{ factor: string; score: number }>;
  monthlyCurve: CropFitMonth[];
  model: { model: string; labelType: string; profiles: number; examples: number; metrics: { mae: number; r2: number; p90AbsoluteError: number } };
  evidenceGrade: 'agroclimatic-screening' | 'demo-vector-map';
  disclaimer: string;
};

export async function predictCropFit(input: { crop: string; latitude: number; longitude: number; soilPh: number; irrigated: boolean }, signal?: AbortSignal) {
  const response = await fetch('/api/cropfit/predict', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'CropFit prediction failed. Start the local CropFit service with npm run ml:serve.');
  return payload as CropFitPrediction;
}

export type CropRecommendation = {
  crop: string; score: number; bestPlantingMonth: string; tags: string[]; reasons: string[]; sourceExample: string;
};

export async function recommendCrops(input: {
  latitude: number; longitude: number; acreage?: number; environment?: 'urban' | 'suburban' | 'rural';
  irrigated?: boolean; lowMaintenance?: boolean; commercial?: boolean; preferences?: string[];
}, signal?: AbortSignal) {
  const response = await fetch('/api/cropfit/recommend', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'CropFit recommendation failed.');
  return payload as { mode: string; recommendations: CropRecommendation[]; matchedExamples: Array<{ id: string; location: string; similarity: number }>; disclaimer: string };
}
