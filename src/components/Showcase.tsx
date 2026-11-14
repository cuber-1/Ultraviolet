import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Heart, X } from 'lucide-react';
import RoofPreview3D from './RoofPreview3D';
import { OptimalPointsChart } from './charts/DeepAgentCharts';
import { getRun, listRuns } from '../services/runs';
import type { Brief } from '../services/cropPlan';
import { briefCrops } from '../services/cropPlan';
import type { AgentComparison, SearchResult } from '../services/vexcel';
import './Showcase.css';

type DemoOutcome = { kind: 'urban'; brief: Brief; criteria: { dates: string[]; targetHours: number; targetAreaSqft: number }; comparison: AgentComparison; top: SearchResult[] };

// Drop the classification scatter image here to replace the live chart in step 2.
const CLASSIFICATION_IMAGE = '/showcase/ml-classification.png';
const fmt = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);

const STEPS = [
  { kicker: 'Roof geometry', title: 'See every obstacle.', body: 'Vexcel elevation data rebuilds each roof in 3D, flags vents, parapets, and HVAC units, and traces the shadows they cast through the day.' },
  { kicker: 'Crop model', title: 'Classified by the crop model.', body: 'CropFit scores how well your crops suit each site, and every roof lands in a class: Prime, Sun-limited, Climate-limited, or Weak.' },
  { kicker: 'Your shortlist', title: 'Swipe your shortlist.', body: 'The Deep Agent ranks the best roofs. Go through them one at a time, save the ones you like, and dig into sun, model, and calendar details.' },
];

/** Scroll-driven tour of the app's features on the home page, built from a stored demo run. */
export default function Showcase() {
  const navigate = useNavigate();
  const [active, setActive] = useState(0);
  const [demo, setDemo] = useState<DemoOutcome | null>(null);
  const [imageOk, setImageOk] = useState(true);
  const [seen3d, setSeen3d] = useState(false);
  const steps = useRef<Array<HTMLElement | null>>([]);
  const section = useRef<HTMLElement>(null);

  // Demo data: the first stored urban demo run (Neon), else any saved urban run.
  useEffect(() => {
    const controller = new AbortController();
    listRuns(controller.signal).then(async (runs) => {
      const pick = runs.find((run) => run.kind === 'urban' && run.demo) ?? runs.find((run) => run.kind === 'urban');
      if (!pick) return;
      const record = await getRun<DemoOutcome>(pick.id, controller.signal);
      if (record.outcome?.kind === 'urban') setDemo(record.outcome);
    }).catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Which step is in the middle of the screen.
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => { if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.step)); });
    }, { rootMargin: '-45% 0px -45% 0px' });
    steps.current.forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
  }, []);
  // Only start the 3D roof once the section is near the viewport.
  useEffect(() => {
    const node = section.current; if (!node) return;
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) setSeen3d(true); }, { rootMargin: '200px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const roof = demo?.top[0] ?? null;
  const crops = demo ? briefCrops(demo.brief).map(({ id, name }) => ({ id, name })) : [];
  const points = useMemo(() => {
    if (!demo) return [];
    const byId = new Map(demo.comparison.candidates.map((item) => [item.id, item]));
    return demo.comparison.simulations.flatMap((simulation, index) => {
      const result = byId.get(simulation.candidateId); if (!result) return [];
      const fitByCrop = Object.fromEntries(crops.map((crop) => { const p = demo.comparison.predictions?.find((item) => item.siteId === result.id && item.cropId === crop.id && item.source === 'ml'); return [crop.id, p ? p.suitability * 100 : null]; }));
      return [{ id: result.id, rank: index + 1, label: result.costar?.buildingName || `Roof ${index + 1}`, sunlitSqft: simulation.sharedAreaSqft, fitByCrop }];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo]);
  const cards = (demo?.top ?? []).slice(0, 3).map((result, index) => {
    const simulation = demo!.comparison.simulations.find((item) => item.candidateId === result.id);
    const preds = (demo!.comparison.predictions ?? []).filter((item) => item.siteId === result.id && item.source === 'ml');
    const fit = preds.length ? Math.round((preds.reduce((sum, item) => sum + item.suitability, 0) / preds.length) * 100) : null;
    return { id: result.id, image: result.imageryUrl, rank: index + 1, sun: simulation?.sharedAreaSqft ?? null, fit };
  });

  return <section className="sc" ref={section} aria-label="What Ultraviolet does">
    <div className="sc-steps">
      {STEPS.map((step, index) => <article key={step.title} ref={(node) => { steps.current[index] = node; }} data-step={index} className={active === index ? 'sc-step active' : 'sc-step'}>
        <span className="sc-kicker"><b>{String(index + 1).padStart(2, '0')}</b> {step.kicker}</span>
        <h2>{step.title}</h2>
        <p>{step.body}</p>
      </article>)}
      <div className="sc-end"><button onClick={() => navigate('/start')}>Get started <ArrowRight size={20} /></button></div>
    </div>

    <div className="sc-stage">
      <div className="sc-frame">
        <div className={`sc-layer${active === 0 ? ' on' : ''}`}>
          {roof && seen3d ? <RoofPreview3D result={roof} date={demo!.criteria.dates[0]} targetHours={demo!.criteria.targetHours} targetAreaSqft={demo!.criteria.targetAreaSqft} controls={false} /> : <div className="sc-wait">Loading a demo roof…</div>}
          <span className="sc-caption">Clean mode · measured obstacles in orange</span>
        </div>
        <div className={`sc-layer sc-chart${active === 1 ? ' on' : ''}`}>
          {imageOk ? <img src={CLASSIFICATION_IMAGE} alt="Crop-model classification scatter plot" onError={() => setImageOk(false)} />
            : points.length ? <OptimalPointsChart points={points} crops={crops} targetAreaSqft={demo!.criteria.targetAreaSqft} /> : <div className="sc-wait">Loading the crop model…</div>}
        </div>
        <div className={`sc-layer sc-deck${active === 2 ? ' on' : ''}`}>
          {cards.length ? cards.slice().reverse().map((card) => <figure key={card.id} className={`sc-card c${card.rank}`}>
            <img src={card.image} alt="" />
            <figcaption><span>Roof {card.rank}</span><strong>{card.sun === null ? '—' : `${fmt(card.sun)} ft²`}<small> in full sun</small></strong>{card.fit !== null && <em>Crop fit {card.fit}</em>}</figcaption>
          </figure>) : <div className="sc-wait">Loading a shortlist…</div>}
          {cards.length > 0 && <div className="sc-deck-actions"><span className="pass"><X size={24} /></span><span className="save"><Heart size={24} /></span></div>}
        </div>
      </div>
      <div className="sc-dots">{STEPS.map((step, index) => <i key={step.title} className={active === index ? 'on' : ''} />)}</div>
    </div>
  </section>;
}
