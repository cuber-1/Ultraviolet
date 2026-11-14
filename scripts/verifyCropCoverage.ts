import { cropFitCropIds, cropFitModelName } from '../server/mlModel.ts';
import { CROPS } from '../src/services/cropPlan.ts';

const expectedMappings: Record<string, string> = {
  greens: 'lettuce', herbs: 'basil', microgreens: 'lettuce', tomatoes: 'tomato', peppers: 'pepper',
  strawberries: 'strawberry', kale: 'kale', beans: 'common bean', cucumbers: 'cucumber', corn: 'corn',
  soybeans: 'soybean', wheat: 'wheat', potatoes: 'potato', melons: 'melon', onions: 'onion', sunflowers: 'sunflower',
};

delete process.env.ML_STRICT;
const supported = new Set(cropFitCropIds());
const onboarding = new Set(CROPS.map(({ id }) => id));
const missing = [...onboarding].filter((id) => !supported.has(id));
const unexpected = [...supported].filter((id) => !onboarding.has(id));
if (missing.length || unexpected.length || supported.size !== 16) {
  throw new Error(`CropFit onboarding coverage mismatch: missing=${missing.join(',')} unexpected=${unexpected.join(',')}`);
}
for (const [id, name] of Object.entries(expectedMappings)) {
  if (cropFitModelName(id) !== name) throw new Error(`CropFit maps ${id} to ${cropFitModelName(id)}, expected ${name}`);
}

process.env.ML_STRICT = '1';
const strict = new Set(cropFitCropIds());
const strictMissing = [...onboarding].filter((id) => !strict.has(id));
if (strict.size !== 15 || strictMissing.length !== 1 || strictMissing[0] !== 'microgreens') {
  throw new Error(`Strict CropFit coverage must exclude only microgreens, got ${strictMissing.join(',')}`);
}
delete process.env.ML_STRICT;

console.log('CropFit onboarding coverage verified: 16/16 resilient, 15/16 strict (microgreens excluded)');
