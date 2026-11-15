// Saved search results (server: /api/runs) so a demo can reopen a finished search instantly.
import { briefCrops, formatArea, MONTH_SHORT, RURAL_REGIONS, urbanAreaLabel, type Brief } from './cropPlan';

export type SavedRunMeta = { id: string; key: string; kind: 'urban' | 'rural'; label: string; savedAt: string; demo?: boolean; source?: 'database' | 'file' };

/** Same answers -> same key. */
export function briefKey(brief: Brief) {
  const crops = [...brief.crops].sort().join(',');
  const place = brief.scale === 'urban' ? brief.urbanArea ?? '' : [...(brief.ruralRegions ?? [])].sort().join(',');
  return [brief.scale, Math.round(brief.areaSqft), crops, place, brief.preferredMonth].join('|');
}

export function briefLabel(brief: Brief) {
  const crops = briefCrops(brief).map((crop) => crop.name).join(', ');
  const place = brief.scale === 'urban' ? urbanAreaLabel(brief) : (brief.ruralRegions ?? []).map((id) => RURAL_REGIONS.find((region) => region.id === id)?.label ?? id).join(' + ');
  return `${place} · ${crops} · ${formatArea(brief.areaSqft)} · from ${MONTH_SHORT[brief.preferredMonth]}`;
}

export async function saveRun(brief: Brief, outcome: unknown) {
  const response = await fetch('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: briefKey(brief), kind: brief.scale, label: briefLabel(brief), outcome }) });
  if (!response.ok) throw new Error('Could not save the run.');
  return response.json() as Promise<{ id: string; savedAt: string }>;
}

export async function listRuns(signal?: AbortSignal) {
  return (await listRunsWithStore(signal)).runs;
}

export async function listRunsWithStore(signal?: AbortSignal): Promise<{ runs: SavedRunMeta[]; store: 'database' | 'database-unavailable' | 'files' }> {
  const response = await fetch('/api/runs', { signal });
  if (!response.ok) return { runs: [], store: 'files' };
  const payload = await response.json() as { runs: SavedRunMeta[]; store?: 'database' | 'database-unavailable' | 'files' };
  return { runs: payload.runs, store: payload.store ?? 'files' };
}

export async function getRun<T>(id: string, signal?: AbortSignal) {
  const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { signal });
  if (!response.ok) throw new Error('Saved run not found.');
  return response.json() as Promise<SavedRunMeta & { outcome: T }>;
}

export const savedTime = (iso: string) => new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

/** True when the crop model answers its health check right now. */
export async function mlOnline(signal?: AbortSignal) {
  try {
    const response = await fetch('/api/ml/health', { signal });
    return response.ok && (await response.json() as { online?: boolean }).online === true;
  } catch { return false; }
}

/** Newest saved run for the same answers whose crop scores came from the trained model. */
export async function findModelRun<T extends { kind: string }>(brief: Brief, signal?: AbortSignal) {
  const key = briefKey(brief);
  const matches = (await listRuns(signal)).filter((run) => run.key === key).sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  for (const meta of matches) {
    const record = await getRun<T & { comparison?: { mlModel?: { source?: string } | null; trace?: unknown[] } }>(meta.id, signal).catch(() => null);
    if (record?.outcome.comparison?.mlModel?.source === 'ml' && record.outcome.comparison.trace?.length) return record;
  }
  return null;
}
