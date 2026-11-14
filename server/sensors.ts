import type { IncomingMessage, ServerResponse } from 'node:http';
import { appendFile, mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Soil-sensor readings from the ESP32 nodes (via hardware/bridge/serial-bridge.mjs or
// directly over Wi-Fi). Kept in memory, appended to runtime/sensors.jsonl, and streamed.
//   POST /api/sensors/readings  { nodeId, soilPct, rawAo?, wet?, digital?, intervalS?, at?, source? }
//   GET  /api/sensors           -> { nodes: [...latest], readings: [...recent] }
//   GET  /api/sensors/stream    -> Server-Sent Events: { type: 'reading', reading }

export type SensorReading = {
  nodeId: string;
  soilPct: number;
  rawAo: number | null;
  wet: boolean | null;
  digital: 'wet' | 'dry' | null;
  intervalS: number | null;
  at: string;
  source: string;
};

const MAX_READINGS = 2_000;
const num = (value: unknown) => (value === null || value === undefined || value === '' ? null : Number.isFinite(Number(value)) ? Number(value) : null);
const readings: SensorReading[] = [];
const listeners = new Set<ServerResponse>();
let loaded = false;

async function load(file: string) {
  if (loaded) return;
  loaded = true;
  try {
    const lines = (await readFile(file, 'utf8')).trim().split('\n').slice(-MAX_READINGS);
    for (const line of lines) { try { readings.push(JSON.parse(line) as SensorReading); } catch { /* skip bad line */ } }
  } catch { /* first run */ }
}

async function readBody(req: IncomingMessage) {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>;
}

function send(res: ServerResponse, status: number, value: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(value));
}

function latestByNode() {
  const nodes = new Map<string, SensorReading & { count: number }>();
  for (const reading of readings) nodes.set(reading.nodeId, { ...reading, count: (nodes.get(reading.nodeId)?.count ?? 0) + 1 });
  return [...nodes.values()].sort((a, b) => a.nodeId.localeCompare(b.nodeId));
}

/** Returns true when the request was handled. */
export async function handleSensorsRoute(pathname: string, req: IncomingMessage, res: ServerResponse, root: string) {
  if (pathname !== '/api/sensors' && !pathname.startsWith('/api/sensors/')) return false;
  const file = resolve(root, 'runtime/sensors.jsonl');
  await load(file);

  if (pathname === '/api/sensors/readings' && req.method === 'POST') {
    const input = await readBody(req);
    const nodeId = typeof input.nodeId === 'string' && input.nodeId.trim() ? input.nodeId.trim().slice(0, 40) : null;
    const soilPct = Number(input.soilPct);
    if (!nodeId || !Number.isFinite(soilPct)) { send(res, 400, { error: 'nodeId and soilPct are required.' }); return true; }
    const reading: SensorReading = {
      nodeId,
      soilPct: Math.max(0, Math.min(100, soilPct)),
      rawAo: num(input.rawAo),
      wet: typeof input.wet === 'boolean' ? input.wet : null,
      digital: input.digital === 'wet' || input.digital === 'dry' ? input.digital : null,
      intervalS: num(input.intervalS) || null,
      at: typeof input.at === 'string' && !Number.isNaN(Date.parse(input.at)) ? input.at : new Date().toISOString(),
      source: typeof input.source === 'string' ? input.source.slice(0, 40) : 'unknown',
    };
    readings.push(reading);
    if (readings.length > MAX_READINGS) readings.splice(0, readings.length - MAX_READINGS);
    try { await mkdir(resolve(file, '..'), { recursive: true }); await appendFile(file, `${JSON.stringify(reading)}\n`); } catch { /* best effort */ }
    for (const listener of listeners) listener.write(`data: ${JSON.stringify({ type: 'reading', reading })}\n\n`);
    send(res, 200, { ok: true });
    return true;
  }

  if (pathname === '/api/sensors' && req.method === 'GET') {
    send(res, 200, { nodes: latestByNode(), readings: readings.slice(-300) });
    return true;
  }

  if (pathname === '/api/sensors/stream' && req.method === 'GET') {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.write(`data: ${JSON.stringify({ type: 'hello', nodes: latestByNode() })}\n\n`);
    listeners.add(res);
    const keepAlive = setInterval(() => res.write(': ping\n\n'), 20_000);
    req.on('close', () => { clearInterval(keepAlive); listeners.delete(res); });
    return true;
  }

  send(res, 404, { error: 'Not found.' });
  return true;
}
