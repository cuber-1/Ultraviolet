import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, CalendarDays, CircleAlert, Droplets, MapPin, RotateCcw, Sun, ThermometerSun } from 'lucide-react';
import Wordmark from '../components/Wordmark';
import SearchGlobe from '../components/SearchGlobe';
import DeepAgentLoader, { type LoaderStage } from '../components/DeepAgentLoader';
import DeepAgentSite from './DeepAgentSite';
import { OptimalPointsChart, PlantingCurveChart, SunCoverageChart } from '../components/charts/DeepAgentCharts';
import { runAgentComparison, type AgentComparison, type CropModelInfo, type CropPrediction, type SearchResult } from '../services/vexcel';
import {
  MONTH_LONG, MONTH_SHORT, applyModel, briefCrops, cropProfiles, fetchMlCapabilities, fetchMonthlyClimate, fetchRegionPredictions, formatArea, loadBrief, planForLocation, ruralPlaces, saveBrief,
  urbanAgentCriteria, urbanAreaLabel, type Brief, type CropTiming, type LocationPlan,
} from '../services/cropPlan';
import { getRun, saveRun, savedTime } from '../services/runs';
import './PlanPage.css';

const TOP_N = 5;
const URBAN_STAGES: LoaderStage[] = [
  { key: 'climate', label: 'Climate calendar' },
  { key: 'planning', label: 'Planning' },
  { key: 'imagery', label: 'Aerial search' },
  { key: 'property', label: 'Property records' },
  { key: 'geometry', label: 'Roof geometry' },
  { key: 'sunlight', label: 'Sunlight' },
  { key: 'model', label: 'Crop model' },
  { key: 'ranking', label: 'Ranking' },
];
const RURAL_STAGES: LoaderStage[] = [
  { key: 'geocode', label: 'Locating towns' },
  { key: 'climate', label: 'NASA climate' },
  { key: 'calendar', label: 'Crop model' },
  { key: 'ranking', label: 'Ranking' },
];

type UrbanOutcome = { kind: 'urban'; brief: Brief; plan: LocationPlan | null; criteria: ReturnType<typeof urbanAgentCriteria>; comparison: AgentComparison; top: SearchResult[] };
type RuralOutcome = { kind: 'rural'; brief: Brief; plans: LocationPlan[]; errors: Array<{ location: string; error: string }>; model?: CropModelInfo | null };
type Outcome = UrbanOutcome | RuralOutcome;

const RESULT_KEY = 'ultraviolet.plan.result';
const saveOutcome = (outcome: Outcome) => { try { sessionStorage.setItem(RESULT_KEY, JSON.stringify(outcome)); } catch { /* storage unavailable */ } };
const loadOutcome = (brief: Brief): Outcome | null => {
  try { const raw = sessionStorage.getItem(RESULT_KEY); const value = raw ? JSON.parse(raw) as Outcome : null; return value && JSON.stringify(value.brief) === JSON.stringify(brief) ? value : null; } catch { return null; }
};
const cropList = (brief: Brief) => { const names = briefCrops(brief).map((crop) => crop.name.toLowerCase()); return names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names.at(-1)}` : names[0] ?? 'your crops'; };
const sqft = (value: number | null | undefined) => value === null || value === undefined ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)} ft²`;
const shortDate = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

export default function PlanPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = location.state as { brief?: Brief; run?: number; savedId?: string } | null;
  const brief = useMemo(() => routeState?.brief ?? loadBrief(), [routeState?.brief]);
  const [outcome, setOutcome] = useState<Outcome | null>(() => (brief && !routeState?.run && !routeState?.savedId ? loadOutcome(brief) : null));
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stageIndex, setStageIndex] = useState(0);
  const [log, setLog] = useState<string[]>([]);
  const [startedAt, setStartedAt] = useState(Date.now());
  const [climatePlan, setClimatePlan] = useState<LocationPlan | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const run = useCallback(async (input: Brief) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    // Only the newest run may touch state (StrictMode and "Run again" can leave an older run finishing).
    const live = () => requestRef.current === controller && !controller.signal.aborted;
    const push = (message: string) => { if (live()) setLog((items) => [...items, message]); };
    const advance = (stages: LoaderStage[], key: string) => { if (live()) setStageIndex((current) => Math.max(current, stages.findIndex((stage) => stage.key === key))); };
    setRunning(true); setError(null); setOutcome(null); setSavedAt(null); setLog([]); setStageIndex(0); setStartedAt(Date.now()); setClimatePlan(null);
    try {
      if (input.scale === 'urban') {
        push(`Reading NASA monthly climate for ${urbanAreaLabel(input)}`);
        const climate = await fetchMonthlyClimate([input.urbanArea ?? ''], controller.signal).catch(() => null);
        if (!live()) return;
        const plan = climate?.results[0] ? planForLocation(input, climate.results[0]) : null;
        setClimatePlan(plan);
        const criteria = urbanAgentCriteria(input, plan);
        push(plan?.moveInMonth !== null && plan ? `Best start month: ${MONTH_LONG[plan.moveInMonth!]}` : 'Climate unavailable; using your preferred month');
        advance(URBAN_STAGES, 'planning');
        const comparison = await runAgentComparison({
          goal: criteria.goal, location: input.urbanArea ?? 'All available Vexcel coverage', lat: 0, lon: 0, radiusM: 20_000,
          dates: criteria.dates, targetHours: criteria.targetHours, targetAreaSqft: criteria.targetAreaSqft,
          crops: briefCrops(input).map((crop) => crop.name), cropProfiles: cropProfiles(input), preferredMonth: input.preferredMonth, source: 'guided',
        }, (event) => { advance(URBAN_STAGES, event.stage); push(event.message); }, controller.signal);
        if (!live()) return;
        const byId = new Map(comparison.candidates.map((candidate) => [candidate.id, candidate]));
        const top = comparison.simulations.flatMap((simulation) => byId.get(simulation.candidateId) ?? []).slice(0, TOP_N);
        const next: UrbanOutcome = { kind: 'urban', brief: input, plan, criteria, comparison, top };
        setOutcome(next); saveOutcome(next); void saveRun(input, next).catch(() => undefined);
        navigate('/plan', { replace: true, state: { brief: input } });
      } else {
        const places = ruralPlaces(input);
        push(`Locating ${places.length} farming towns`);
        const [climate, caps] = await Promise.all([fetchMonthlyClimate(places, controller.signal), fetchMlCapabilities(controller.signal)]);
        if (!live()) return;
        advance(RURAL_STAGES, 'climate'); push('Reading NASA POWER monthly climatology');
        advance(RURAL_STAGES, 'calendar'); push(`Scoring ${briefCrops(input).length} crops in ${climate.results.length} towns with the crop model`);
        // Strict live mode: a model failure is an error, never a quiet calendar substitute.
        const model = await fetchRegionPredictions(input, climate.results, controller.signal).catch((reason) => { if (caps?.strict) throw reason; return null; });
        if (!live()) return;
        if (model) push(model.model.source === 'ml' ? `Crop model ${model.model.name} scored every town` : 'Crop model offline; using the climate crop calendar');
        const plans = climate.results.map((result) => applyModel(planForLocation(input, result), model?.predictions ?? [], input.preferredMonth)).sort((a, b) => b.score - a.score);
        advance(RURAL_STAGES, 'ranking'); push('Ranking by crop fit');
        if (!live()) return;
        const next: RuralOutcome = { kind: 'rural', brief: input, plans, errors: climate.errors, model: model?.model ?? null };
        setOutcome(next); saveOutcome(next); void saveRun(input, next).catch(() => undefined);
        navigate('/plan', { replace: true, state: { brief: input } });
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'The search failed.';
      // A dropped stream (server restart, Wi-Fi blip) surfaces as a bare "network error" / "Failed to fetch".
      if (live()) setError(/network|failed to fetch|load failed|terminated/i.test(message) ? 'The connection to the Ultraviolet server dropped mid-search (it may have restarted). Your answers are saved; try again.' : message);
    } finally {
      if (requestRef.current === controller && !controller.signal.aborted) setRunning(false);
    }
  }, [navigate]);

  // Open a saved result instantly instead of running the search again.
  useEffect(() => {
    const id = routeState?.savedId;
    if (!id) return;
    const controller = new AbortController();
    getRun<Outcome>(id, controller.signal).then((record) => {
      setOutcome(record.outcome); saveOutcome(record.outcome); saveBrief(record.outcome.brief); setSavedAt(record.savedAt); setError(null);
    }).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Saved run not found.'); });
    return () => controller.abort();
  }, [routeState?.savedId]);

  useEffect(() => {
    if (routeState?.savedId) return;
    if (brief && !outcome) void run(brief);
    return () => requestRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brief, routeState?.run]);

  useEffect(() => {
    if (!running) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [running]);

  const openSite = useCallback((id: string) => navigate(`/plan?site=${encodeURIComponent(id)}`), [navigate]);

  if (!brief) return <Navigate to="/start" replace />;

  const selectedId = new URLSearchParams(location.search).get('site');
  if (outcome?.kind === 'urban' && selectedId) {
    const order = rankedIds(outcome);
    const result = outcome.top.find((item) => item.id === selectedId) ?? outcome.comparison.candidates.find((item) => item.id === selectedId);
    if (result) return <DeepAgentSite result={result} rank={order.indexOf(result.id) + 1} total={outcome.top.length}
      simulation={outcome.comparison.simulations.find((item) => item.candidateId === result.id) ?? null}
      predictions={(outcome.comparison.predictions ?? []).filter((item) => item.siteId === result.id)}
      crops={briefCrops(outcome.brief).map(({ id, name }) => ({ id, name }))}
      criteria={outcome.criteria} preferredMonth={outcome.brief.preferredMonth}
      explanation={outcome.comparison.narrative?.explanations.find((item) => item.candidateId === result.id)?.explanation ?? null}
      mlModel={outcome.comparison.mlModel ?? null} onClose={() => navigate('/plan')} />;
  }

  const cancel = () => { requestRef.current?.abort(); setRunning(false); navigate('/start'); };
  const urban = brief.scale === 'urban';

  return <div className="plan-page">
    {running && <DeepAgentLoader
      kicker={urban ? 'DEEP AGENT · LIVE' : 'CLIMATE MATCH · LIVE'}
      title={urban ? 'Finding your roof' : 'Finding your region'}
      subtitle={urban
        ? `Searching ${urbanAreaLabel(brief)} for ${formatArea(brief.areaSqft)} of roof that suits ${cropList(brief)}.`
        : `Comparing ${ruralPlaces(brief).length} farming towns for ${cropList(brief)} on ${formatArea(brief.areaSqft)}.`}
      stages={urban ? URBAN_STAGES : RURAL_STAGES}
      activeIndex={stageIndex}
      message={log.at(-1) ?? 'Starting'}
      log={log}
      startedAt={startedAt}
      expected={urban ? 'USUALLY 1–3 MIN' : 'A FEW SECONDS'}
      insight={urban && climatePlan ? <TimingInsight plan={climatePlan} brief={brief} /> : undefined}
      onCancel={cancel}
    />}

    <header className="plan-header">
      <button className="plan-back" onClick={() => navigate('/start')}><ArrowLeft size={16} /> Edit answers</button>
      <Wordmark />
      <button className="plan-rerun" onClick={() => void run(brief)} disabled={running}><RotateCcw size={14} /> Run again</button>
    </header>

    {savedAt && outcome && !running && <div className="saved-banner"><span className="mono">SAVED RESULT</span><span>From {savedTime(savedAt)}. Opened instantly; nothing was re-run.</span><button onClick={() => void run(brief)}><RotateCcw size={13} /> Run live now</button></div>}
    {error && <main className="plan-main"><div className="plan-error"><CircleAlert /><div><strong>{urban ? 'The Deep Agent could not finish' : 'Climate lookup failed'}</strong><p>{error}</p><div><button onClick={() => void run(brief)}>Try again</button><button onClick={() => navigate('/start')}>Edit answers</button></div></div></div></main>}
    {outcome?.kind === 'urban' && <UrbanResults outcome={outcome} onOpen={openSite} />}
    {outcome?.kind === 'rural' && <RuralResults outcome={outcome} />}
  </div>;
}

function TimingInsight({ plan, brief }: { plan: LocationPlan; brief: Brief }) {
  return <div className="timing-insight">
    <span className="mono">CLIMATE CALENDAR · {plan.climate.name.toUpperCase()}</span>
    <div>{plan.timings.map((timing) => <p key={timing.crop.id}><strong>{timing.crop.name}</strong>{timing.startMonth === null ? 'No full season in this climate' : `Plant ${MONTH_SHORT[timing.startMonth]} → harvest ${MONTH_SHORT[timing.harvestMonth!]}`}</p>)}</div>
    <small>Looking for {Math.max(...briefCrops(brief).map((crop) => crop.sunHours))} h of direct sun across {formatArea(brief.areaSqft)}.</small>
  </div>;
}

function CropCalendar({ timings, preferredMonth }: { timings: CropTiming[]; preferredMonth: number }) {
  return <div className="crop-calendar">
    <div className="crop-calendar-row crop-calendar-head"><span />{MONTH_SHORT.map((month, index) => <em key={month} className={index === preferredMonth ? 'preferred' : ''}>{month[0]}</em>)}</div>
    {timings.map((timing) => {
      const inWindow = (month: number) => timing.startMonth !== null && ((month - timing.startMonth + 12) % 12) < timing.crop.growMonths;
      return <div className="crop-calendar-row" key={timing.crop.id}>
        <span>{timing.crop.name}</span>
        {timing.growable.map((ok, month) => <i key={month} className={[ok ? 'ok' : '', inWindow(month) ? 'window' : '', month === timing.startMonth ? 'start' : ''].join(' ')} title={`${MONTH_LONG[month]}: ${ok ? 'temperature fits' : 'outside temperature range'}${month === timing.startMonth ? ' · recommended start' : ''}`} />)}
      </div>;
    })}
    <div className="crop-calendar-key"><span><i className="window" /> Recommended season</span><span><i className="ok" /> Temperature fits</span><span><i /> Too hot or cold</span></div>
  </div>;
}

function UrbanResults({ outcome, onOpen }: { outcome: UrbanOutcome; onOpen: (id: string) => void }) {
  const { brief, plan, criteria, comparison, top } = outcome;
  const simulations = new Map(comparison.simulations.map((simulation) => [simulation.candidateId, simulation]));
  const explanations = new Map((comparison.narrative?.explanations ?? []).map((item) => [item.candidateId, item.explanation]));
  const [hovered, setHovered] = useState<string | null>(null);
  const points = useMemo(() => top.map((result, index) => ({ id: result.id, lat: result.lat, lon: result.lon, rank: index + 1 })), [top]);
  const predictionsBySite = useMemo(() => { const map = new Map<string, CropPrediction[]>(); for (const item of comparison.predictions ?? []) map.set(item.siteId, [...(map.get(item.siteId) ?? []), item]); return map; }, [comparison.predictions]);
  const cropName = (id: string) => briefCrops(brief).find((crop) => crop.id === id)?.name ?? id;
  return <main className="plan-main">
    <section className="plan-hero">
      <span className="mono">{comparison.mode === 'deep-agent' ? `DEEP AGENT · ${comparison.model ?? ''}`.trim() : 'DIRECT COMPARISON'} · {urbanAreaLabel(brief).toUpperCase()}</span>
      <h1>Your top {top.length} roofs for {cropList(brief)}.</h1>
      <dl className="plan-stats">
        <div><dt>Growing area</dt><dd>{formatArea(criteria.targetAreaSqft)}</dd></div>
        <div><dt>Direct sun needed</dt><dd>{criteria.targetHours} h / day</dd></div>
        <div><dt>Best start</dt><dd>{MONTH_LONG[criteria.startMonth]}</dd></div>
        <div><dt>Sun checked on</dt><dd>{criteria.dates.map(shortDate).join(' + ')}</dd></div>
      </dl>
    </section>

    <UrbanInsights outcome={outcome} onOpen={onOpen} />

    <section className="plan-grid">
      <ol className="roof-list">
        {top.length === 0 && <li className="plan-empty">No roofs came back from this search. Try another city or a smaller area.</li>}
        {top.map((result, index) => {
          const simulation = simulations.get(result.id);
          const shared = simulation?.sharedAreaSqft ?? null;
          const ratio = shared === null ? 0 : Math.min(1, shared / criteria.targetAreaSqft);
          const meets = shared !== null && shared >= criteria.targetAreaSqft;
          const title = result.costar?.buildingName || result.costar?.address || (result.property?.roofAreaSqft ? `${sqft(result.property.roofAreaSqft)} roof` : 'Rooftop');
          return <li key={result.id} className={hovered === result.id ? 'roof-card hovered' : 'roof-card'} onMouseEnter={() => setHovered(result.id)} onMouseLeave={() => setHovered(null)}>
            <button onClick={() => onOpen(result.id)}>
              <span className="roof-rank">{index + 1}</span>
              <img src={result.imageryUrl} alt="" loading="lazy" />
              <div className="roof-body">
                <strong>{title}</strong>
                <span className="roof-address"><MapPin size={12} /> {result.costar?.address || `${result.lat.toFixed(4)}, ${result.lon.toFixed(4)}`}</span>
                <div className="roof-meter"><div style={{ width: `${ratio * 100}%` }} className={meets ? 'meets' : ''} /></div>
                <span className="roof-metric">{shared === null ? 'Sunlight not assessed · missing roof geometry' : <><b>{sqft(shared)}</b> gets {criteria.targetHours} h on both dates{meets ? ' · meets your area' : ` · ${Math.round(ratio * 100)}% of target`}</>}</span>
                {explanations.get(result.id) && <p className="roof-why">{explanations.get(result.id)}</p>}
                {(predictionsBySite.get(result.id)?.length ?? 0) > 0 && <div className="roof-crops">{predictionsBySite.get(result.id)!.map((item) => <span key={item.cropId} title={item.notes ?? undefined}><b>{cropName(item.cropId)}</b> {Math.round(item.suitability * 100)}%{item.plantMonth !== null ? ` · plant ${MONTH_SHORT[item.plantMonth]}${item.harvestMonth !== null ? ` → ${MONTH_SHORT[item.harvestMonth]}` : ''}` : ' · no season'}</span>)}</div>}
                <div className="roof-chips">
                  {result.property?.roofAreaSqft && <span>{sqft(result.property.roofAreaSqft)} roof</span>}
                  {result.costar ? <span>{result.costar.propertyType}</span> : <span className="muted">No property record</span>}
                  {result.costar?.listing?.active && <span className="hot">Active listing</span>}
                  {(result.costar?.matterport.length ?? 0) > 0 && <span>3D tour</span>}
                  {simulation?.geometry.obstructionCount ? <span>{simulation.geometry.obstructionCount} obstructions</span> : null}
                </div>
              </div>
              <span className="roof-open">Open <ArrowRight size={14} /></span>
            </button>
          </li>;
        })}
      </ol>

      <aside className="plan-side">
        <div className="plan-globe"><SearchGlobe points={points} onPointClick={onOpen} /></div>
        {comparison.mlModel && <ModelCard model={comparison.mlModel} />}
        {plan && <div className="plan-card"><header><CalendarDays size={15} /><strong>When to start</strong><span className="mono">{plan.climate.name}</span></header><CropCalendar timings={plan.timings} preferredMonth={brief.preferredMonth} /></div>}
        {comparison.narrative?.summary && <div className="plan-card"><header><Sun size={15} /><strong>Agent summary</strong></header><p>{comparison.narrative.summary}</p></div>}
        {(comparison.narrative?.unknowns.length ?? 0) > 0 && <details className="plan-card plan-unknowns"><summary>What we couldn’t verify ({comparison.narrative!.unknowns.length})</summary><ul>{comparison.narrative!.unknowns.map((item) => <li key={item}>{item}</li>)}</ul></details>}
      </aside>
    </section>
  </main>;
}

function RuralResults({ outcome }: { outcome: RuralOutcome }) {
  const { brief, plans, errors } = outcome;
  const top = useMemo(() => plans.slice(0, TOP_N), [plans]);
  const points = useMemo(() => top.map((plan, index) => ({ id: plan.climate.query, lat: plan.climate.lat, lon: plan.climate.lon, rank: index + 1 })), [top]);
  const [openId, setOpenId] = useState<string | null>(top[0]?.climate.query ?? null);
  return <main className="plan-main">
    <section className="plan-hero rural">
      <span className="mono">{outcome.model?.source === 'ml' ? `CROP MODEL · ${outcome.model.name.toUpperCase()}` : 'CLIMATE MATCH · NASA POWER'} · {plans.length} TOWNS COMPARED</span>
      <h1>Your top {top.length} regions for {cropList(brief)}.</h1>
      <dl className="plan-stats">
        <div><dt>Land</dt><dd>{formatArea(brief.areaSqft)}</dd></div>
        <div><dt>Crops</dt><dd>{briefCrops(brief).length}</dd></div>
        <div><dt>Preferred start</dt><dd>{MONTH_LONG[brief.preferredMonth]}</dd></div>
        <div><dt>Best match</dt><dd>{top[0]?.climate.name ?? '—'}</dd></div>
      </dl>
    </section>

    <section className="plan-grid">
      <ol className="region-list">
        {top.map((plan, index) => {
          const open = openId === plan.climate.query;
          const wait = plan.moveInMonth === null ? null : (plan.moveInMonth - brief.preferredMonth + 12) % 12;
          return <li key={plan.climate.query} className={open ? 'region-card open' : 'region-card'}>
            <button className="region-summary" onClick={() => setOpenId(open ? null : plan.climate.query)}>
              <span className="roof-rank">{index + 1}</span>
              <div><strong>{plan.climate.name}</strong><span className="roof-address"><MapPin size={12} /> {plan.climate.region}</span></div>
              <div className="region-move"><small>START</small><b>{plan.moveInMonth === null ? 'No season' : MONTH_SHORT[plan.moveInMonth]}</b><small>{wait === null ? '' : wait === 0 ? 'right away' : `in ${wait} mo`}</small></div>
              <div className="region-score"><b>{plan.score}</b><small>FIT</small></div>
            </button>
            {open && <div className="region-detail">
              <div className="region-metrics">
                <span><Sun size={14} /><b>{plan.climate.annual.solarMjM2Day.toFixed(1)}</b> MJ/m²/day</span>
                <span><ThermometerSun size={14} /><b>{plan.climate.annual.temperatureC.toFixed(1)}°C</b> mean</span>
                <span><Droplets size={14} /><b>{plan.climate.annual.precipitationMmDay.toFixed(1)}</b> mm/day rain</span>
              </div>
              <CropCalendar timings={plan.timings} preferredMonth={brief.preferredMonth} />
              <ul className="region-reasons">{plan.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </div>}
          </li>;
        })}
        {errors.map((item) => <li key={item.location} className="plan-empty">{item.location}: {item.error}</li>)}
      </ol>
      <aside className="plan-side">
        <div className="plan-globe"><SearchGlobe points={points} onPointClick={setOpenId} unitLabel="REGIONS" /></div>
        {outcome.model && <ModelCard model={outcome.model} />}
        <div className="plan-card"><header><CircleAlert size={15} /><strong>How this is scored</strong></header><p>{outcome.model?.source === 'ml' ? 'Fit is the crop model’s average suitability across your crops, and planting windows come from the model. ' : ''}{outcome.model?.source === 'ml' ? 'Without the model, fit' : 'Fit'} combines how many of your crops have a full growing season (45%), how soon they can start after your preferred month (25%), season length (15%), and annual solar resource (15%). A month counts when NASA’s average temperature sits inside the crop’s range. Soil, water rights, parcels, and price are not assessed yet.</p></div>
      </aside>
    </section>
  </main>;
}

function ModelCard({ model }: { model: CropModelInfo }) {
  const live = model.source === 'ml';
  return <div className={live ? 'plan-card model-card live' : 'plan-card model-card'}>
    <header><Sun size={15} /><strong>{live ? (model.error ? 'Crop model error' : 'Crop model') : 'Crop calendar'}</strong><span className="mono">{live ? `${model.name}${model.version ? ` · ${model.version}` : ''}` : 'MODEL OFFLINE'}</span></header>
    <p>{live
      ? 'Suitability and planting windows come from the trained crop model, using each site’s climate and measured sunlight. Ranking blends 60% sunlit area with 40% crop suitability.'
      : 'The trained crop model is not connected, so suitability and timing come from NASA monthly temperatures and each crop’s growing range.'}</p>
    {model.error && <p className="model-error">{model.error}</p>}
  </div>;
}

/** Roof ids in final rank order (server already sorted simulations). */
function rankedIds(outcome: UrbanOutcome) {
  return outcome.comparison.simulations.map((item) => item.candidateId);
}

function UrbanInsights({ outcome, onOpen }: { outcome: UrbanOutcome; onOpen: (id: string) => void }) {
  const { brief, criteria, comparison } = outcome;
  const crops = briefCrops(brief).map(({ id, name }) => ({ id, name }));
  const byId = new Map(comparison.candidates.map((item) => [item.id, item]));
  const roofs = comparison.simulations.flatMap((simulation, index) => {
    const result = byId.get(simulation.candidateId);
    if (!result) return [];
    const hours = simulation.perDate.map((item) => item.meanHours).filter((value): value is number => value !== null);
    const label = result.costar?.buildingName || result.costar?.address?.split(',')[0] || (result.property?.roofAreaSqft ? `${Math.round(result.property.roofAreaSqft / 1000)}k ft² roof` : 'Rooftop');
    return [{ id: result.id, rank: index + 1, label, sunlitSqft: simulation.sharedAreaSqft, roofSqft: result.property?.roofAreaSqft ?? null, meanHours: hours.length ? hours.reduce((a, b) => a + b, 0) / hours.length : null }];
  });
  const predictions = comparison.predictions ?? [];
  const fitPoints = roofs.map((roof) => ({ ...roof, fitByCrop: Object.fromEntries(crops.map((crop) => { const p = predictions.find((item) => item.siteId === roof.id && item.cropId === crop.id && item.source === 'ml'); return [crop.id, p ? p.suitability * 100 : null]; })) }));
  const reference = roofs[0] ? predictions.filter((item) => item.siteId === roofs[0].id) : [];
  const series = crops.flatMap((crop) => { const p = reference.find((item) => item.cropId === crop.id); return p?.curve?.length === 12 ? [{ id: crop.id, name: crop.name, curve: p.curve, plantMonth: p.plantMonth, harvestMonth: p.harvestMonth, suitableMonths: p.suitableMonths ?? [] }] : []; });
  const best = roofs.reduce<typeof roofs[number] | null>((top, roof) => (roof.sunlitSqft ?? -1) > (top?.sunlitSqft ?? -1) ? roof : top, null);
  const meeting = roofs.filter((roof) => (roof.sunlitSqft ?? 0) >= criteria.targetAreaSqft).length;
  const firstStart = series.filter((item) => item.plantMonth !== null).sort((a, b) => ((a.plantMonth! - brief.preferredMonth + 12) % 12) - ((b.plantMonth! - brief.preferredMonth + 12) % 12))[0];
  return <section className="insights">
    <article className="insight-card">
      <header><span className="mono">01 · SUN COVERAGE</span><h2>{best?.sunlitSqft ? `Up to ${new Intl.NumberFormat('en-US').format(Math.round(best.sunlitSqft))} ft² gets ${criteria.targetHours} h of sun.` : 'Sun coverage'}</h2><p>{meeting} of {roofs.length} roofs checked have enough area in {criteria.targetHours}+ hours of direct sun on every date.</p></header>
      <SunCoverageChart rows={roofs} targetAreaSqft={criteria.targetAreaSqft} targetHours={criteria.targetHours} onSelect={onOpen} />
    </article>
    <article className="insight-card">
      <header><span className="mono">02 · OPTIMAL POINTS</span><h2>Where sun and crop fit meet.</h2><p>Each roof by sunlit area and the crop model’s fit for your crops. Prime roofs clear both lines.</p></header>
      {predictions.some((item) => item.source === 'ml') ? <OptimalPointsChart points={fitPoints} crops={crops} targetAreaSqft={criteria.targetAreaSqft} onSelect={onOpen} /> : <p className="viz-empty">The crop model did not score this search{comparison.mlModel?.error ? `: ${comparison.mlModel.error}` : ''}.</p>}
    </article>
    <article className="insight-card wide">
      <header><span className="mono">03 · WHEN TO START</span><h2>{firstStart ? `Start ${firstStart.name.toLowerCase()} in ${['January','February','March','April','May','June','July','August','September','October','November','December'][firstStart.plantMonth!]}.` : 'When to start'}</h2><p>Crop-model fit for each planting month in {urbanAreaLabel(brief)}, with the model’s uncertainty. Circles mark the recommended start on or after your chosen month.</p></header>
      <PlantingCurveChart series={series} preferredMonth={brief.preferredMonth} />
    </article>
  </section>;
}
