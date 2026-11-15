import type { ReactNode } from 'react';

/** Google Maps search URL: the street address when we have one, otherwise the exact roof coordinates. */
export function googleMapsUrl(lat: number, lon: number, address?: string | null) {
  const text = address?.split(' · ')[0]?.trim();
  const query = text && /\d/.test(text) && !/^-?\d+\.\d+,\s*-?\d+\.\d+$/.test(text) ? text : `${lat.toFixed(6)},${lon.toFixed(6)}`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/** An address that opens Google Maps in a new tab. Stops pointer events so it works inside swipeable cards. */
export default function MapsLink({ lat, lon, address, children, className }: { lat: number; lon: number; address?: string | null; children?: ReactNode; className?: string }) {
  return <a className={`maps-link ${className ?? ''}`.trim()} href={googleMapsUrl(lat, lon, address)} target="_blank" rel="noreferrer" title="Open in Google Maps"
    onPointerDown={(event) => event.stopPropagation()} onMouseDown={(event) => event.stopPropagation()} onTouchStart={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
    {children ?? address}
  </a>;
}
