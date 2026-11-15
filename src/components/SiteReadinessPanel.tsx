import { CheckCircle2, CircleHelp, ShieldCheck, TriangleAlert, XCircle } from 'lucide-react';
import { assessSiteReadiness, type ReadinessFlag, type ReadinessTone } from '../services/siteReadiness';
import type { SearchResult, SunlightEvidence } from '../services/vexcel';

const META: Record<ReadinessTone, { label: string; icon: typeof CheckCircle2 }> = {
  green: { label: 'Green flag', icon: CheckCircle2 },
  caution: { label: 'Caution', icon: TriangleAlert },
  red: { label: 'Red flag', icon: XCircle },
  unknown: { label: 'Verify', icon: CircleHelp },
};

function Flag({ flag }: { flag: ReadinessFlag }) {
  const Icon = META[flag.tone].icon;
  return <article className={`readiness-flag ${flag.tone}`} title={`${META[flag.tone].label}${flag.priority === 'high' ? ' · high priority' : ''}: ${flag.detail}`}>
    <Icon size={17} />
    <div><strong>{flag.label}</strong><p>{flag.detail}</p></div>
  </article>;
}

export default function SiteReadinessPanel({ result, simulation, targetAreaSqft }: { result: SearchResult; simulation: SunlightEvidence | null | undefined; targetAreaSqft: number }) {
  const readiness = assessSiteReadiness(result, simulation, targetAreaSqft);
  const green = readiness.flags.filter((flag) => flag.tone === 'green');
  const red = readiness.flags.filter((flag) => flag.tone === 'red');
  const rankPriority = { high: 0, medium: 1, low: 2 } as const;
  const verify = readiness.flags.filter((flag) => flag.tone === 'caution' || flag.tone === 'unknown').sort((a, b) => rankPriority[a.priority] - rankPriority[b.priority]);
  return <main className="readiness-page">
    <header className="readiness-head">
      <div><span className="das-label"><ShieldCheck size={16} /> Site readiness</span><h2>What looks promising, and what could stop the project</h2><p>Screened from Vexcel, CoStar and the sunlight model. Unknowns stay visible instead of being scored as safe.</p></div>
      <div className="readiness-summary">
        <strong>{readiness.reviewed}<small> / {readiness.flags.length}</small></strong>
        <span>checks backed by data</span>
        <div><i className="green">{readiness.counts.green} green</i><i className="red">{readiness.counts.red} red</i><i className="unknown">{readiness.counts.caution + readiness.counts.unknown} review</i></div>
      </div>
    </header>
    <div className="readiness-columns">
      <section><h3><CheckCircle2 size={18} /> Green flags <span>{green.length}</span></h3>{green.length ? green.map((flag) => <Flag key={flag.id} flag={flag} />) : <p className="readiness-empty">No green flags have enough evidence yet.</p>}</section>
      <section><h3><XCircle size={18} /> Potential red flags <span>{red.length}</span></h3>{red.length ? red.map((flag) => <Flag key={flag.id} flag={flag} />) : <p className="readiness-empty">No red flags in the available data.</p>}</section>
      <section><h3><CircleHelp size={18} /> Needs verification <span>{verify.length}</span></h3>{verify.map((flag) => <Flag key={flag.id} flag={flag} />)}</section>
    </div>
    <footer className="readiness-disclaimer"><TriangleAlert size={16} /><span>Early due diligence, not structural, fire-code, zoning or food-safety approval. Every roof still needs an engineer and a code review before building.</span></footer>
  </main>;
}
