import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import './DeepAgentCharts.css';

// Palette validated with the dataviz validator (light surface):
// crops = categorical slots 1-4 (adjacent pairs pass CVD/normal-vision; 3 & 4 need labels -> direct labels + table);
// classes = slots 1-3 all-pairs + neutral gray, each with its own marker shape.
export const CROP_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'];
export const CLASSES = {
  prime: { label: 'Prime', hint: 'Enough sunlit area and a strong crop fit', color: '#1baf7a', shape: 'circle' },
  sun: { label: 'Sun-limited', hint: 'Good crop fit, not enough sunlit area', color: '#eb6834', shape: 'triangle' },
  climate: { label: 'Climate-limited', hint: 'Enough sunlit area, weaker crop fit', color: '#2a78d6', shape: 'square' },
  weak: { label: 'Weak', hint: 'Short on both', color: '#a69689', shape: 'ring' },
} as const;
export type ClassKey = keyof typeof CLASSES;
export const FIT_THRESHOLD = 70;
const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
const surrogateError = (point: { errorP80?: number | null; uncertainty: number | null }) => point.errorP80 ?? point.uncertainty;
export const formatSurrogateError = (value: number | null | undefined) => value == null ? '—' : value < .1 ? '<0.1' : value.toFixed(value < 1 ? 1 : 0);

export function classify(sunlit: number | null, fit: number | null, target: number): ClassKey {
  const enoughSun = sunlit !== null && sunlit >= target;
  const goodFit = fit !== null && fit >= FIT_THRESHOLD;
  return enoughSun && goodFit ? 'prime' : goodFit ? 'sun' : enoughSun ? 'climate' : 'weak';
}

/** Draw charts at their real pixel width so text and marks stay 1:1 at any container size. */
function useWidth(ref: React.RefObject<HTMLDivElement | null>, fallback = 640) {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current; if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(320, Math.round(entry.contentRect.width))));
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

function useTip() {
  const ref = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const show = (event: React.MouseEvent, content: ReactNode) => {
    const box = ref.current?.getBoundingClientRect();
    if (box) setTip({ x: event.clientX - box.left, y: event.clientY - box.top, content });
  };
  const node = tip && <div className="viz-tip" style={{ left: tip.x, top: tip.y }}>{tip.content}</div>;
  return { ref, show, hide: () => setTip(null), node };
}

function Shape({ kind, x, y, r, color }: { kind: string; x: number; y: number; r: number; color: string }) {
  if (kind === 'square') return <rect x={x - r * .85} y={y - r * .85} width={r * 1.7} height={r * 1.7} rx={2} fill={color} className="viz-ring" />;
  if (kind === 'triangle') return <path d={`M${x},${y - r * 1.05} L${x + r},${y + r * .75} L${x - r},${y + r * .75} Z`} fill={color} className="viz-ring" />;
  if (kind === 'ring') return <circle cx={x} cy={y} r={r * .8} fill="#fff" stroke={color} strokeWidth={2.5} />;
  return <circle cx={x} cy={y} r={r} fill={color} className="viz-ring" />;
}

// ---------------------------------------------------------------- Sun coverage
export type SunRow = { id: string; rank: number; label: string; sunlitSqft: number | null; roofSqft: number | null; meanHours: number | null };

export function SunCoverageChart({ rows, targetAreaSqft, targetHours, onSelect }: { rows: SunRow[]; targetAreaSqft: number; targetHours: number; onSelect?: (id: string) => void }) {
  const tip = useTip();
  const width = useWidth(tip.ref); const rowH = 38; const left = Math.min(168, width * .3); const right = 132; const top = 26;
  const height = top + rows.length * rowH + 8;
  const max = Math.max(targetAreaSqft, ...rows.map((row) => row.sunlitSqft ?? 0)) * 1.08 || 1;
  const x = (value: number) => left + (value / max) * (width - left - right);
  return <div className="viz" ref={tip.ref}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Area getting ${targetHours} hours of direct sun on every checked date, per roof`}>
      <line x1={x(targetAreaSqft)} x2={x(targetAreaSqft)} y1={top - 8} y2={height - 4} className="viz-ref" />
      <text x={x(targetAreaSqft)} y={top - 12} textAnchor="middle" className="viz-ref-label">Your target {fmt(targetAreaSqft)} ft²</text>
      {rows.map((row, index) => {
        const y = top + index * rowH + rowH / 2;
        const meets = row.sunlitSqft !== null && row.sunlitSqft >= targetAreaSqft;
        return <g key={row.id} className={onSelect ? 'viz-clickable' : undefined} onClick={() => onSelect?.(row.id)}
          onMouseMove={(event) => tip.show(event, <><strong>#{row.rank} {row.label}</strong><span>{row.sunlitSqft === null ? 'Not assessed (no roof geometry)' : `${fmt(row.sunlitSqft)} ft² gets ${targetHours} h on every date`}</span>{row.roofSqft && <span>Roof {fmt(row.roofSqft)} ft²{row.sunlitSqft !== null ? ` · ${Math.round((row.sunlitSqft / row.roofSqft) * 100)}% of roof` : ''}</span>}{row.meanHours !== null && <span>Average {row.meanHours.toFixed(1)} h of direct sun</span>}</>)} onMouseLeave={tip.hide}>
          <rect x={0} y={y - rowH / 2} width={width} height={rowH} fill="transparent" />
          <text x={left - 12} y={y + 4} textAnchor="end" className="viz-label"><tspan className="viz-rank">#{row.rank}</tspan> {row.label.length > 20 ? `${row.label.slice(0, 19)}…` : row.label}</text>
          <rect x={left} y={y - 6} width={width - left - right} height={12} rx={6} className="viz-track" />
          {row.sunlitSqft !== null && <rect x={left} y={y - 6} width={Math.max(4, x(row.sunlitSqft) - left)} height={12} rx={6} fill={meets ? '#e85d04' : '#f6b27e'} />}
          <text x={width - right + 10} y={y + 4} className="viz-value">{row.sunlitSqft === null ? 'Not assessed' : `${fmt(row.sunlitSqft)} ft²`}{row.meanHours !== null && <tspan className="viz-muted"> · {row.meanHours.toFixed(1)} h</tspan>}</text>
        </g>;
      })}
    </svg>
    <div className="viz-legend"><span><i style={{ background: '#e85d04' }} /> Meets your area</span><span><i style={{ background: '#f6b27e' }} /> Below your area</span><span className="viz-muted">Value · average daily direct-sun hours</span></div>
    {tip.node}
    <TableView headers={['Rank', 'Roof', `Area with ${targetHours} h sun`, 'Roof area', 'Avg sun']} rows={rows.map((row) => [`#${row.rank}`, row.label, row.sunlitSqft === null ? '—' : `${fmt(row.sunlitSqft)} ft²`, row.roofSqft ? `${fmt(row.roofSqft)} ft²` : '—', row.meanHours === null ? '—' : `${row.meanHours.toFixed(1)} h`])} />
  </div>;
}

// ---------------------------------------------------------------- Optimal points
export type FitPoint = { id: string; rank: number; label: string; sunlitSqft: number | null; fitByCrop: Record<string, number | null> };

export function OptimalPointsChart({ points, crops, targetAreaSqft, onSelect }: { points: FitPoint[]; crops: Array<{ id: string; name: string }>; targetAreaSqft: number; onSelect?: (id: string) => void }) {
  const tip = useTip();
  const [crop, setCrop] = useState<string>('all');
  const fit = (point: FitPoint) => {
    const values = (crop === 'all' ? Object.values(point.fitByCrop) : [point.fitByCrop[crop]]).filter((value): value is number => value !== null && value !== undefined);
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  const width = useWidth(tip.ref); const height = Math.min(380, Math.max(300, width * .55)); const m = { l: 52, r: 24, t: 18, b: 46 };
  const xmax = Math.max(targetAreaSqft * 1.6, ...points.map((point) => point.sunlitSqft ?? 0)) * 1.08;
  const x = (value: number) => m.l + (value / xmax) * (width - m.l - m.r);
  const y = (value: number) => height - m.b - (value / 100) * (height - m.t - m.b);
  const rows = points.map((point) => ({ point, fit: fit(point), cls: classify(point.sunlitSqft, fit(point), targetAreaSqft) }));
  const fits = rows.map((row) => row.fit).filter((value): value is number => value !== null);
  const flat = fits.length > 1 && Math.max(...fits) - Math.min(...fits) < 6;
  const counts = Object.fromEntries((Object.keys(CLASSES) as ClassKey[]).map((key) => [key, rows.filter((row) => row.cls === key).length]));
  return <div className="viz" ref={tip.ref}>
    <div className="viz-filters" role="group" aria-label="Crop">
      <button className={crop === 'all' ? 'active' : ''} onClick={() => setCrop('all')}>All crops (average)</button>
      {crops.map((item) => <button key={item.id} className={crop === item.id ? 'active' : ''} onClick={() => setCrop(item.id)}>{item.name}</button>)}
    </div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Roofs by sunlit area and crop-model fit">
      <rect x={x(targetAreaSqft)} y={m.t} width={width - m.r - x(targetAreaSqft)} height={y(FIT_THRESHOLD) - m.t} className="viz-quad-prime" />
      {[0, 25, 50, 75, 100].map((tick) => <g key={tick}><line x1={m.l} x2={width - m.r} y1={y(tick)} y2={y(tick)} className="viz-grid" /><text x={m.l - 8} y={y(tick) + 4} textAnchor="end" className="viz-axis">{tick}</text></g>)}
      {[0, .25, .5, .75, 1].map((f) => <text key={f} x={x(xmax * f / 1.08)} y={height - m.b + 18} textAnchor="middle" className="viz-axis">{fmt(xmax * f / 1.08 / 1000)}k</text>)}
      <line x1={x(targetAreaSqft)} x2={x(targetAreaSqft)} y1={m.t} y2={height - m.b} className="viz-ref" />
      <line x1={m.l} x2={width - m.r} y1={y(FIT_THRESHOLD)} y2={y(FIT_THRESHOLD)} className="viz-ref" />
      <text x={width - m.r - 6} y={m.t + 14} textAnchor="end" className="viz-quad-label">PRIME</text>
      <text x={m.l + 6} y={m.t + 14} className="viz-quad-label">SUN-LIMITED</text>
      <text x={width - m.r - 6} y={height - m.b - 8} textAnchor="end" className="viz-quad-label">CLIMATE-LIMITED</text>
      <text x={m.l + 6} y={height - m.b - 8} className="viz-quad-label">WEAK</text>
      <text x={(m.l + width - m.r) / 2} y={height - 6} textAnchor="middle" className="viz-axis-title">Area with enough sun (ft²) →</text>
      <text transform={`translate(14 ${(m.t + height - m.b) / 2}) rotate(-90)`} textAnchor="middle" className="viz-axis-title">Crop-model fit (0–100) →</text>
      {rows.filter((row) => row.point.sunlitSqft !== null && row.fit !== null).map(({ point, fit: value, cls }) => {
        const px = x(point.sunlitSqft!); const py = y(value!); const style = CLASSES[cls];
        return <g key={point.id} className={onSelect ? 'viz-clickable' : undefined} onClick={() => onSelect?.(point.id)}
          onMouseMove={(event) => tip.show(event, <><strong>#{point.rank} {point.label}</strong><span>{style.label}: {style.hint.toLowerCase()}</span><span>{fmt(point.sunlitSqft!)} ft² with enough sun</span><span>Crop fit {value!.toFixed(0)}{crop === 'all' ? ' (average of your crops)' : ''}</span></>)} onMouseLeave={tip.hide}>
          <circle cx={px} cy={py} r={16} fill="transparent" />
          <Shape kind={style.shape} x={px} y={py} r={8} color={style.color} />
          <text x={px + 12} y={py - 8} className="viz-point-label">#{point.rank}</text>
        </g>;
      })}
    </svg>
    <div className="viz-legend">{(Object.keys(CLASSES) as ClassKey[]).map((key) => <span key={key}><svg width="14" height="14" aria-hidden="true"><Shape kind={CLASSES[key].shape} x={7} y={7} r={5} color={CLASSES[key].color} /></svg>{CLASSES[key].label} <b>{counts[key]}</b></span>)}</div>
    <p className="viz-note">Lines: your target area ({fmt(targetAreaSqft)} ft²) and a crop fit of {FIT_THRESHOLD}.{flat ? ' Crop fit is nearly identical across these roofs because they share one climate, so sunlit area decides the ranking.' : ''}</p>
    {tip.node}
    <TableView headers={['Rank', 'Roof', 'Sunlit area', 'Crop fit', 'Class']} rows={rows.map((row) => [`#${row.point.rank}`, row.point.label, row.point.sunlitSqft === null ? '—' : `${fmt(row.point.sunlitSqft)} ft²`, row.fit === null ? '—' : row.fit.toFixed(0), CLASSES[row.cls].label])} />
  </div>;
}

// ---------------------------------------------------------------- Planting curves
export type CurveSeries = { id: string; name: string; curve: Array<{ month: number; score: number; uncertainty: number | null; errorP80?: number | null }>; plantMonth: number | null; harvestMonth: number | null; suitableMonths: number[] };

export function PlantingCurveChart({ series, preferredMonth, focusId = null }: { series: CurveSeries[]; preferredMonth: number; focusId?: string | null }) {
  const tip = useTip();
  const [hover, setHover] = useState<number | null>(null);
  // Bumping this replays the draw-in animation (clicking the chart, switching crops).
  const [replay, setReplay] = useState(0);
  const width = useWidth(tip.ref); const height = 280; const m = { l: 40, r: 128, t: 22, b: 30 };
  const band = (width - m.l - m.r) / 12;
  const x = (month: number) => m.l + (month + .5) * band;
  const y = (value: number) => height - m.b - (Math.max(0, Math.min(100, value)) / 100) * (height - m.t - m.b);
  const usable = series.filter((item) => item.curve.length === 12);
  // Direct labels at the right edge, nudged apart so they never collide.
  const labels = useMemo(() => {
    const placed = usable.map((item, index) => ({ id: item.id, name: item.name, color: CROP_COLORS[index % CROP_COLORS.length], y: y(item.curve[11].score) })).sort((a, b) => a.y - b.y);
    for (let i = 1; i < placed.length; i += 1) if (placed[i].y - placed[i - 1].y < 14) placed[i].y = placed[i - 1].y + 14;
    return placed;
  }, [usable]);
  if (!usable.length) return <p className="viz-empty">The crop model did not return monthly curves for this search. Run it again with the model online to see them.</p>;
  return <div className="viz" ref={tip.ref}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Crop-model fit by planting month (click to replay)" onClick={() => setReplay((value) => value + 1)} style={{ cursor: 'pointer' }}>
      <g key={`${focusId ?? 'all'}-${replay}`} className="viz-draw-scope">
      <rect x={m.l + preferredMonth * band} y={m.t} width={band} height={height - m.t - m.b} className="viz-col-highlight" />
      <text x={x(preferredMonth)} y={m.t - 8} textAnchor="middle" className="viz-ref-label">Your start</text>
      {[0, 25, 50, 75, 100].map((tick) => <g key={tick}><line x1={m.l} x2={width - m.r} y1={y(tick)} y2={y(tick)} className="viz-grid" /><text x={m.l - 8} y={y(tick) + 4} textAnchor="end" className="viz-axis">{tick}</text></g>)}
      {MONTHS.map((label, month) => <text key={month} x={x(month)} y={height - m.b + 18} textAnchor="middle" className={month === preferredMonth ? 'viz-axis strong' : 'viz-axis'}>{label}</text>)}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={m.t} y2={height - m.b} className="viz-crosshair" />}
      {usable.map((item, index) => {
        const color = CROP_COLORS[index % CROP_COLORS.length];
        const upper = item.curve.map((point) => `${x(point.month)},${y(point.score + (surrogateError(point) ?? 0))}`);
        const lower = item.curve.slice().reverse().map((point) => `${x(point.month)},${y(point.score - (surrogateError(point) ?? 0))}`);
        const dim = focusId !== null && focusId !== item.id;
        const delay = (dim ? 0 : .15) + index * .18;
        return <g key={item.id} opacity={dim ? .3 : 1}>
          {focusId === item.id && <polygon points={[...upper, ...lower].join(' ')} fill={color} opacity={.14} className="viz-fade" style={{ animationDelay: `${delay + .9}s` }} />}
          <polyline points={item.curve.map((point) => `${x(point.month)},${y(point.score)}`).join(' ')} fill="none" stroke={color} strokeWidth={dim ? 2 : 2.5} strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="viz-draw" style={{ animationDelay: `${delay}s` }} />
          {item.suitableMonths.map((month) => <circle key={month} cx={x(month)} cy={y(item.curve[month].score)} r={3.5} fill={color} className="viz-ring viz-pop" style={{ animationDelay: `${delay + .2 + (month / 12) * 1.1}s`, transformOrigin: `${x(month)}px ${y(item.curve[month].score)}px` }} />)}
          {item.plantMonth !== null && <g className="viz-pop" style={{ animationDelay: `${delay + 1.35}s`, transformOrigin: `${x(item.plantMonth)}px ${y(item.curve[item.plantMonth].score)}px` }}><circle cx={x(item.plantMonth)} cy={y(item.curve[item.plantMonth].score)} r={7} fill="#fff" stroke={color} strokeWidth={2.5} /><circle cx={x(item.plantMonth)} cy={y(item.curve[item.plantMonth].score)} r={3} fill={color} /></g>}
        </g>;
      })}
      {labels.map((label) => <g key={label.id} className="viz-fade" style={{ animationDelay: '1.2s' }}><circle cx={width - m.r + 12} cy={label.y - 4} r={4} fill={label.color} /><text x={width - m.r + 20} y={label.y} className="viz-label">{label.name.length > 16 ? `${label.name.slice(0, 15)}…` : label.name}</text></g>)}
      </g>
      {MONTHS.map((_, month) => <rect key={month} x={m.l + month * band} y={m.t} width={band} height={height - m.t - m.b} fill="transparent"
        onMouseMove={(event) => { setHover(month); tip.show(event, <><strong>Plant in {MONTH_NAMES[month]}</strong>{usable.map((item, index) => { const point = item.curve[month]; const error = surrogateError(point); return <span key={item.id}><i style={{ background: CROP_COLORS[index % CROP_COLORS.length] }} />{item.name}: {point.score.toFixed(0)}{error !== null ? ` ± ${formatSurrogateError(error)} (80%)` : ''}{item.plantMonth === month ? ' · recommended' : item.suitableMonths.includes(month) ? ' · workable' : ''}</span>; })}</>); }}
        onMouseLeave={() => { setHover(null); tip.hide(); }} />)}
    </svg>
    <div className="viz-legend">{usable.map((item, index) => <span key={item.id}><i style={{ background: CROP_COLORS[index % CROP_COLORS.length] }} />{item.name}{item.plantMonth !== null ? ` · plant ${MONTH_NAMES[item.plantMonth]}` : ' · no workable month'}</span>)}<span className="viz-muted">◯ recommended start · • workable month{focusId ? ' · band = calibrated 80% surrogate error' : ''}</span></div>
    {tip.node}
    <TableView headers={['Crop', ...MONTH_NAMES]} rows={usable.map((item) => [item.name, ...item.curve.map((point) => `${point.score.toFixed(0)}${item.plantMonth === point.month ? '★' : ''}`)])} />
  </div>;
}

// ---------------------------------------------------------------- Component scores (ML tab)
export function ComponentBars({ components }: { components: Record<string, number> }) {
  const entries = Object.entries(components);
  return <div className="viz-components">{entries.map(([name, value]) => <div key={name}>
    <span>{name.replace(/_/g, ' ')}</span><i><b style={{ width: `${Math.max(2, Math.min(100, value))}%` }} /></i><strong>{value.toFixed(0)}</strong>
  </div>)}</div>;
}

// ---------------------------------------------------------------- Crop timeline (calendar tab)
export function CropTimeline({ rows, preferredMonth, checkDates }: { rows: Array<{ id: string; name: string; plantMonth: number | null; harvestMonth: number | null; suitableMonths: number[]; growDays?: { min: number; max: number } | null }>; preferredMonth: number; checkDates: string[] }) {
  const checked = new Set(checkDates.map((date) => new Date(`${date}T12:00:00`).getMonth()));
  const span = (start: number, end: number) => { const months: number[] = []; for (let m = start; ; m = (m + 1) % 12) { months.push(m); if (m === end || months.length > 12) break; } return months; };
  return <div className="viz-timeline">
    <div className="viz-timeline-row head"><span />{MONTH_NAMES.map((name, month) => <em key={name} className={month === preferredMonth ? 'preferred' : ''}>{name}</em>)}</div>
    {rows.map((row, index) => {
      const color = CROP_COLORS[index % CROP_COLORS.length];
      const grow = row.plantMonth !== null && row.harvestMonth !== null ? span(row.plantMonth, row.harvestMonth) : [];
      return <div className="viz-timeline-row" key={row.id}>
        <span><i style={{ background: color }} />{row.name}</span>
        {MONTH_NAMES.map((name, month) => {
          const growing = grow.includes(month);
          return <div key={name} className={['cell', row.suitableMonths.includes(month) ? 'workable' : '', growing ? 'growing' : ''].join(' ')} style={growing ? { background: color } : row.suitableMonths.includes(month) ? { background: `${color}26` } : undefined}
            title={`${name}: ${month === row.plantMonth ? 'plant' : month === row.harvestMonth ? 'harvest' : growing ? 'growing' : row.suitableMonths.includes(month) ? 'workable planting month' : 'not recommended'}`}>
            {month === row.plantMonth && <small>Plant</small>}{month === row.harvestMonth && month !== row.plantMonth && <small>Harvest</small>}
          </div>;
        })}
      </div>;
    })}
    <div className="viz-timeline-row checks"><span>Sun checked</span>{MONTH_NAMES.map((name, month) => <div key={name} className="cell">{checked.has(month) && <small>☀</small>}</div>)}</div>
    <div className="viz-legend"><span><i style={{ background: CROP_COLORS[0] }} /> Growing season (plant → harvest)</span><span><i style={{ background: `${CROP_COLORS[0]}26` }} /> Other workable planting months</span><span>☀ months the roof's sun was simulated</span></div>
  </div>;
}

// ---------------------------------------------------------------- shared
function TableView({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return <details className="viz-table"><summary>Show as table</summary><div><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div></details>;
}
