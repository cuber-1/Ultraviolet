import { useEffect, useRef, useState } from 'react';
import { geoGraticule10, geoOrthographic, geoPath } from 'd3-geo';
import L, { type LayerGroup, type Map as LeafletMap } from 'leaflet';
import { feature } from 'topojson-client';
import countriesTopology from 'world-atlas/countries-110m.json';
import 'leaflet/dist/leaflet.css';

const countryFeatures = feature(countriesTopology as never, countriesTopology.objects.countries as never);

type Scope = { name: string; lat: number; lon: number; radiusM: number };
type GlobePoint = { id: string; lat: number; lon: number; rank: number };

function project(lat: number, lon: number, centerLon: number, radius: number) {
  const phi = lat * Math.PI / 180;
  const lambda = (lon - centerLon) * Math.PI / 180;
  const visible = Math.cos(phi) * Math.cos(lambda) >= 0;
  return { x: radius + radius * Math.cos(phi) * Math.sin(lambda), y: radius - radius * Math.sin(phi), visible };
}

export default function SearchGlobe({ scope, points = [], onPointClick }: { scope: Scope; points?: GlobePoint[]; onPointClick?: (id: string) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapElementRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerLayerRef = useRef<LayerGroup | null>(null);
  const [rotation, setRotation] = useState(-95);
  const [zoom, setZoom] = useState(1);
  const drag = useRef<{ x: number; rotation: number } | null>(null);
  const markers = useRef<Array<{ id: string; x: number; y: number }>>([]);
  const hasResults = points.length > 0;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const size = canvas.clientWidth;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.scale(dpr, dpr);
    const radius = size * 0.43 * zoom;
    const center = size / 2;
    const gradient = context.createRadialGradient(center - radius * .3, center - radius * .35, radius * .1, center, center, radius);
    gradient.addColorStop(0, '#fff8ef');
    gradient.addColorStop(.72, '#f2b681');
    gradient.addColorStop(1, '#df6411');
    context.beginPath(); context.arc(center, center, radius, 0, Math.PI * 2); context.fillStyle = gradient; context.fill();
    context.save(); context.beginPath(); context.arc(center, center, radius, 0, Math.PI * 2); context.clip();
    const globeProjection = geoOrthographic().translate([center, center]).scale(radius).rotate([-rotation, 0]).clipAngle(90);
    const globePath = geoPath(globeProjection, context);
    context.beginPath(); globePath(countryFeatures); context.fillStyle = 'rgba(255,249,240,.55)'; context.fill('evenodd');
    context.beginPath(); globePath(geoGraticule10()); context.strokeStyle = 'rgba(123,62,19,.15)'; context.lineWidth = .75; context.stroke();
    context.beginPath(); globePath(countryFeatures); context.strokeStyle = 'rgba(91,44,14,.62)'; context.lineWidth = 1.05; context.lineJoin = 'round'; context.stroke();
    const marker = project(scope.lat, scope.lon, rotation, radius);
    if (marker.visible) {
      const x = marker.x + center - radius; const y = marker.y + center - radius;
      context.beginPath(); context.arc(x, y, 15, 0, Math.PI * 2); context.fillStyle = 'rgba(232,93,4,.2)'; context.fill();
      context.beginPath(); context.arc(x, y, 5, 0, Math.PI * 2); context.fillStyle = '#e85d04'; context.fill();
    }
    markers.current = [];
    points.forEach((item) => {
      const point = project(item.lat, item.lon, rotation, radius);
      if (!point.visible) return;
      const x = point.x + center - radius; const y = point.y + center - radius;
      markers.current.push({ id: item.id, x, y });
      context.beginPath(); context.arc(x, y, 9, 0, Math.PI * 2); context.fillStyle = '#ffffff'; context.fill();
      context.fillStyle = '#b84400'; context.font = 'bold 8px system-ui'; context.textAlign = 'center'; context.textBaseline = 'middle'; context.fillText(String(item.rank), x, y + .5);
    });
    context.restore();
  }, [points, rotation, scope, zoom]);

  useEffect(() => {
    if (!hasResults || !mapElementRef.current || mapRef.current) return;
    const map = L.map(mapElementRef.current, { zoomControl: false, minZoom: 3, maxZoom: 19, attributionControl: true });
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    L.control.zoom({ position: 'bottomleft' }).addTo(map);
    markerLayerRef.current = L.layerGroup().addTo(map);
    map.setView([scope.lat, scope.lon], 12);
    return () => { map.remove(); mapRef.current = null; markerLayerRef.current = null; };
  }, [hasResults]);

  useEffect(() => {
    const map = mapRef.current;
    const markerLayer = markerLayerRef.current;
    if (!hasResults || !map || !markerLayer) return;
    markerLayer.clearLayers();
    const bounds = L.latLngBounds([]);
    let latitudeTotal = 0;
    let longitudeTotal = 0;
    points.forEach((item) => {
      latitudeTotal += item.lat;
      longitudeTotal += item.lon;
      bounds.extend([item.lat, item.lon]);
      const icon = L.divIcon({ className: 'roof-result-pin-shell', html: `<span class="roof-result-pin"><b>${item.rank}</b></span>`, iconSize: [38, 46], iconAnchor: [19, 45] });
      const marker = L.marker([item.lat, item.lon], { icon, title: `Open roof ${item.rank}`, keyboard: true }).addTo(markerLayer);
      marker.on('click', () => onPointClick?.(item.id));
    });
    const center: [number, number] = [latitudeTotal / points.length, longitudeTotal / points.length];
    requestAnimationFrame(() => {
      map.invalidateSize();
      const fittedZoom = points.length === 1 ? 17 : map.getBoundsZoom(bounds, false, L.point(88, 88));
      map.flyTo(center, Math.max(3, Math.min(17, fittedZoom - (points.length > 1 ? 1 : 0))), { duration: .85 });
    });
  }, [hasResults, onPointClick, points]);

  return <div className={`search-globe ${hasResults ? 'showing-results-map' : ''}`}>
    {hasResults ? <><div ref={mapElementRef} className="results-leaflet-map" aria-label={`Map centered on ${points.length} rooftop results`} /><div className="results-map-meta mono"><span>{points.length} ROOFS</span><strong>FIT TO RESULTS</strong></div></> : <canvas
      ref={canvasRef}
      aria-label="Rotatable world globe"
      onPointerDown={(event) => { drag.current = { x: event.clientX, rotation }; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { if (drag.current) setRotation(drag.current.rotation - (event.clientX - drag.current.x) * .45); }}
      onPointerUp={(event) => { const start = drag.current; drag.current = null; if (!start || Math.abs(event.clientX - start.x) > 4) return; const rect = event.currentTarget.getBoundingClientRect(); const scale = event.currentTarget.clientWidth / rect.width; const x = (event.clientX - rect.left) * scale; const y = (event.clientY - rect.top) * scale; const nearest = markers.current.find((item) => Math.hypot(item.x - x, item.y - y) < 14); if (nearest) onPointClick?.(nearest.id); }}
      onWheel={(event) => { event.preventDefault(); setZoom((value) => Math.min(1.12, Math.max(.72, value - event.deltaY * .001))); }}
    />}
  </div>;
}
