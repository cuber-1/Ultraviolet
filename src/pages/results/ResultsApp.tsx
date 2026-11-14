import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Heart, Home, Layers, LineChart, Map as MapIcon, Pencil, RotateCcw, Sparkles, Star, Trash2, X } from 'lucide-react';
import Wordmark from '../../components/Wordmark';
import { ActivityFeed, AgentTrace } from './AgentTrace';
import { CLASSES, CROP_COLORS, classify } from '../../components/charts/DeepAgentCharts';
import { briefCrops, estimateFood, formatLbs, urbanAreaLabel, type Brief } from '../../services/cropPlan';
import { roofTitle, useAddresses } from '../../services/addresses';
import { addFavorite, loadFavorites, removeFavorite, type Favorite } from '../../services/favorites';
import type { AgentComparison, SearchResult } from '../../services/vexcel';
import './ResultsApp.css';

type View = 'deck' | 'saved' | 'insights' | 'agent';
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const fmt = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
const firstSentence = (text: string | undefined) => text ? (text.match(/^.*?[.!?](\s|$)/)?.[0] ?? text).trim() : null;

type Props = {
  brief: Brief;
  criteria: { dates: string[]; targetHours: number; targetAreaSqft: number };
  comparison: AgentComparison;
  top: SearchResult[];
  insights: ReactNode;
  savedAt: string | null;
  onEdit: () => void;
  onRerun: () => void;
  onOpen: (id: string) => void;
  onMap?: () => void;
  onHome?: () => void;
};

export default function ResultsApp({ brief, criteria, comparison, top, insights, savedAt, onEdit, onRerun, onOpen, onMap, onHome }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const view = (['deck', 'saved', 'insights', 'agent'].includes(params.get('view') ?? '') ? params.get('view') : 'deck') as View;
  const index = Math.max(0, Math.min(top.length, Number(params.get('i')) || 0));
  const go = useCallback((next: { view?: View; i?: number }) => {
    const search = new URLSearchParams({ view: next.view ?? view, i: String(next.i ?? index) });
    navigate(`/plan?${search}`, { replace: true, state: location.state });
  }, [index, location.state, navigate, view]);
  const [favorites, setFavorites] = useState<Favorite[]>(loadFavorites);

  const crops = briefCrops(brief);
  const addresses = useAddresses(top.map((result) => ({ id: result.id, lat: result.lat, lon: result.lon, known: Boolean(result.costar?.buildingName || result.costar?.address) })));
  const roofs = useMemo(() => top.map((result, rank) => {
    const simulation = comparison.simulations.find((item) => item.candidateId === result.id);
    const predictions = (comparison.predictions ?? []).filter((item) => item.siteId === result.id);
    const scored = predictions.filter((item) => item.source === 'ml');
    const fit = scored.length ? (scored.reduce((sum, item) => sum + item.suitability, 0) / scored.length) * 100 : null;
    const starts = predictions.filter((item) => item.plantMonth !== null).map((item) => item.plantMonth!).sort((a, b) => ((a - brief.preferredMonth + 12) % 12) - ((b - brief.preferredMonth + 12) % 12));
    const hours = simulation?.perDate.map((item) => item.meanHours).filter((value): value is number => value !== null) ?? [];
    const sunlit = simulation?.sharedAreaSqft ?? null;
    return {
      result, rank: rank + 1, predictions,
      name: roofTitle(result, addresses.get(result.id)).name,
      address: roofTitle(result, addresses.get(result.id)).line,
      food: estimateFood(sunlit, crops, new Set(predictions.filter((item) => item.source === 'ml' && item.plantMonth === null).map((item) => item.cropId))),
      sunlit, fit, start: (starts[0] ?? null) as number | null,
      meanHours: hours.length ? hours.reduce((a, b) => a + b, 0) / hours.length : null,
      why: firstSentence(comparison.narrative?.explanations.find((item) => item.candidateId === result.id)?.explanation),
      cls: classify(sunlit, fit, criteria.targetAreaSqft),
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [addresses, brief.preferredMonth, comparison, criteria.targetAreaSqft, top]);

  const save = (roof: typeof roofs[number]) => setFavorites(addFavorite({
    id: roof.result.id, name: roof.name, address: roof.address, imageryUrl: roof.result.imageryUrl, city: urbanAreaLabel(brief),
    sunlitSqft: roof.sunlit, fit: roof.fit, startMonth: roof.start, crops: crops.map((crop) => crop.name), savedAt: new Date().toISOString(),
  }));
  const savedIds = new Set(favorites.map((item) => item.id));

  return <div className="ra">
    <header className="ra-bar">
      <div className="ra-brand"><button className="ra-home" onClick={onHome} title="Back to the home page"><Home size={18} /><Wordmark /></button><span>{urbanAreaLabel(brief)} · {crops.map((crop) => crop.name).join(', ')}</span></div>
      <nav className="ra-nav" aria-label="Results views">
        {([['deck', 'Roofs', Layers], ['saved', `Saved${favorites.length ? ` ${favorites.length}` : ''}`, Heart], ['insights', 'Insights', LineChart], ['agent', 'Agent', Sparkles]] as const).map(([key, label, Icon]) =>
          <button key={key} className={view === key ? 'active' : ''} onClick={() => go({ view: key })}><Icon size={17} />{label}</button>)}
      </nav>
      <div className="ra-actions">
        {onMap && <button onClick={onMap}><MapIcon size={16} /> Map</button>}
        {savedAt && <span className="ra-saved-pill" title="Opened from a saved run; nothing was re-run">Saved run</span>}
        <button onClick={onEdit}><Pencil size={16} /> Edit</button>
        <button onClick={onRerun}><RotateCcw size={16} /> Run again</button>
      </div>
    </header>

    {view === 'deck' && <Deck roofs={roofs} index={index} total={top.length} criteria={criteria} crops={crops.map((crop) => crop.id)} cropNames={crops.map((crop) => crop.name)} savedIds={savedIds}
      onIndex={(i) => go({ i })} onSave={save} onOpen={onOpen} onShowSaved={() => go({ view: 'saved' })} />}

    {view === 'saved' && <main className="ra-saved">
      <h1>{favorites.length ? `${favorites.length} saved ${favorites.length === 1 ? 'roof' : 'roofs'}` : 'No saved roofs yet'}</h1>
      <p>{favorites.length ? 'Kept in this browser across searches.' : 'Swipe right or tap the star on a roof to keep it here.'}</p>
      <div className="ra-saved-grid">{favorites.map((item) => {
        const here = top.some((result) => result.id === item.id);
        return <article key={item.id} className="ra-saved-item">
          <button className="ra-saved-open" onClick={() => here && onOpen(item.id)} disabled={!here} title={here ? 'Open details' : 'From an earlier search'}>
            <img src={item.imageryUrl} alt="" />
            <div><strong>{item.name}</strong><span>{item.sunlitSqft !== null ? `${fmt(item.sunlitSqft)} ft² in sun` : 'Sun not assessed'}{item.fit !== null ? ` · fit ${Math.round(item.fit)}` : ''}{item.startMonth !== null ? ` · start ${MONTHS[item.startMonth].slice(0, 3)}` : ''}</span><small>{here ? item.crops.join(', ') : `${item.city} · earlier search`}</small></div>
          </button>
          <button className="ra-saved-remove" onClick={() => setFavorites(removeFavorite(item.id))} aria-label={`Remove ${item.name}`}><Trash2 size={16} /></button>
        </article>;
      })}</div>
    </main>}

    {view === 'insights' && <main className="ra-insights">{insights}</main>}

    {view === 'agent' && <main className="ra-agent">
      <h1>What the Deep Agent did</h1>
      <p>Every prompt, model turn, and tool call from this search, in order. The same run is traced in LangSmith.</p>
      {(comparison.trace ?? []).some((event) => event.kind === 'activity') && <><h2 className="feed-heading">Activity</h2><ActivityFeed events={comparison.trace ?? []} /></>}
      <h2 className="feed-heading">Full trace</h2>
      <AgentTrace events={comparison.trace ?? []} model={comparison.model ?? null} />
    </main>}
  </div>;
}

type Roof = { food: ReturnType<typeof estimateFood>; result: SearchResult; rank: number; name: string; address: string; sunlit: number | null; fit: number | null; start: number | null; meanHours: number | null; why: string | null; cls: keyof typeof CLASSES; predictions: NonNullable<AgentComparison['predictions']> };

function Deck({ roofs, index, total, criteria, crops, cropNames, savedIds, onIndex, onSave, onOpen, onShowSaved }: {
  roofs: Roof[]; index: number; total: number; criteria: Props['criteria']; crops: string[]; cropNames: string[]; savedIds: Set<string>;
  onIndex: (i: number) => void; onSave: (roof: Roof) => void; onOpen: (id: string) => void; onShowSaved: () => void;
}) {
  const [dx, setDx] = useState(0);
  const [exit, setExit] = useState<'left' | 'right' | null>(null);
  const start = useRef<number | null>(null);
  const roof = roofs[index];
  const decide = useCallback((direction: 'left' | 'right') => {
    if (!roof || exit) return;
    if (direction === 'right') onSave(roof);
    setExit(direction);
    window.setTimeout(() => { setExit(null); setDx(0); onIndex(index + 1); }, 260);
  }, [exit, index, onIndex, onSave, roof]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return;
      if (event.key === 'ArrowLeft') decide('left');
      if (event.key === 'ArrowRight') decide('right');
      if ((event.key === 'Enter' || event.key === 'ArrowUp') && roof) onOpen(roof.result.id);
      if (event.key === 'Backspace' && index > 0) onIndex(index - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [decide, index, onIndex, onOpen, roof]);

  if (!roof) {
    const saved = roofs.filter((item) => savedIds.has(item.result.id)).length;
    return <main className="ra-done">
      <Star size={40} />
      <h1>{saved ? `You saved ${saved} of ${total} roofs.` : `That's all ${total} roofs.`}</h1>
      <div><button className="ra-primary" onClick={onShowSaved}>See saved roofs</button><button onClick={() => onIndex(0)}>Go through again</button></div>
    </main>;
  }
  const offset = exit === 'left' ? -1400 : exit === 'right' ? 1400 : dx;
  const meets = roof.sunlit !== null && roof.sunlit >= criteria.targetAreaSqft;
  return <main className="ra-deck">
    <div className="ra-progress" aria-label={`Roof ${index + 1} of ${total}`}>{roofs.map((item, i) => <i key={item.result.id} className={i < index ? 'done' : i === index ? 'now' : ''} />)}</div>
    <article className={`ra-card${exit ? ' leaving' : ''}${start.current !== null ? ' dragging' : ''}`} style={{ transform: `translateX(${offset}px) rotate(${offset / 40}deg)` }}
      onPointerDown={(event) => { if ((event.target as HTMLElement).closest('button')) return; start.current = event.clientX; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { if (start.current !== null) setDx(event.clientX - start.current); }}
      onPointerUp={() => { const moved = dx; start.current = null; if (moved > 120) decide('right'); else if (moved < -120) decide('left'); else setDx(0); }}>
      <div className="ra-photo">
        <img src={roof.result.imageryUrl} alt={`Aerial view of ${roof.name}`} draggable={false} />
        <span className="ra-stamp save" style={{ opacity: Math.max(0, Math.min(1, dx / 120)) }}>Save</span>
        <span className="ra-stamp pass" style={{ opacity: Math.max(0, Math.min(1, -dx / 120)) }}>Pass</span>
        <span className="ra-class"><i style={{ background: CLASSES[roof.cls].color }} />{CLASSES[roof.cls].label}</span>
      </div>
      <div className="ra-info">
        <span className="ra-count">Roof {roof.rank} of {total}{savedIds.has(roof.result.id) ? ' · saved' : ''}</span>
        <h1>{roof.name}</h1>
        <p className="ra-address">{roof.address}</p>
        <div className="ra-stats">
          <div className="ra-food"><strong>{roof.food ? `≈${formatLbs(roof.food.lbsPerYear)}` : '—'}<small> lbs</small></strong><span>food a year (est.)</span></div>
          <div><strong>{roof.sunlit === null ? '—' : `${fmt(roof.sunlit)}`}<small> ft²</small></strong><span>{meets ? 'in full sun, meets your area' : `in ${criteria.targetHours}h+ sun`}</span></div>
          <div><strong>{roof.fit === null ? '—' : Math.round(roof.fit)}</strong><span>crop fit</span></div>
          <div><strong>{roof.start === null ? '—' : MONTHS[roof.start].slice(0, 3)}</strong><span>start</span></div>
        </div>
        <ul className="ra-crops">{crops.map((id, i) => { const item = roof.predictions.find((p) => p.cropId === id); return <li key={id}><i style={{ background: CROP_COLORS[i % CROP_COLORS.length] }} />{cropNames[i]}<b>{item ? Math.round(item.suitability * 100) : '—'}</b></li>; })}</ul>
        {roof.why && <p className="ra-why">{roof.why}</p>}
        <div className="ra-buttons">
          <button className="ra-round pass" onClick={() => decide('left')} aria-label="Pass"><X size={28} /></button>
          <button className="ra-round save" onClick={() => decide('right')} aria-label="Save"><Heart size={28} /></button>
          <button className="ra-details" onClick={() => onOpen(roof.result.id)}>Details <ArrowRight size={18} /></button>
        </div>
      </div>
    </article>
  </main>;
}
