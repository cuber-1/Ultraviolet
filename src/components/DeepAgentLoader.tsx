import { useEffect, useState, type ReactNode } from 'react';
import { Check, LoaderCircle } from 'lucide-react';
import './DeepAgentLoader.css';

export type LoaderStage = { key: string; label: string };

type Props = {
  kicker: string;
  title: string;
  subtitle: string;
  stages: LoaderStage[];
  activeIndex: number;
  message: string;
  log: string[];
  startedAt: number;
  expected: string;
  insight?: ReactNode;
  onCancel: () => void;
};

const COLUMNS = 14;
const ROWS = 8;

export default function DeepAgentLoader({ kicker, title, subtitle, stages, activeIndex, message, log, startedAt, expected, insight, onCancel }: Props) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

  return <div className="agent-loader" role="dialog" aria-modal="true" aria-labelledby="agent-loader-title">
    <button className="agent-loader-cancel mono" onClick={onCancel}>CANCEL</button>

    <div className="agent-loader-stage" aria-hidden="true">
      <div className="agent-loader-sky"><span className="agent-loader-sun" /></div>
      <div className="agent-loader-roof" style={{ gridTemplateColumns: `repeat(${COLUMNS}, 1fr)` }}>
        {Array.from({ length: COLUMNS * ROWS }, (_, index) => {
          const column = index % COLUMNS;
          const row = Math.floor(index / COLUMNS);
          return <i key={index} style={{ animationDelay: `${(column / COLUMNS) * 6 + (row % 3) * .25}s` }} />;
        })}
      </div>
    </div>

    <section className="agent-loader-content">
      <div className="agent-loader-kicker mono"><i /> {kicker}</div>
      <h2 id="agent-loader-title">{title}</h2>
      <p className="agent-loader-subtitle">{subtitle}</p>

      <ol className="agent-loader-rail">
        {stages.map((stage, index) => <li key={stage.key} className={index < activeIndex ? 'done' : index === activeIndex ? 'active' : ''}>
          <span>{index < activeIndex ? <Check size={11} /> : index === activeIndex ? <LoaderCircle size={12} className="spin" /> : index + 1}</span>
          <small>{stage.label}</small>
        </li>)}
      </ol>

      <div className="agent-loader-now" role="status" aria-live="polite">
        <strong>{message}</strong>
        <span className="mono">{elapsed} ELAPSED · {expected}</span>
      </div>

      {log.length > 1 && <ul className="agent-loader-log mono">{log.slice(-4, -1).reverse().map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}</ul>}

      {insight && <div className="agent-loader-insight">{insight}</div>}
    </section>
  </div>;
}
