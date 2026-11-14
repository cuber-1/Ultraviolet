import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, ArrowLeft, ArrowRight, Brain, Building2, CircleAlert, Cpu, LoaderCircle, Play, Satellite, Sprout, Sun } from 'lucide-react';
import Wordmark from '../components/Wordmark';
import { CROPS, MONTH_LONG, MONTH_SHORT, RURAL_REGIONS, URBAN_AREAS, fetchMonthlyClimate, type Brief, type MonthlyClimate } from '../services/cropPlan';
import type { CropModelInfo, CropPrediction } from '../services/vexcel';
import { getRun, listRunsWithStore, savedTime, type SavedRunMeta } from '../services/runs';
import './PlanPage.css';
import './ModelPage.css';

type Health = {
  configured: boolean; online: boolean; latencyMs: number | null; model: { name?: string; version?: string } | null;
  metrics?: Record<string, number> | null; error: string | null;
  evidence?: { grade?: string; observedOutcomeGate?: { passed: boolean; scope?: string; observations: number; spearman: number; bootstrap95: [number, number] } | null } | null;
};
type Status = { agent?: { configured: boolean; model: string | null; provider: string | null; baseUrl?: string | null; tracing?: { enabled: boolean; project: string } }; ml?: { configured: boolean; url: string | null } };

const PLACES = [
  ...URBAN_AREAS.map((area) => ({ label: area.label, value: area.value, kind: 'city' as const })),
  ...RURAL_REGIONS.flatMap((region) => region.places.slice(0, 2)).map((value) => ({ label: value.split(',')[0], value, kind: 'farm' as const })),
];
const host = (url: string | null | undefined) => { try { return url ? new URL(url).host : null; } catch { return url ?? null; } };
const pct = (value: number) => `${Math.round(value * 100)}%`;
const heat = (value: number) => `rgba(232, 93, 4, ${(0.08 + 0.85 * value).toFixed(2)})`;

export default function ModelPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [runs, setRuns] = useState<SavedRunMeta[]>([]);
  const [store, setStore] = useState<'database' | 'database-unavailable' | 'files'>('files');
  const refresh = useCallback(() => {
    void fetch('/api/vexcel/status').then((response) => response.json()).then(setStatus).catch(() => setStatus(null));
    void fetch('/api/ml/health').then((response) => response.json()).then(setHealth).catch(() => setHealth(null));
    void listRunsWithStore().then((result) => { setRuns(result.runs); setStore(result.store); }).catch(() => setRuns([]));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const openRun = async (id: string) => {
    const record = await getRun<{ brief: Brief }>(id);
    navigate('/plan', { state: { brief: record.outcome.brief, savedId: id } });
  };

  const modelLive = Boolean(health?.online);
  const stages = [
    { icon: Sprout, title: 'Your answers', detail: 'Space, crops, place, start month', state: 'ok' as const, meta: 'ONBOARDING' },
    { icon: Satellite, title: 'Vexcel imagery', detail: 'Aerial search, roof outlines, DSM/DTM heights', state: status ? 'ok' as const : 'warn' as const, meta: status ? 'LIVE' : 'CHECKING' },
    { icon: Sun, title: 'Sun simulator', detail: 'Clear-sky shadows every 30 min on your season’s dates', state: 'ok' as const, meta: 'IN-APP' },
    { icon: Cpu, title: 'Crop model', detail: modelLive ? `${health?.model?.name ?? 'Model'}${health?.model?.version ? ` ${health.model.version}` : ''} · ${health?.latencyMs} ms` : health?.configured ? `Offline: ${health.error ?? 'unreachable'}` : 'Not connected; using crop calendar', state: modelLive ? 'ok' as const : 'warn' as const, meta: modelLive ? host(status?.ml?.url) ?? 'ONLINE' : 'CALENDAR FALLBACK' },
    { icon: Brain, title: 'Deep Agent', detail: status?.agent?.configured ? `${status.agent.model} via ${host(status.agent.baseUrl) ?? status.agent.provider}` : 'No model key', state: status?.agent?.configured ? 'ok' as const : 'warn' as const, meta: 'LANGGRAPH' },
    { icon: Activity, title: 'LangSmith', detail: status?.agent?.tracing?.enabled ? `Tracing to ${status.agent.tracing.project}` : 'Tracing off', state: status?.agent?.tracing?.enabled ? 'ok' as const : 'warn' as const, meta: 'TRACES' },
  ];

  return <div className="model-page">
    <header className="model-header">
      <button className="plan-back" onClick={() => navigate('/')}><ArrowLeft size={16} /> Home</button>
      <Wordmark />
      <button className="plan-back model-refresh" onClick={refresh}>Refresh status</button>
    </header>
    <main className="model-main">
      <section className="model-hero">
        <span className="mono">UNDER THE HOOD</span>
        <h1>How Ultraviolet decides.</h1>
        <p>Every search runs live: aerial imagery, roof geometry, a sun simulator, the crop model, and a Deep Agent that explains the ranking. Each run is traced in LangSmith and saved here for instant replay.</p>
      </section>

      <section className="pipeline" aria-label="Pipeline status">
        {stages.map(({ icon: Icon, title, detail, state, meta }, index) => <Fragment key={title}>
          <article className={`pipeline-node ${state}`}><header><Icon size={18} /><i /></header><strong>{title}</strong><p>{detail}</p><span className="mono">{meta}</span></article>
          {index < stages.length - 1 && <ArrowRight className="pipeline-arrow" size={16} />}
        </Fragment>)}
      </section>

      <ModelExplorer health={health} />

      <section className="model-section">
        <header><div><span className="mono">03 / SAVED RUNS</span><h2>Recent searches</h2></div><span>{store === 'database' ? 'Stored in Neon Postgres, shared by every copy of the app.' : store === 'database-unavailable' ? 'Database unreachable; showing local saves only.' : 'Stored on this machine.'} Open any result instantly.</span></header>
        {runs.length === 0 ? <p className="model-empty">No saved runs yet. Finish a search from <button onClick={() => navigate('/start')}>Get started</button> and it appears here.</p>
          : <ol className="run-list">{runs.slice(0, 12).map((run) => <li key={run.id}><button onClick={() => void openRun(run.id)}>
            <span className={`run-kind ${run.kind}`}>{run.kind === 'urban' ? <Building2 size={14} /> : <Sprout size={14} />}{run.kind}</span>
            <strong>{run.demo && <em className="run-demo">Demo</em>}{run.label}</strong><span className="mono">{savedTime(run.savedAt)}</span><ArrowRight size={14} />
          </button></li>)}</ol>}
      </section>
    </main>
  </div>;
}

function ModelExplorer({ health }: { health: Health | null }) {
  const [crops, setCrops] = useState<string[]>(['tomatoes', 'greens', 'corn']);
  const [places, setPlaces] = useState<string[]>(['Houston, Texas', 'Los Angeles, California', 'Fresno, California', 'Des Moines, Iowa', 'Yuma, Arizona']);
  const [month, setMonth] = useState(new Date().getMonth());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ model: CropModelInfo; predictions: CropPrediction[]; climates: MonthlyClimate[]; request: unknown; latencyMs: number } | null>(null);
  const [selected, setSelected] = useState<{ site: string; crop: string } | null>(null);
  const toggle = (list: string[], set: (value: string[]) => void, value: string, max: number) => set(list.includes(value) ? list.filter((item) => item !== value) : list.length >= max ? list : [...list, value]);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const climate = await fetchMonthlyClimate(places);
      const profiles = CROPS.filter((crop) => crops.includes(crop.id)).map(({ id, name, sunHours, tempMinC, tempMaxC, growMonths }) => ({ id, name, sunHours, tempMinC, tempMaxC, growMonths }));
      const request = {
        crops: profiles, preferredMonth: month, targetAreaSqft: 5_000, targetSunHours: Math.max(...profiles.map((crop) => crop.sunHours)),
        sites: climate.results.map((item) => ({ id: item.query, kind: 'region', lat: item.lat, lon: item.lon, climate: { temperatureC: item.temperatureC, solarMjM2Day: item.solarMjM2Day, precipitationMmDay: item.precipitationMmDay, history: item.history }, roof: null })),
      };
      const started = performance.now();
      const response = await fetch('/api/ml/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Model request failed.');
      setResult({ ...payload, climates: climate.results, request, latencyMs: Math.round(performance.now() - started) });
      setSelected({ site: climate.results[0]?.query, crop: profiles[0]?.id });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Model request failed.');
    } finally { setLoading(false); }
  };

  const lookup = useMemo(() => new Map((result?.predictions ?? []).map((item) => [`${item.siteId}::${item.cropId}`, item])), [result]);
  const resultCrops = CROPS.filter((crop) => result?.predictions.some((item) => item.cropId === crop.id));
  const detail = selected && result ? { prediction: lookup.get(`${selected.site}::${selected.crop}`), climate: result.climates.find((item) => item.query === selected.site), crop: CROPS.find((crop) => crop.id === selected.crop) } : null;

  return <section className="model-section">
    <header><div><span className="mono">02 / MODEL EXPLORER</span><h2>Ask the crop model directly</h2></div>
      <div className="model-pill-group"><span className={`model-pill ${health?.online ? 'live' : ''}`}>{health?.online ? `● ${health.model?.name ?? 'Model'} online` : '○ Crop calendar fallback'}</span>{health?.metrics && <span className="model-metrics mono">{Object.entries(health.metrics).map(([key, value]) => `${({ mae: 'MAE', r2: 'R²', p90AbsoluteError: 'P90 ERR' } as Record<string, string>)[key] ?? key.toUpperCase()} ${Number(value).toFixed(key === 'r2' ? 2 : 1)}`).join(' · ')}</span>}{health?.evidence?.observedOutcomeGate && <span className={`model-evidence mono ${health.evidence.observedOutcomeGate.passed ? 'passed' : ''}`}>{health.evidence.observedOutcomeGate.passed ? 'OBSERVED-OUTCOME GATE PASSED' : `SCREENING ONLY · YIELD GATE NOT PASSED · N=${health.evidence.observedOutcomeGate.observations}`}</span>}</div></header>
    <div className="explorer-controls">
      <div><small className="mono">CROPS (UP TO 5)</small><div className="chip-row">{CROPS.map((crop) => <button key={crop.id} className={crops.includes(crop.id) ? 'chip active' : 'chip'} onClick={() => toggle(crops, setCrops, crop.id, 5)}>{crop.name}</button>)}</div></div>
      <div><small className="mono">PLACES (UP TO 8)</small><div className="chip-row">{PLACES.map((place) => <button key={place.value} className={places.includes(place.value) ? 'chip active' : 'chip'} onClick={() => toggle(places, setPlaces, place.value, 8)}>{place.label}<em>{place.kind}</em></button>)}</div></div>
      <div className="explorer-run"><label><small className="mono">START MONTH</small><select value={month} onChange={(event) => setMonth(Number(event.target.value))}>{MONTH_LONG.map((name, index) => <option key={name} value={index}>{name}</option>)}</select></label>
        <button className="explorer-go" disabled={loading || !crops.length || !places.length} onClick={() => void run()}>{loading ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />} Run model</button></div>
    </div>

    {error && <div className="plan-error"><CircleAlert /><div><strong>Model request failed</strong><p>{error}</p></div></div>}

    {result && <div className="explorer-result">
      <div className="explorer-meta mono"><span>{result.model.source === 'ml' ? `MODEL · ${result.model.name}${result.model.version ? ` ${result.model.version}` : ''}` : 'CROP CALENDAR · MODEL OFFLINE'}</span><span>{result.predictions.length} PREDICTIONS · {result.latencyMs} MS</span></div>
      {result.model.error && <div className="model-warning"><CircleAlert size={14} /><span>{result.model.source === 'ml' ? 'Some crops used the crop calendar: ' : 'Model call failed, showing the crop calendar: '}{result.model.error}</span></div>}
      <div className="heatmap-wrap"><table className="heatmap">
        <thead><tr><th />{resultCrops.map((crop) => <th key={crop.id}>{crop.name}</th>)}</tr></thead>
        <tbody>{result.climates.map((climate) => <tr key={climate.query}><th>{climate.name}<small>{climate.region.split(',')[0]}</small></th>{resultCrops.map((crop) => {
          const item = lookup.get(`${climate.query}::${crop.id}`);
          const active = selected?.site === climate.query && selected?.crop === crop.id;
          return <td key={crop.id}><button className={active ? 'active' : ''} style={{ background: heat(item?.suitability ?? 0), color: (item?.suitability ?? 0) > .55 ? '#fff' : 'var(--black)' }} onClick={() => setSelected({ site: climate.query, crop: crop.id })}>
            <b>{item ? pct(item.suitability) : '—'}</b><small>{item?.plantMonth != null ? `${MONTH_SHORT[item.plantMonth]}→${MONTH_SHORT[item.harvestMonth ?? item.plantMonth]}` : 'no season'}</small>
          </button></td>;
        })}</tr>)}</tbody>
      </table></div>

      {detail?.climate && detail.crop && <div className="explorer-detail">
        <div><span className="mono">WHY · {detail.climate.name.toUpperCase()} · {detail.crop.name.toUpperCase()}</span>
          <h3>{detail.prediction ? `${pct(detail.prediction.suitability)} suitable` : 'No prediction'}{detail.prediction?.plantMonth != null ? ` · plant ${MONTH_LONG[detail.prediction.plantMonth]}` : ''}</h3>
          {detail.prediction?.notes && <p>{detail.prediction.notes}</p>}{detail.prediction?.confidence != null && <p className="mono model-confidence">CONFIDENCE {pct(detail.prediction.confidence)} · SOURCE {detail.prediction.source === 'ml' ? 'MODEL' : 'CROP CALENDAR'}</p>}
          <ClimateChart climate={detail.climate} cropMin={detail.crop.tempMinC} cropMax={detail.crop.tempMaxC} plant={detail.prediction?.plantMonth ?? null} grow={detail.crop.growMonths} />
        </div>
        <details><summary>Raw model input and output</summary><div className="json-pair">
          <pre>{JSON.stringify({ ...(result.request as object), sites: (result.request as { sites: Array<{ id: string }> }).sites.filter((site) => site.id === selected?.site), crops: (result.request as { crops: Array<{ id: string }> }).crops.filter((crop) => crop.id === selected?.crop) }, null, 2)}</pre>
          <pre>{JSON.stringify({ model: result.model, predictions: [detail.prediction] }, null, 2)}</pre>
        </div></details>
      </div>}
    </div>}
  </section>;
}

function ClimateChart({ climate, cropMin, cropMax, plant, grow }: { climate: MonthlyClimate; cropMin: number; cropMax: number; plant: number | null; grow: number }) {
  const width = 600; const height = 180; const pad = 28;
  const lo = Math.min(-5, ...climate.temperatureC, cropMin) ; const hi = Math.max(40, ...climate.temperatureC, cropMax);
  const y = (t: number) => height - pad - ((t - lo) / (hi - lo)) * (height - 2 * pad);
  const band = (width - 2 * pad) / 12;
  const inWindow = (month: number) => plant !== null && ((month - plant + 12) % 12) < grow;
  const maxSolar = Math.max(...climate.solarMjM2Day);
  return <svg className="climate-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Monthly temperature in ${climate.name} against the crop's range`}>
    <rect x={pad} y={y(cropMax)} width={width - 2 * pad} height={y(cropMin) - y(cropMax)} className="crop-band" />
    <text x={width - pad} y={y(cropMax) - 4} textAnchor="end" className="chart-note">crop range {cropMin}–{cropMax}°C</text>
    {climate.temperatureC.map((t, month) => {
      const x = pad + month * band;
      return <g key={month}>
        {inWindow(month) && <rect x={x} y={pad - 8} width={band} height={height - 2 * pad + 8} className="window-band" />}
        <rect x={x + band * .3} y={height - pad - (climate.solarMjM2Day[month] / maxSolar) * 34} width={band * .4} height={(climate.solarMjM2Day[month] / maxSolar) * 34} className="solar-bar"><title>{climate.solarMjM2Day[month].toFixed(1)} MJ/m²/day</title></rect>
        <circle cx={x + band / 2} cy={y(t)} r={4.5} className={t >= cropMin && t <= cropMax ? 'temp-dot ok' : 'temp-dot'}><title>{MONTH_LONG[month]}: {t.toFixed(1)}°C</title></circle>
        <text x={x + band / 2} y={height - 8} textAnchor="middle" className="chart-month">{MONTH_SHORT[month][0]}</text>
      </g>;
    })}
    <polyline points={climate.temperatureC.map((t, month) => `${pad + month * band + band / 2},${y(t)}`).join(' ')} className="temp-line" />
  </svg>;
}
