import { cp, mkdir, readdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const collections = [
  { source: 'vexcel_sites', destination: 'vexcel' },
  { source: 'vexcel_rooftops', destination: 'vexcel-rooftops' },
];

let synced = 0;
for (const collection of collections) {
  const sourceRoot = resolve(projectRoot, `../Vexcel_API_Hackathon_Tutorial_PDF_PY/output/${collection.source}`);
  const destinationRoot = resolve(projectRoot, `public/${collection.destination}`);
  const entries = await readdir(sourceRoot, { withFileTypes: true }).catch(() => []);
  const sites = entries.filter((entry) => entry.isDirectory());

  await mkdir(destinationRoot, { recursive: true });
  for (const site of sites) {
    await cp(resolve(sourceRoot, site.name), resolve(destinationRoot, site.name), { recursive: true, force: true });
    console.log(`Synced ${collection.destination} output for ${site.name}`);
    synced += 1;
  }
}

if (synced === 0) {
  console.error('No Vexcel outputs found. Run vexcel_four_sites.py first.');
  process.exit(1);
}

console.log(`Synced ${synced} Vexcel site folders`);
