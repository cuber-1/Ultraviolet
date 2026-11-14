export type MetricPoint = { x: number; y: number };
export type MetricPolygon = { outer: MetricPoint[]; holes: MetricPoint[][] };
export type MetricRoofGeometry = MetricPolygon[];

function removeOuterParens(value: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith('(') || !trimmed.endsWith(')')) return trimmed;
  let depth = 0;
  for (let index = 0; index < trimmed.length; index += 1) {
    if (trimmed[index] === '(') depth += 1;
    if (trimmed[index] === ')') depth -= 1;
    if (depth === 0 && index < trimmed.length - 1) return trimmed;
  }
  return trimmed.slice(1, -1).trim();
}

function splitTopLevel(value: string) {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '(') depth += 1;
    if (value[index] === ')') depth -= 1;
    if (value[index] === ',' && depth === 0) {
      parts.push(value.slice(start, index).trim());
      start = index + 1;
    }
  }
  parts.push(value.slice(start).trim());
  return parts.filter(Boolean);
}

function parseRing(value: string, centerLat: number, centerLon: number, imageRadiusM: number) {
  return splitTopLevel(removeOuterParens(value)).flatMap((coordinate) => {
    const [lonText, latText] = coordinate.trim().split(/\s+/);
    const lon = Number(lonText);
    const lat = Number(latText);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return [];
    const eastM = (lon - centerLon) * 111_320 * Math.cos(centerLat * Math.PI / 180);
    const northM = (lat - centerLat) * 111_320;
    return [{ x: imageRadiusM + eastM, y: imageRadiusM - northM }];
  });
}

function parsePolygon(value: string, centerLat: number, centerLon: number, imageRadiusM: number): MetricPolygon | null {
  const rings = splitTopLevel(removeOuterParens(value)).map((ring) => parseRing(ring, centerLat, centerLon, imageRadiusM)).filter((ring) => ring.length >= 3);
  return rings.length ? { outer: rings[0], holes: rings.slice(1) } : null;
}

export function roofWktToMetricGeometry(wkt: string | null | undefined, centerLat: number, centerLon: number, imageRadiusM: number): MetricRoofGeometry {
  if (!wkt) return [];
  const normalized = wkt.replace(/^SRID=\d+;/i, '').trim();
  const match = normalized.match(/^(POLYGON|MULTIPOLYGON)\s*(\(.*\))$/is);
  if (!match) return [];
  const body = removeOuterParens(match[2]);
  const polygonValues = match[1].toUpperCase() === 'MULTIPOLYGON' ? splitTopLevel(body) : [match[2]];
  return polygonValues.flatMap((value) => {
    const polygon = parsePolygon(value, centerLat, centerLon, imageRadiusM);
    return polygon ? [polygon] : [];
  });
}

/** Compatibility helper for consumers that only support one exterior ring. */
export function roofWktToMetricPolygon(wkt: string | null | undefined, centerLat: number, centerLon: number, imageRadiusM: number): MetricPoint[] {
  return roofWktToMetricGeometry(wkt, centerLat, centerLon, imageRadiusM)[0]?.outer ?? [];
}

export function geometryBounds(geometry: MetricRoofGeometry, fallbackSize: number) {
  const points = geometry.flatMap((polygon) => polygon.outer);
  if (!points.length) return { x: 0, y: 0, width: fallbackSize, height: fallbackSize };
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(1, Math.max(...xs) - x), height: Math.max(1, Math.max(...ys) - y) };
}

export function geometryRequiredRadius(geometry: MetricRoofGeometry, padding = 1.12) {
  const points = geometry.flatMap((polygon) => [polygon.outer, ...polygon.holes].flat());
  return points.length ? Math.max(...points.map((point) => Math.max(Math.abs(point.x), Math.abs(point.y)))) * padding : 0;
}

export function polygonBounds(points: MetricPoint[], fallbackSize: number) {
  return geometryBounds(points.length ? [{ outer: points, holes: [] }] : [], fallbackSize);
}

export function insideMetricPolygon(x: number, y: number, polygon: MetricPoint[]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    if (((a.y > y) !== (b.y > y)) && x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

export function insideMetricGeometry(x: number, y: number, geometry: MetricRoofGeometry) {
  return geometry.some((polygon) => insideMetricPolygon(x, y, polygon.outer) && !polygon.holes.some((hole) => insideMetricPolygon(x, y, hole)));
}

export function metricPointToLonLat(point: MetricPoint, centerLat: number, centerLon: number, imageRadiusM: number) {
  const eastM = point.x - imageRadiusM;
  const northM = imageRadiusM - point.y;
  return { lat: centerLat + northM / 111_320, lon: centerLon + eastM / (111_320 * Math.cos(centerLat * Math.PI / 180)) };
}
