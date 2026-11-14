import { useEffect, useRef, useState, type ReactNode } from 'react';
import L, { type LayerGroup, type Map as LeafletMap } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowRight, Check, Home, LoaderCircle, X } from 'lucide-react';
import AgentCompanion from './AgentCompanion';
import './MapStage.css';

export type MapStageStage = { key: string; label: string };
export type MapPin = { id: string; lat: number; lon: number; rank: number; label: string };

type Props = {
  mode: 'loading' | 'done';
  focus: Array<{ lat: number; lon: number }>;
  discovered: Array<{ lat: number; lon: number }>;
  pins: MapPin[];
  title: string;
  subtitle: string;
  stages: MapStageStage[];
  activeIndex: number;
  message: string;
  startedAt: number;
  feed?: ReactNode;
  summary?: string;
  ctaLabel: string;
  onContinue: () => void;
  onCancel: () => void;
  onHome?: () => void;
};

const WORLD: [number, number] = [25, -60];

/**
 * Full-screen map that carries a search: flies from the US to the search area, ripples
 * gradient waves while the agent works, drops each discovered site, then frames the top
 * results with numbered pins and a button into the results.
 */
export default function MapStage({ mode, focus, discovered, pins, title, subtitle, stages, activeIndex, message, startedAt, feed, summary, ctaLabel, onContinue, onCancel, onHome }: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const dots = useRef<LayerGroup | null>(null);
  const pinLayer = useRef<LayerGroup | null>(null);
  const [waves, setWaves] = useState<Array<{ x: number; y: number; size: number }>>([]);
  const [now, setNow] = useState(Date.now());
  const [tab, setTab] = useState<'activity' | 'steps'>('activity');
  const feedRef = useRef<HTMLDivElement>(null);
  // Keep the newest activity in view.
  useEffect(() => { const node = feedRef.current; if (node) node.scrollTop = node.scrollHeight; });
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));

  // Map setup + opening flight.
  useEffect(() => {
    if (!element.current || map.current) return;
    const instance = L.map(element.current, { zoomControl: false, attributionControl: true, zoomSnap: .25 }).setView(WORLD, 2);
    // Esri light-gray canvas: no API key, quiet colours that let the waves and pins stand out.
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors' }).addTo(instance);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16 }).addTo(instance);
    dots.current = L.layerGroup().addTo(instance);
    pinLayer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    return () => { instance.stop(); instance.remove(); map.current = null; };
  }, []);

  // Fly into the search area, then keep the camera gently moving while loading.
  const focusKey = focus.map((point) => `${point.lat},${point.lon}`).join('|');
  useEffect(() => {
    const instance = map.current; if (!instance || !focus.length || mode !== 'loading') return;
    const target = focus.length === 1 ? L.latLng(focus[0].lat, focus[0].lon) : L.latLngBounds(focus.map((point) => [point.lat, point.lon] as [number, number])).getCenter();
    const zoom = focus.length === 1 ? 10.5 : Math.min(7, instance.getBoundsZoom(L.latLngBounds(focus.map((point) => [point.lat, point.lon] as [number, number])).pad(.6)));
    // Zoom in from the whole world onto the search area.
    const start = window.setTimeout(() => instance.flyTo(target, zoom, { duration: 3.6, easeLinearity: .15 }), 400);
    let tick = 0;
    const drift = window.setInterval(() => {
      tick += 1;
      const wobble = focus.length === 1 ? .045 : .9;
      instance.flyTo([target.lat + Math.sin(tick) * wobble * .5, target.lng + Math.cos(tick * .7) * wobble], zoom + (tick % 2 ? .5 : 0), { duration: 5.5, easeLinearity: .1 });
    }, 6500);
    return () => { window.clearTimeout(start); window.clearInterval(drift); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey, mode]);

  // Gradient waves follow the focus point(s) on screen.
  useEffect(() => {
    const instance = map.current; if (!instance) return;
    const place = () => setWaves(focus.map((point) => {
      const center = instance.latLngToContainerPoint([point.lat, point.lon]);
      const edge = instance.latLngToContainerPoint([point.lat, point.lon + (focus.length === 1 ? .22 : 1.6)]);
      return { x: center.x, y: center.y, size: Math.max(160, Math.abs(edge.x - center.x) * 2) };
    }));
    place();
    instance.on('move zoom resize', place);
    return () => { instance.off('move zoom resize', place); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey]);

  // Done: stop waves, frame the top results, drop numbered pins.
  const pinKey = pins.map((pin) => pin.id).join('|');
  useEffect(() => {
    const instance = map.current; if (!instance || mode !== 'done' || !pins.length) return;
    dots.current?.clearLayers();
    pinLayer.current?.clearLayers();
    instance.stop();
    const bounds = L.latLngBounds(pins.map((pin) => [pin.lat, pin.lon] as [number, number]));
    instance.flyToBounds(bounds.pad(.35), { duration: 1.8, maxZoom: 15, paddingTopLeft: [420, 80], paddingBottomRight: [80, 160] });
    const timers = pins.map((pin, index) => window.setTimeout(() => {
      if (!pinLayer.current) return;
      L.marker([pin.lat, pin.lon], { icon: L.divIcon({ className: 'ms-pin-shell', html: `<span class="ms-pin"><b>${pin.rank}</b></span><span class="ms-pin-label">${pin.label.replace(/</g, '&lt;')}</span>`, iconSize: [44, 52], iconAnchor: [22, 50] }), title: `#${pin.rank} ${pin.label}` }).addTo(pinLayer.current!);
    }, 1900 + index * 220));
    return () => { timers.forEach((timer) => window.clearTimeout(timer)); pinLayer.current?.clearLayers(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, pinKey]);

  return <div className={`ms ms-${mode}`}>
    <div ref={element} className="ms-map" />
    {mode === 'loading' && waves[0] && <div className="ms-dim" aria-hidden="true" style={{ background: `radial-gradient(circle at ${waves[0].x}px ${waves[0].y}px, transparent ${waves[0].size * .35}px, rgba(28, 24, 20, .38) ${waves[0].size * 1.1}px)` }} />}
    {mode === 'loading' && <div className="ms-waves" aria-hidden="true">{waves.map((wave, index) => <div key={index} className="ms-wave-group" style={{ left: wave.x, top: wave.y, width: wave.size, height: wave.size }}>
      <i className="ms-glow" /><i className="ms-sweep" /><i className="ms-ring" /><i className="ms-ring r2" /><i className="ms-ring r3" /><i className="ms-core" />
    </div>)}</div>}

    {mode === 'loading' && <div className="ms-companion"><AgentCompanion message={stages[activeIndex]?.label ? `${stages[activeIndex].label}…` : 'Working on it…'} detail={message} /></div>}

    <aside className="ms-panel">
      {onHome && mode === 'done' && <button className="ms-home" onClick={onHome}><Home size={16} /> Home</button>}
      <span className="ms-kicker">{mode === 'loading' ? <><i /> Searching live</> : <><Check size={15} /> Search complete</>}</span>
      <h1>{title}</h1>
      <p className="ms-sub">{subtitle}</p>
      {mode === 'loading' && feed && <div className="ms-progress"><span>Step {Math.min(activeIndex + 1, stages.length)} of {stages.length} · {stages[Math.min(activeIndex, stages.length - 1)]?.label}</span><i><b style={{ width: `${(Math.min(activeIndex, stages.length) / stages.length) * 100}%` }} /></i></div>}
      {mode === 'loading' && feed && <div className="ms-tabs" role="tablist"><button role="tab" aria-selected={tab === 'activity'} className={tab === 'activity' ? 'active' : ''} onClick={() => setTab('activity')}>Live activity</button><button role="tab" aria-selected={tab === 'steps'} className={tab === 'steps' ? 'active' : ''} onClick={() => setTab('steps')}>Steps</button></div>}
      {(!feed || mode === 'done' || tab === 'steps') && <>
        <ol className="ms-steps">{stages.map((stage, index) => {
        const state = mode === 'done' || index < activeIndex ? 'done' : index === activeIndex ? 'active' : '';
        return <li key={stage.key} className={state}><span>{state === 'done' ? <Check size={14} /> : state === 'active' ? <LoaderCircle size={14} className="spin" /> : index + 1}</span>{stage.label}</li>;
      })}</ol>
      </>}
      {mode === 'loading' && feed && tab === 'activity' && <div className="ms-feed" ref={feedRef}>{feed}</div>}
      {mode === 'loading' && <div className="ms-now"><strong>{message}</strong><small>{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} elapsed</small></div>}
      {mode === 'loading' && <button className="ms-cancel" onClick={onCancel}><X size={15} /> Cancel</button>}
    </aside>

    {mode === 'done' && <div className="ms-cta">
      {summary && <p>{summary}</p>}
      <button onClick={onContinue}>{ctaLabel} <ArrowRight size={22} /></button>
    </div>}
  </div>;
}
