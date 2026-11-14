import { BoundedExpiringCache, CROPFIT_CACHE_MAX_ENTRIES, cropFitRequestCacheKey } from '../server/mlModel.ts';

const base = {
  crop: 'tomato', latitude: 29.76, longitude: -95.37, soilPh: 6.5, irrigated: true,
  climate: [{ month: 'JAN', temperatureC: 20, precipitationMmDay: 3, solarMjM2Day: 18 }],
};
const first = cropFitRequestCacheKey('http://model-a', base);
if (first !== cropFitRequestCacheKey('http://model-a', { ...base })) throw new Error('Equivalent CropFit payloads produced different cache keys.');
for (const changed of [
  { ...base, soilPh: 7 },
  { ...base, irrigated: false },
  { ...base, latitude: 29.761 },
  { ...base, climate: [{ ...base.climate[0], temperatureC: 21 }] },
]) {
  if (first === cropFitRequestCacheKey('http://model-a', changed)) throw new Error('Materially different CropFit requests collided in cache.');
}
if (first === cropFitRequestCacheKey('http://model-b', base)) throw new Error('Primary and backup model cache keys collided.');

const cache = new BoundedExpiringCache<number>(2);
cache.set('a', 1, 100); cache.set('b', 2, 100);
if (cache.get('a', 10) !== 1) throw new Error('Cache hit failed.');
cache.set('c', 3, 100);
if (cache.get('b', 10) !== undefined || cache.get('a', 10) !== 1 || cache.get('c', 10) !== 3) throw new Error('Cache did not evict the least-recently-used entry.');
cache.set('expired', 4, 20);
if (cache.get('expired', 20) !== undefined || cache.size > 2) throw new Error('Cache did not expire or bound entries.');
if (CROPFIT_CACHE_MAX_ENTRIES !== 2_048) throw new Error('Production CropFit cache limit changed unexpectedly.');

console.log('CropFit cache verified: full-request keys, model isolation, expiry, and 2048-entry LRU bound');
