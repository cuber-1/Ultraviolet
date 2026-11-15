import { insideMetricGeometry, metricPointToLonLat, type MetricRoofGeometry } from './roofGeometry';
import type { Obstruction } from './sunSimulation';

/** How far around the roof we look for buildings and trees that could shade it. */
export const NEIGHBOR_MARGIN_M = 40;
/** Ignore anything that does not rise at least this far above the roof plane. */
const SHADE_THRESHOLD_M = 1;
/** Below this height above the ground a sample is treated as pavement or yard, not a structure. */
const STRUCTURE_MIN_M = 2.5;
/** Keep the shadow model fast enough for the time slider. */
const MAX_CASTERS = 90;
const MAX_SAMPLES = 360;

type Bounds = { x: number; y: number; width: number; height: number };
export type NeighborCell = { x: number; y: number; lat: number; lon: number };
export type NeighborGrid = { cells: NeighborCell[]; stepM: number };
/** One sampled column of a nearby building or tree. Heights are in metres. */
export type NeighborBlock = { x: number; y: number; size: number; heightAboveGroundM: number; heightAboveRoofM: number; /** Index into `casters` when this block is in the shadow model. */ casterIndex: number | null };
export type NeighborModel = { blocks: NeighborBlock[]; casters: Obstruction[]; tallerCount: number; maxAboveRoofM: number | null };

/** Sample points in a ring around the roof footprint (outside the roof, inside the margin). */
export function neighborGrid(roofBounds: Bounds, roofGeometry: MetricRoofGeometry, lat: number, lon: number, imageRadiusM: number, marginM = NEIGHBOR_MARGIN_M): NeighborGrid {
  const outer = { x: roofBounds.x - marginM, y: roofBounds.y - marginM, width: roofBounds.width + marginM * 2, height: roofBounds.height + marginM * 2 };
  const ringArea = outer.width * outer.height - roofBounds.width * roofBounds.height;
  const stepM = Math.max(5, Math.sqrt(Math.max(1, ringArea) / MAX_SAMPLES));
  const cells: NeighborCell[] = [];
  for (let y = outer.y + stepM / 2; y < outer.y + outer.height; y += stepM) {
    for (let x = outer.x + stepM / 2; x < outer.x + outer.width; x += stepM) {
      if (insideMetricGeometry(x, y, roofGeometry)) continue;
      // Skip a thin band hugging the roof edge so parapets and the wall itself are not read as neighbors.
      if (x > roofBounds.x - 2 && x < roofBounds.x + roofBounds.width + 2 && y > roofBounds.y - 2 && y < roofBounds.y + roofBounds.height + 2 && nearRoof(x, y, roofGeometry)) continue;
      cells.push({ x, y, ...metricPointToLonLat({ x, y }, lat, lon, imageRadiusM) });
    }
  }
  return { cells: cells.slice(0, MAX_SAMPLES), stepM };
}

function nearRoof(x: number, y: number, geometry: MetricRoofGeometry) {
  return [[2, 0], [-2, 0], [0, 2], [0, -2]].some(([dx, dy]) => insideMetricGeometry(x + dx, y + dy, geometry));
}

/**
 * Turn sampled surface (DSM) and ground (DTM) heights into neighbor blocks for the 3D view and
 * shadow casters for the sun model. Only things taller than the roof can shade it.
 */
export function neighborModel(grid: NeighborGrid, samples: Array<{ dsmM: number | null; dtmM: number | null }>, roofPlaneM: number, roofBounds: Bounds): NeighborModel {
  const blocks: NeighborBlock[] = [];
  grid.cells.forEach((cell, index) => {
    const sample = samples[index];
    if (!sample || sample.dsmM === null || sample.dtmM === null) return;
    const heightAboveGroundM = sample.dsmM - sample.dtmM;
    if (heightAboveGroundM < STRUCTURE_MIN_M) return;
    blocks.push({ x: cell.x, y: cell.y, size: grid.stepM, heightAboveGroundM, heightAboveRoofM: sample.dsmM - roofPlaneM, casterIndex: null });
  });
  const centerX = roofBounds.x + roofBounds.width / 2;
  const centerY = roofBounds.y + roofBounds.height / 2;
  const taller = blocks.filter((block) => block.heightAboveRoofM >= SHADE_THRESHOLD_M)
    // Closest and tallest first: those are the ones that can reach the roof.
    .sort((a, b) => Math.hypot(a.x - centerX, a.y - centerY) / a.heightAboveRoofM - Math.hypot(b.x - centerX, b.y - centerY) / b.heightAboveRoofM);
  const kept = taller.slice(0, MAX_CASTERS);
  kept.forEach((block, index) => { block.casterIndex = index; });
  return {
    blocks,
    casters: kept.map((block) => ({ x: block.x - block.size / 2, y: block.y - block.size / 2, width: block.size, depth: block.size, heightM: block.heightAboveRoofM })),
    tallerCount: taller.length,
    maxAboveRoofM: taller.length ? Math.max(...taller.map((block) => block.heightAboveRoofM)) : null,
  };
}
