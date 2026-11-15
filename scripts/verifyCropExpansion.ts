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

console.log('Crop expansion policy verified: spring wheat and silage corn pass locked evidence gates but remain isolated from production');
