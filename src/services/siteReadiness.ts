import type { SearchResult, SunlightEvidence } from './vexcel';

export type ReadinessTone = 'green' | 'caution' | 'red' | 'unknown';
export type ReadinessFlag = {
  id: string;
  label: string;
  detail: string;
  tone: ReadinessTone;
  priority: 'high' | 'medium' | 'low';
};

export type SiteReadiness = {
  flags: ReadinessFlag[];
  counts: Record<ReadinessTone, number>;
  reviewed: number;
  score: number;
};

const lower = (value: string | null | undefined) => value?.trim().toLowerCase() ?? '';
const yearsOld = (year: number | null | undefined) => year ? Math.max(0, new Date().getFullYear() - year) : null;

export function assessSiteReadiness(result: SearchResult, simulation: SunlightEvidence | null | undefined, targetAreaSqft: number): SiteReadiness {
  const flags: ReadinessFlag[] = [];
  const add = (flag: ReadinessFlag) => flags.push(flag);
  const costar = result.costar;
  const property = result.property;
  const age = yearsOld(costar?.yearBuilt);
  const height = simulation?.geometry.buildingHeightM ?? null;
  const stories = costar?.stories ?? null;
  const material = property?.roofMaterial?.trim() || null;
  const obstructionCount = simulation?.geometry.obstructionCount ?? null;
  const sunlit = simulation?.sharedAreaSqft ?? null;

  add(age === null ? {
    id: 'age', label: 'Building age unavailable', detail: 'Obtain construction and renovation records before structural screening.', tone: 'unknown', priority: 'medium',
  } : age <= 25 ? {
    id: 'age', label: `Built ${costar!.yearBuilt}`, detail: `${age} years old in the property record; structural capacity still requires an engineer.`, tone: 'green', priority: 'medium',
  } : age <= 50 ? {
    id: 'age', label: `Built ${costar!.yearBuilt}`, detail: `${age} years old. Review roof replacement, waterproofing, and structural records.`, tone: 'caution', priority: 'medium',
  } : {
    id: 'age', label: `Older building · ${costar!.yearBuilt}`, detail: `${age} years old. Treat structural and waterproofing review as an early gate.`, tone: 'red', priority: 'high',
  });

  add(material ? {
    id: 'material', label: `Roof material · ${material}`, detail: 'Material is identified by aerial property data; confirm membrane condition and assembly on site.', tone: 'caution', priority: 'medium',
  } : {
    id: 'material', label: 'Roof material unknown', detail: 'Confirm membrane, deck, drainage, penetrations, and remaining service life.', tone: 'unknown', priority: 'high',
  });

  const accessValue = height ?? (stories ? stories * 3.4 : null);
  add(accessValue === null ? {
    id: 'height', label: 'Building height unavailable', detail: 'Height affects wind exposure, emergency access, and material handling.', tone: 'unknown', priority: 'medium',
  } : accessValue <= 15 ? {
    id: 'height', label: height !== null ? `${height.toFixed(1)} m building height` : `${stories} stories`, detail: 'Lower-rise access can simplify logistics, but the actual route still needs review.', tone: 'green', priority: 'medium',
  } : accessValue <= 30 ? {
    id: 'height', label: height !== null ? `${height.toFixed(1)} m building height` : `${stories} stories`, detail: 'Plan lifting, freight access, wind protection, and emergency response.', tone: 'caution', priority: 'medium',
  } : {
    id: 'height', label: height !== null ? `Tall building · ${height.toFixed(1)} m` : `Tall building · ${stories} stories`, detail: 'Height adds meaningful wind, access, lifting, and emergency-response complexity.', tone: 'red', priority: 'high',
  });

  add(sunlit === null ? {
    id: 'sun', label: 'Seasonal shadow result unavailable', detail: 'Roof geometry could not support the current sunlight screen.', tone: 'unknown', priority: 'high',
  } : sunlit >= targetAreaSqft ? {
    id: 'sun', label: `${Math.round(sunlit).toLocaleString()} ft² clears the sun target`, detail: 'The selected area meets the requested direct-sun threshold on every simulated date.', tone: 'green', priority: 'high',
  } : {
    id: 'sun', label: 'Insufficient qualifying sun area', detail: `${Math.round(sunlit).toLocaleString()} ft² qualifies versus ${Math.round(targetAreaSqft).toLocaleString()} ft² requested.`, tone: 'red', priority: 'high',
  });

  add(obstructionCount === null ? {
    id: 'obstacles', label: 'Roof obstacles not measured', detail: 'Obstacles, setbacks, drains, and maintenance paths still need mapping.', tone: 'unknown', priority: 'high',
  } : obstructionCount <= 8 ? {
    id: 'obstacles', label: `${obstructionCount} elevated roof ${obstructionCount === 1 ? 'sample' : 'samples'}`, detail: 'The elevation screen found relatively little raised rooftop interference.', tone: 'green', priority: 'medium',
  } : obstructionCount <= 24 ? {
    id: 'obstacles', label: `${obstructionCount} elevated roof samples`, detail: 'Lay out beds around equipment, drains, setbacks, and maintenance access.', tone: 'caution', priority: 'medium',
  } : {
    id: 'obstacles', label: `Crowded roof · ${obstructionCount} elevated samples`, detail: 'Rooftop equipment may materially reduce usable contiguous growing space.', tone: 'red', priority: 'high',
  });

  add(costar?.matterport.length ? {
    id: 'access-evidence', label: `${costar.matterport.length} interior 3D ${costar.matterport.length === 1 ? 'scan' : 'scans'}`, detail: 'Use the scans to pre-screen stairs, roof hatches, freight routes, and loading access.', tone: 'green', priority: 'low',
  } : {
    id: 'access-evidence', label: 'No interior access scan', detail: 'A site visit is needed to trace the route from loading area to roof.', tone: 'unknown', priority: 'medium',
  });

  add({
    id: 'egress', label: 'Emergency exits: verify on site', detail: 'Required for every roof: confirm code-compliant egress, firefighter access, guardrails, setbacks, and occupancy limits.', tone: 'unknown', priority: 'high',
  });
  add({
    id: 'structure', label: 'Structural load: engineer review', detail: 'Required for every roof: a licensed structural engineer must assess dead, live, wind, snow, water, and saturated-growing-system loads.', tone: 'unknown', priority: 'high',
  });
  const geometry = simulation?.geometry;
  const neighborLoss = geometry?.neighborLossSqft ?? null;
  const taller = geometry?.neighborTallerCount ?? 0;
  const tallest = geometry?.neighborMaxAboveRoofM ?? null;
  add(!geometry?.neighborsChecked || neighborLoss === null ? {
    id: 'neighbor-shadow', label: 'Neighbor shadows need review', detail: 'Surrounding buildings were not sampled for this search; rerun it to include them.', tone: 'unknown', priority: 'high',
  } : !taller ? {
    id: 'neighbor-shadow', label: 'No taller neighbors within 40 m', detail: 'Nothing around the roof rises above it, so no outside shade on the growing area.', tone: 'green', priority: 'high',
  } : neighborLoss < 50 ? {
    id: 'neighbor-shadow', label: 'Neighbors do not shade the beds', detail: `Taller structures nearby (up to ${tallest?.toFixed(1)} m above the roof) were included in the shadow model and cost no qualifying sun area.`, tone: 'green', priority: 'high',
  } : neighborLoss < 0.15 * targetAreaSqft ? {
    id: 'neighbor-shadow', label: `Neighbors shade ${Math.round(neighborLoss).toLocaleString()} ft²`, detail: `Taller structures nearby (up to ${tallest?.toFixed(1)} m above the roof) cut some qualifying sun area. Already counted in the sun result.`, tone: 'caution', priority: 'high',
  } : {
    id: 'neighbor-shadow', label: `Neighbors shade ${Math.round(neighborLoss).toLocaleString()} ft²`, detail: `Taller structures nearby (up to ${tallest?.toFixed(1)} m above the roof) remove a large share of the sun area. Already counted in the sun result.`, tone: 'red', priority: 'high',
  });
  add({
    id: 'consumers', label: 'Consumer travel time not measured', detail: 'Add grocery, restaurant, school, and distribution destinations before claiming last-mile savings.', tone: 'unknown', priority: 'medium',
  });
  add(costar?.zoning ? {
    id: 'zoning', label: `Zoning record · ${costar.zoning}`, detail: 'A zoning value is available, but rooftop agriculture and structures still need local approval review.', tone: 'caution', priority: 'high',
  } : {
    id: 'zoning', label: 'Zoning compatibility unknown', detail: 'Check agricultural use, greenhouse structures, utilities, signage, and food-handling requirements.', tone: 'unknown', priority: 'high',
  });

  const materialName = lower(material);
  if (materialName.includes('concrete') || materialName.includes('metal')) {
    const item = flags.find((flag) => flag.id === 'material');
    if (item) item.detail += ' The recorded material is commonly screenable for rooftop projects, but is not proof of capacity.';
  }

  const counts = flags.reduce<Record<ReadinessTone, number>>((all, flag) => ({ ...all, [flag.tone]: all[flag.tone] + 1 }), { green: 0, caution: 0, red: 0, unknown: 0 });
  const reviewed = flags.length - counts.unknown;
  const score = Math.max(0, Math.round(100 * (counts.green + counts.caution * .45) / Math.max(1, flags.length)));
  return { flags, counts, reviewed, score };
}
