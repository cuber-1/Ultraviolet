import { applyModel, type LocationPlan, type MonthlyClimate } from '../src/services/cropPlan.ts';
import type { CropPrediction } from '../src/services/vexcel.ts';

const climate: MonthlyClimate = {
  query: 'test', name: 'Test County', region: 'TX', lat: 30, lon: -96,
  temperatureC: Array(12).fill(22), solarMjM2Day: Array(12).fill(18), precipitationMmDay: Array(12).fill(3),
  history: [], annual: { temperatureC: 22, solarMjM2Day: 18, precipitationMmDay: 3 }, source: 'test',
};
const basePlan = (): LocationPlan => ({ climate, timings: [], moveInMonth: null, score: 0, reasons: [] });
const prediction = (cropId: string, suitability: number, observed?: number): CropPrediction => ({
  siteId: 'test', cropId, suitability, plantMonth: 2, harvestMonth: 5, confidence: .8,
  expectedYield: null, notes: null, source: 'ml',
  observedYieldEvidence: observed === undefined ? null : {
    county: 'Test County', state: 'TX', distanceKm: 10, years: [2024, 2025], observations: 2,
    meanPercentile: observed, p10Percentile: observed, p90Percentile: observed, meanYieldBushelsPerAcre: 100,
    observedYieldPrior: { expectedPercentile: observed, interval80: [0, 1], interval90: [0, 1], historyBucket: '2-3', calibrationExamples: 100 },
    history: [], evidenceGrade: 'observed-county-prior', source: 'USDA', disclaimer: 'County evidence.',
  },
});

const lowObserved = applyModel(basePlan(), [prediction('corn', .95, .2)], 2);
const highObserved = applyModel(basePlan(), [prediction('corn', .6, .8)], 2);
if (lowObserved.score !== 20 || highObserved.score !== 80 || highObserved.score <= lowObserved.score) {
  throw new Error('Rural ranking did not prefer the validated observed prior over climate-only suitability.');
}
const unsupported = applyModel(basePlan(), [prediction('tomatoes', .7)], 2);
if (unsupported.score !== 70 || unsupported.rankingEvidence?.method !== 'agroclimatic') {
  throw new Error('CropFit suitability was not retained for crops without USDA evidence.');
}
const mixed = applyModel(basePlan(), [prediction('corn', .8, .4), prediction('tomatoes', .6)], 2);
if (mixed.score !== 50 || mixed.rankingEvidence?.observedCrops !== 1 || !mixed.reasons[0]?.includes('USDA')) {
  throw new Error('Mixed rural evidence was not combined or labelled correctly.');
}
console.log('Rural ranking verified: USDA prior for supported crops, CropFit for the rest');
