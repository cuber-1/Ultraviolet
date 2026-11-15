import http from 'node:http';
import { once } from 'node:events';

import { mlModelHealth, predictCropSuitability } from '../server/mlModel.ts';

const start = async (handler: Parameters<typeof http.createServer>[0]) => {
  const server = http.createServer(handler);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server;
};
const url = (server: http.Server) => `http://127.0.0.1:${(server.address() as { port: number }).port}`;
const send = (res: http.ServerResponse, status: number, body: object) => {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(body));
};

let primaryRecovered = false;
let recoveredRequests = 0;
const cropFitResponse = {
  score: 81, bestPlantingMonth: 'MAR', suitableMonths: ['MAR', 'APR'], confidence: 0.7,
  growingDays: { min: 60, max: 90 }, limitingFactors: [{ factor: 'water', score: 75 }],
  monthlyCurve: [{ month: 'MAR', score: 81, uncertainty: 5 }],
  observedYieldEvidence: {
    county: 'Fort Bend County', state: 'TX', distanceKm: 46.7, years: [2024, 2025], observations: 2,
    meanPercentile: .4, p10Percentile: .3, p90Percentile: .5, meanYieldBushelsPerAcre: 140,
    observedYieldPrior: { expectedPercentile: .4, interval80: [.2, .6], interval90: [.1, .7], historyBucket: '2-3', calibrationExamples: 100 },
    history: [{ year: 2024, yieldBushelsPerAcre: 140, percentile: .4 }], evidenceGrade: 'observed-county-prior', source: 'USDA', disclaimer: 'County prior.',
  },
};
const primary = await start(async (req, res) => {
  if (!primaryRecovered) return send(res, 503, { error: 'spark unavailable' });
  if (req.url === '/health') return send(res, 200, { model: 'CropFit recovered' });
  if (req.url === '/predict') {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    const body = JSON.parse(Buffer.concat(chunks).toString()) as { crop?: unknown };
    if (typeof body.crop !== 'string') return send(res, 400, { error: 'expected CropFit request' });
    recoveredRequests += 1;
    return send(res, 200, cropFitResponse);
  }
  return send(res, 404, {});
});
let receivedClimate = false;
let backupRevision = '0.6.2:run-a';
let backupScore = 81;
let backupRequests = 0;
let backupHealthDown = false;
const backup = await start(async (req, res) => {
  if (req.url === '/health') return backupHealthDown ? send(res, 503, { error: 'health unavailable' }) : send(res, 200, { model: 'CropFit backup', apiVersion: '0.6.2', revision: backupRevision });
  if (req.url === '/predict') {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    const body = JSON.parse(Buffer.concat(chunks).toString()) as { climate?: unknown[] };
    receivedClimate = body.climate?.length === 12;
    backupRequests += 1;
    return send(res, 200, { ...cropFitResponse, score: backupScore, monthlyCurve: [{ month: 'MAR', score: backupScore, uncertainty: 5 }] });
  }
  send(res, 404, {});
});
const failedBackup = await start((_req, res) => send(res, 503, { error: 'backup unavailable' }));

const request = {
  crops: [
    { id: 'tomatoes', name: 'Tomatoes', sunHours: 8, tempMinC: 16, tempMaxC: 30, growMonths: 3 },
    { id: 'herbs', name: 'Herbs', sunHours: 6, tempMinC: 15, tempMaxC: 30, growMonths: 2 },
  ],
  preferredMonth: 2,
  targetAreaSqft: 1000,
  targetSunHours: 8,
  sites: [{
    id: 'houston', kind: 'roof' as const, lat: 29.76, lon: -95.37,
    climate: {
      temperatureC: [12, 14, 18, 22, 26, 29, 31, 31, 28, 23, 18, 14],
      solarMjM2Day: Array(12).fill(20), precipitationMmDay: Array(12).fill(3),
    },
    roof: { roofAreaSqft: 5000, sharedAreaSqft: 3000, meanSunHours: 8, obstructionCount: 2, buildingHeightM: 10 },
  }],
};

try {
  process.env.ML_MODEL_URL = url(primary);
  process.env.ML_MODEL_FALLBACK_URL = url(backup);
  process.env.ML_MODEL_TIMEOUT_MS = '1000';
  const backupResult = await predictCropSuitability(request);
  const health = await mlModelHealth();
  const herbs = backupResult.predictions.find(({ cropId }) => cropId === 'herbs');
  if (backupResult.model.name !== 'CropFit backup' || backupResult.model.source !== 'ml' || health.role !== 'backup' || !receivedClimate || backupResult.predictions[0]?.observedYieldEvidence?.observedYieldPrior?.interval90[1] !== .7 || !herbs?.notes?.includes('Representative EcoCrop profile for Herbs: basil.')) {
    throw new Error('Primary-to-backup failover did not select the backup model.');
  }
  const cachedBackup = await predictCropSuitability(request);
  if (backupRequests !== request.crops.length || cachedBackup.predictions[0]?.suitability !== .81) {
    throw new Error('Same-revision CropFit response was not reused from cache.');
  }
  backupRevision = '0.6.2:run-b';
  backupScore = 64;
  const revisedBackup = await predictCropSuitability(request);
  if (backupRequests !== request.crops.length * 2 || revisedBackup.predictions[0]?.suitability !== .64) {
    throw new Error('Retrained model revision reused stale CropFit predictions.');
  }
  backupHealthDown = true;
  const requestsBeforeUnverified = backupRequests;
  await predictCropSuitability(request);
  await predictCropSuitability(request);
  if (backupRequests !== requestsBeforeUnverified + request.crops.length * 2) {
    throw new Error('CropFit predictions were cached while model revision was unverified.');
  }
  backupHealthDown = false;

  primaryRecovered = true;
  const recoveredResult = await predictCropSuitability(request);
  if (recoveredResult.model.name !== 'CropFit recovered' || recoveredResult.model.source !== 'ml' || recoveredRequests !== request.crops.length) {
    throw new Error('Recovered primary was not immediately redetected as CropFit.');
  }

  primaryRecovered = false;
  process.env.ML_MODEL_FALLBACK_URL = url(failedBackup);
  const calendarRequest = {
    ...request,
    sites: request.sites.map((site) => ({
      ...site,
      climate: site.climate ? { ...site.climate, temperatureC: site.climate.temperatureC.map((value) => value + .1) } : null,
    })),
  };
  const calendarResult = await predictCropSuitability(calendarRequest);
  if (calendarResult.model.source !== 'calendar-fallback' || calendarResult.predictions.length !== 2) {
    throw new Error('Model-to-calendar failover did not return calendar predictions.');
  }
  console.log('ML recovery verified: revision cache bust -> primary down -> backup -> primary recovered -> crop calendar');
} finally {
  primary.close();
  backup.close();
  failedBackup.close();
}
