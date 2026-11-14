import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Building2, Check, Sprout, Tractor, Warehouse } from 'lucide-react';
import Wordmark from '../components/Wordmark';
import {
  ACRE_SQFT, CROPS, MONTH_LONG, MONTH_SHORT, RURAL_REGIONS, URBAN_AREAS,
  fetchMlCapabilities, formatArea, loadBrief, saveBrief, scaleForArea, type Brief, type MlCapabilities,
} from '../services/cropPlan';
import { briefKey, listRuns, savedTime, type SavedRunMeta } from '../services/runs';
import './OnboardingPage.css';

const SIZE_PRESETS = [
  { id: 'patio', label: 'Small roof', detail: 'Up to 1,500 ft²', areaSqft: 1_000, icon: Building2 },
  { id: 'roof', label: 'Large roof', detail: '1,500 – 20,000 ft²', areaSqft: 5_000, icon: Warehouse },
  { id: 'small-farm', label: 'Small farm', detail: '1 – 20 acres', areaSqft: 5 * ACRE_SQFT, icon: Sprout },
  { id: 'farm', label: 'Large farm', detail: '20+ acres', areaSqft: 80 * ACRE_SQFT, icon: Tractor },
] as const;

const STEPS = ['Space', 'Crops', 'Location', 'Timing', 'Review'] as const;
const MAX_CROPS = 4;

export default function OnboardingPage() {
  const navigate = useNavigate();
  const saved = useMemo(loadBrief, []);
  const [step, setStep] = useState(0);
  const [areaSqft, setAreaSqft] = useState(saved?.areaSqft ?? 5_000);
  const [unit, setUnit] = useState<'sqft' | 'acres'>(saved && saved.areaSqft >= ACRE_SQFT ? 'acres' : 'sqft');
  const [crops, setCrops] = useState<string[]>(saved?.crops ?? []);
  const [urbanArea, setUrbanArea] = useState<string>(saved?.urbanArea ?? URBAN_AREAS[0].value);
  const [ruralRegions, setRuralRegions] = useState<string[]>(saved?.ruralRegions ?? []);
  const [preferredMonth, setPreferredMonth] = useState(saved?.preferredMonth ?? new Date().getMonth());

  const scale = scaleForArea(areaSqft);
  const [caps, setCaps] = useState<MlCapabilities | null>(null);
  useEffect(() => { const controller = new AbortController(); void fetchMlCapabilities(controller.signal).then(setCaps); return () => controller.abort(); }, []);
  // Strict live mode: only crops the trained model scores natively can be chosen.
  const modelCrop = (id: string) => !caps?.supportedCrops || caps.supportedCrops.includes(id);
  const strictBlocked = (id: string) => Boolean(caps?.strict) && !modelCrop(id);
  const cropOptions = CROPS.filter((crop) => crop.scale === 'both' || crop.scale === scale);
  const chosenCrops = crops.filter((id) => cropOptions.some((crop) => crop.id === id) && !strictBlocked(id));
  const ready = [areaSqft > 0, chosenCrops.length > 0, scale === 'urban' ? Boolean(urbanArea) : ruralRegions.length > 0, true, true];
  // Each completed step fills a full share; answering the current step fills most of its share.
  const progress = step === STEPS.length - 1 ? 1 : Math.min(1, (step + (ready[step] ? .75 : .2)) / STEPS.length);

  const brief: Brief = { scale, areaSqft, crops: chosenCrops, urbanArea: scale === 'urban' ? urbanArea : undefined, ruralRegions: scale === 'rural' ? ruralRegions : undefined, preferredMonth };
  const unitValue = unit === 'acres' ? +(areaSqft / ACRE_SQFT).toFixed(2) : Math.round(areaSqft);
  const toggleCrop = (id: string) => setCrops((items) => items.includes(id) ? items.filter((item) => item !== id) : items.length >= MAX_CROPS ? items : [...items, id]);
  const toggleRegion = (id: string) => setRuralRegions((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]);
  const next = () => setStep((value) => Math.min(STEPS.length - 1, value + 1));
  const back = () => step === 0 ? navigate('/') : setStep((value) => value - 1);
  const start = () => { saveBrief(brief); navigate('/plan', { state: { brief, run: Date.now() } }); };
  const [savedMatch, setSavedMatch] = useState<SavedRunMeta | null>(null);
  const key = briefKey(brief);
  useEffect(() => {
    if (step !== STEPS.length - 1) return;
    const controller = new AbortController();
    listRuns(controller.signal).then((runs) => setSavedMatch(runs.find((item) => item.key === key && item.demo) ?? runs.find((item) => item.key === key) ?? null)).catch(() => setSavedMatch(null));
    return () => controller.abort();
  }, [step, key]);
  const openSaved = () => { if (!savedMatch) return; saveBrief(brief); navigate('/plan', { state: { brief, savedId: savedMatch.id } }); };

  return <div className="onboarding">
    <header className="onboarding-header">
      <button className="onboarding-icon-button" onClick={back} aria-label="Back"><ArrowLeft size={18} /></button>
      <Wordmark />
      <ol className="onboarding-steps" aria-label="Progress">
        {STEPS.map((label, index) => <li key={label} className={index === step ? 'current' : index < step ? 'done' : ''}><button disabled={index > step && !ready.slice(0, index).every(Boolean)} onClick={() => setStep(index)}>{index < step ? <Check size={11} /> : String(index + 1).padStart(2, '0')}<span>{label}</span></button></li>)}
      </ol>
    </header>
    <div className="onboarding-progress" role="progressbar" aria-label="Onboarding progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
      <i style={{ width: `${progress * 100}%` }} />
      <span>{Math.round(progress * 100)}% · {step < STEPS.length - 1 ? `${STEPS.length - 1 - step} ${STEPS.length - 1 - step === 1 ? 'step' : 'steps'} left` : 'Ready to search'}</span>
    </div>

    <main className="onboarding-body" key={step}>
      {step === 0 && <section>
        <p className="onboarding-kicker mono">01 · YOUR SPACE</p>
        <h1>How much space do you want to grow on?</h1>
        <p className="onboarding-lede">Rooftops under an acre search live aerial imagery. An acre or more compares farming regions.</p>
        <div className="size-grid">
          {SIZE_PRESETS.map(({ id, label, detail, areaSqft: preset, icon: Icon }) => <button key={id} className={Math.abs(areaSqft - preset) < 1 ? 'choice active' : 'choice'} onClick={() => { setAreaSqft(preset); setUnit(preset >= ACRE_SQFT ? 'acres' : 'sqft'); }}>
            <Icon size={22} /><strong>{label}</strong><span>{detail}</span>
          </button>)}
        </div>
        <div className="size-exact">
          <label>Exact size<input type="number" min={unit === 'acres' ? 0.1 : 50} step={unit === 'acres' ? 0.5 : 100} value={unitValue} onChange={(event) => { const value = Math.max(0, Number(event.target.value) || 0); setAreaSqft(unit === 'acres' ? value * ACRE_SQFT : value); }} /></label>
          <div className="unit-switch"><button className={unit === 'sqft' ? 'active' : ''} onClick={() => setUnit('sqft')}>ft²</button><button className={unit === 'acres' ? 'active' : ''} onClick={() => setUnit('acres')}>acres</button></div>
          <span className={`scale-pill ${scale}`}>{scale === 'urban' ? <Building2 size={14} /> : <Tractor size={14} />}{scale === 'urban' ? 'Urban rooftop search' : 'Rural region search'}</span>
        </div>
      </section>}

      {step === 1 && <section>
        <p className="onboarding-kicker mono">02 · CROPS</p>
        <h1>What do you want to grow?</h1>
        <p className="onboarding-lede">Pick up to {MAX_CROPS}. Each crop sets the sunlight the roof needs and the months it can grow.</p>
        <div className="crop-grid">
          {cropOptions.map((crop) => { const active = chosenCrops.includes(crop.id); return <button key={crop.id} className={active ? 'crop active' : 'crop'} onClick={() => toggleCrop(crop.id)} disabled={strictBlocked(crop.id) || (!active && chosenCrops.length >= MAX_CROPS)} title={strictBlocked(crop.id) ? 'Not scored by the trained CropFit model' : undefined}>
            <span className="crop-check">{active && <Check size={12} />}</span>
            <strong>{crop.name}</strong><small>{crop.note}</small>
            <span className="crop-facts mono">{crop.sunHours}H SUN · {crop.tempMinC}–{crop.tempMaxC}°C · {crop.growMonths} MO</span>
            {caps?.supportedCrops && <span className={modelCrop(crop.id) ? 'crop-model on' : 'crop-model'}>{modelCrop(crop.id) ? 'CropFit model' : caps.strict ? 'Not in CropFit' : 'Calendar estimate'}</span>}
          </button>; })}
        </div>
      </section>}

      {step === 2 && <section>
        <p className="onboarding-kicker mono">03 · LOCATION</p>
        <h1>{scale === 'urban' ? 'Which city should we search?' : 'Which regions should we compare?'}</h1>
        <p className="onboarding-lede">{scale === 'urban' ? 'These cities have live Vexcel aerial and elevation coverage.' : 'Pick one or more. Each region adds several farming towns to compare.'}</p>
        <div className="place-grid">
          {scale === 'urban'
            ? URBAN_AREAS.map((area) => <button key={area.id} className={urbanArea === area.value ? 'choice active' : 'choice'} onClick={() => setUrbanArea(area.value)}><Building2 size={20} /><strong>{area.label}</strong><span>{area.detail}</span></button>)
            : RURAL_REGIONS.map((region) => <button key={region.id} className={ruralRegions.includes(region.id) ? 'choice active' : 'choice'} onClick={() => toggleRegion(region.id)}><Sprout size={20} /><strong>{region.label}</strong><span>{region.detail}</span><small>{region.places.map((place) => place.split(',')[0]).join(' · ')}</small></button>)}
        </div>
      </section>}

      {step === 3 && <section>
        <p className="onboarding-kicker mono">04 · TIMING</p>
        <h1>When would you like to start?</h1>
        <p className="onboarding-lede">We find the first month on or after this one when your crops can go in, then check sunlight for that season.</p>
        <div className="month-grid">
          {MONTH_SHORT.map((month, index) => <button key={month} className={preferredMonth === index ? 'active' : ''} onClick={() => setPreferredMonth(index)}>{month}{index === new Date().getMonth() && <small>now</small>}</button>)}
        </div>
      </section>}

      {step === 4 && <section>
        <p className="onboarding-kicker mono">05 · REVIEW</p>
        <h1>{scale === 'urban' ? 'Ready to find your roof.' : 'Ready to find your region.'}</h1>
        <dl className="review-list">
          <div><dt>Space</dt><dd>{formatArea(areaSqft)} · {scale === 'urban' ? 'urban rooftop' : 'rural land'}</dd><button onClick={() => setStep(0)}>Edit</button></div>
          <div><dt>Crops</dt><dd>{chosenCrops.map((id) => CROPS.find((crop) => crop.id === id)?.name).join(', ')}</dd><button onClick={() => setStep(1)}>Edit</button></div>
          <div><dt>{scale === 'urban' ? 'City' : 'Regions'}</dt><dd>{scale === 'urban' ? URBAN_AREAS.find((area) => area.value === urbanArea)?.label : ruralRegions.map((id) => RURAL_REGIONS.find((region) => region.id === id)?.label).join(', ')}</dd><button onClick={() => setStep(2)}>Edit</button></div>
          <div><dt>Start</dt><dd>{MONTH_LONG[preferredMonth]} or later</dd><button onClick={() => setStep(3)}>Edit</button></div>
        </dl>
        <p className="onboarding-lede">{scale === 'urban'
          ? 'The Deep Agent searches live aerial imagery, checks property records, measures each roof’s height and obstructions, and simulates sunlight on your season’s dates. Expect one to three minutes.'
          : 'We read NASA monthly climate for each farming town and match it to your crops’ growing calendars. This takes a few seconds.'}</p>
      </section>}
    </main>

    <footer className="onboarding-footer">
      <span className="mono">{STEPS[step].toUpperCase()} · {step + 1} / {STEPS.length}</span>
      {step < STEPS.length - 1
        ? <button className="onboarding-next" disabled={!ready[step]} onClick={next}>Continue <ArrowRight size={16} /></button>
        : <div className="onboarding-final">{savedMatch && <button className="onboarding-saved" onClick={openSaved} title="Opens the saved result instantly without re-running">{savedMatch.demo ? 'Open demo result' : `Open saved result · ${savedTime(savedMatch.savedAt)}`}</button>}<button className="onboarding-next" onClick={start}>{scale === 'urban' ? 'Run Deep Agent' : 'Find regions'} <ArrowRight size={16} /></button></div>}
    </footer>
  </div>;
}
