import { useState } from 'react';
import { ArrowLeft, ChevronRight, Heart, Layers3, MapPin, ScanSearch, Share2, X } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import { imagePath, IMAGERY_VIEWS, SITES, type ImageryView, type Site } from '../data/sites';
import './ListingDetailPage.css';

const ANALYSIS_LABELS = ['Structures', 'Vehicles', 'Tree cover', 'Solar panels', 'Standing water'];
const VIEWS = IMAGERY_VIEWS;

type AnalysisPanelProps = {
  site: Site;
  view: ImageryView;
  onClose: () => void;
};

function AnalysisPanel({ site, view, onClose }: AnalysisPanelProps) {
  const [selected, setSelected] = useState(['Structures', 'Tree cover']);
  const [prepared, setPrepared] = useState(false);

  const toggle = (label: string) => {
    setPrepared(false);
    setSelected((current) => current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label]);
  };

  return (
    <div className="analysis-scrim" role="presentation" onMouseDown={onClose}>
      <aside className="analysis-panel" role="dialog" aria-modal="true" aria-label="Overlay analysis setup" onMouseDown={(event) => event.stopPropagation()}>
        <div className="analysis-panel-header">
          <div><p className="mono">ANALYSIS WORKSPACE</p><h2>{view.label} view</h2></div>
          <button onClick={onClose} aria-label="Close analysis panel"><X size={19} /></button>
        </div>
        <img src={imagePath(site.id, view.filename)} alt={`${view.label} aerial view for analysis`} />
        <div className="analysis-copy">
          <p className="analysis-address">{site.address}</p>
          <p>Choose the objects or conditions the future Vexcel Elements pipeline should detect on this exact view.</p>
        </div>
        <div className="analysis-options">
          <span className="mono">DETECTION LABELS</span>
          {ANALYSIS_LABELS.map((label) => (
            <label key={label}>
              <input type="checkbox" checked={selected.includes(label)} onChange={() => toggle(label)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <button className="prepare-analysis" onClick={() => setPrepared(true)} disabled={selected.length === 0}>
          <ScanSearch size={17} /> Prepare overlay analysis
        </button>
        <div className={`analysis-status ${prepared ? 'prepared' : ''}`}>
          <span />
          <p>{prepared
            ? `Prepared for ${selected.join(', ')}. Connect the server-side /elements/detect call to execute.`
            : 'No model result has been generated. Imagery shown here is the original Vexcel extract.'}</p>
        </div>
      </aside>
    </div>
  );
}

export default function ListingDetailPage() {
  const navigate = useNavigate();
  const { siteId } = useParams();
  const site = SITES.find((candidate) => candidate.id === siteId);
  const [analysisView, setAnalysisView] = useState<ImageryView | null>(null);
  const [saved, setSaved] = useState(false);

  if (!site) {
    return <main className="missing-property"><h1>Property not found</h1><button onClick={() => navigate('/listings')}>Back to listings</button></main>;
  }

  const scrollToView = (viewId: string) => {
    document.getElementById(`view-${viewId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="detail-page">
      <header className="detail-header">
        <button className="detail-back" onClick={() => navigate('/listings')}><ArrowLeft size={17} /> All listings</button>
        <Wordmark />
        <div className="detail-header-actions">
          <button><Share2 size={16} /> Share</button>
          <button className={saved ? 'saved' : ''} onClick={() => setSaved(!saved)}><Heart size={16} fill={saved ? 'currentColor' : 'none'} /> {saved ? 'Saved' : 'Save'}</button>
        </div>
      </header>

      <main>
        <section className="detail-title">
          <div className="detail-breadcrumb mono"><button onClick={() => navigate('/listings')}>LAND LISTINGS</button><ChevronRight size={12} /><span>{site.city.toUpperCase()}</span><ChevronRight size={12} /><span>{site.id}</span></div>
          <div className="detail-title-row">
            <div><p className="detail-type">{site.listing}</p><h1>{site.address}</h1><p className="detail-location"><MapPin size={15} /> {site.city}, {site.state}</p></div>
            <div className="detail-acreage"><strong>{site.acres}</strong><span>acres</span></div>
          </div>
        </section>

        <section className="detail-gallery" aria-label="Property image gallery">
          <button className="gallery-primary" onClick={() => scrollToView('ortho')}>
            <img src={imagePath(site.id, 'ortho_parcel.jpg')} alt={`Top-down parcel view of ${site.address}`} />
            <span className="mono">ORTHO · PARCEL OUTLINE</span>
          </button>
          <div className="gallery-secondary">
            {VIEWS.slice(1).map((view) => (
              <button key={view.id} onClick={() => scrollToView(view.id)}>
                <img src={imagePath(site.id, view.filename)} alt={`${view.label} oblique view`} />
                <span className="mono">{view.label.toUpperCase()}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="detail-summary">
          <div className="detail-description"><p className="mono">PROPERTY OVERVIEW</p><h2>{site.headline}</h2><p>{site.summary}</p></div>
          <dl>
            <div><dt>CoStar Property ID</dt><dd>{site.id}</dd></div>
            <div><dt>Parcel</dt><dd>{site.parcel}</dd></div>
            <div><dt>Current signal</dt><dd>{site.use}</dd></div>
            <div><dt>Coordinates</dt><dd>{site.lat}, {site.lon}</dd></div>
          </dl>
        </section>

        <nav className="view-navigation" aria-label="Aerial view navigation">
          <div><Layers3 size={17} /><span>5 aerial views</span></div>
          {VIEWS.map((view) => <button key={view.id} onClick={() => scrollToView(view.id)}>{view.label}</button>)}
        </nav>

        <section className="view-stack">
          {VIEWS.map((view, index) => (
            <figure id={`view-${view.id}`} className="aerial-view" key={view.id}>
              <figcaption>
                <div><span className="view-number mono">{String(index + 1).padStart(2, '0')} / 05</span><h2>{view.label}</h2><p>{view.description}</p></div>
                <button onClick={() => setAnalysisView(view)}><ScanSearch size={17} /> Analyze overlay</button>
              </figcaption>
              <div className="aerial-image-wrap">
                <img src={imagePath(site.id, view.filename)} alt={`${view.label} Vexcel imagery of ${site.address}`} loading={index === 0 ? 'eager' : 'lazy'} />
                <span className="view-source mono">VEXCEL IMAGING · ORIGINAL EXTRACT</span>
                <button className="image-analysis-button" onClick={() => setAnalysisView(view)}><ScanSearch size={17} /> Analyze this view</button>
              </div>
            </figure>
          ))}
        </section>
      </main>

      {analysisView && <AnalysisPanel site={site} view={analysisView} onClose={() => setAnalysisView(null)} />}
    </div>
  );
}
