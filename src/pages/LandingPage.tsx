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

  return (
    <div className="landing">
      <header className="landing-header">
        <Wordmark />
        <nav>
          <button onClick={() => navigate('/agriculture/urban')}>Urban</button>
          <button onClick={() => navigate('/agriculture/rural')}>Rural</button>
          <button onClick={() => navigate('/listings')}>Listings</button>
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
          <button className="primary" onClick={() => navigate('/agriculture/urban')}>Explore urban rooftops →</button>
          <button className="secondary" onClick={() => navigate('/listings')}>Browse listings</button>
        </div>
      </main>
    </div>
  );
}
