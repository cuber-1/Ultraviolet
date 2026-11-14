// Saved search results (server: /api/runs) so a demo can reopen a finished search instantly.
import { briefCrops, formatArea, MONTH_SHORT, RURAL_REGIONS, urbanAreaLabel, type Brief } from './cropPlan';

export type SavedRunMeta = { id: string; key: string; kind: 'urban' | 'rural'; label: string; savedAt: string };

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
  const response = await fetch('/api/runs', { signal });
  if (!response.ok) return [] as SavedRunMeta[];
  return ((await response.json()) as { runs: SavedRunMeta[] }).runs;
}

export async function getRun<T>(id: string, signal?: AbortSignal) {
  const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { signal });
  if (!response.ok) throw new Error('Saved run not found.');
  return response.json() as Promise<SavedRunMeta & { outcome: T }>;
}

export const savedTime = (iso: string) => new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
