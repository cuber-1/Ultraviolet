// Vercel function: the same /api middleware the Vite dev/preview server uses.
// vercel.json rewrites /api/<path> to /api/handler?__p=<path>; restore the original URL here.
import type { IncomingMessage, ServerResponse } from 'node:http';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { vexcelApiPlugin } from './vexcelPlugin';

type Handler = (req: IncomingMessage, res: ServerResponse, next: (error?: unknown) => void) => void;
let handler: Handler | null = null;
let startupError: string | null = null;
try {
  const root = process.cwd();
  const bundledCostar = join(root, 'deploy-data/costar');
  if (!process.env.COSTAR_DATA_DIR && existsSync(bundledCostar)) process.env.COSTAR_DATA_DIR = bundledCostar;
  vexcelApiPlugin(root).configurePreviewServer({ middlewares: { use: (next) => { handler = next as unknown as Handler; } } });
} catch (error) {
  startupError = error instanceof Error ? `${error.message}\n${error.stack}` : String(error);
  console.error('API startup failed', startupError);
}

export default function api(req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url ?? '/', 'http://localhost');
  const path = url.searchParams.get('__p');
  if (path !== null) { url.searchParams.delete('__p'); req.url = `/api/${path}${url.search}`; }
  if (!handler) {
    res.statusCode = 500;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ error: 'API failed to start.', detail: startupError }));
    return;
  }
  handler(req, res, () => {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ error: 'Unknown endpoint.' }));
  });
}
