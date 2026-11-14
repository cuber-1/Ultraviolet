import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Bell, Building2, CalendarDays, CheckCircle2, CircleAlert, LoaderCircle, MapPin, Moon, Pause, Play, Search, Sprout, Sun, X } from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import SearchGlobe from '../components/SearchGlobe';
import RuralExplorer from '../components/RuralExplorer';
import InfraredSurface from '../components/InfraredSurface';
import AgentCompanion from '../components/AgentCompanion';
import { createPhotonWatch, fetchElevations, runAgentComparison, searchVexcel, type AgentComparison, type AgentProgress, type ElevationResponse, type PhotonWatchInput, type SearchResult } from '../services/vexcel';
import { shadowVector, simulate, type AreaSelection, type Obstruction } from '../services/sunSimulation';
import { geometryBounds, geometryRequiredRadius, insideMetricGeometry, metricPointToLonLat, roofWktToMetricGeometry } from '../services/roofGeometry';
import './AgriculturePage.css';
import './AgricultureEnhancements.css';

const Roof3DVisualizer = lazy(() => import('../components/Roof3DVisualizer'));

const ACCEPTANCE_GOAL = 'Find a rooftop with 5,000 square feet that gets at least six hours of direct sun in April and October.';
const SEARCH_AREAS = [
  { label: 'Houston', value: 'Houston, Texas' },
  { label: 'Los Angeles', value: 'Los Angeles, California' },
  { label: 'Stockton / Central Valley', value: 'Stockton, California' },
] as const;
const formatArea = (area: number | null) => area === null ? 'Not assessed' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(area)} ft²`;
const timeLabel = (minute: number) => {
  const hour24 = Math.floor(minute / 60) % 24;
  const hour12 = hour24 % 12 || 12;
  return `${hour12}:${String(minute % 60).padStart(2, '0')} ${hour24 < 12 ? 'AM' : 'PM'}`;
};
const siteTimeZone = (lon: number) => lon < -112 ? 'America/Los_Angeles' : lon < -100 ? 'America/Denver' : lon < -85 ? 'America/Chicago' : 'America/New_York';
function offsetForDate(date: string, timeZone: string) {
  const instant = new Date(`${date}T12:00:00Z`);
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(instant).map((part) => [part.type, part.value]));
  return (Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second)) - instant.getTime()) / 3_600_000;
}

export function SiteWorkspace({ result, onClose, initialDate = '2026-04-15', initialTargetHours = 6, targetAreaSqft = 5_000, backLabel = 'Results', embedded = false, initialSurfaceMode }: { result: SearchResult; onClose: () => void; initialDate?: string; initialTargetHours?: number; targetAreaSqft?: number; backLabel?: string; embedded?: boolean; initialSurfaceMode?: 'imagery' | 'clean' }) {
  const roofArea = result.property?.roofAreaSqft ?? 5_000;
  const uncenteredRoofGeometry = useMemo(() => roofWktToMetricGeometry(result.property?.roofWkt, result.lat, result.lon, 0), [result.lat, result.lon, result.property?.roofWkt]);
  const imageRadiusM = Math.min(250, Math.max(55, Math.sqrt(roofArea * .092903) * .9, geometryRequiredRadius(uncenteredRoofGeometry)));
  const roofWidth = imageRadiusM * 2;
  const roofDepth = imageRadiusM * 2;
  const roofGeometry = useMemo(() => roofWktToMetricGeometry(result.property?.roofWkt, result.lat, result.lon, imageRadiusM), [imageRadiusM, result.lat, result.lon, result.property?.roofWkt]);
  const roofBounds = useMemo(() => geometryBounds(roofGeometry, roofWidth), [roofGeometry, roofWidth]);
  const roofPath = useMemo(() => roofGeometry.map((polygon) => [polygon.outer, ...polygon.holes].map((ring) => `${ring.map((item, index) => `${index ? 'L' : 'M'}${item.x},${item.y}`).join(' ')} Z`).join(' ')).join(' '), [roofGeometry]);
  const elevationGrid = useMemo(() => {
    const size = 12;
    const cellWidth = roofBounds.width / size;
    const cellDepth = roofBounds.height / size;
    const cells: Array<{ x: number; y: number; lat: number; lon: number }> = [];
    for (let row = 0; row < size; row += 1) for (let column = 0; column < size; column += 1) {
      const x = roofBounds.x + (column + .5) * cellWidth;
      const y = roofBounds.y + (row + .5) * cellDepth;
      if (insideMetricGeometry(x, y, roofGeometry)) cells.push({ x, y, ...metricPointToLonLat({ x, y }, result.lat, result.lon, imageRadiusM) });
    }
    return { cells, cellWidth, cellDepth };
  }, [imageRadiusM, result.lat, result.lon, roofBounds, roofGeometry]);
  const [elevations, setElevations] = useState<ElevationResponse | null>(null);
  const [elevationError, setElevationError] = useState<string | null>(null);
  const [elevationLoading, setElevationLoading] = useState(false);
  useEffect(() => {
    if (elevationGrid.cells.length < 2) { setElevationError('Roof footprint has too few valid elevation samples.'); return; }
    const controller = new AbortController();
    setElevationLoading(true); setElevationError(null); setElevations(null);
    fetchElevations(elevationGrid.cells.map(({ lat, lon }) => ({ lat, lon })), controller.signal)
      .then(setElevations).catch((error) => { if (!controller.signal.aborted) setElevationError(error instanceof Error ? error.message : 'Elevation sampling failed.'); })
      .finally(() => { if (!controller.signal.aborted) setElevationLoading(false); });
    return () => controller.abort();
  }, [elevationGrid]);
  const elevationModel = useMemo(() => {
    if (!elevations) return null;
    const valid = elevations.samples.map((sample, index) => ({ sample, cell: elevationGrid.cells[index] })).filter((item) => item.cell && item.sample.dsmM !== null && item.sample.dtmM !== null);
    if (!valid.length) return null;
    const median = (values: number[]) => { const sorted = [...values].sort((a, b) => a - b); return sorted[Math.floor(sorted.length / 2)]; };
    const roofPlaneM = median(valid.map((item) => item.sample.dsmM!));
    const groundM = median(valid.map((item) => item.sample.dtmM!));
    const obstructions: Obstruction[] = valid.filter((item) => item.sample.dsmM! - roofPlaneM >= .75).map((item) => ({ x: item.cell.x - elevationGrid.cellWidth / 2, y: item.cell.y - elevationGrid.cellDepth / 2, width: elevationGrid.cellWidth, depth: elevationGrid.cellDepth, heightM: item.sample.dsmM! - roofPlaneM }));
    const rawBuildingHeightM = roofPlaneM - groundM;
    return { roofPlaneM, groundM, buildingHeightM: rawBuildingHeightM >= 1 ? rawBuildingHeightM : null, obstructions, validSamples: valid.length };
  }, [elevationGrid, elevations]);
  const obstructions = elevations ? elevationModel?.obstructions ?? [] : null;
  const initialSelection = useMemo<AreaSelection>(() => {
    const scale = Math.sqrt(Math.min(1, targetAreaSqft / roofArea));
    return { x: roofBounds.x + roofBounds.width * (1 - scale) / 2, y: roofBounds.y + roofBounds.height * (1 - scale) / 2, width: roofBounds.width * scale, height: roofBounds.height * scale };
  }, [roofArea, roofBounds, targetAreaSqft]);
  const [selection, setSelection] = useState(initialSelection);
  const [date, setDate] = useState(initialDate);
  const [minute, setMinute] = useState(720);
  const [playing, setPlaying] = useState(false);
  const [targetHours, setTargetHours] = useState(initialTargetHours);
  const [layer, setLayer] = useState<'aerial' | 'infrared' | 'tour' | 'sun'>('sun');
  const [sunView, setSunView] = useState<'model' | 'analysis'>('model');
  const [solarSurface, setSolarSurface] = useState<'rgb' | 'irg'>('rgb');
  const [infraredFailed, setInfraredFailed] = useState(false);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const timeZone = siteTimeZone(result.lon);
  const timezoneOffsetHours = offsetForDate(date, timeZone);
  const simulation = useMemo(() => simulate({ date, minute, timezoneOffsetHours, lat: result.lat, lon: result.lon, roofAreaSqft: roofArea, roofWidthM: roofWidth, roofDepthM: roofDepth, roofGeometry, selection, obstructions, targetHours }), [date, minute, timezoneOffsetHours, result.lat, result.lon, roofArea, roofWidth, roofDepth, roofGeometry, selection, obstructions, targetHours]);
  const activeShadowSources = useMemo(() => new Set(simulation.cells.flatMap((cell) => cell.blockedBy === null ? [] : [cell.blockedBy])), [simulation.cells]);
  const sunlightDirection = useMemo(() => {
    const azimuth = simulation.sun.azimuth * Math.PI / 180;
    const reach = Math.min(roofWidth, roofDepth) * .32;
    const center = { x: roofWidth * .5, y: roofDepth * .5 };
    return { startX: center.x + Math.sin(azimuth) * reach, startY: center.y - Math.cos(azimuth) * reach, endX: center.x, endY: center.y };
  }, [roofDepth, roofWidth, simulation.sun.azimuth]);

  useEffect(() => { if (!playing) return; const timer = window.setInterval(() => setMinute((value) => (value + 15) % 1440), 240); return () => window.clearInterval(timer); }, [playing]);
  const point = (event: React.PointerEvent<SVGSVGElement>) => { const rect = event.currentTarget.getBoundingClientRect(); return { x: Math.max(0, Math.min(roofWidth, (event.clientX - rect.left) / rect.width * roofWidth)), y: Math.max(0, Math.min(roofDepth, (event.clientY - rect.top) / rect.height * roofDepth)) }; };
  const imageryUrl = `${result.imageryUrl}&radiusM=${imageRadiusM}`;
  const infraredActive = layer === 'infrared' || (layer === 'sun' && solarSurface === 'irg');
  const tour = result.costar?.matterport[0] ?? null;
  const costar = result.costar;
  const buildingName = costar?.buildingName || costar?.address || `${result.lat.toFixed(5)}, ${result.lon.toFixed(5)}`;

  return <div className={embedded ? 'site-workspace embedded' : 'site-workspace'}>
    {!embedded && <button className="site-floating-back" onClick={onClose}><ArrowLeft size={16} /> {backLabel}</button>}
    <div className="site-layout">
      <section className="site-visual">
        <div className="layer-tabs">
          <span className="layer-site-label mono">{buildingName}</span>
          <button className={layer === 'aerial' ? 'active' : ''} onClick={() => setLayer('aerial')}>Aerial</button>
          <button className={layer === 'infrared' ? 'active' : ''} onClick={() => { setInfraredFailed(false); setLayer('infrared'); }}>Infrared <small>CIR</small></button>
          <button className={layer === 'tour' ? 'active' : ''} onClick={() => setLayer('tour')}>3D Tour <small>{tour ? 'COSTAR' : 'NONE'}</small></button>
          <button className={layer === 'sun' ? 'active' : ''} onClick={() => setLayer('sun')}><Sun size={14} /> Solar</button>
          {layer === 'sun' && <><div className="surface-switch"><button className={solarSurface === 'rgb' ? 'active' : ''} onClick={() => setSolarSurface('rgb')}>RGB</button><button className={solarSurface === 'irg' ? 'active' : ''} onClick={() => setSolarSurface('irg')}>CIR</button></div><div className="sun-view-switch"><button className={sunView === 'model' ? 'active' : ''} onClick={() => setSunView('model')}>3D</button><button className={sunView === 'analysis' ? 'active' : ''} onClick={() => setSunView('analysis')}>Plan</button></div></>}
        </div>
        {(layer === 'tour' && !tour) || (layer === 'infrared' && infraredFailed) ? <div className="unavailable-layer"><CircleAlert size={24} /><h3>{layer === 'infrared' ? 'Infrared unavailable' : 'No Matterport tour'}</h3><p>{layer === 'infrared' ? 'Vexcel did not return an IRG image for this location.' : 'This CoStar property has no Matterport attachment.'}</p><button onClick={() => setLayer('sun')}>View sunlight</button></div> : layer === 'tour' && tour ? <div className="tour-frame"><iframe title={tour.caption} src={`https://my.matterport.com/show/?m=${encodeURIComponent(tour.modelId)}&play=1&qs=1`} allowFullScreen allow="fullscreen; xr-spatial-tracking" /><span className="tour-source mono">COSTAR {costar?.propertyId} · {tour.caption}</span></div> : <div className="roof-stage">
          {layer === 'sun' && sunView === 'model' && elevationModel ? <Suspense fallback={<div className="roof-3d-loading"><LoaderCircle className="spin" /> Loading roof</div>}><Roof3DVisualizer initialSurfaceMode={initialSurfaceMode} roofGeometry={roofGeometry} roofBounds={roofBounds} roofWidthM={roofWidth} roofDepthM={roofDepth} buildingHeightM={elevationModel.buildingHeightM} obstructions={elevationModel.obstructions} cells={simulation.cells} imageryUrl={solarSurface === 'irg' ? `${imageryUrl}&bands=irg` : imageryUrl} surfaceLabel={solarSurface === 'irg' ? 'CIR / IRG' : 'RGB'} sun={simulation.sun} localTime={`${timeLabel(minute)} local`} /></Suspense> : <>
            {infraredActive ? <InfraredSurface src={`${imageryUrl}&bands=irg`} alt={`Denoised near-infrared intensity at ${result.lat}, ${result.lon}`} onError={() => setInfraredFailed(true)} /> : <img src={imageryUrl} alt={`Aerial imagery at ${result.lat}, ${result.lon}`} />}
            {infraredActive && <div className="infrared-note"><strong>NIR INTENSITY</strong><span>Denoised IRG red band · darker orange indicates stronger near-infrared response.</span></div>}
            <svg className={layer === 'sun' ? 'roof-overlay interactive' : 'roof-overlay'} viewBox={`0 0 ${roofWidth} ${roofDepth}`} preserveAspectRatio="xMidYMid meet" onPointerDown={(event) => { if (layer !== 'sun') return; dragStart.current = point(event); event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={(event) => { if (layer !== 'sun' || !dragStart.current) return; const end = point(event); setSelection({ x: Math.min(dragStart.current.x, end.x), y: Math.min(dragStart.current.y, end.y), width: Math.max(1, Math.abs(end.x - dragStart.current.x)), height: Math.max(1, Math.abs(end.y - dragStart.current.y)) }); }} onPointerUp={() => { dragStart.current = null; }}>
              <defs><clipPath id="growing-area"><rect x={selection.x} y={selection.y} width={selection.width} height={selection.height} /></clipPath><marker id="sun-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" /></marker></defs>
              {roofPath && <path d={roofPath} fillRule="evenodd" className={simulation.sun.altitude > 0 ? 'roof-outline' : 'roof-outline night'} />}
              {layer === 'sun' && <>{obstructions?.map((item, index) => <rect key={index} x={item.x} y={item.y} width={item.width} height={item.depth} className={activeShadowSources.has(index) ? 'dsm-obstruction active' : 'dsm-obstruction'} />)}
                {simulation.sun.altitude > 0 && <g className="sun-explanation"><line x1={sunlightDirection.startX} y1={sunlightDirection.startY} x2={sunlightDirection.endX} y2={sunlightDirection.endY} markerEnd="url(#sun-arrow)" />{obstructions?.map((item, index) => { const vector = shadowVector(simulation.sun, item.heightM); if (!vector || !activeShadowSources.has(index)) return null; const x = item.x + item.width / 2; const y = item.y + item.depth / 2; return <line key={index} className="shadow-trace" x1={x} y1={y} x2={x + vector.dx} y2={y + vector.dy}><title>{`${item.heightM.toFixed(1)} m height · ${vector.lengthM.toFixed(1)} m projected shadow`}</title></line>; })}</g>}
                <g clipPath="url(#growing-area)">{simulation.cells.map((cell, index) => <rect key={index} x={cell.x - selection.width / 40} y={cell.y - selection.height / 40} width={selection.width / 20 + .2} height={selection.height / 20 + .2} className={cell.sunlit ? 'sun-cell' : 'shade-cell'}><title>{cell.sunlit ? `${cell.hours.toFixed(1)} estimated direct-sun hours` : cell.blockedBy === null ? 'Sun below horizon' : `Blocked by DSM cell ${cell.blockedBy + 1}`}</title></rect>)}</g>
                <rect x={selection.x} y={selection.y} width={selection.width} height={selection.height} className="growing-outline" /></>}
            </svg>
            {layer === 'sun' && <><div className={simulation.sun.altitude > 0 ? 'sun-direction-badge' : 'sun-direction-badge night'}>{simulation.sun.altitude > 0 ? <Sun size={14} /> : <Moon size={14} />}<span>{simulation.sun.altitude > 0 ? <><strong>{Math.round(simulation.sun.azimuth)}° azimuth</strong>{simulation.sun.altitude.toFixed(1)}° elevation · orange traces originate at measured height cells</> : <><strong>Night</strong>Sun below the horizon · no cast shadows</>}</span></div><div className="overlay-key"><span><i className="roof-key" /> Roof</span><span><i className="height-key" /> Height</span><span><i className="trace-key" /> Shadow</span><span>{activeShadowSources.size} blockers</span><span>Drag to redraw</span></div></>}
          </>}
        </div>}
      </section>

      <aside className="simulation-panel">
        <div className="site-title"><span className="mono">SITE / {costar ? `COSTAR ${costar.propertyId}` : 'UNMATCHED'}</span><h1>{buildingName}</h1><p><MapPin size={13} /> {costar?.address || `${result.lat.toFixed(5)}, ${result.lon.toFixed(5)}`}</p><div className="site-chips"><span>{formatArea(result.property?.roofAreaSqft ?? null)} roof</span><span>Vexcel {(result.score * 100).toFixed(1)}%</span>{costar && <span>{costar.matchDistanceM} m match</span>}</div></div>

        {costar ? <section className="costar-card"><header><div><span className="mono">COSTAR</span><strong>{costar.propertyType}{costar.buildingClass ? ` · Class ${costar.buildingClass}` : ''}</strong></div>{costar.photoUrl && <img src={costar.photoUrl} alt="" />}</header><dl><div><dt>Building area</dt><dd>{formatArea(costar.grossBuildingAreaSqft)}</dd></div><div><dt>Stories</dt><dd>{costar.stories ?? '—'}</dd></div><div><dt>Built</dt><dd>{costar.yearBuilt ?? '—'}</dd></div><div><dt>Rating</dt><dd>{costar.buildingRating ? `${costar.buildingRating} / 5` : '—'}</dd></div></dl>{costar.apartment && <div className="costar-strip"><span>{costar.apartment.availableUnits} of {costar.apartment.units ?? '—'} units available</span>{costar.apartment.minRent && <span>${costar.apartment.minRent.toLocaleString()}–${costar.apartment.maxRent?.toLocaleString()} rent</span>}</div>}<div className="listing-line"><i className={costar.listing?.active ? 'active' : ''} /><span>{costar.listing ? `${costar.listing.statuses.join(', ')} · ${costar.listing.types.join(', ')}` : 'No commercial listing record'}</span><span>{costar.matterport.length} tours</span></div></section> : <div className="costar-missing"><span className="mono">COSTAR</span><p>No property is within 125 m. Aerial and sunlight views are still available.</p></div>}

        <div className="source-status"><span>{result.property ? <CheckCircle2 /> : <CircleAlert />} {roofGeometry.length ? `${roofGeometry.length} Vexcel roof ${roofGeometry.length === 1 ? 'surface' : 'surfaces'} · full WKT outline` : 'Roof outline unavailable'}</span><span>{elevationLoading ? <LoaderCircle className="spin" /> : elevationModel ? <CheckCircle2 /> : <CircleAlert />} {elevationLoading ? 'Reading elevation' : elevationModel ? `${elevationModel.validSamples} elevation points · ${elevationModel.obstructions.length} roof features` : elevationError || 'Elevation unavailable'}</span></div>

        <div className="date-row"><label><CalendarDays size={14} /> Date<input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label><div><button onClick={() => setDate('2026-04-15')}>Apr 15</button><button onClick={() => setDate('2026-06-21')}>Jun 21</button><button onClick={() => setDate('2026-10-15')}>Oct 15</button><button onClick={() => setDate('2026-12-15')}>Dec 15</button></div></div>
        <div className="time-control"><div><button onClick={() => setPlaying((value) => !value)}>{playing ? <Pause size={15} /> : <Play size={15} />}</button><strong>{timeLabel(minute)}</strong><span>{timeZone.replace('America/', '')} · {simulation.sun.altitude > 0 ? `${simulation.sun.altitude.toFixed(1)}° / ${simulation.sun.azimuth.toFixed(0)}°` : 'Night · sun below horizon'}</span></div><input type="range" min="0" max="1439" step="5" value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></div>
        <div className="target-control"><label>Daily direct-sun threshold <strong>{targetHours} h</strong></label><input type="range" min="2" max="10" step=".5" value={targetHours} onChange={(event) => setTargetHours(Number(event.target.value))} /></div>
        <div className="simulation-metrics"><div><small>SELECTED AREA</small><strong>{formatArea(simulation.totalAreaSqft)}</strong></div><div><small>SUNLIT NOW</small><strong>{formatArea(simulation.directAreaSqft)}</strong></div><div><small>DAILY MEAN</small><strong>{simulation.estimatedHours === null ? 'Unknown' : `${simulation.estimatedHours.toFixed(1)} h`}</strong></div><div><small>ABOVE THRESHOLD</small><strong>{formatArea(simulation.meetingTargetAreaSqft)}</strong></div></div>
        <p className="method-note"><strong>CALCULATION</strong> · Vexcel roof outline with DSM heights measured from the roof plane. Sunlight is checked every {simulation.resolutionMinutes} minutes under clear skies.</p>
      </aside>
    </div>
  </div>;
}

function PhotonWatchDialog({ query, searchArea, onClose, onCreated }: { query: string; searchArea: string; onClose: () => void; onCreated: (id: string) => void }) {
  const [platform, setPlatform] = useState<PhotonWatchInput['platform']>('imessage');
  const [handle, setHandle] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const placeholder = platform === 'email' ? 'you@example.com' : platform === 'telegram' ? '@username' : '+1 555 555 0123';
  return <div className="photon-watch-backdrop" role="dialog" aria-modal="true" aria-labelledby="photon-watch-title"><form className="photon-watch-dialog" onSubmit={async (event) => { event.preventDefault(); setSaving(true); setError(null); try { const watch = await createPhotonWatch({ goal: query, location: searchArea || 'All available Vexcel coverage', lat: 0, lon: 0, radiusM: 20_000, dates: ['2026-04-15', '2026-10-15'], targetHours: 6, targetAreaSqft: 5_000, platform, handle }); onCreated(watch.id); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Photon watch setup failed.'); } finally { setSaving(false); } }}>
    <button type="button" className="photon-watch-close" onClick={onClose} aria-label="Close"><X /></button>
    <span className="mono">PHOTON 2.0 · OPENING ALERTS</span><h2 id="photon-watch-title">Hear when a roof opens.</h2><p>Ultraviolet will watch this search, have Deep Agent investigate new listing evidence, and message only after the roof and sunlight checks run.</p>
    <blockquote>{query || ACCEPTANCE_GOAL}</blockquote>
    <label>Message channel<select value={platform} onChange={(event) => setPlatform(event.target.value as PhotonWatchInput['platform'])}><option value="imessage">iMessage</option><option value="sms">SMS</option><option value="telegram">Telegram</option><option value="email">Email</option><option value="whatsapp_business">WhatsApp Business</option></select></label>
    <label>Destination<input required value={handle} onChange={(event) => setHandle(event.target.value)} placeholder={placeholder} /></label>
    {error && <div className="photon-watch-error"><CircleAlert /><span>{error}</span></div>}
    <button className="photon-watch-submit" disabled={saving || !handle.trim()}>{saving ? <><LoaderCircle className="spin" /> Connecting Photon…</> : <><Bell /> Watch new openings</>}</button>
    <small>Checks every 15 minutes while the Ultraviolet server is running. Photon credentials stay on the server.</small>
  </form></div>;
}

function AgentLoadingScreen({ query, progress, onCancel }: { query: string; progress: AgentProgress[]; onCancel: () => void }) {
  const steps = (progress.length ? progress : [{ stage: 'planning', message: 'Starting rooftop comparison' } as AgentProgress]).slice(-4);
  const firstIndex = Math.max(0, progress.length - steps.length);
  const current = steps.at(-1)!;
  const companionMessage = current.stage.toLowerCase().includes('imag') ? 'Scanning the city…'
    : current.stage.toLowerCase().includes('propert') ? 'Checking the records…'
      : current.stage.toLowerCase().includes('geometr') ? 'Tracing each rooftop…'
        : current.stage.toLowerCase().includes('sun') ? 'Following the sunlight…'
          : current.stage.toLowerCase().includes('rank') || current.stage.toLowerCase().includes('compar') ? 'Weighing the evidence…'
            : 'Working on it…';
  return <div className="agent-loading-screen" role="dialog" aria-modal="true" aria-labelledby="agent-loading-title">
    <button className="agent-loading-cancel" onClick={onCancel}>Cancel</button>
    <div className="agent-loading-orbit" aria-hidden="true"><span /><span /><span /></div>
    <AgentCompanion message={companionMessage} detail={current.message} />
    <section className="agent-loading-content">
      <div className="agent-loading-kicker"><i /> DEEP AGENT · LIVE</div>
      <h2 id="agent-loading-title">Finding the right roof</h2>
      <p>{query || ACCEPTANCE_GOAL}</p>
      <div className="agent-step-stage" role="status" aria-live="polite" aria-atomic="false">
        {steps.map((step, index) => { const distance = steps.length - 1 - index; return <div className={`agent-loading-step agent-loading-step-${distance}`} key={`${firstIndex + index}:${step.stage}:${step.message}`}><span>{String(firstIndex + index + 1).padStart(2, '0')}</span><div><small>{step.stage}</small><strong>{step.message}</strong></div>{distance === 0 && <LoaderCircle className="spin" />}</div>; })}
      </div>
      <div className="agent-loading-sources"><span>Vexcel imagery</span><span>CoStar records</span><span>Roof geometry</span><span>Sunlight model</span></div>
    </section>
  </div>;
}

export default function AgriculturePage() {
  const navigate = useNavigate(); const location = useLocation(); const { mode = 'urban' } = useParams(); const rural = mode === 'rural';
  const [query, setQuery] = useState(ACCEPTANCE_GOAL); const [searchArea, setSearchArea] = useState(''); const [results, setResults] = useState<SearchResult[]>([]); const [searching, setSearching] = useState(false); const [error, setError] = useState<string | null>(null); const [errorSource, setErrorSource] = useState<'search' | 'agent'>('search'); const [searched, setSearched] = useState(false); const requestRef = useRef<AbortController | null>(null);
  const [agentRunning, setAgentRunning] = useState(false); const [agentProgress, setAgentProgress] = useState<AgentProgress[]>([]); const [comparison, setComparison] = useState<AgentComparison | null>(null); const [secondDate, setSecondDate] = useState('2026-10-15');
  const [watchOpen, setWatchOpen] = useState(false); const [activeWatchId, setActiveWatchId] = useState<string | null>(null);
  const effectiveQuery = query.trim() || ACCEPTANCE_GOAL;
  const selectedId = new URLSearchParams(location.search).get('site'); const selected = results.find((result) => result.id === selectedId) ?? null;
  const runSearch = useCallback(async () => { requestRef.current?.abort(); const controller = new AbortController(); requestRef.current = controller; setSearching(true); setErrorSource('search'); setError(null); setSearched(true); setComparison(null); setAgentProgress([]); try { const response = await searchVexcel({ query: effectiveQuery, location: searchArea || 'All available Vexcel coverage' }, controller.signal); setResults(response.results); } catch (reason) { if (!controller.signal.aborted) { setResults([]); setError(reason instanceof Error ? reason.message : 'Search failed.'); } } finally { if (!controller.signal.aborted) setSearching(false); } }, [effectiveQuery, searchArea]);
  const runAgent = useCallback(async (requestedDates = ['2026-04-15', secondDate], followUp?: string) => { requestRef.current?.abort(); const controller = new AbortController(); requestRef.current = controller; setAgentRunning(true); setAgentProgress([]); setComparison(null); setErrorSource('agent'); setError(null); setSearched(true); try { const response = await runAgentComparison({ goal: effectiveQuery, followUp, location: searchArea || 'All available Vexcel coverage', lat: 0, lon: 0, radiusM: 20_000, dates: requestedDates, targetHours: 6, targetAreaSqft: 5_000 }, (event) => setAgentProgress((items) => [...items, event]), controller.signal); const candidates = new Map(response.candidates.map((candidate) => [candidate.id, candidate])); setComparison(response); setResults(response.simulations.flatMap((simulation) => { const candidate = candidates.get(simulation.candidateId); return candidate ? [candidate] : []; })); } catch (reason) { if (!controller.signal.aborted) { setResults([]); setError(reason instanceof Error ? reason.message : 'Deep Agent comparison failed.'); } } finally { if (!controller.signal.aborted) setAgentRunning(false); } }, [effectiveQuery, searchArea, secondDate]);
  const changeSeason = () => { const next = secondDate === '2026-12-15' ? '2026-10-15' : '2026-12-15'; setSecondDate(next); void runAgent(['2026-04-15', next], next === '2026-12-15' ? 'Try December instead' : 'Try October instead'); };
  const cancelAgent = () => { requestRef.current?.abort(); setAgentRunning(false); setAgentProgress([]); };
  const simulationById = useMemo(() => new Map((comparison?.simulations ?? []).map((simulation) => [simulation.candidateId, simulation])), [comparison]);
  useEffect(() => { if (!agentRunning) return; const previous = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = previous; }; }, [agentRunning]);
  useEffect(() => () => requestRef.current?.abort(), []); const open = (result: SearchResult) => { setResults((items) => items.some((item) => item.id === result.id) ? items : [...items, result]); navigate(`/agriculture/urban?site=${encodeURIComponent(result.id)}`); }; if (selected) return <SiteWorkspace result={selected} onClose={() => navigate('/agriculture/urban')} />;
  return <div className="agriculture-page">{agentRunning && <AgentLoadingScreen query={effectiveQuery} progress={agentProgress} onCancel={cancelAgent} />}{watchOpen && <PhotonWatchDialog query={effectiveQuery} searchArea={searchArea} onClose={() => setWatchOpen(false)} onCreated={(id) => { setActiveWatchId(id); setWatchOpen(false); }} />}<header className="agriculture-header"><button className="agriculture-back" onClick={() => navigate('/')}><ArrowLeft size={18} /></button><Wordmark /><nav className="agriculture-modes"><button className={!rural ? 'active' : ''} onClick={() => navigate('/agriculture/urban')}><Building2 size={15} /> Explore urban agriculture</button><button className={rural ? 'active' : ''} onClick={() => navigate('/agriculture/rural')}><Sprout size={15} /> Explore rural agriculture</button></nav><div className="agriculture-status"><i /><span className="mono">{rural ? 'NASA POWER LIVE' : 'VEXCEL CONNECTED'}</span></div></header>
    {rural ? <RuralExplorer /> : <main className="urban-discovery">
      <section className="discovery-commandbar"><div className="commandbar-title"><span className="mono">URBAN ROOFTOPS</span><h1>Find a roof</h1><p>Search aerial imagery, review property records, and check sunlight.</p></div><form onSubmit={(event) => { event.preventDefault(); runSearch(); }}><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search Vexcel imagery" /><label className="search-area"><MapPin /><select value={searchArea} onChange={(event) => setSearchArea(event.target.value)} aria-label="Search location"><option value="">All areas</option>{SEARCH_AREAS.map((area) => <option key={area.value} value={area.value}>{area.label}</option>)}</select></label><button type="submit" disabled={searching || agentRunning}>{searching ? <LoaderCircle className="spin" /> : 'Search'}</button><button type="button" className="deepagent-search" disabled={searching || agentRunning} onClick={() => runAgent()}>{agentRunning ? <LoaderCircle className="spin" /> : 'Use Deep Agent instead'}</button><button type="button" className={activeWatchId ? 'watch-search active' : 'watch-search'} onClick={() => setWatchOpen(true)}><Bell /> {activeWatchId ? 'Watching' : 'Watch openings'}</button></form><div className="commandbar-meta"><span><i /> VEXCEL CONNECTED</span>{activeWatchId && <span>PHOTON WATCH ACTIVE</span>}</div></section>
      <section className="discovery-workbench"><div className="globe-panel"><div className="panel-label"><span className="mono">01 / MAP</span><span>{results.length ? 'Fit to results · select a numbered roof' : 'Drag to rotate · scroll to zoom'}</span></div><SearchGlobe points={results.map((result, index) => ({ id: result.id, lat: result.lat, lon: result.lon, rank: index + 1 }))} onPointClick={(id) => { const result = results.find((item) => item.id === id); if (result) open(result); }} /></div>
        <aside className="search-results"><div className="results-heading"><div><span className="mono">02 / {comparison ? 'DEEP AGENT RESULTS' : 'RESULTS'}</span><h2>{searching ? 'Searching…' : agentRunning ? 'Comparing roofs…' : results.length ? `${results.length} roofs` : searched ? 'No results' : 'Search to begin'}</h2></div>{comparison ? <button className="season-followup" onClick={changeSeason} disabled={agentRunning}>Try {secondDate === '2026-12-15' ? 'October' : 'December'}</button> : results.length > 0 && <span>Image relevance</span>}</div>{agentRunning && agentProgress.length > 0 && <div className="inline-agent-progress" role="status" aria-live="polite"><LoaderCircle className="spin" /><span>{agentProgress.at(-1)?.message}</span></div>}{comparison && <div className="inline-agent-summary"><strong>{comparison.model || 'Direct comparison'}</strong><span>Apr 15 + {secondDate === '2026-10-15' ? 'Oct 15' : 'Dec 15'} · ranked by shared area receiving 6 h</span></div>}{error && <div className="access-error"><CircleAlert /><div><strong>{errorSource === 'agent' ? 'Comparison unavailable' : 'Search unavailable'}</strong><p>{error}</p><small>No unverified results are shown.</small></div></div>}{!error && !searching && !agentRunning && !results.length && <div className="results-empty"><span className="mono">NO RESULTS</span><p>Search by location, roof size, or growing goal.</p></div>}{!error && !searching && !agentRunning && results.length > 0 && <div className="live-results">{results.map((result, index) => { const simulation = simulationById.get(result.id); return <button key={result.id} onClick={() => open(result)}><img src={result.imageryUrl} alt="" /><span className="score mono">{comparison ? `#${index + 1}` : `${(result.score * 100).toFixed(1)} RELEVANCE`}</span><div><strong>{result.costar?.buildingName || (result.property?.roofAreaSqft ? `${formatArea(result.property.roofAreaSqft)} roof` : 'Unmatched coordinate')}</strong><span><MapPin /> {result.costar?.address || `${result.lat.toFixed(5)}, ${result.lon.toFixed(5)}`}</span><small>{simulation ? simulation.sharedAreaSqft === null ? 'Sunlight not assessed · missing geometry' : `${formatArea(simulation.sharedAreaSqft)} receives 6 h on both dates` : result.costar ? `${result.costar.propertyType}${result.costar.listing?.active ? ' · active listing' : ''}` : result.property?.roofWkt ? 'Vexcel roof outline' : 'Aerial image only'}</small><p>{result.costar ? `COSTAR ${result.costar.propertyId} · ${result.costar.matchDistanceM} M` : 'NO COSTAR MATCH ≤125 M'} · {simulation ? `${simulation.geometry.validSamples} HEIGHT POINTS` : result.costar?.matterport.length ? `${result.costar.matterport.length} TOURS` : 'NO TOUR'}</p></div></button>; })}</div>}</aside></section>
      </main>}
  </div>;
}
