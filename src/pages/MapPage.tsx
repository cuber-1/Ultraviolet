import { useEffect, useRef, useState } from 'react';
import L, { type Map as LeafletMap } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowLeft, ArrowUpRight, Building2, Images, List, MapPin, ScanSearch } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Wordmark from '../components/Wordmark';
import { imagePath, SITES, type Market } from '../data/sites';
import './MapPage.css';

const MARKET_CENTERS: Record<Market, [number, number]> = {
  Houston: [29.9717, -95.5587],
  'Los Angeles': [33.997, -118.33],
};

export default function MapPage() {
  const navigate = useNavigate();
  const mapElementRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const [selectedId, setSelectedId] = useState(SITES[0].id);
  const selectedSite = SITES.find((site) => site.id === selectedId) ?? SITES[0];

  useEffect(() => {
    if (!mapElementRef.current || mapRef.current) return;

    const map = L.map(mapElementRef.current, { zoomControl: false, minZoom: 3 });
    mapRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    const bounds = L.latLngBounds([]);
    SITES.forEach((site, index) => {
      const marketIndex = SITES.filter((candidate) => candidate.city === site.city).findIndex((candidate) => candidate.id === site.id);
      const offsetDirection = marketIndex === 0 ? 'left' : 'right';
      const icon = L.divIcon({
        className: `land-map-marker-shell marker-offset-${offsetDirection}`,
        html: `<span class="land-map-marker"><b>${index + 1}</b><i>${site.acres} ac</i></span>`,
        iconSize: [78, 42],
        iconAnchor: offsetDirection === 'left' ? [78, 42] : [0, 42],
      });

      const marker = L.marker([site.lat, site.lon], { icon, title: site.address }).addTo(map);
      marker.on('click', () => setSelectedId(site.id));
      bounds.extend([site.lat, site.lon]);
    });

    map.fitBounds(bounds, { padding: [80, 80] });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const focusSite = (siteId: string) => {
    const site = SITES.find((candidate) => candidate.id === siteId);
    if (!site) return;
    setSelectedId(site.id);
    mapRef.current?.flyTo([site.lat, site.lon], 16, { duration: 0.8 });
  };

  const focusMarket = (market: Market) => {
    const zoom = market === 'Houston' ? 13 : 11;
    mapRef.current?.flyTo(MARKET_CENTERS[market], zoom, { duration: 0.9 });
  };

  return (
    <div className="map-page">
      <header className="map-header">
        <button className="map-back" onClick={() => navigate('/')} aria-label="Back to landing page"><ArrowLeft size={18} /></button>
        <Wordmark />
        <div className="map-title"><span className="mono">DEMO MAP</span><strong>4 candidate properties</strong></div>
        <div className="map-market-actions">
          <button onClick={() => focusMarket('Houston')}>Houston <span>2</span></button>
          <button onClick={() => focusMarket('Los Angeles')}>Los Angeles <span>2</span></button>
        </div>
        <button className="list-view-button" onClick={() => navigate('/listings')}><List size={16} /> List view</button>
      </header>

      <main className="map-workspace">
        <aside className="map-sidebar">
          <div className="map-sidebar-heading">
            <p className="mono">LAND INTELLIGENCE</p>
            <h1>Explore the four sites</h1>
            <p>Select a property to inspect its Vexcel imagery and open the full analysis workspace.</p>
          </div>

          <div className="map-listings">
            {SITES.map((site, index) => (
              <button key={site.id} className={`map-listing-card ${selectedId === site.id ? 'active' : ''}`} onClick={() => focusSite(site.id)}>
                <img src={imagePath(site.id, 'ortho_parcel.jpg')} alt="" />
                <span className="map-card-number mono">{String(index + 1).padStart(2, '0')}</span>
                <span className="map-card-copy">
                  <strong>{site.address}</strong>
                  <span><MapPin size={12} /> {site.city}, {site.state}</span>
                  <small>{site.acres} acres · {site.use}</small>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="map-stage" aria-label="Interactive map of candidate land sites">
          <div ref={mapElementRef} className="leaflet-map" />
          <div className="map-legend mono"><span><i className="houston-dot" /> HOUSTON · 2</span><span><i className="la-dot" /> LOS ANGELES · 2</span></div>

          <article className="map-selection-card">
            <div className="selection-image">
              <img src={imagePath(selectedSite.id, 'ortho_parcel.jpg')} alt={`Vexcel aerial view of ${selectedSite.address}`} />
              <span className="mono"><Images size={13} /> 5 VEXCEL VIEWS</span>
            </div>
            <div className="selection-copy">
              <p className="mono">SELECTED PROPERTY · {selectedSite.id}</p>
              <h2>{selectedSite.address}</h2>
              <span><MapPin size={13} /> {selectedSite.city}, {selectedSite.state}</span>
              <div className="selection-facts">
                <div><Building2 size={15} /><span><small>LAND USE</small>{selectedSite.use}</span></div>
                <div><strong>{selectedSite.acres}</strong><span><small>SIZE</small>acres</span></div>
              </div>
              <button onClick={() => navigate(`/listings/${selectedSite.id}`)}><ScanSearch size={16} /> Open imagery & analysis <ArrowUpRight size={15} /></button>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
