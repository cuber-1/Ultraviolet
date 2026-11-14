import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import './LandingPage.css';

const CHARS = '·∿~=+−|/\\.:,;!?@#$%^&*()[]{}01<>≈≡∂∑∏√±×÷∞∠∆∇⊕⊗◦●○◆◇▲△▷▻';

function buildGrid(columns: number, rows: number): string[][] {
  return Array.from({ length: rows }, () =>
    Array.from({ length: columns }, () => CHARS[Math.floor(Math.random() * CHARS.length)]),
  );
}

function DataField() {
  const fieldRef = useRef<HTMLDivElement>(null);
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

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frameRef.current);
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
    </div>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const date = time.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const clock = time.toLocaleTimeString('en-GB', { hour12: false });

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="brand-lockup">
          <Wordmark />
          <span className="mono">ROOFTOP AGRICULTURE</span>
        </div>
        <nav>
          <button onClick={() => navigate('/agriculture/urban')}>Urban Agriculture</button>
          <button onClick={() => navigate('/agriculture/rural')}>Rural Agriculture</button>
          <button onClick={() => navigate('/listings')}>Listings</button>
          <span className="mono">{clock} LOCAL</span>
        </nav>
      </header>

      <DataField />
      <div className="landing-fade" />

      <aside className="sample-summary" aria-label="Current sample summary">
        <div><strong>ON</strong><span className="mono">VEXCEL SEARCH</span></div>
        <div><strong>30M</strong><span className="mono">SUN SAMPLING</span></div>
        <div><strong>2D</strong><span className="mono">SEASONAL OVERLAP</span></div>
      </aside>

      <main className="landing-content">
        <h1><span>Find the space.</span><span>Grow the city.</span></h1>
        <div className="landing-bottom">
          <div>
            <p className="landing-meta mono">VEXCEL AERIAL × SUNLIGHT · {date}</p>
            <p>Search aerial imagery for growing space,<br />review roof outlines, and check sunlight across seasons.</p>
          </div>
          <div className="landing-actions">
            <button onClick={() => navigate('/agriculture/urban')}>Explore urban rooftops →</button>
            <span className="mono">URBAN AVAILABLE · RURAL NOT YET COVERED</span>
          </div>
        </div>
      </main>
    </div>
  );
}
