import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Droplets, Home, Radio, Usb } from 'lucide-react';
import Wordmark from '../components/Wordmark';
import './SensorsPage.css';

type Reading = { nodeId: string; soilPct: number; rawAo: number | null; wet: boolean | null; digital: 'wet' | 'dry' | null; intervalS: number | null; at: string; source: string };

const ago = (iso: string, now: number) => { const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000)); return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ${s % 60}s ago`; };
const status = (pct: number) => pct < 20 ? { label: 'Dry · water soon', tone: 'dry' } : pct <= 60 ? { label: 'Good moisture', tone: 'good' } : { label: 'Wet · hold off watering', tone: 'wet' };

/** Live soil-moisture readings from the ESP32 sensor nodes. */
export default function SensorsPage() {
  const navigate = useNavigate();
  const [readings, setReadings] = useState<Reading[]>([]);
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    void fetch('/api/sensors').then((response) => response.json()).then((payload: { readings: Reading[] }) => setReadings(payload.readings ?? [])).catch(() => undefined);
    const stream = new EventSource('/api/sensors/stream');
    stream.onopen = () => setConnected(true);
    stream.onerror = () => setConnected(false);
    stream.onmessage = (event) => {
      const message = JSON.parse(event.data) as { type: string; reading?: Reading };
      if (message.type === 'reading' && message.reading) setReadings((items) => [...items.slice(-299), message.reading!]);
    };
    return () => stream.close();
  }, []);

  const nodes = useMemo(() => {
    const byNode = new Map<string, Reading[]>();
    for (const reading of readings) byNode.set(reading.nodeId, [...(byNode.get(reading.nodeId) ?? []), reading]);
    return [...byNode.entries()].map(([id, items]) => ({ id, items, latest: items[items.length - 1] })).sort((a, b) => a.id.localeCompare(b.id));
  }, [readings]);

  return <div className="sp">
    <header className="sp-bar">
      <button className="sp-home" onClick={() => navigate('/')}><Home size={18} /><Wordmark /></button>
      <span className={connected ? 'sp-live on' : 'sp-live'}><i />{connected ? 'Live' : 'Connecting…'}</span>
    </header>
    <main className="sp-main">
      <h1>Live sensors</h1>
      <p className="sp-lede">Soil moisture from Ultraviolet's ESP32 sensor nodes, streamed as each reading arrives.</p>

      {!nodes.length && <section className="sp-empty">
        <Usb size={28} />
        <h2>Waiting for the first reading</h2>
        <p>Plug the sensor node into this computer and start the bridge in a terminal:</p>
        <code>npm run hardware:bridge</code>
        <p className="sp-muted">The node reports every 30 seconds; the first reading appears here as soon as it arrives.</p>
      </section>}

      <div className="sp-grid">{nodes.map(({ id, items, latest }) => {
        const state = status(latest.soilPct);
        const interval = latest.intervalS ?? 30;
        const since = (now - Date.parse(latest.at)) / 1000;
        const stale = since > interval * 2.5;
        const next = Math.max(0, Math.ceil(interval - since));
        const saturated = latest.rawAo !== null && latest.rawAo >= 4090;
        return <article key={id} className={`sp-node ${state.tone}${stale ? ' stale' : ''}`}>
          <header><span><Radio size={16} /> {id}</span><small>{latest.source === 'usb-serial' ? 'USB' : latest.source} · {ago(latest.at, now)}</small></header>
          <div className="sp-gauge">
            <svg viewBox="0 0 200 120" aria-hidden="true">
              <path d="M20 110 A80 80 0 0 1 180 110" className="sp-arc-track" />
              {latest.soilPct >= 1 && <path d="M20 110 A80 80 0 0 1 180 110" className="sp-arc" pathLength={100} style={{ strokeDasharray: `${latest.soilPct} 200` }} />}
            </svg>
            <div><strong>{latest.soilPct.toFixed(0)}<small>%</small></strong><span>soil moisture</span></div>
          </div>
          <p className={`sp-state ${state.tone}`}><Droplets size={16} /> {state.label}</p>
          {saturated && <p className="sp-hint">The sensor is reading its maximum ({latest.rawAo}). It's probably in air or unplugged. Push the probe into the soil.</p>}
          <dl>
            <div><dt>Raw sensor</dt><dd>{latest.rawAo ?? '—'}</dd></div>
            <div><dt>Wet pin</dt><dd>{latest.digital ?? (latest.wet === null ? '—' : latest.wet ? 'wet' : 'dry')}</dd></div>
            <div><dt>Next reading</dt><dd>{stale ? 'overdue' : `in ${next}s`}</dd></div>
            <div><dt>Readings</dt><dd>{items.length}</dd></div>
          </dl>
          <History items={items} />
        </article>;
      })}</div>
    </main>
  </div>;
}

function History({ items }: { items: Reading[] }) {
  const recent = items.slice(-60);
  if (recent.length < 2) return <p className="sp-muted sp-history-empty"><Activity size={14} /> History appears after a couple of readings.</p>;
  const width = 320; const height = 90;
  const x = (index: number) => (index / (recent.length - 1)) * width;
  const y = (pct: number) => height - (pct / 100) * (height - 8) - 4;
  const line = recent.map((item, index) => `${x(index)},${y(item.soilPct)}`).join(' ');
  return <div className="sp-history">
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Soil moisture history">
      <polygon points={`0,${height} ${line} ${width},${height}`} className="sp-area" />
      <polyline points={line} className="sp-line" />
    </svg>
    <div className="sp-history-axis"><span>{new Date(recent[0].at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span><span>now</span></div>
  </div>;
}
