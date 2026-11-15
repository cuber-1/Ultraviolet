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
      <aside className="cropfit-summary"><div className="cropfit-score"><Sprout /><strong>{Math.round(best?.historicalMedian ?? prediction.score)}</strong><span>RELIABLE MONTH FIT</span></div><dl><div><dt>Risk-adjusted start</dt><dd>{reliableMonth}</dd></div><div><dt>Historical success</dt><dd>{prediction.plantingReliability ? `${Math.round(prediction.plantingReliability.successRate * 100)}% / ${prediction.plantingReliability.years} yr` : 'Not available'}</dd></div>{prediction.observedYieldEvidence && <div><dt>USDA county history</dt><dd>{Math.round(prediction.observedYieldEvidence.meanPercentile * 100)}th pct · {prediction.observedYieldEvidence.county}</dd></div>}<div><dt>Screening confidence</dt><dd>{Math.round(prediction.confidence * 100)}%</dd></div><div><dt>Crop cycle</dt><dd>{Math.round(prediction.growingDays.min)}–{Math.round(prediction.growingDays.max)} days</dd></div><div><dt>Profile</dt><dd><em>{prediction.profile.scientific_name}</em></dd></div></dl><div className="cropfit-limit"><span>LIMITING SIGNALS</span>{prediction.limitingFactors.map((item) => <p key={item.factor}><b>{label(item.factor)}</b><i><span style={{ width: `${item.score}%` }} /></i><strong>{Math.round(item.score)}</strong></p>)}</div></aside>
      <div className="cropfit-chart"><div className="cropfit-chart-title"><span><BarChart3 /> 10-year planting reliability</span><small>Bar = median fit · band = 2015–2024 p10–p90</small></div><div className="cropfit-bars">{prediction.monthlyCurve.map((month) => <div className={month.month === best?.month ? 'best' : ''} key={month.month}><div className="cropfit-bar-track">{month.historicalP10 !== undefined && month.historicalP90 !== undefined && <span className="cropfit-history" style={{ bottom: `${month.historicalP10}%`, height: `${Math.max(2, month.historicalP90 - month.historicalP10)}%` }} />}<i style={{ height: `${Math.max(2, month.historicalMedian ?? month.score)}%` }} /></div><strong>{Math.round(month.historicalMedian ?? month.score)}</strong><small>{month.month}</small><em>{month.reliability === undefined ? `${month.temperatureC.toFixed(0)}°` : `${Math.round(month.reliability * 100)}%`}</em></div>)}</div><div className="cropfit-window"><span>RELIABLE WINDOW</span><strong>{prediction.suitableMonths.join(' · ') || 'No robust month found'}</strong><p>{prediction.disclaimer}</p></div>{prediction.observedYieldEvidence && <YieldHistoryChart evidence={prediction.observedYieldEvidence} />}</div>
    </div>}
  </section>;
}

function YieldHistoryChart({ evidence }: { evidence: NonNullable<CropFitPrediction['observedYieldEvidence']> }) {
  const width = 560; const height = 154; const left = 30; const right = 12; const top = 24; const bottom = 28;
  const chartHeight = height - top - bottom; const band = (width - left - right) / Math.max(1, evidence.history.length);
  const y = (percentile: number) => top + (1 - percentile) * chartHeight;
  const prior = evidence.observedYieldPrior;
  return <section className="cropfit-yield"><header><div><span>OBSERVED USDA COUNTY PRIOR</span><strong>{evidence.county}, {evidence.state} · {evidence.distanceKm.toFixed(0)} km away</strong></div><em>{prior ? `EXPECTED ${Math.round(prior.expectedPercentile * 100)}TH · 80% ${prior.intervalMethod === 'spatial-transfer-conformal' ? 'TRANSFER ' : ''}BAND ${Math.round(prior.interval80[0] * 100)}–${Math.round(prior.interval80[1] * 100)}TH` : `${Math.round(evidence.p10Percentile * 100)}–${Math.round(evidence.p90Percentile * 100)}th historical range`}</em></header>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Published ${evidence.county} yield history`}>
      {prior && <><rect x={left} y={y(prior.interval80[1])} width={width - left - right} height={y(prior.interval80[0]) - y(prior.interval80[1])} className="yield-prior-band"><title>Calibrated 80% future county interval: {Math.round(prior.interval80[0] * 100)}th–{Math.round(prior.interval80[1] * 100)}th percentile</title></rect><line x1={left} x2={width - right} y1={y(prior.expectedPercentile)} y2={y(prior.expectedPercentile)} className="yield-prior-line" /></>}
      <line x1={left} x2={width - right} y1={y(.5)} y2={y(.5)} className="yield-midline" /><text x={left - 5} y={y(.5) + 3} textAnchor="end">50</text>
      {evidence.history.map((item, index) => { const x = left + index * band + band * .2; const barWidth = band * .6; const barTop = y(item.percentile); return <g key={item.year}>
        <rect x={x} y={barTop} width={barWidth} height={top + chartHeight - barTop} className="yield-bar"><title>{item.year}: {item.yieldBushelsPerAcre.toFixed(1)} bu/acre · {Math.round(item.percentile * 100)}th percentile</title></rect>
        <text x={x + barWidth / 2} y={Math.max(top - 5, barTop - 5)} textAnchor="middle" className="yield-value">{Math.round(item.yieldBushelsPerAcre)}</text><text x={x + barWidth / 2} y={height - 8} textAnchor="middle" className="yield-year">{String(item.year).slice(2)}</text>
      </g>; })}
    </svg><footer><span>BAR = OBSERVED YEAR</span><span>LABEL = PUBLISHED BU/ACRE</span>{prior && <span>BAND = CALIBRATED 80% RANGE · {Math.round(prior.interval80[0] * 100)}–{Math.round(prior.interval80[1] * 100)}TH</span>}<p>{evidence.disclaimer}</p></footer>
  </section>;
}
