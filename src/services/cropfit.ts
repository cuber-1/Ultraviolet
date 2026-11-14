export type CropFitMonth = {
  month: string;
  monthIndex: number;
  score: number;
  uncertainty: number;
  temperatureC: number;
  precipitationMmDay: number;
  solarMjM2Day: number;
  components: { temperature: number; water: number; soil_ph: number; solar: number };
};

export type CropFitPrediction = {
  crop: string;
  profile: { scientific_name: string; common_name: string; category: string; growing_days_min: number; growing_days_max: number };
  location: { latitude: number; longitude: number };
  score: number;
  confidence: number;
  bestPlantingMonth: string;
  suitableMonths: string[];
  growingDays: { min: number; max: number };
  limitingFactors: Array<{ factor: string; score: number }>;
  monthlyCurve: CropFitMonth[];
  model: { model: string; labelType: string; profiles: number; examples: number; metrics: { mae: number; r2: number; p90AbsoluteError: number } };
  evidenceGrade: 'agroclimatic-screening';
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
