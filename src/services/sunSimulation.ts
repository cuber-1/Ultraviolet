import type { MetricPoint, MetricRoofGeometry } from './roofGeometry';
export type { MetricPoint, MetricPolygon, MetricRoofGeometry } from './roofGeometry';

export type SunPosition = { altitude: number; azimuth: number };
export type AreaSelection = { x: number; y: number; width: number; height: number };
export type Obstruction = { x: number; y: number; width: number; depth: number; heightM: number };
export type CellResult = { x: number; y: number; sunlit: boolean; hours: number; blockedBy: number | null };
export type ShadowVector = { dx: number; dy: number; lengthM: number };
export type SimulationResult = {
  sun: SunPosition;
  cells: CellResult[];
  totalAreaSqft: number;
  directAreaSqft: number | null;
  meetingTargetAreaSqft: number | null;
  estimatedHours: number | null;
  resolutionMinutes: number;
  geometryAvailable: boolean;
};

const radians = (degrees: number) => degrees * Math.PI / 180;
const degrees = (value: number) => value * 180 / Math.PI;

export function sunPosition(date: Date, lat: number, lon: number): SunPosition {
  const julian = date.getTime() / 86_400_000 + 2_440_587.5;
  const n = julian - 2_451_545;
  const meanLongitude = (280.46 + 0.9856474 * n) % 360;
  const anomaly = radians((357.528 + 0.9856003 * n) % 360);
  const longitude = radians(meanLongitude + 1.915 * Math.sin(anomaly) + 0.02 * Math.sin(2 * anomaly));
  const obliquity = radians(23.439 - 0.0000004 * n);
  const rightAscension = Math.atan2(Math.cos(obliquity) * Math.sin(longitude), Math.cos(longitude));
  const declination = Math.asin(Math.sin(obliquity) * Math.sin(longitude));
  const gmst = (280.46061837 + 360.98564736629 * (julian - 2_451_545)) % 360;
  const hourAngle = radians(((gmst + lon - degrees(rightAscension) + 540) % 360) - 180);
  const latitude = radians(lat);
  const altitude = Math.asin(Math.sin(latitude) * Math.sin(declination) + Math.cos(latitude) * Math.cos(declination) * Math.cos(hourAngle));
  const azimuth = Math.atan2(-Math.sin(hourAngle), Math.tan(declination) * Math.cos(latitude) - Math.sin(latitude) * Math.cos(hourAngle));
  return { altitude: degrees(altitude), azimuth: (degrees(azimuth) + 360) % 360 };
}

export function shadowVector(sun: SunPosition, obstructionHeightM: number): ShadowVector | null {
  if (sun.altitude <= 0) return null;
  const lengthM = obstructionHeightM / Math.tan(radians(sun.altitude));
  const shadowAzimuth = radians((sun.azimuth + 180) % 360);
  return { dx: Math.sin(shadowAzimuth) * lengthM, dy: -Math.cos(shadowAzimuth) * lengthM, lengthM };
}

function shaded(x: number, y: number, sun: SunPosition, obstruction: Obstruction) {
  if (sun.altitude <= 0) return true;
  const vector = shadowVector(sun, obstruction.heightM)!;
  // Cheap reject: the point must sit inside the box swept by the shadow.
  if (x < obstruction.x + Math.min(0, vector.dx) || x > obstruction.x + obstruction.width + Math.max(0, vector.dx)
    || y < obstruction.y + Math.min(0, vector.dy) || y > obstruction.y + obstruction.depth + Math.max(0, vector.dy)) return false;
  const samples = Math.max(1, Math.ceil(vector.lengthM / 1.5));
  for (let i = 0; i <= samples; i += 1) {
    const t = i / samples;
    const left = obstruction.x + vector.dx * t;
    const top = obstruction.y + vector.dy * t;
    if (x >= left && x <= left + obstruction.width && y >= top && y <= top + obstruction.depth) return true;
  }
  return false;
}

function localDate(date: string, minutes: number, timezoneOffsetHours: number) {
  const utcMinutes = minutes - timezoneOffsetHours * 60;
  return new Date(`${date}T00:00:00Z`).getTime() + utcMinutes * 60_000;
}

function insideRing(x: number, y: number, ring: MetricPoint[]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const a = ring[i];
    const b = ring[j];
    if (((a.y > y) !== (b.y > y)) && x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

function insideRoofGeometry(x: number, y: number, geometry: MetricRoofGeometry) {
  return geometry.some((polygon) => insideRing(x, y, polygon.outer) && !polygon.holes.some((hole) => insideRing(x, y, hole)));
}

export function simulate(input: {
  date: string;
  minute: number;
  timezoneOffsetHours: number;
  lat: number;
  lon: number;
  roofAreaSqft: number;
  roofWidthM: number;
  roofDepthM: number;
  roofGeometry?: MetricRoofGeometry;
  roofPolygon?: MetricPoint[];
  selection: AreaSelection;
  obstructions: Obstruction[] | null;
  targetHours: number;
  resolutionMinutes?: number;
  gridSize?: number;
}): SimulationResult {
  const resolutionMinutes = input.resolutionMinutes ?? 30;
  const gridSize = input.gridSize ?? 20;
  const selectionArea = input.selection.width * input.selection.height;
  const areaGridSize = input.gridSize ?? 20;
  const roofGeometry = input.roofGeometry?.length ? input.roofGeometry : input.roofPolygon?.length ? [{ outer: input.roofPolygon, holes: [] }] : [];
  const selectedRoofCells = roofGeometry.length ? Array.from({ length: areaGridSize * areaGridSize }, (_, index) => {
    const row = Math.floor(index / areaGridSize);
    const column = index % areaGridSize;
    const x = input.selection.x + (column + .5) * input.selection.width / areaGridSize;
    const y = input.selection.y + (row + .5) * input.selection.height / areaGridSize;
    return insideRoofGeometry(x, y, roofGeometry);
  }).filter(Boolean).length : null;
  const totalAreaSqft = selectedRoofCells === null
    ? input.roofAreaSqft * selectionArea / (input.roofWidthM * input.roofDepthM)
    : selectedRoofCells * selectionArea / (areaGridSize * areaGridSize) * 10.7639;
  const now = new Date(localDate(input.date, input.minute, input.timezoneOffsetHours));
  const sun = sunPosition(now, input.lat, input.lon);
  if (!input.obstructions) return { sun, cells: [], totalAreaSqft, directAreaSqft: null, meetingTargetAreaSqft: null, estimatedHours: null, resolutionMinutes, geometryAvailable: false };
  const cells: CellResult[] = [];
  const daySamples: Array<{ minute: number; sun: SunPosition }> = [];
  for (let minute = 0; minute < 1_440; minute += resolutionMinutes) {
    const position = sunPosition(new Date(localDate(input.date, minute, input.timezoneOffsetHours)), input.lat, input.lon);
    if (position.altitude > 0) daySamples.push({ minute, sun: position });
  }
  for (let row = 0; row < gridSize; row += 1) {
    for (let column = 0; column < gridSize; column += 1) {
      const x = input.selection.x + (column + 0.5) * input.selection.width / gridSize;
      const y = input.selection.y + (row + 0.5) * input.selection.height / gridSize;
      if (roofGeometry.length && !insideRoofGeometry(x, y, roofGeometry)) continue;
      const blockedBy = sun.altitude > 0 ? input.obstructions.findIndex((obstruction) => shaded(x, y, sun, obstruction)) : -1;
      const isShaded = sun.altitude <= 0 || blockedBy >= 0;
      const sunnySamples = daySamples.filter((sample) => !input.obstructions!.some((obstruction) => shaded(x, y, sample.sun, obstruction))).length;
      cells.push({ x, y, sunlit: sun.altitude > 0 && !isShaded, hours: sunnySamples * resolutionMinutes / 60, blockedBy: blockedBy >= 0 ? blockedBy : null });
    }
  }
  const cellArea = cells.length ? totalAreaSqft / cells.length : 0;
  const directAreaSqft = cells.filter((cell) => cell.sunlit).length * cellArea;
  const meetingTargetAreaSqft = cells.filter((cell) => cell.hours >= input.targetHours).length * cellArea;
  const estimatedHours = cells.length ? cells.reduce((sum, cell) => sum + cell.hours, 0) / cells.length : null;
  return { sun, cells, totalAreaSqft, directAreaSqft, meetingTargetAreaSqft, estimatedHours, resolutionMinutes, geometryAvailable: true };
}

export function sharedMeetingArea(results: SimulationResult[], targetHours = 6) {
  if (!results.length || results.some((result) => !result.geometryAvailable || !result.cells.length)) return null;
  const shared = results[0].cells.filter((_, index) => results.every((result) => result.cells[index]?.hours >= targetHours)).length;
  return shared * results[0].totalAreaSqft / results[0].cells.length;
}

export function predictableShadowLength(heightM: number, altitudeDegrees: number) {
  return heightM / Math.tan(radians(altitudeDegrees));
}
