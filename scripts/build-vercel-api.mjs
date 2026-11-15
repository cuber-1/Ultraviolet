// Bundle the server code into one Vercel function file. npm packages stay external
// npm packages are bundled too: Vercel's file tracing misses nested ESM package.json files (LangGraph SDK).
import { build } from 'esbuild';
await build({
  entryPoints: ['server/vercelEntry.ts'],
  outfile: 'api/handler.mjs',
  bundle: true, platform: 'node', format: 'esm', target: 'node20',
  banner: { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" },
  logLevel: 'info',
});
