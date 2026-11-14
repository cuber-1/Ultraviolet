import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CircleAlert, Droplets, LoaderCircle, MapPin, Search, Sun, ThermometerSun } from 'lucide-react';
import SearchGlobe from './SearchGlobe';
import { compareRuralLocations, type RuralClimateResult, type RuralComparison, type RuralGoal } from '../services/rural';

const STARTING_PLACES = 'Fresno, California; Yuma, Arizona; Yakima, Washington; Salinas, California; McAllen, Texas';

const goalLabels: Record<RuralGoal, string> = {
  balanced: 'Balanced growing climate',
  sun: 'High solar resource',
  'low-irrigation': 'Lower irrigation pressure',
};

export default function RuralExplorer() {
  const [places, setPlaces] = useState(STARTING_PLACES);
  const [goal, setGoal] = useState<RuralGoal>('balanced');
  const [comparison, setComparison] = useState<RuralComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const run = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const locations = places.split(/[;\n]/).map((place) => place.trim()).filter(Boolean);
    setLoading(true); setError(null);
    try { setComparison(await compareRuralLocations(locations, goal, controller.signal)); }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Rural comparison failed.'); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, [goal, places]);
  useEffect(() => { void run(); return () => requestRef.current?.abort(); }, []);
  const results = comparison?.results ?? [];
  const scope = useMemo(() => results.length ? {
    name: 'Compared regions',
    lat: results.reduce((sum, result) => sum + result.lat, 0) / results.length,
    lon: results.reduce((sum, result) => sum + result.lon, 0) / results.length,
    radiusM: 20_000,
  } : { name: 'United States', lat: 38.5, lon: -98.5, radiusM: 20_000 }, [results]);

  return <main className="rural-explorer">
    <section className="rural-commandbar">
      <div><span className="mono">RURAL REGION SCREENING</span><h1>Compare growing regions</h1><p>Start with climate evidence. Verify soil, water rights, and parcels before choosing land.</p></div>
      <form onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <Search />
        <textarea aria-label="Places to compare" value={places} onChange={(event) => setPlaces(event.target.value)} rows={2} />
        <label>Priority<select value={goal} onChange={(event) => setGoal(event.target.value as RuralGoal)}><option value="balanced">Balanced growing climate</option><option value="sun">High solar resource</option><option value="low-irrigation">Lower irrigation pressure</option></select></label>
        <button disabled={loading}>{loading ? <LoaderCircle className="spin" /> : 'Compare places'}</button>
      </form>
      <div className="rural-source-line"><span><i /> NASA POWER LIVE</span><span>OPEN-METEO GEOCODING</span><span>SOIL + PARCELS NOT ASSESSED</span></div>
    </section>
    <section className="rural-workbench">
      <div className="rural-map-panel"><div className="panel-label"><span className="mono">01 / REGIONS</span><span>{results.length ? 'Ranked locations · map fit to results' : 'Loading regional evidence'}</span></div><SearchGlobe scope={scope} onScopeChange={() => {}} points={results.map((result, index) => ({ id: result.query, lat: result.lat, lon: result.lon, rank: index + 1 }))} presets={[]} /></div>
      <aside className="rural-results">
        <header><div><span className="mono">02 / CLIMATE FIT</span><h2>{loading ? 'Reading climate…' : results.length ? `${results.length} regions` : 'No results'}</h2></div><span>{goalLabels[goal]}</span></header>
        {error && <div className="rural-error"><CircleAlert /><span>{error}</span></div>}
        {!error && results.map((result, index) => <RuralResult key={result.query} result={result} rank={index + 1} />)}
        {comparison?.errors.map((item) => <div className="rural-missing" key={item.location}><CircleAlert /><span><strong>{item.location}</strong>{item.error}</span></div>)}
      </aside>
    </section>
    <section className="rural-method"><div><span className="mono">WHAT THIS RANKING MEANS</span><h2>Regional climate first.<br />Land diligence next.</h2></div><p>The score transparently combines annual solar resource, average growing temperature, and precipitation according to the selected priority. It is a regional screen—not a farm recommendation. USDA soil capability, irrigation supply and rights, flood risk, zoning, ownership, price, and an on-site assessment still determine whether a parcel works.</p></section>
  </main>;
}

function RuralResult({ result, rank }: { result: RuralClimateResult; rank: number }) {
  return <article className="rural-result">
    <div className="rural-rank"><span>#{rank}</span><strong>{result.score}</strong><small>CLIMATE FIT</small></div>
    <div className="rural-result-main"><div className="rural-result-title"><div><h3>{result.name}</h3><p><MapPin /> {result.region}</p></div><span>{result.lat.toFixed(3)}, {result.lon.toFixed(3)}</span></div>
      <div className="rural-metrics"><div><Sun /><span><small>SOLAR</small><strong>{result.solarMjM2Day.toFixed(1)}</strong><em>MJ/m²/day</em></span></div><div><Droplets /><span><small>PRECIPITATION</small><strong>{result.precipitationMmDay.toFixed(2)}</strong><em>mm/day</em></span></div><div><ThermometerSun /><span><small>MEAN TEMP</small><strong>{result.temperatureC.toFixed(1)}°</strong><em>Celsius</em></span></div></div>
      <p className="rural-reason">{result.reason}</p><div className="rural-evidence"><span>NASA POWER</span><span>{result.period}</span><span className="unknown">SOIL UNKNOWN</span><span className="unknown">PARCEL UNKNOWN</span></div>
    </div>
  </article>;
}
