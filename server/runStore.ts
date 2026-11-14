import type { IncomingMessage, ServerResponse } from 'node:http';
import { mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Saved search results for instant replay (e.g. during a demo).
// Stored in Postgres when DATABASE_URL is set (see below), else as JSON under <project>/runtime/runs (gitignored).
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

// ---- Postgres (Neon) store --------------------------------------------------
// With DATABASE_URL set, runs live in Postgres (table `runs`) via Neon's HTTP SQL
// endpoint, so every copy of the app shares the same demo runs. Local files remain
// the fallback when the database is unset or unreachable.

type DbRow = { id: string; key: string; kind: 'urban' | 'rural'; label: string; saved_at: string; is_demo: boolean; outcome?: unknown };
const databaseUrl = () => process.env.DATABASE_URL?.trim() || null;

async function sql<T>(query: string, params: unknown[] = []): Promise<T[]> {
  const url = databaseUrl();
  if (!url) throw new Error('DATABASE_URL is not set.');
  const host = new URL(url.replace(/^postgres(ql)?:/, 'https:')).host;
  const response = await fetch(`https://${host}/sql`, {
    method: 'POST',
    headers: { 'Neon-Connection-String': url, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, params }),
    signal: AbortSignal.timeout(10_000),
  });
  const payload = await response.json().catch(() => ({})) as { rows?: T[]; message?: string };
  if (!response.ok) throw new Error(payload.message || `Database HTTP ${response.status}`);
  return payload.rows ?? [];
}

const toMeta = (row: DbRow): RunMeta & { demo: boolean; source: 'database' } => ({ id: row.id, key: row.key, kind: row.kind, label: row.label, savedAt: new Date(row.saved_at).toISOString(), demo: row.is_demo, source: 'database' });

export function runStoreStatus() {
  return { database: Boolean(databaseUrl()) };
}

/** Returns true when the request was handled. */
export async function handleRunsRoute(pathname: string, req: IncomingMessage, res: ServerResponse, root: string) {
  if (pathname !== '/api/runs' && !pathname.startsWith('/api/runs/')) return false;
  const dir = resolve(root, 'runtime/runs');
  const db = Boolean(databaseUrl());
  if (pathname === '/api/runs' && req.method === 'GET') {
    const files = (await listMeta(dir)).map((run) => ({ ...run, demo: false, source: 'file' as const }));
    let rows: Array<ReturnType<typeof toMeta>> = [];
    let databaseError: string | null = null;
    if (db) {
      try { rows = (await sql<DbRow>('select id, key, kind, label, saved_at, is_demo from runs order by is_demo desc, saved_at desc limit 100')).map(toMeta); }
      catch (reason) { databaseError = reason instanceof Error ? reason.message : 'Database unavailable.'; }
    }
    const seen = new Set(rows.map((run) => run.id));
    const runs = [...rows, ...files.filter((run) => !seen.has(run.id))].sort((a, b) => Number(b.demo) - Number(a.demo) || b.savedAt.localeCompare(a.savedAt));
    send(res, 200, { runs, store: db ? (databaseError ? 'database-unavailable' : 'database') : 'files', databaseError });
    return true;
  }
  if (pathname === '/api/runs' && req.method === 'POST') {
    const input = await readJson(req);
    const kind = input.kind === 'rural' ? 'rural' : input.kind === 'urban' ? 'urban' : null;
    if (!kind || typeof input.key !== 'string' || !input.outcome || typeof input.outcome !== 'object') { send(res, 400, { error: 'Send key, kind, label, and outcome.' }); return true; }
    const savedAt = new Date().toISOString();
    const id = `${savedAt.replace(/[^0-9]/g, '').slice(0, 14)}-${Math.random().toString(36).slice(2, 8)}`;
    const record = { id, key: input.key.slice(0, 400), kind, label: String(input.label ?? '').slice(0, 200), savedAt, outcome: input.outcome };
    if (db) {
      try {
        await sql('insert into runs (id, key, kind, label, saved_at, is_demo, outcome) values ($1, $2, $3, $4, $5, $6, $7::jsonb)', [id, record.key, kind, record.label, savedAt, input.demo === true, JSON.stringify(record.outcome)]);
        send(res, 200, { id, savedAt, store: 'database' });
        return true;
      } catch (reason) { console.warn(`Run not saved to database, using local file: ${reason instanceof Error ? reason.message : reason}`); }
    }
    await mkdir(dir, { recursive: true });
    await writeFile(resolve(dir, `${id}.json`), JSON.stringify(record));
    await prune(dir);
    send(res, 200, { id, savedAt, store: 'file' });
    return true;
  }
  const id = pathname.slice('/api/runs/'.length);
  if (req.method === 'GET' && ID.test(id)) {
    if (db) {
      try {
        const [row] = await sql<DbRow>('select id, key, kind, label, saved_at, is_demo, outcome from runs where id = $1', [id]);
        if (row) { send(res, 200, { ...toMeta(row), outcome: row.outcome }); return true; }
      } catch { /* fall through to the file store */ }
    }
    const file = resolve(dir, `${id}.json`);
    if (!(await stat(file).catch(() => null))) { send(res, 404, { error: 'Saved run not found.' }); return true; }
    res.setHeader('Content-Type', 'application/json');
    res.end(await readFile(file, 'utf8'));
    return true;
  }
  send(res, 404, { error: 'Not found.' });
  return true;
}
