import { readFileSync } from 'node:fs';

type Candidate = {
  crop: string;
  observations: number;
  coverage: number;
  spearman: number | null;
  bootstrap95: [number | null, number | null];
  finalTest: {
    observations: number;
    coverage: number;
    spearman: number | null;
    bootstrap95: [number | null, number | null];
  };
  passed: boolean;
};

const report = JSON.parse(readFileSync(
  new URL('../machine-learning/evaluation/crop-expansion-validation-v2.json', import.meta.url),
  'utf8',
)) as { acceptedCrops: string[]; candidates: Candidate[]; dataNotes: string[] };

const passesBlock = (block: Pick<Candidate, 'observations' | 'coverage' | 'spearman' | 'bootstrap95'>) => block.observations >= 100
  && block.spearman !== null && block.spearman >= .5
  && block.bootstrap95[0] !== null && block.bootstrap95[0] > .3
  && block.coverage >= .5;
const passesGate = (candidate: Candidate) => passesBlock(candidate) && passesBlock(candidate.finalTest);

for (const candidate of report.candidates) {
  if (candidate.passed !== passesGate(candidate)) {
    throw new Error(`Crop expansion decision is inconsistent with the frozen gate: ${candidate.crop}`);
  }
}
const computedAccepted = report.candidates.filter(passesGate).map(({ crop }) => crop);
if (JSON.stringify(report.acceptedCrops) !== JSON.stringify(computedAccepted)) {
  throw new Error('Accepted crop list does not match the frozen expansion gate.');
}
if (JSON.stringify(report.acceptedCrops) !== JSON.stringify(['silage corn', 'spring wheat'])) {
  throw new Error('Locked crop-subtype expansion result changed unexpectedly.');
}
if (!report.dataNotes.some((note) => note.includes('excludes chickpeas'))
  || !report.dataNotes.some((note) => note.includes('never pooled'))) {
  throw new Error('USDA definition-break guards are no longer documented.');
}

const atlas = JSON.parse(readFileSync(
  new URL('../machine-learning/evaluation/yield-atlas-v9.json', import.meta.url),
  'utf8',
)) as { crops: string[]; records: { crop: string }[] };
if (JSON.stringify(atlas.crops) !== JSON.stringify(['corn', 'soybean', 'wheat'])
  || atlas.records.some(({ crop }) => crop === 'silage corn' || crop === 'spring wheat')) {
  throw new Error('Validated crop subtypes entered production without a separate atlas promotion.');
}

const subtypeAtlas = JSON.parse(readFileSync(
  new URL('../machine-learning/evaluation/yield-atlas-subtypes-v1.json', import.meta.url),
  'utf8',
)) as {
  crops: string[];
  records: Array<{ crop: string; yieldUnit: string; history: Array<{ yieldPerAcre: number }> }>;
  spatialTransferValidation?: { selectedNeighborhoodByCrop?: Record<string, { maxNeighbors: number; distancePower: number; historyPower: number; distanceOffsetKm: number }>; distanceOnlyNeighborhoodByCrop?: Record<string, { maxNeighbors: number; distancePower: number; historyPower: number; distanceOffsetKm: number }>; selectedDisagreementAlphasByCrop?: Record<string, number>; selectedRegionalScalesByCrop?: Record<string, Record<string, { scale80: number; scale90: number }>>; supportedRegionsByCrop?: Record<string, string[]> };
  validation: { acceptedCrops: string[]; gate: { passed: boolean }; selectedNeighborhoods: Record<string, { maxNeighbors: number; distancePower: number; historyPower: number; distanceOffsetKm: number }>; distanceOnlyNeighborhoods: Record<string, { maxNeighbors: number; distancePower: number; historyPower: number; distanceOffsetKm: number }>; selectedDisagreementAlphas: Record<string, number>; disagreementScaleSelection: Array<{ crop: string; selected: number; developmentWidthReduction: number; minimumDevelopmentWidthReduction: number }>; selectedRegionalScales: Record<string, Record<string, { scale80: number; scale90: number }>>; supportedRegionsByCrop: Record<string, string[]>; perCrop: Array<{ crop: string; passed: boolean; spearmanGain: number; spearmanGainBootstrap95: [number, number]; maeReduction: number; pointValidation: Record<'development' | 'stability' | 'final', { spearmanGain: number; maeReduction: number }>; historyReliabilityComparison: Record<'development' | 'stability' | 'final', { spearmanGain: number; maeReduction: number }> & { finalSpearmanGainBootstrap95: [number, number] }; disagreementCalibrationComparison: { selectedAlpha: number; finalBaseline: { meanWidth90: number }; finalSelected: { meanWidth90: number } }; signal: { observations: number; spearman: number; bootstrap95: [number, number] }; development: { coverage80: number; coverage90: number }; stability: { coverage80: number; coverage90: number }; final: { coverage80: number; coverage90: number; meanWidth90: number }; perRegion: Array<{ region: string; final: { observations: number; coverage80: number; coverage90: number; meanWidth90: number } }> }> };
};
const expectedNeighborhoods = {
  'silage corn': { maxNeighbors: 5, distancePower: 2, historyPower: 1, distanceOffsetKm: 5 },
  'spring wheat': { maxNeighbors: 5, distancePower: 2, historyPower: 0, distanceOffsetKm: 5 },
};
const expectedDistanceOnlyNeighborhoods = {
  'silage corn': { maxNeighbors: 5, distancePower: 1, historyPower: 0, distanceOffsetKm: 5 },
  'spring wheat': { maxNeighbors: 5, distancePower: 2, historyPower: 0, distanceOffsetKm: 5 },
};
const expectedRegionalScales = {
  'silage corn': { Midwest: { scale80: 1.05, scale90: 1.1 }, Northeast: { scale80: 1, scale90: 1 } },
  'spring wheat': { Midwest: { scale80: 1, scale90: 1.05 }, West: { scale80: 1.15, scale90: 1.05 } },
};
const expectedDisagreementAlphas = { 'silage corn': 0, 'spring wheat': 5 };
const expectedRegions = { 'silage corn': ['Midwest', 'Northeast'], 'spring wheat': ['Midwest', 'West'] };
if (JSON.stringify(subtypeAtlas.crops) !== JSON.stringify(['silage corn', 'spring wheat'])
  || JSON.stringify(subtypeAtlas.validation.acceptedCrops) !== JSON.stringify(['silage corn', 'spring wheat'])
  || JSON.stringify(subtypeAtlas.validation.selectedNeighborhoods) !== JSON.stringify(expectedNeighborhoods)
  || JSON.stringify(subtypeAtlas.spatialTransferValidation?.selectedNeighborhoodByCrop) !== JSON.stringify(expectedNeighborhoods)
  || JSON.stringify(subtypeAtlas.validation.distanceOnlyNeighborhoods) !== JSON.stringify(expectedDistanceOnlyNeighborhoods)
  || JSON.stringify(subtypeAtlas.spatialTransferValidation?.distanceOnlyNeighborhoodByCrop) !== JSON.stringify(expectedDistanceOnlyNeighborhoods)
  || JSON.stringify(subtypeAtlas.validation.selectedDisagreementAlphas) !== JSON.stringify(expectedDisagreementAlphas)
  || JSON.stringify(subtypeAtlas.spatialTransferValidation?.selectedDisagreementAlphasByCrop) !== JSON.stringify(expectedDisagreementAlphas)
  || JSON.stringify(subtypeAtlas.validation.selectedRegionalScales) !== JSON.stringify(expectedRegionalScales)
  || JSON.stringify(subtypeAtlas.spatialTransferValidation?.selectedRegionalScalesByCrop) !== JSON.stringify(expectedRegionalScales)
  || JSON.stringify(subtypeAtlas.validation.supportedRegionsByCrop) !== JSON.stringify(expectedRegions)
  || JSON.stringify(subtypeAtlas.spatialTransferValidation?.supportedRegionsByCrop) !== JSON.stringify(expectedRegions)
  || !subtypeAtlas.validation.gate.passed || subtypeAtlas.records.length !== 690) {
  throw new Error('Crop-subtype production atlas identity or promotion gate changed unexpectedly.');
}
if (!subtypeAtlas.validation.disagreementScaleSelection.every((item) => item.selected === 0
  || item.developmentWidthReduction >= item.minimumDevelopmentWidthReduction)) {
  throw new Error('Neighbor-disagreement scaling bypassed its development-width selection floor.');
}
for (const item of subtypeAtlas.validation.perCrop) {
  const passes = item.signal.observations >= 100 && item.signal.spearman >= .5 && item.signal.bootstrap95[0] > .3
    && item.spearmanGainBootstrap95[0] > 0
    && Object.values(item.pointValidation).every((block) => block.spearmanGain > 0 && block.maeReduction > 0)
    && (['development', 'stability', 'final'] as const).every((key) => item.historyReliabilityComparison[key].spearmanGain >= 0
      && item.historyReliabilityComparison[key].maeReduction >= 0)
    && (item.disagreementCalibrationComparison.selectedAlpha === 0
      || item.disagreementCalibrationComparison.finalSelected.meanWidth90 < item.disagreementCalibrationComparison.finalBaseline.meanWidth90)
    && item.development.coverage80 >= .78 && item.development.coverage90 >= .88
    && item.stability.coverage80 >= .78 && item.stability.coverage90 >= .88
    && item.final.coverage80 >= .75 && item.final.coverage80 <= .9
    && item.final.coverage90 >= .87 && item.final.coverage90 <= .96 && item.final.meanWidth90 <= .8
    && item.perRegion.every((region) => region.final.observations >= 50 && region.final.coverage80 >= .7
      && region.final.coverage90 >= .85 && region.final.coverage90 <= .98 && region.final.meanWidth90 <= .9);
  if (item.passed !== passes) {
    throw new Error(`Crop-subtype held-out contract failed: ${item.crop}`);
  }
}
if (subtypeAtlas.records.some((record) => !['bu/acre', 'tons/acre'].includes(record.yieldUnit)
  || record.history.some((item) => !Number.isFinite(item.yieldPerAcre)))) {
  throw new Error('Crop-subtype atlas lost explicit, finite yield units.');
}

console.log('Crop expansion policy verified: five-county subtype priors improve locked transfer with history reliability, disagreement scaling, and region-safe uncertainty');
