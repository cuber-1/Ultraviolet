import { useEffect, useState } from 'react';

// Street addresses for roofs (server: /api/geo/reverse, OpenStreetMap). Fetched one at a time
// because the upstream service allows about one lookup per second; cached for the session.
export type RoofAddress = { street: string | null; area: string | null; label: string };
const memory = new Map<string, RoofAddress | null>();

export function useAddresses(points: Array<{ id: string; lat: number; lon: number; known?: boolean }>) {
  const [addresses, setAddresses] = useState<Map<string, RoofAddress | null>>(() => new Map(points.flatMap((point) => memory.has(point.id) ? [[point.id, memory.get(point.id)!] as const] : [])));
  const key = points.map((point) => point.id).join('|');
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const point of points) {
        if (cancelled) return;
        if (point.known || memory.has(point.id)) { if (memory.has(point.id)) setAddresses((current) => new Map(current).set(point.id, memory.get(point.id)!)); continue; }
        try {
          const response = await fetch(`/api/geo/reverse?lat=${point.lat}&lon=${point.lon}`);
          const value = response.ok ? await response.json() as RoofAddress : null;
          memory.set(point.id, value);
        } catch { memory.set(point.id, null); }
        if (!cancelled) setAddresses((current) => new Map(current).set(point.id, memory.get(point.id)!));
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return addresses;
}

/** Display name + address line for a roof: CoStar first, then the street address, then size. */
export function roofTitle(result: { lat: number; lon: number; costar?: { buildingName?: string | null; address?: string } | null; property?: { roofAreaSqft: number | null } | null }, address: RoofAddress | null | undefined) {
  const size = result.property?.roofAreaSqft ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(result.property.roofAreaSqft)} ft² rooftop` : 'Rooftop';
  if (result.costar?.buildingName) return { name: result.costar.buildingName, line: result.costar.address ?? address?.label ?? '' };
  if (result.costar?.address) return { name: result.costar.address.split(',')[0], line: result.costar.address.split(',').slice(1).join(',').trim() || size };
  if (address?.street) return { name: address.street, line: [address.area, size].filter(Boolean).join(' · ') };
  if (address?.area) return { name: size, line: address.area };
  return { name: size, line: `${result.lat.toFixed(4)}, ${result.lon.toFixed(4)}` };
}
