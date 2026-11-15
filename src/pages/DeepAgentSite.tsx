import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Box, CalendarDays, Cpu, ExternalLink, LayoutGrid, MapPin, ShieldCheck, Sun } from 'lucide-react';
import { SiteWorkspace } from './AgriculturePage';
import RoofPreview3D from '../components/RoofPreview3D';
import { CLASSES, ComponentBars, CropTimeline, PlantingCurveChart, classify, CROP_COLORS } from '../components/charts/DeepAgentCharts';
import type { CropModelInfo, CropPrediction, SearchResult, SunlightEvidence } from '../services/vexcel';
import { cropById, estimateFood, formatLbs, type Crop } from '../services/cropPlan';
import { roofTitle, useAddresses } from '../services/addresses';
import './DeepAgentSite.css';
import MapsLink from '../components/MapsLink';
import SiteReadinessPanel from '../components/SiteReadinessPanel';

export type SiteCrop = { id: string; name: string };
type Tab = 'overview' | 'readiness' | 'sun' | 'model' | 'calendar' | 'tour';
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const fmt = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
/** Sun score 0-100: 60 pts for area (full when twice the requested area meets the sun target), 40 pts for average direct-sun hours (full at 12 h). */
export function sunScore(sunlitSqft: number | null, targetSqft: number, meanHours: number | null) {
  if (sunlitSqft === null) return null;
  const area = Math.min(1, sunlitSqft / Math.max(1, targetSqft * 2));
  const hours = meanHours === null ? 0 : Math.min(1, meanHours / 12);
  return Math.round(60 * area + 40 * hours);
}
const shortDate = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

export default function DeepAgentSite({ result, rank, total, simulation, predictions, crops, criteria, explanation, mlModel, preferredMonth, initialTab, onClose }: {
  result: SearchResult; rank: number; total: number;
  simulation: SunlightEvidence | null; predictions: CropPrediction[]; crops: SiteCrop[];
  criteria: { dates: string[]; targetHours: number; targetAreaSqft: number };
  explanation: string | null; mlModel: CropModelInfo | null; preferredMonth: number; initialTab?: string | null; onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>(initialTab === 'readiness' ? 'readiness' : 'overview');
  const addresses = useAddresses([{ id: result.id, lat: result.lat, lon: result.lon, known: Boolean(result.costar?.buildingName || result.costar?.address) }]);
  const title = roofTitle(result, addresses.get(result.id));
  const name = title.name;
  const sunlit = simulation?.sharedAreaSqft ?? null;
  const hours = simulation?.perDate.map((item) => item.meanHours).filter((value): value is number => value !== null) ?? [];
  const meanHours = hours.length ? hours.reduce((sum, value) => sum + value, 0) / hours.length : null;
  const modelPredictions = predictions.filter((item) => item.source === 'ml');
  const avgFit = modelPredictions.length ? (modelPredictions.reduce((sum, item) => sum + item.suitability, 0) / modelPredictions.length) * 100 : null;
  const cls = classify(sunlit, avgFit, criteria.targetAreaSqft);
  const sun = sunScore(sunlit, criteria.targetAreaSqft, meanHours);
  const lead = predictions.find((item) => item.source === 'ml' && item.plantMonth !== null) ?? null;
  const leadPoint = lead?.curve?.find((point) => point.month === lead.plantMonth) ?? null;
  const cropProfiles = crops.map((crop) => cropById(crop.id)).filter((crop): crop is Crop => Boolean(crop));
  const food = estimateFood(sunlit, cropProfiles, new Set(predictions.filter((item) => item.source === 'ml' && item.plantMonth === null).map((item) => item.cropId)));
  const starts = predictions.filter((item) => item.plantMonth !== null).sort((a, b) => ((a.plantMonth! - preferredMonth + 12) % 12) - ((b.plantMonth! - preferredMonth + 12) % 12));
  const cropName = (id: string) => crops.find((crop) => crop.id === id)?.name ?? id;
  const tabs: Array<{ key: Tab; label: string; icon: typeof Sun }> = [
    { key: 'overview', label: 'Overview', icon: LayoutGrid }, { key: 'readiness', label: 'Red & green flags', icon: ShieldCheck }, { key: 'sun', label: 'Sun coverage', icon: Sun },
    { key: 'model', label: 'ML model', icon: Cpu }, { key: 'calendar', label: 'Calendar', icon: CalendarDays },
    ...(result.costar?.matterport.length ? [{ key: 'tour' as Tab, label: '3D tour', icon: Box }] : []),
  ];

  return <div className="das">
    <header className="das-header">
      <button className="das-back" onClick={onClose}><ArrowLeft size={16} /> Top {total}</button>
      <div className="das-title"><span className="das-eyebrow">Roof {rank} of {total}</span><h1>{name}</h1><p><MapPin size={13} /> <MapsLink lat={result.lat} lon={result.lon} address={title.line} /></p></div>
      <span className="das-class" style={{ borderColor: CLASSES[cls].color }}><i style={{ background: CLASSES[cls].color }} />{CLASSES[cls].label}</span>
    </header>
    <nav className="das-tabs" role="tablist">{tabs.map(({ key, label, icon: Icon }) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}><Icon size={15} /> {label}</button>)}</nav>

    {tab === 'overview' && <main className="das-body das-overview">
      <RoofPreview3D result={result} date={criteria.dates[0]} targetHours={criteria.targetHours} targetAreaSqft={criteria.targetAreaSqft} />
      <section>
        <div className="das-metrics">
          <Metric tone="sun" label="Sun score" value={sun === null ? '—' : `${sun}`} unit="/ 100" hint={sunlit === null ? 'Roof geometry missing' : `${fmt(sunlit)} ft² gets ${criteria.targetHours} h+ · ${meanHours === null ? '—' : meanHours.toFixed(1)} h average`} />
          <Metric tone="fit" label="Crop fit" value={avgFit === null ? '—' : `${Math.round(avgFit)}`} unit={leadPoint?.uncertainty != null ? `± ${Math.round(leadPoint.uncertainty)}` : '/ 100'} hint={lead ? `${cropName(lead.cropId)} in ${MONTHS[lead.plantMonth!]}${leadPoint?.historicalP10 != null && leadPoint.historicalP90 != null ? ` · past years ${Math.round(leadPoint.historicalP10)}–${Math.round(leadPoint.historicalP90)}` : ''}` : 'Model unavailable'} />
          <Metric tone="food" label="Food per year" value={food ? formatLbs(food.lbsPerYear) : '—'} unit="lbs" hint={food ? `${fmt(food.usableSqft)} ft² of beds · estimate` : 'Needs sunlit area'} />
        </div>
        {explanation && <div className="das-card das-why"><span className="das-label">Why it ranks #{rank}</span><p title={explanation}>{explanation}</p></div>}
        <div className="das-pair">
        <div className="das-card">
          <span className="das-label">Your crops here</span>
          <ul className="das-crops">{crops.map((crop, index) => { const item = predictions.find((p) => p.cropId === crop.id); return <li key={crop.id}><i style={{ background: CROP_COLORS[index % CROP_COLORS.length] }} /><strong>{crop.name}</strong>{item ? <span>{Math.round(item.suitability * 100)} fit · {item.plantMonth !== null ? `plant ${MONTHS[item.plantMonth].slice(0, 3)}${item.harvestMonth !== null ? ` → harvest ${MONTHS[item.harvestMonth].slice(0, 3)}` : ''}` : 'no workable month'}</span> : <span className="muted">Not scored by the model</span>}</li>; })}</ul>
        </div>
        <div className="das-card">
          <span className="das-label">Property</span>
          {result.costar ? <dl className="das-dl">
            <div><dt>Type</dt><dd>{result.costar.propertyType}</dd></div>
            <div><dt>Listing</dt><dd>{result.costar.listing?.active ? [...new Set(['Active', ...result.costar.listing.statuses])].join(' · ') : 'No active listing'}</dd></div>
            <div><dt>Roof (Vexcel)</dt><dd>{result.property?.roofAreaSqft ? `${fmt(result.property.roofAreaSqft)} ft²` : '—'}</dd></div>
            <div><dt>3D tours</dt><dd>{result.costar.matterport.length || 'None'}</dd></div>
          </dl> : <p className="muted">No CoStar property record within 125 m. Roof area from Vexcel: {result.property?.roofAreaSqft ? `${fmt(result.property.roofAreaSqft)} ft²` : 'unknown'}.</p>}
        </div>
        </div>
      </section>
    </main>}

    {tab === 'readiness' && <SiteReadinessPanel result={result} simulation={simulation} targetAreaSqft={criteria.targetAreaSqft} />}

    {tab === 'sun' && <main className="das-sun">
      <div className="das-sun-bar">
        <div className="das-sun-score"><span className="das-label">Sun score</span><strong>{sun ?? '—'}<small>/ 100</small></strong></div>
        <p>{sunlit === null ? 'No sunlight simulation for this roof.' : <><b>{fmt(sunlit)} ft²</b> gets {criteria.targetHours}+ hours of direct sun on every simulated date ({criteria.dates.map(shortDate).join(', ')}), {Math.round((sunlit / criteria.targetAreaSqft) * 100)}% of your {fmt(criteria.targetAreaSqft)} ft², averaging <b>{meanHours === null ? '—' : meanHours.toFixed(1)} h</b> a day.</>}</p>
      </div>
      <SiteWorkspace embedded initialSurfaceMode="clean" result={result} onClose={onClose} initialDate={criteria.dates[0]} initialTargetHours={criteria.targetHours} targetAreaSqft={criteria.targetAreaSqft} />
    </main>}

    {tab === 'tour' && result.costar && <TourTab name={name} tours={result.costar.matterport} roofSqft={result.property?.roofAreaSqft ?? null} sunlit={sunlit} />}

    {tab === 'model' && <ModelTab predictions={predictions} crops={crops} preferredMonth={preferredMonth} mlModel={mlModel} />}

    {tab === 'calendar' && <main className="das-body das-calendar">
      <div className="das-card wide">
        <span className="das-label">When to start</span>
        <h2>{starts[0] ? `Start with ${cropName(starts[0].cropId).toLowerCase()} in ${MONTHS[starts[0].plantMonth!]}.` : 'No workable planting month for these crops.'}</h2>
        <CropTimeline preferredMonth={preferredMonth} checkDates={criteria.dates} rows={crops.map((crop) => { const item = predictions.find((p) => p.cropId === crop.id); return { id: crop.id, name: crop.name, plantMonth: item?.plantMonth ?? null, harvestMonth: item?.harvestMonth ?? null, suitableMonths: item?.suitableMonths ?? [], growDays: item?.growingDays ?? null }; })} />
      </div>
      <div className="das-card wide">
        <span className="das-label">Step by step</span>
        <ol className="das-steps">{starts.map((item) => <li key={item.cropId}><strong>{MONTHS[item.plantMonth!]}</strong><span>Plant {cropName(item.cropId).toLowerCase()}{item.growingDays ? ` · ${Math.round(item.growingDays.min)}–${Math.round(item.growingDays.max)} days to harvest` : ''}{item.harvestMonth !== null ? ` · expect a harvest around ${MONTHS[item.harvestMonth]}` : ''}.</span>{(item.suitableMonths?.length ?? 0) > 1 && <small>Other workable starts: {item.suitableMonths!.filter((m) => m !== item.plantMonth).map((m) => MONTHS[m].slice(0, 3)).join(', ')}</small>}</li>)}
          <li><strong>Sun check</strong><span>Roof sunlight was simulated on {criteria.dates.map(shortDate).join(' and ')} for {criteria.targetHours} hours of direct sun.</span></li></ol>
      </div>
    </main>}
  </div>;
}

function Metric({ tone, label, value, unit, hint }: { tone: 'sun' | 'fit' | 'food'; label: string; value: string; unit: string; hint: string }) {
  return <div className={`das-metric ${tone}`}><span className="das-label">{label}</span><strong>{value}<small>{unit}</small></strong><small>{hint}</small></div>;
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return <div className="das-stat"><span className="das-label">{label}</span><strong>{value}</strong><small>{hint}</small></div>;
}

function ModelTab({ predictions, crops, preferredMonth, mlModel }: { predictions: CropPrediction[]; crops: SiteCrop[]; preferredMonth: number; mlModel: CropModelInfo | null }) {
  const scored = crops.filter((crop) => predictions.some((item) => item.cropId === crop.id));
  const [cropId, setCropId] = useState(scored[0]?.id ?? '');
  const [health, setHealth] = useState<{ metrics?: Record<string, number> | null; model?: { name?: string } | null } | null>(null);
  useEffect(() => { void fetch('/api/ml/health').then((response) => response.json()).then(setHealth).catch(() => setHealth(null)); }, []);
  const item = predictions.find((p) => p.cropId === cropId) ?? null;
  const index = Math.max(0, crops.findIndex((crop) => crop.id === cropId));
  const series = useMemo(() => crops.flatMap((crop) => { const p = predictions.find((x) => x.cropId === crop.id); return p?.curve?.length === 12 ? [{ id: crop.id, name: crop.name, curve: p.curve, plantMonth: p.plantMonth, harvestMonth: p.harvestMonth, suitableMonths: p.suitableMonths ?? [] }] : []; }), [crops, predictions]);
  const point = item?.curve?.find((entry) => entry.month === item.plantMonth) ?? null;
  const components = point?.components ?? null;
  if (!item) return <main className="das-body"><p className="viz-empty">The crop model did not score these crops for this roof.</p></main>;
  return <main className="das-body das-model">
    <div className="das-card wide">
      <div className="das-model-head"><div><span className="das-label">Crop model · {mlModel?.name ?? 'unknown'}</span><h2>Fit by planting month</h2></div>
        <div className="viz-filters">{scored.map((crop) => <button key={crop.id} className={crop.id === cropId ? 'active' : ''} onClick={() => setCropId(crop.id)}>{crop.name}</button>)}</div></div>
      <PlantingCurveChart series={series} preferredMonth={preferredMonth} focusId={cropId} />
    </div>
    <div className="das-model-grid">
      <div className="das-card">
        <span className="das-label" style={{ color: CROP_COLORS[index % CROP_COLORS.length] }}>{crops[index]?.name}</span>
        <div className="das-score"><strong>{Math.round(item.suitability * 100)}</strong><span>fit if planted in {item.plantMonth !== null ? MONTHS[item.plantMonth] : '—'}</span></div>
        <dl className="das-dl">
          <div><dt>Model uncertainty</dt><dd>{point?.uncertainty != null ? `± ${Math.round(point.uncertainty)} points` : '—'}</dd></div>
          <div><dt>Past 10 years (weather)</dt><dd>{point?.historicalP10 != null && point.historicalP90 != null ? `${Math.round(point.historicalP10)}–${Math.round(point.historicalP90)}` : '—'}</dd></div>
          <div><dt>Growing days</dt><dd>{item.growingDays ? `${Math.round(item.growingDays.min)}–${Math.round(item.growingDays.max)}` : '—'}</dd></div>
          <div><dt>Source</dt><dd>{item.source === 'ml' ? 'Trained model' : 'Crop calendar'}</dd></div>
          <div><dt>Evidence</dt><dd>{item.evidenceGrade?.replace(/-/g, ' ') ?? '—'}</dd></div>
        </dl>
      </div>
      <div className="das-card">
        <span className="das-label">What drives the score{item.plantMonth !== null ? ` in ${MONTHS[item.plantMonth]}` : ''}</span>
        {components ? <ComponentBars components={components} /> : <p className="muted">No component breakdown returned.</p>}
        {item.notes && <p className="das-note">{item.notes}</p>}
      </div>
      <div className="das-card">
        <span className="das-label">Crop requirements (FAO EcoCrop)</span>
        {item.profile ? <dl className="das-dl">
          <div><dt>Species</dt><dd><em>{item.profile.scientificName ?? '—'}</em></dd></div>
          <div><dt>Optimal temperature</dt><dd>{item.profile.tempOptC ? `${item.profile.tempOptC[0]}–${item.profile.tempOptC[1]} °C` : '—'}</dd></div>
          <div><dt>Optimal rainfall</dt><dd>{item.profile.rainOptMm ? `${fmt(item.profile.rainOptMm[0])}–${fmt(item.profile.rainOptMm[1])} mm/yr` : '—'}</dd></div>
          <div><dt>Optimal soil pH</dt><dd>{item.profile.phOpt ? `${item.profile.phOpt[0]}–${item.profile.phOpt[1]}` : '—'}</dd></div>
        </dl> : <p className="muted">No crop profile returned.</p>}
      </div>
      <div className="das-card">
        <span className="das-label">About the model</span>
        <p>{health?.model?.name ?? mlModel?.name ?? 'Crop model'}{health?.metrics ? ` · held-out error ${health.metrics.mae?.toFixed(1)} points (MAE), R² ${health.metrics.r2?.toFixed(2)}` : ''}.</p>
        <p className="muted">Agroclimatic screening from climate, soil pH, irrigation, and FAO crop requirements. Not a yield forecast or purchase recommendation. Roof shading is handled separately by the sun simulator.</p>
      </div>
    </div>
  </main>;
}

/** Matterport scans of the building (from CoStar): walk the inside before visiting the roof. */
function TourTab({ name, tours, roofSqft, sunlit }: { name: string; tours: Array<{ modelId: string; caption: string }>; roofSqft: number | null; sunlit: number | null }) {
  const unique = useMemo(() => [...new Map(tours.map((tour) => [tour.modelId, tour])).values()], [tours]);
  const [active, setActive] = useState(unique[0]?.modelId ?? '');
  const current = unique.find((tour) => tour.modelId === active) ?? unique[0];
  if (!current) return null;
  return <main className="das-body das-tour">
    <div className="das-card wide das-tour-head">
      <div>
        <span className="das-label">Matterport 3D scan · via CoStar</span>
        <h2>Walk {name} before you visit.</h2>
        <p>Vexcel measured the roof from above{roofSqft ? ` (${fmt(roofSqft)} ft²` : ''}{sunlit !== null ? `, ${fmt(sunlit)} ft² in full sun)` : roofSqft ? ')' : ''}. The scan shows the inside: check for stairs or a roof hatch, freight access and loading doors for soil and water, and the space you would lease below the farm.</p>
      </div>
      <a className="das-tour-open" href={`https://my.matterport.com/show/?m=${current.modelId}`} target="_blank" rel="noreferrer">Open full screen <ExternalLink size={14} /></a>
    </div>
    {unique.length > 1 && <div className="das-tour-chips">{unique.map((tour) => <button key={tour.modelId} className={tour.modelId === current.modelId ? 'active' : ''} onClick={() => setActive(tour.modelId)}>{tour.caption || tour.modelId}</button>)}</div>}
    <iframe key={current.modelId} className="das-tour-frame" title={`Matterport tour: ${current.caption}`} src={`https://my.matterport.com/show/?m=${current.modelId}&play=1&qs=1&brand=0&help=0`} allow="xr-spatial-tracking; fullscreen" allowFullScreen />
  </main>;
}
