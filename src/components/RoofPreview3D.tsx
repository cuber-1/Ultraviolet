import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { fetchElevations, type ElevationResponse, type SearchResult } from '../services/vexcel';
import { simulate, type AreaSelection, type Obstruction } from '../services/sunSimulation';
import { geometryBounds, geometryRequiredRadius, insideMetricGeometry, metricPointToLonLat, roofWktToMetricGeometry } from '../services/roofGeometry';
import './RoofPreview3D.css';

const Roof3DVisualizer = lazy(() => import('./Roof3DVisualizer'));

const siteTimeZone = (lon: number) => lon < -112 ? 'America/Los_Angeles' : lon < -100 ? 'America/Denver' : lon < -85 ? 'America/Chicago' : 'America/New_York';
function offsetForDate(date: string, timeZone: string) {
  const instant = new Date(`${date}T12:00:00Z`);
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(instant).map((part) => [part.type, part.value]));
  return (Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second)) - instant.getTime()) / 3_600_000;
}
const clock = (minute: number) => { const h = Math.floor(minute / 60); return `${h % 12 || 12}:${String(minute % 60).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`; };

/**
 * Self-rotating 3D roof for the Deep Agent overview: clean roof (green surface, measured
 * obstacles and their shadows), a slow sun sweep across the day, and one Infrared toggle.
 * Same geometry, elevation, and sun maths as the full simulator.
 */
export default function RoofPreview3D({ result, date, targetHours, targetAreaSqft, controls = true }: { result: SearchResult; date: string; targetHours: number; targetAreaSqft: number; controls?: boolean }) {
  const [infrared, setInfrared] = useState(false);
  const [minute, setMinute] = useState(8 * 60);
  const roofArea = result.property?.roofAreaSqft ?? 5_000;
  const uncentered = useMemo(() => roofWktToMetricGeometry(result.property?.roofWkt, result.lat, result.lon, 0), [result.lat, result.lon, result.property?.roofWkt]);
  const radius = Math.min(250, Math.max(55, Math.sqrt(roofArea * .092903) * .9, geometryRequiredRadius(uncentered)));
  const size = radius * 2;
  const roofGeometry = useMemo(() => roofWktToMetricGeometry(result.property?.roofWkt, result.lat, result.lon, radius), [radius, result.lat, result.lon, result.property?.roofWkt]);
  const bounds = useMemo(() => geometryBounds(roofGeometry, size), [roofGeometry, size]);
  const grid = useMemo(() => {
    const n = 12; const cellWidth = bounds.width / n; const cellDepth = bounds.height / n;
    const cells: Array<{ x: number; y: number; lat: number; lon: number }> = [];
    for (let row = 0; row < n; row += 1) for (let column = 0; column < n; column += 1) {
      const x = bounds.x + (column + .5) * cellWidth; const y = bounds.y + (row + .5) * cellDepth;
      if (insideMetricGeometry(x, y, roofGeometry)) cells.push({ x, y, ...metricPointToLonLat({ x, y }, result.lat, result.lon, radius) });
    }
    return { cells, cellWidth, cellDepth };
  }, [bounds, radius, result.lat, result.lon, roofGeometry]);
  const [elevations, setElevations] = useState<ElevationResponse | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (grid.cells.length < 2) { setFailed(true); return; }
    const controller = new AbortController();
    setElevations(null); setFailed(false);
    fetchElevations(grid.cells.map(({ lat, lon }) => ({ lat, lon })), controller.signal).then(setElevations).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [grid]);
  const model = useMemo(() => {
    if (!elevations) return null;
    const valid = elevations.samples.map((sample, index) => ({ sample, cell: grid.cells[index] })).filter((item) => item.cell && item.sample.dsmM !== null && item.sample.dtmM !== null);
    if (!valid.length) return null;
    const median = (values: number[]) => { const sorted = [...values].sort((a, b) => a - b); return sorted[Math.floor(sorted.length / 2)]; };
    const plane = median(valid.map((item) => item.sample.dsmM!)); const ground = median(valid.map((item) => item.sample.dtmM!));
    const obstructions: Obstruction[] = valid.filter((item) => item.sample.dsmM! - plane >= .75).map((item) => ({ x: item.cell.x - grid.cellWidth / 2, y: item.cell.y - grid.cellDepth / 2, width: grid.cellWidth, depth: grid.cellDepth, heightM: item.sample.dsmM! - plane }));
    return { buildingHeightM: plane - ground >= 1 ? plane - ground : null, obstructions };
  }, [elevations, grid]);
  const selection = useMemo<AreaSelection>(() => {
    const scale = Math.sqrt(Math.min(1, targetAreaSqft / roofArea));
    return { x: bounds.x + bounds.width * (1 - scale) / 2, y: bounds.y + bounds.height * (1 - scale) / 2, width: bounds.width * scale, height: bounds.height * scale };
  }, [bounds, roofArea, targetAreaSqft]);
  // Gentle sun sweep from 7 AM to 7 PM, looping.
  useEffect(() => { const timer = window.setInterval(() => setMinute((value) => value >= 19 * 60 ? 7 * 60 : value + 10), 220); return () => window.clearInterval(timer); }, []);
  const simulation = useMemo(() => simulate({ date, minute, timezoneOffsetHours: offsetForDate(date, siteTimeZone(result.lon)), lat: result.lat, lon: result.lon, roofAreaSqft: roofArea, roofWidthM: size, roofDepthM: size, roofGeometry, selection, obstructions: model?.obstructions ?? null, targetHours }), [date, minute, model, result.lat, result.lon, roofArea, roofGeometry, selection, size, targetHours]);
  const imageryUrl = `${result.imageryUrl}&radiusM=${radius}${infrared ? '&bands=irg' : ''}`;

  return <div className="roof-preview">
    {model ? <Suspense fallback={<div className="roof-preview-wait"><LoaderCircle className="spin" /> Building the roof</div>}>
      <Roof3DVisualizer key={infrared ? 'ir' : 'rgb'} roofGeometry={roofGeometry} roofBounds={bounds} roofWidthM={size} roofDepthM={size} buildingHeightM={model.buildingHeightM} obstructions={model.obstructions} cells={simulation.cells} imageryUrl={imageryUrl} surfaceLabel={infrared ? 'CIR / IRG' : 'RGB'} sun={simulation.sun} localTime={clock(minute)} autoRotate initialSurfaceMode="clean" minimal />
    </Suspense> : failed ? <img className="roof-preview-fallback" src={result.imageryUrl} alt="Aerial view of the roof" /> : <div className="roof-preview-wait"><LoaderCircle className="spin" /> Reading roof heights</div>}
    {model && <div className="roof-preview-chip">☀ {clock(minute)} · {model.obstructions.length} {model.obstructions.length === 1 ? 'obstacle' : 'obstacles'}</div>}
    {model && controls && <>
      <button className={infrared ? 'roof-preview-ir active' : 'roof-preview-ir'} onClick={() => setInfrared((value) => !value)} aria-pressed={infrared}>{infrared ? 'Infrared on' : 'Infrared'}</button>
    </>}
  </div>;
}
