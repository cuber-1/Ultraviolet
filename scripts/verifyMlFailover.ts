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

const primary = await start((_req, res) => send(res, 503, { error: 'spark unavailable' }));
const backup = await start((req, res) => {
  if (req.url === '/health') return send(res, 200, { model: { name: 'backup-cropfit', version: 'demo' } });
  if (req.url === '/predict') return send(res, 200, {
    model: { name: 'backup-cropfit', version: 'demo' },
    predictions: [{ siteId: 'houston', cropId: 'tomatoes', suitability: 0.81, plantMonth: 2, harvestMonth: 4, confidence: 0.7 }],
  });
  send(res, 404, {});
});
const failedBackup = await start((_req, res) => send(res, 503, { error: 'backup unavailable' }));

const request = {
  crops: [{ id: 'tomatoes', name: 'Tomatoes', sunHours: 8, tempMinC: 16, tempMaxC: 30, growMonths: 3 }],
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
  if (backupResult.model.name !== 'backup-cropfit' || backupResult.model.source !== 'ml' || health.role !== 'backup') {
    throw new Error('Primary-to-backup failover did not select the backup model.');
  }

  process.env.ML_MODEL_FALLBACK_URL = url(failedBackup);
  const calendarResult = await predictCropSuitability(request);
  if (calendarResult.model.source !== 'calendar-fallback' || calendarResult.predictions.length !== 1) {
    throw new Error('Model-to-calendar failover did not return calendar predictions.');
  }
  console.log('ML failover verified: primary -> backup -> crop calendar');
} finally {
  primary.close();
  backup.close();
  failedBackup.close();
}
