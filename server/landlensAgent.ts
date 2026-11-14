import { ChatOpenAI } from '@langchain/openai';
import { createDeepAgent } from 'deepagents';
import { tool, toolStrategy } from 'langchain';
import { z } from 'zod';

export type AgentCandidate = {
  id: string;
  rank: number;
  lat: number;
  lon: number;
  score: number;
  matchReason: string;
  property: null | { roofWkt: string | null; roofAreaSqft: number | null; captureDate: string | null };
  costar: null | {
    propertyId: number;
    address: string;
    buildingName: string | null;
    propertyType: string;
    matchDistanceM: number;
    listing: null | { active: boolean; statuses: string[]; types: string[] };
    apartment?: null | { availableUnits: number };
    matterport: Array<{ modelId: string; caption: string }>;
  };
  imageryUrl: string;
};

export type GeometryEvidence = {
  candidateId: string;
  available: boolean;
  roofAreaSqft: number | null;
  buildingHeightM: number | null;
  validSamples: number;
  obstructionCount: number;
  dsmCollections: string[];
  dtmCollections: string[];
  reason: string | null;
};

export type SunlightEvidence = {
  candidateId: string;
  dates: string[];
  targetHours: number;
  targetAreaSqft: number;
  sharedAreaSqft: number | null;
  perDate: Array<{ date: string; areaMeetingTargetSqft: number | null; meanHours: number | null }>;
  geometry: GeometryEvidence;
};

export type LandLensAgentServices = {
  search: (query: string) => Promise<AgentCandidate[]>;
  geometry: (candidate: AgentCandidate) => Promise<GeometryEvidence>;
  simulate: (candidate: AgentCandidate, dates: string[], targetHours: number, targetAreaSqft: number) => Promise<SunlightEvidence>;
};

export type AgentProgress = { stage: 'planning' | 'imagery' | 'property' | 'geometry' | 'sunlight' | 'ranking'; message: string };

const responseSchema = z.object({
  summary: z.string(),
  criteria: z.object({
    location: z.string(),
    targetAreaSqft: z.number(),
    targetHours: z.number(),
    dates: z.array(z.string()),
  }),
  explanations: z.array(z.object({ candidateId: z.string(), explanation: z.string() })),
  unknowns: z.array(z.string()),
});

function configuredModel() {
  const nrpKey = process.env.NRP_API_KEY;
  const apiKey = process.env.LANDLENS_AGENT_API_KEY || nrpKey || process.env.OPENAI_API_KEY;
  if (!apiKey) return null;
  const model = process.env.LANDLENS_AGENT_MODEL || (nrpKey ? 'qwen3' : 'gpt-5-mini');
  const baseURL = process.env.LANDLENS_AGENT_BASE_URL || (nrpKey ? 'https://ellm.nrp-nautilus.io/v1' : undefined);
  return {
    name: model,
    client: new ChatOpenAI({
      model,
      apiKey,
      temperature: 0,
      configuration: baseURL ? { baseURL } : undefined,
    }),
  };
}

// Measured on NRP (Nov 2026) with a single agent calling the tools directly: qwen3 finished
// a 4-site comparison in ~35s with a correct ranking. The earlier two-subagent design took
// 120-150s with qwen3 and ~390s with deepseek-v4-flash, so subagents were removed.
// A live 12-candidate Houston run took ~225s, mostly Vexcel geometry and sunlight work.
const AGENT_TIMEOUT_MS = Number(process.env.LANDLENS_AGENT_TIMEOUT_MS) || 420_000;
const AGENT_RECURSION_LIMIT = Number(process.env.LANDLENS_AGENT_RECURSION_LIMIT) || 80;
// Each candidate costs a geometry + sunlight run; 8 keeps a top-5 answer to a few minutes.
const AGENT_MAX_CANDIDATES = Number(process.env.LANDLENS_AGENT_MAX_CANDIDATES) || 8;

export function landLensAgentStatus() {
  const model = configuredModel();
  return { configured: Boolean(model), model: model?.name ?? null, provider: process.env.NRP_API_KEY ? 'NRP' : model ? 'OpenAI-compatible' : null };
}

export async function runLandLensAgent(input: {
  goal: string;
  followUp?: string;
  location: string;
  dates: string[];
  targetHours: number;
  targetAreaSqft: number;
}, services: LandLensAgentServices, progress: (event: AgentProgress) => void) {
  const model = configuredModel();
  if (!model) throw new Error('Agent model access is not configured. Set NRP_API_KEY or LANDLENS_AGENT_API_KEY.');

  const candidates = new Map<string, AgentCandidate>();
  const simulations = new Map<string, SunlightEvidence>();
  const geometryResults = new Map<string, GeometryEvidence>();
  let searchResults: AgentCandidate[] | null = null;

  const searchImagery = tool(async ({ query }: { query: string }) => {
    progress({ stage: 'imagery', message: `Searching Vexcel imagery near ${input.location}` });
    const results = searchResults ?? (await services.search(query)).slice(0, AGENT_MAX_CANDIDATES);
    searchResults = results;
    results.forEach((candidate) => candidates.set(candidate.id, candidate));
    return results.map((candidate) => ({
      candidateId: candidate.id,
      score: candidate.score,
      matchReason: candidate.matchReason,
      roofAreaSqft: candidate.property?.roofAreaSqft ?? null,
      imageryUrl: candidate.imageryUrl,
    }));
  }, {
    name: 'search_rooftop_imagery',
    description: 'Search real Vexcel aerial imagery for rooftop candidates within the selected geographic scope.',
    schema: z.object({ query: z.string() }),
  });

  const lookupProperty = tool(async ({ candidateId }: { candidateId: string }) => {
    progress({ stage: 'property', message: `Checking property and tour records for ${candidateId}` });
    const candidate = candidates.get(candidateId);
    if (!candidate) return { candidateId, available: false, reason: 'Run rooftop imagery search first.' };
    return {
      candidateId,
      available: Boolean(candidate.costar),
      property: candidate.costar,
      roofAreaSqft: candidate.property?.roofAreaSqft ?? null,
      captureDate: candidate.property?.captureDate ?? null,
      evidenceUrl: `#/agriculture/urban?site=${encodeURIComponent(candidateId)}`,
    };
  }, {
    name: 'lookup_property_record',
    description: 'Look up the matched CoStar property, listing status, and verified Matterport attachments for a candidate.',
    schema: z.object({ candidateId: z.string() }),
  });

  const resolveGeometry = tool(async ({ candidateId }: { candidateId: string }) => {
    progress({ stage: 'geometry', message: `Resolving roof and elevation geometry for ${candidateId}` });
    const candidate = candidates.get(candidateId);
    if (!candidate) return { candidateId, available: false, reason: 'Run rooftop imagery search first.' };
    const existing = geometryResults.get(candidateId);
    if (existing) return existing;
    const resolved = await services.geometry(candidate);
    geometryResults.set(candidateId, resolved);
    return resolved;
  }, {
    name: 'resolve_roof_geometry',
    description: 'Resolve the Vexcel roof outline and DSM minus DTM height evidence for a candidate. Never invent missing geometry.',
    schema: z.object({ candidateId: z.string() }),
  });

  const simulateSunlight = tool(async ({ candidateId, dates, targetHours, targetAreaSqft }: { candidateId: string; dates: string[]; targetHours: number; targetAreaSqft: number }) => {
    progress({ stage: 'sunlight', message: `Calculating shared sunlight area for ${candidateId}` });
    const candidate = candidates.get(candidateId);
    if (!candidate) return { candidateId, sharedAreaSqft: null, reason: 'Run rooftop imagery search first.' };
    const cacheKey = `${candidateId}:${dates.join(',')}:${targetHours}:${targetAreaSqft}`;
    const cached = simulations.get(cacheKey);
    if (cached) return cached;
    const result = await services.simulate(candidate, dates, targetHours, targetAreaSqft);
    simulations.set(cacheKey, result);
    simulations.set(candidateId, result);
    return result;
  }, {
    name: 'simulate_rooftop_sunlight',
    description: 'Run the same clear-sky geometry simulator used by the roof UI and calculate area meeting the target on every requested date.',
    schema: z.object({
      candidateId: z.string(),
      dates: z.array(z.string()).min(1),
      targetHours: z.number().min(1).max(14),
      targetAreaSqft: z.number().positive(),
    }),
  });

  progress({ stage: 'planning', message: 'Planning the site comparison' });
  const agent = createDeepAgent({
    model: model.client,
    tools: [searchImagery, lookupProperty, resolveGeometry, simulateSunlight],
    responseFormat: toolStrategy(responseSchema),
    systemPrompt: `You compare real urban rooftops for growing goals. Call search_rooftop_imagery exactly once. Then, for every candidate ID it returns, call lookup_property_record and simulate_rooftop_sunlight (it resolves geometry itself; call resolve_roof_geometry only if you need height details). Batch independent tool calls in the same turn. Do not repeat a call you already made. Rank only by sharedAreaSqft returned by the sunlight tool. A verified Matterport tour may break a near tie but can never outrank materially greater suitable area. Never estimate missing geometry, listing status, or sunlight; list them under unknowns. Write the summary, explanations, and unknowns in plain, friendly language for a grower: refer to sites by rank or address rather than coordinates, round numbers, and never include tool or field names, code identifiers, or URLs. Keep each explanation to one or two sentences about why that roof ranks where it does.`,
  });

  let narrative: z.infer<typeof responseSchema> | null = null;
  try {
    const result = await agent.invoke({
      messages: [{ role: 'user', content: `${input.goal}\nLocation: ${input.location}\nRepresentative dates: ${input.dates.join(', ')}\nDirect sun target: ${input.targetHours} hours\nGrowing area target: ${input.targetAreaSqft} square feet.${input.followUp ? `\nFollow-up: ${input.followUp}` : ''}` }],
    } as never, { recursionLimit: AGENT_RECURSION_LIMIT, signal: AbortSignal.timeout(AGENT_TIMEOUT_MS) });
    narrative = result.structuredResponse ?? null;
  } catch (reason) {
    progress({ stage: 'ranking', message: `Model planning ended; ranking completed tool evidence directly` });
    console.warn('Deep Agent stopped before its narrative response:', reason instanceof Error ? reason.message : String(reason));
  }
  progress({ stage: 'ranking', message: 'Ranking by shared qualifying area' });

  return {
    model: model.name,
    narrative,
    candidates: [...candidates.values()],
    simulations: [...new Map([...simulations.values()].map((item) => [item.candidateId, item])).values()],
  };
}
