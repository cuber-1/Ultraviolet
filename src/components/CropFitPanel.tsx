import { useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, CircleAlert, Droplets, LoaderCircle, Sprout } from 'lucide-react';
import { predictCropFit, type CropFitPrediction } from '../services/cropfit';
import type { RuralClimateResult } from '../services/rural';

const CROPS = ['strawberry', 'tomato', 'lettuce', 'spinach', 'pepper', 'cucumber', 'corn', 'soybean', 'wheat', 'rice', 'potato', 'okra'];
const label = (value: string) => value.replace('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

export default function CropFitPanel({ locations }: { locations: RuralClimateResult[] }) {
  const [crop, setCrop] = useState('strawberry');
  const [selected, setSelected] = useState(0);
  const [soilPh, setSoilPh] = useState(6.5);
  const [irrigated, setIrrigated] = useState(true);
  const [prediction, setPrediction] = useState<CropFitPrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const location = locations[Math.min(selected, Math.max(0, locations.length - 1))];
  useEffect(() => {
    if (!location) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(null);
    predictCropFit({ crop, latitude: location.lat, longitude: location.lon, soilPh, irrigated }, controller.signal)
      .then(setPrediction)
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'CropFit failed.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [crop, irrigated, location, soilPh]);
  const reliableMonth = prediction?.bestReliablePlantingMonth || prediction?.bestPlantingMonth;
  const best = useMemo(() => prediction?.monthlyCurve.find((month) => month.month === reliableMonth), [prediction, reliableMonth]);
  return <section className="cropfit-lab">
    <header><div><span className="mono">03 / CROPFIT MODEL</span><h2>When could this crop work?</h2><p>Monthly suitability from climate, crop requirements, water assumptions, and soil pH.</p></div><div className="cropfit-controls"><label>Crop<select value={crop} onChange={(event) => setCrop(event.target.value)}>{CROPS.map((item) => <option key={item}>{item}</option>)}</select></label><label>Region<select value={selected} onChange={(event) => setSelected(Number(event.target.value))}>{locations.map((item, index) => <option key={item.query} value={index}>{item.name}</option>)}</select></label><label>Soil pH<input type="number" min="2.5" max="10.5" step=".1" value={soilPh} onChange={(event) => setSoilPh(Number(event.target.value))} /></label><label className="cropfit-check"><input type="checkbox" checked={irrigated} onChange={(event) => setIrrigated(event.target.checked)} /><Droplets /> Irrigated</label></div></header>
    {loading && <div className="cropfit-state"><LoaderCircle className="spin" /> Running 12 seasonal scenarios…</div>}
    {error && <div className="cropfit-state error"><CircleAlert /> {error}</div>}
    {!loading && !error && prediction && <div className="cropfit-body">
      <aside className="cropfit-summary"><div className="cropfit-score"><Sprout /><strong>{Math.round(best?.historicalMedian ?? prediction.score)}</strong><span>RELIABLE MONTH FIT</span></div><dl><div><dt>Risk-adjusted start</dt><dd>{reliableMonth}</dd></div><div><dt>Historical success</dt><dd>{prediction.plantingReliability ? `${Math.round(prediction.plantingReliability.successRate * 100)}% / ${prediction.plantingReliability.years} yr` : 'Not available'}</dd></div><div><dt>Screening confidence</dt><dd>{Math.round(prediction.confidence * 100)}%</dd></div><div><dt>Crop cycle</dt><dd>{Math.round(prediction.growingDays.min)}–{Math.round(prediction.growingDays.max)} days</dd></div><div><dt>Profile</dt><dd><em>{prediction.profile.scientific_name}</em></dd></div></dl><div className="cropfit-limit"><span>LIMITING SIGNALS</span>{prediction.limitingFactors.map((item) => <p key={item.factor}><b>{label(item.factor)}</b><i><span style={{ width: `${item.score}%` }} /></i><strong>{Math.round(item.score)}</strong></p>)}</div></aside>
      <div className="cropfit-chart"><div className="cropfit-chart-title"><span><BarChart3 /> 10-year planting reliability</span><small>Bar = median fit · band = 2015–2024 p10–p90</small></div><div className="cropfit-bars">{prediction.monthlyCurve.map((month) => <div className={month.month === best?.month ? 'best' : ''} key={month.month}><div className="cropfit-bar-track">{month.historicalP10 !== undefined && month.historicalP90 !== undefined && <span className="cropfit-history" style={{ bottom: `${month.historicalP10}%`, height: `${Math.max(2, month.historicalP90 - month.historicalP10)}%` }} />}<i style={{ height: `${Math.max(2, month.historicalMedian ?? month.score)}%` }} /></div><strong>{Math.round(month.historicalMedian ?? month.score)}</strong><small>{month.month}</small><em>{month.reliability === undefined ? `${month.temperatureC.toFixed(0)}°` : `${Math.round(month.reliability * 100)}%`}</em></div>)}</div><div className="cropfit-window"><span>RELIABLE WINDOW</span><strong>{prediction.suitableMonths.join(' · ') || 'No robust month found'}</strong><p>{prediction.disclaimer}</p></div></div>
    </div>}
  </section>;
}
