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
  validation: { acceptedCrops: string[]; gate: { passed: boolean }; perCrop: Array<{ crop: string; passed: boolean; signal: { observations: number; spearman: number; bootstrap95: [number, number] }; development: { coverage80: number; coverage90: number }; stability: { coverage80: number; coverage90: number }; final: { coverage80: number; coverage90: number; meanWidth90: number } }> };
};
if (JSON.stringify(subtypeAtlas.crops) !== JSON.stringify(['spring wheat'])
  || JSON.stringify(subtypeAtlas.validation.acceptedCrops) !== JSON.stringify(['spring wheat'])
  || !subtypeAtlas.validation.gate.passed || subtypeAtlas.records.length !== 297) {
  throw new Error('Crop-subtype production atlas identity or promotion gate changed unexpectedly.');
}
for (const item of subtypeAtlas.validation.perCrop) {
  const passes = item.signal.observations >= 100 && item.signal.spearman >= .5 && item.signal.bootstrap95[0] > .3
    && item.development.coverage80 >= .78 && item.development.coverage90 >= .88
    && item.stability.coverage80 >= .78 && item.stability.coverage90 >= .88
    && item.final.coverage80 >= .75 && item.final.coverage80 <= .9
    && item.final.coverage90 >= .87 && item.final.coverage90 <= .96 && item.final.meanWidth90 <= .8;
  if (item.passed !== passes) {
    throw new Error(`Crop-subtype held-out contract failed: ${item.crop}`);
  }
}
if (subtypeAtlas.records.some((record) => record.yieldUnit !== 'bu/acre'
  || record.history.some((item) => !Number.isFinite(item.yieldPerAcre)))) {
  throw new Error('Crop-subtype atlas lost explicit, finite yield units.');
}

console.log('Crop expansion policy verified: spring wheat passes locked spatial transfer; silage corn remains isolated after failing the transfer rank floor');
