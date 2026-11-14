import type { IncomingMessage, ServerResponse } from 'node:http';
import { mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Saved search results for instant replay (e.g. during a demo).
// Stored as JSON under <project>/runtime/runs (gitignored).
//   POST /api/runs        { key, kind, label, outcome }  -> { id, savedAt }
//   GET  /api/runs                                        -> { runs: [{ id, key, kind, label, savedAt }] }
//   GET  /api/runs/<id>                                   -> { id, key, kind, label, savedAt, outcome }

const MAX_RUNS = 60;
const MAX_BYTES = 4_000_000;
const ID = /^[a-z0-9-]{8,64}$/;

type RunMeta = { id: string; key: string; kind: 'urban' | 'rural'; label: string; savedAt: string };

async function readJson(req: IncomingMessage) {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BYTES) throw new Error('Saved run is too large.');
    chunks.push(Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>;
}

function send(res: ServerResponse, status: number, value: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(value));
}

async function listMeta(dir: string): Promise<RunMeta[]> {
  const files = (await readdir(dir).catch(() => [] as string[])).filter((name) => name.endsWith('.json'));
  const metas = await Promise.all(files.map(async (name) => {
    try {
      const value = JSON.parse(await readFile(resolve(dir, name), 'utf8')) as RunMeta;
      return { id: value.id, key: value.key, kind: value.kind, label: value.label, savedAt: value.savedAt };
    } catch { return null; }
  }));
  return metas.filter((item): item is RunMeta => Boolean(item)).sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

async function prune(dir: string) {
  const runs = await listMeta(dir);
  await Promise.all(runs.slice(MAX_RUNS).map((run) => rm(resolve(dir, `${run.id}.json`), { force: true })));
}

/** Returns true when the request was handled. */
export async function handleRunsRoute(pathname: string, req: IncomingMessage, res: ServerResponse, root: string) {
  if (pathname !== '/api/runs' && !pathname.startsWith('/api/runs/')) return false;
  const dir = resolve(root, 'runtime/runs');
  if (pathname === '/api/runs' && req.method === 'GET') { send(res, 200, { runs: await listMeta(dir) }); return true; }
  if (pathname === '/api/runs' && req.method === 'POST') {
    const input = await readJson(req);
    const kind = input.kind === 'rural' ? 'rural' : input.kind === 'urban' ? 'urban' : null;
    if (!kind || typeof input.key !== 'string' || !input.outcome || typeof input.outcome !== 'object') { send(res, 400, { error: 'Send key, kind, label, and outcome.' }); return true; }
    await mkdir(dir, { recursive: true });
    const savedAt = new Date().toISOString();
    const id = `${savedAt.replace(/[^0-9]/g, '').slice(0, 14)}-${Math.random().toString(36).slice(2, 8)}`;
    const record = { id, key: input.key.slice(0, 400), kind, label: String(input.label ?? '').slice(0, 200), savedAt, outcome: input.outcome };
    await writeFile(resolve(dir, `${id}.json`), JSON.stringify(record));
    await prune(dir);
    send(res, 200, { id, savedAt });
    return true;
  }
  const id = pathname.slice('/api/runs/'.length);
  if (req.method === 'GET' && ID.test(id)) {
    const file = resolve(dir, `${id}.json`);
    if (!(await stat(file).catch(() => null))) { send(res, 404, { error: 'Saved run not found.' }); return true; }
    res.setHeader('Content-Type', 'application/json');
    res.end(await readFile(file, 'utf8'));
    return true;
  }
  send(res, 404, { error: 'Not found.' });
  return true;
}
