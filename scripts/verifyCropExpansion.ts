import { readFileSync } from 'node:fs';

type Candidate = {
  crop: string;
  observations: number;
  coverage: number;
  spearman: number;
  bootstrap95: [number, number];
  passed: boolean;
};

const report = JSON.parse(readFileSync(
  new URL('../machine-learning/evaluation/crop-expansion-validation-v1.json', import.meta.url),
  'utf8',
)) as { acceptedCrops: string[]; candidates: Candidate[]; dataNotes: string[] };

const passesGate = (candidate: Candidate) => candidate.observations >= 100
  && candidate.spearman >= .5
  && candidate.bootstrap95[0] > .3
  && candidate.coverage >= .5;

for (const candidate of report.candidates) {
  if (candidate.passed !== passesGate(candidate)) {
    throw new Error(`Crop expansion decision is inconsistent with the frozen gate: ${candidate.crop}`);
  }
}
const computedAccepted = report.candidates.filter(passesGate).map(({ crop }) => crop);
if (JSON.stringify(report.acceptedCrops) !== JSON.stringify(computedAccepted)) {
  throw new Error('Accepted crop list does not match the frozen expansion gate.');
}
if (report.acceptedCrops.length !== 0) {
  throw new Error('Production coverage changed without a new reviewed crop-expansion protocol.');
}
if (!report.dataNotes.some((note) => note.includes('excludes chickpeas'))) {
  throw new Error('The 2019 USDA dry-bean definition break is no longer documented.');
}

console.log('Crop expansion policy verified: no rejected USDA series enters production');
