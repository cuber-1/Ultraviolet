import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Play } from 'lucide-react';
import { DEMO_BRIEF, saveBrief } from '../services/cropPlan';
import { useNavigate } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import Showcase from '../components/Showcase';
import './LandingPage.css';

const CHARS = '·∿~=+−|/\\.:,;!?@#$%^&*()[]{}01<>≈≡∂∑∏√±×÷∞∠∆∇⊕⊗◦●○◆◇▲△▷▻';
const CURSOR_GLYPHS = ['∆', '⊕', '∑', '◇', '∞', '∇', '≈', '○'];
const SHOWCASE_STEPS = 3;
const SHOWCASE_INTERVAL_MS = 6500;

function buildGrid(columns: number, rows: number): string[][] {
  return Array.from({ length: rows }, () =>
    Array.from({ length: columns }, () => CHARS[Math.floor(Math.random() * CHARS.length)]),
  );
}

function DataField() {
  const fieldRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<string[][]>([]);
  const frameRef = useRef<number>(0);
  const [, render] = useState(0);

  useEffect(() => {
    const field = fieldRef.current;
    if (!field) return;

    const sizeGrid = () => {
      const node = fieldRef.current;
      if (!node) return;
      gridRef.current = buildGrid(
        Math.max(1, Math.floor(node.clientWidth / 11)),
        Math.max(1, Math.floor(node.clientHeight / 18) + 1),
      );
      render((value) => value + 1);
    };

    sizeGrid();
    const observer = new ResizeObserver(sizeGrid);
    observer.observe(field);

    let frame = 0;
    const animate = () => {
      frame += 1;
      if (frame % 8 === 0) {
        gridRef.current = gridRef.current.map((row) =>
          row.map((character) => Math.random() < 0.015
            ? CHARS[Math.floor(Math.random() * CHARS.length)]
            : character),
        );
        render((value) => value + 1);
      }
      frameRef.current = requestAnimationFrame(animate);
    };
    frameRef.current = requestAnimationFrame(animate);

    const moveCursor = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return;
      const node = fieldRef.current;
      const cursor = cursorRef.current;
      if (!node || !cursor) return;
      const bounds = node.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      node.style.setProperty('--cursor-x', `${x}px`);
      node.style.setProperty('--cursor-y', `${y}px`);
      cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      cursor.classList.add('visible');
    };
    const hideCursor = () => cursorRef.current?.classList.remove('visible');
    window.addEventListener('pointermove', moveCursor, { passive: true });
    document.documentElement.addEventListener('mouseleave', hideCursor);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('pointermove', moveCursor);
      document.documentElement.removeEventListener('mouseleave', hideCursor);
    };
  }, []);

  return (
    <div ref={fieldRef} className="data-field" aria-hidden="true">
      {gridRef.current.map((row, rowIndex) => (
        <div className="data-row" key={rowIndex}>
          {row.map((character, columnIndex) => (
            <span key={columnIndex}>{character}</span>
          ))}
        </div>
      ))}
      <div ref={cursorRef} className="data-cursor">
        <div>{CURSOR_GLYPHS.map((glyph, index) => <span key={glyph} style={{ transform: `rotate(${index * 45}deg) translateY(-66px)` }}>{glyph}</span>)}</div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = window.setInterval(() => setStep((current) => (current + 1) % SHOWCASE_STEPS), SHOWCASE_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [cycle]);

  const moveShowcase = (direction: -1 | 1) => {
    setStep((current) => (current + direction + SHOWCASE_STEPS) % SHOWCASE_STEPS);
    setCycle((current) => current + 1);
  };

  return (
    <div className="landing-page">
    <div className="landing">
      <header className="landing-header">
        <div className="landing-brand"><Wordmark /><button className="landing-demo" onClick={() => { saveBrief(DEMO_BRIEF); navigate('/plan', { state: { brief: DEMO_BRIEF, run: Date.now() } }); }} title="Replays a Houston search scored by the CropFit model"><Play size={12} fill="currentColor" /> Demo</button></div>
        <nav>
          <button onClick={() => navigate('/model')}>How it works</button>
          <button onClick={() => navigate('/agriculture/urban')}>Urban</button>
          <button onClick={() => navigate('/sensors')}>Sensors</button>
        </nav>
      </header>

      <DataField />
      <div className="landing-fade" />

      <main className="landing-content">
        <p className="landing-eyebrow mono">ULTRAVIOLET · ROOFTOP AGRICULTURE</p>
        <h1><span>Find the space.</span><span>Grow the space.</span></h1>
        <p className="landing-lede">
          Search aerial imagery for growing space, review roof outlines,
          and check sunlight across seasons.
        </p>
        <div className="landing-actions">
          <button className="primary" onClick={() => navigate('/start')}>Get started →</button>
          <button className="secondary" onClick={() => navigate('/agriculture/urban')}>Search rooftops directly</button>
        </div>
      </main>
      <aside className="landing-showcase">
        <Showcase active={step} />
        <div className="landing-showcase-controls">
          <button onClick={() => moveShowcase(-1)} aria-label="Show previous dashboard feature"><ChevronLeft size={20} /></button>
          <span className="mono">{String(step + 1).padStart(2, '0')} / {String(SHOWCASE_STEPS).padStart(2, '0')}</span>
          <button onClick={() => moveShowcase(1)} aria-label="Show next dashboard feature"><ChevronRight size={20} /></button>
        </div>
      </aside>
    </div>
    </div>
  );
}
