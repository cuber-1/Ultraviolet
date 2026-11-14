import { useMemo, useState } from 'react';
import { ArrowLeft, ArrowUpRight, ChevronDown, Heart, Map as MapIcon, MapPin, Search, SlidersHorizontal } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import { imagePath, SITES, type Market } from '../data/sites';
import './ListingsPage.css';

export default function ListingsPage() {
  const navigate = useNavigate();
  const [market, setMarket] = useState<'All' | Market>('All');
  const [query, setQuery] = useState('');
  const [saved, setSaved] = useState<string[]>([]);

  const visibleSites = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return SITES.filter((site) => {
      const matchesMarket = market === 'All' || site.city === market;
      const matchesQuery = !normalized || [site.address, site.city, site.state, site.id, site.listing]
        .join(' ').toLowerCase().includes(normalized);
      return matchesMarket && matchesQuery;
    });
  }, [market, query]);

  const toggleSaved = (siteId: string) => {
    setSaved((current) => current.includes(siteId)
      ? current.filter((id) => id !== siteId)
      : [...current, siteId]);
  };

  return (
    <div className="marketplace-page">
      <header className="marketplace-header">
        <button className="icon-button" onClick={() => navigate('/')} aria-label="Back to landing page"><ArrowLeft size={18} /></button>
        <Wordmark />
        <div className="header-search">
          <MapPin size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="City, address, or CoStar ID" aria-label="Search land listings" />
          <button aria-label="Search"><Search size={17} /></button>
        </div>
        <div className="marketplace-header-actions">
          <button className="map-link" onClick={() => navigate('/map')}><MapIcon size={16} /> Map</button>
          <button className="saved-link"><Heart size={17} /> Saved <span>{saved.length}</span></button>
        </div>
      </header>

      <main className="marketplace-main">
        <section className="results-heading">
          <div>
            <p className="eyebrow mono">VEXCEL-VERIFIED SHORTLIST</p>
            <h1>Land opportunities</h1>
            <p>Browse parcel facts and five aerial perspectives for every candidate site.</p>
          </div>
          <div className="heading-stat"><strong>{visibleSites.length}</strong><span className="mono">PROPERTIES</span></div>
        </section>

        <section className="filter-bar" aria-label="Listing filters">
          <div className="market-filters">
            {(['All', 'Houston', 'Los Angeles'] as const).map((option) => (
              <button key={option} className={market === option ? 'active' : ''} onClick={() => setMarket(option)}>{option}</button>
            ))}
          </div>
          <button className="filter-button"><SlidersHorizontal size={15} /> Filters</button>
          <button className="sort-button">Sort: Recommended <ChevronDown size={14} /></button>
        </section>

        <section className="property-grid">
          {visibleSites.map((site) => (
            <article className="property-card" key={site.id} onClick={() => navigate(`/listings/${site.id}`)}>
              <div className="property-image">
                <img src={imagePath(site.id, 'ortho_parcel.jpg')} alt={`Parcel outlined in Vexcel imagery at ${site.address}`} />
                <span className="image-count mono">1 / 5 · VEXCEL</span>
                <button
                  className={`save-button ${saved.includes(site.id) ? 'saved' : ''}`}
                  aria-label={saved.includes(site.id) ? 'Remove from saved' : 'Save property'}
                  onClick={(event) => { event.stopPropagation(); toggleSaved(site.id); }}
                ><Heart size={18} fill={saved.includes(site.id) ? 'currentColor' : 'none'} /></button>
              </div>
              <div className="property-card-content">
                <div className="property-card-topline"><span>{site.listing}</span><span className="mono">ID {site.id}</span></div>
                <div className="property-title-row">
                  <div><h2>{site.address}</h2><p><MapPin size={13} /> {site.city}, {site.state}</p></div>
                  <div className="property-acres"><strong>{site.acres}</strong><span>acres</span></div>
                </div>
                <p className="property-summary">{site.summary}</p>
                <div className="property-card-footer">
                  <div><span className="mono">LAND USE</span><strong>{site.use}</strong></div>
                  <button>View property <ArrowUpRight size={15} /></button>
                </div>
              </div>
            </article>
          ))}
        </section>

        {visibleSites.length === 0 && (
          <div className="empty-state"><h2>No properties found</h2><p>Try another city, address, or property ID.</p><button onClick={() => { setQuery(''); setMarket('All'); }}>Clear search</button></div>
        )}
      </main>
    </div>
  );
}
