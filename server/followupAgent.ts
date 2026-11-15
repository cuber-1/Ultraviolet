import { MemorySaver } from '@langchain/langgraph';
import { createDeepAgent } from 'deepagents';
import { tool, toolStrategy } from 'langchain';
import { z } from 'zod';
import { configuredAgentModel, type AgentCandidate, type AgentTraceEvent, type SunlightEvidence } from './landlensAgent';
import { predictCropSuitability, type MlCrop, type MlPrediction } from './mlModel';
import { roofSites } from './landlensAgent';

// "Ask Ultraviolet": a follow-up conversation on a finished rooftop search.
// The search evidence is written into the Deep Agent's virtual filesystem, the conversation is kept in a
// checkpointer (one thread per results session), and the agent re-runs only the tools a question needs.

export type FollowUpContext = {
  location: string;
  crops: MlCrop[];
  preferredMonth: number;
  criteria: { dates: string[]; targetHours: number; targetAreaSqft: number };
  notes?: string | null;
  candidates: AgentCandidate[];
  simulations: SunlightEvidence[];
  predictions: Array<MlPrediction & { curve?: Array<{ month: number; score: number }> }>;
  explanations?: Array<{ candidateId: string; explanation: string }>;
  ranking: string[];
};

export type FollowUpServices = {
  simulate: (candidate: AgentCandidate, dates: string[], targetHours: number, targetAreaSqft: number) => Promise<SunlightEvidence>;
};

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const checkpointer = new MemorySaver();
const seededThreads = new Set<string>();
const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

const responseSchema = z.object({
  answer: z.string().describe('Plain-language reply for the grower, 1-5 short sentences, citing the numbers the tools returned.'),
  showCandidateIds: z.array(z.string()).nullable().describe('Roof candidate IDs the results deck should show, in order, when the user asks to filter, narrow or reorder. Null to leave the deck unchanged.'),
  viewLabel: z.string().nullable().describe('Short label for that filtered view, e.g. "Active listings". Null when showCandidateIds is null.'),
});

const name = (candidate: AgentCandidate | undefined) => candidate?.costar?.buildingName || candidate?.costar?.address?.split(',')[0] || (candidate?.property?.roofAreaSqft ? `${nf.format(candidate.property.roofAreaSqft)} ft² roof` : 'Rooftop');

function evidenceFiles(context: FollowUpContext) {
  const byId = new Map(context.candidates.map((candidate) => [candidate.id, candidate]));
  const now = new Date().toISOString();
  const file = (content: string, mimeType = 'text/markdown') => ({ content, mimeType, created_at: now, modified_at: now });
  const roofs = context.ranking.map((id, index) => {
    const candidate = byId.get(id);
    const simulation = context.simulations.find((item) => item.candidateId === id);
    const hours = simulation?.perDate.map((item) => item.meanHours).filter((value): value is number => value !== null) ?? [];
    const crops = context.predictions.filter((item) => item.siteId === id).map((item) => ({
      crop: context.crops.find((crop) => crop.id === item.cropId)?.name ?? item.cropId,
      fit: Math.round(item.suitability * 100),
      plant: item.plantMonth === null ? null : MONTHS[item.plantMonth],
      harvest: item.harvestMonth === null ? null : MONTHS[item.harvestMonth],
      fitByPlantingMonth: item.curve?.length === 12 ? Object.fromEntries(item.curve.map((point) => [MONTHS[point.month].slice(0, 3), Math.round(point.score)])) : null,
    }));
    return {
      rank: index + 1, candidateId: id, name: name(candidate), address: candidate?.costar?.address ?? null,
      propertyType: candidate?.costar?.propertyType ?? null,
      listingActive: candidate?.costar?.listing?.active ?? false, listingStatuses: candidate?.costar?.listing?.statuses ?? [],
      matterportTours: candidate?.costar?.matterport.length ?? 0,
      roofAreaSqft: candidate?.property?.roofAreaSqft ?? null,
      sunlitSqft: simulation?.sharedAreaSqft ?? null, averageSunHours: hours.length ? Number((hours.reduce((a, b) => a + b, 0) / hours.length).toFixed(1)) : null,
      obstacles: simulation?.geometry.obstructionCount ?? null, buildingHeightM: simulation?.geometry.buildingHeightM ?? null,
      crops, whyItRanks: context.explanations?.find((item) => item.candidateId === id)?.explanation ?? null,
    };
  });
  const summary = [
    `# Rooftop search: ${context.location}`,
    `Crops: ${context.crops.map((crop) => crop.name).join(', ')}. Start month: ${MONTHS[context.preferredMonth]}.`,
    `Target: ${nf.format(context.criteria.targetAreaSqft)} ft² with ${context.criteria.targetHours}+ hours of direct sun on ${context.criteria.dates.join(' and ')}.`,
    context.notes ? `User notes: ${context.notes}` : 'User notes: none.',
    '', '| Rank | Roof | Sunlit ft² | Avg sun h | Crop fit | Listing | Tours |', '|---|---|---|---|---|---|---|',
    ...roofs.map((roof) => `| ${roof.rank} | ${roof.name} (${roof.candidateId}) | ${roof.sunlitSqft === null ? 'n/a' : nf.format(roof.sunlitSqft)} | ${roof.averageSunHours ?? 'n/a'} | ${roof.crops.length ? Math.round(roof.crops.reduce((sum, crop) => sum + crop.fit, 0) / roof.crops.length) : 'n/a'} | ${roof.listingActive ? 'active' : 'none'} | ${roof.matterportTours} |`),
  ].join('\n');
  return {
    '/evidence/summary.md': file(summary),
    // One roof per line keeps the file short enough to read in a single call.
    '/evidence/roofs.json': file(`[\n${roofs.map((roof) => JSON.stringify(roof)).join(',\n')}\n]`, 'application/json'),
    '/evidence/criteria.json': file(JSON.stringify({ location: context.location, crops: context.crops.map((crop) => ({ id: crop.id, name: crop.name })), preferredMonth: MONTHS[context.preferredMonth], ...context.criteria, notes: context.notes ?? null }, null, 2), 'application/json'),
  };
}

export async function runFollowUpAgent(input: { threadId: string; message: string; context: FollowUpContext; signal?: AbortSignal }, services: FollowUpServices, onTrace: (event: AgentTraceEvent) => void) {
  const model = configuredAgentModel();
  if (!model) throw new Error('Agent model access is not configured.');
  const started = Date.now();
  const trace: AgentTraceEvent[] = [];
  const emit = (event: AgentTraceEvent) => { trace.push(event); onTrace(event); };
  const activity = (toolName: string, title: string, detail: string) => emit({ kind: 'activity', tool: toolName, title, detail, at: Date.now() - started });
  const { context } = input;
  const byId = new Map(context.candidates.map((candidate) => [candidate.id, candidate]));

  const simulateDates = tool(async ({ candidateIds, dates, targetHours }: { candidateIds: string[]; dates: string[]; targetHours?: number | null }) => {
    const hours = targetHours ?? context.criteria.targetHours;
    const known = candidateIds.map((id) => byId.get(id)).filter((candidate): candidate is AgentCandidate => Boolean(candidate)).slice(0, 5);
    if (!known.length) return { error: 'Unknown candidate IDs. Read /evidence/roofs.json for valid IDs.' };
    const results = await Promise.all(known.map(async (candidate) => {
      const result = await services.simulate(candidate, dates, hours, context.criteria.targetAreaSqft).catch(() => null);
      const sunHours = result?.perDate.map((item) => item.meanHours).filter((value): value is number => value !== null) ?? [];
      return { candidateId: candidate.id, name: name(candidate), sunlitSqft: result?.sharedAreaSqft ?? null, averageSunHours: sunHours.length ? Number((sunHours.reduce((a, b) => a + b, 0) / sunHours.length).toFixed(1)) : null, perDate: result?.perDate ?? [] };
    }));
    activity('simulate_rooftop_sunlight', `Re-simulated sunlight on ${dates.join(', ')}`, results.map((item) => `${item.name} ${item.sunlitSqft === null ? 'n/a' : `${nf.format(item.sunlitSqft)} ft²`}${item.averageSunHours !== null ? ` · ${item.averageSunHours} h` : ''}`).join(' · '));
    return { targetHours: hours, dates, roofs: results };
  }, {
    name: 'simulate_sunlight_on_dates',
    description: 'Re-run the shadow-accurate sun simulation for up to 5 roofs on new dates (YYYY-MM-DD), e.g. mid-December. Use only when the stored evidence does not already answer the question.',
    schema: z.object({ candidateIds: z.array(z.string()).min(1).max(5), dates: z.array(z.string()).min(1).max(3), targetHours: z.number().min(1).max(14).nullable().optional() }),
  });

  const scoreCrops = tool(async ({ candidateIds, cropIds, month }: { candidateIds: string[]; cropIds?: string[] | null; month: number }) => {
    const known = candidateIds.map((id) => byId.get(id)).filter((candidate): candidate is AgentCandidate => Boolean(candidate)).slice(0, 5);
    const crops = cropIds?.length ? context.crops.filter((crop) => cropIds.includes(crop.id)) : context.crops;
    if (!known.length || !crops.length) return { error: 'Unknown roof or crop IDs. Read /evidence/criteria.json and /evidence/roofs.json.' };
    try {
      const response = await predictCropSuitability({ crops, preferredMonth: month, targetAreaSqft: context.criteria.targetAreaSqft, targetSunHours: context.criteria.targetHours, sites: await roofSites(known, new Map(context.simulations.map((item) => [item.candidateId, item]))) });
      const rows = response.predictions.map((item) => ({ candidateId: item.siteId, name: name(byId.get(item.siteId)), crop: crops.find((crop) => crop.id === item.cropId)?.name ?? item.cropId, fit: Math.round(item.suitability * 100), plant: item.plantMonth === null ? null : MONTHS[item.plantMonth], harvest: item.harvestMonth === null ? null : MONTHS[item.harvestMonth], source: item.source }));
      activity('predict_crop_suitability', `Scored ${crops.map((crop) => crop.name.toLowerCase()).join(', ')} from ${MONTHS[month]}`, rows.slice(0, 6).map((row) => `${row.name}: ${row.crop} ${row.fit}${row.plant ? ` · plant ${row.plant.slice(0, 3)}` : ''}`).join(' · '));
      return { model: response.model.name, source: response.model.source, rows };
    } catch (reason) {
      activity('predict_crop_suitability', 'Crop model unavailable', 'Answering from the monthly fit curves saved with the search');
      return { error: reason instanceof Error ? reason.message : 'Crop model failed.', instruction: 'Use fitByPlantingMonth in /evidence/roofs.json instead and say the scores come from the earlier model run.' };
    }
  }, {
    name: 'score_crops_from_month',
    description: 'Run the CropFit model again for some roofs with a different start month (0 = January). Check fitByPlantingMonth in /evidence/roofs.json first; it often already has the answer.',
    schema: z.object({ candidateIds: z.array(z.string()).min(1).max(5), cropIds: z.array(z.string()).nullable().optional(), month: z.number().int().min(0).max(11) }),
  });

  const systemPrompt = `You are Ultraviolet's rooftop-farming analyst, continuing a conversation about a rooftop search that already ran. All of the search's evidence is in your filesystem: the summary table is included in the first message of this conversation (it lists every roof's sunlit area, sun hours, crop fit, listing status and tours), so answer from it directly whenever it is enough. Read /evidence/roofs.json only when you need more detail, such as obstacles, building height, or each crop's fit for every planting month; read the whole file in one call rather than paging or grepping. Answer from that evidence whenever it is enough. Only call simulate_sunlight_on_dates when the question needs sunlight on dates that were not simulated, and only call score_crops_from_month when the saved monthly fits cannot answer it. Re-run tools for at most the five roofs that matter. Keep notes of anything the user tells you (preferences, constraints) in /notes/preferences.md and respect them in later answers.
Interpret subjective language ("low maintenance", "best year-round", "only serious options") yourself and say how you interpreted it, but every number must come from the evidence files or a tool result: never estimate area, sunlight, crop fit, or listing status. Crop fit is agroclimatic screening, not yield. When the user asks to filter, narrow, or reorder the roofs (e.g. "only active listings"), set showCandidateIds to the matching IDs in the order to show and give the view a short label. Reply in plain, friendly language: refer to roofs by rank and name, round numbers, and never mention tool names, file paths, JSON, or candidate IDs in the answer.`;

  const agent = createDeepAgent({
    model: model.client,
    tools: [simulateDates, scoreCrops],
    responseFormat: toolStrategy(responseSchema),
    systemPrompt,
    checkpointer,
  });

  const first = !seededThreads.has(input.threadId);
  if (first) emit({ kind: 'prompt', role: 'system', title: 'Follow-up instructions', text: systemPrompt, at: 0 });
  emit({ kind: 'prompt', role: 'user', title: 'Your question', text: input.message, at: 0 });
  const llmStarts = new Map<string, number>();
  const toolStarts = new Map<string, { name: string; args: string; at: number }>();
  const clip = (value: unknown, max = 500) => { const text = typeof value === 'string' ? value : JSON.stringify(value); return text && text.length > max ? `${text.slice(0, max)}…` : text ?? ''; };
  const callbacks = [{
    handleChatModelStart: (_llm: unknown, _messages: unknown, runId: string) => { llmStarts.set(runId, Date.now()); },
    handleLLMEnd: (output: { generations?: Array<Array<{ text?: string; message?: { content?: unknown; tool_calls?: Array<{ name: string; args: unknown }>; usage_metadata?: { total_tokens?: number } } }>> }, runId: string) => {
      const message = output.generations?.[0]?.[0]?.message;
      const content = typeof message?.content === 'string' ? message.content : '';
      const begun = llmStarts.get(runId) ?? Date.now();
      emit({ kind: 'llm', text: clip(content.trim(), 800), toolCalls: (message?.tool_calls ?? []).map((call) => ({ name: call.name, args: clip(call.args, 240) })), ms: Date.now() - begun, tokens: message?.usage_metadata?.total_tokens ?? null, at: begun - started });
    },
    handleToolStart: (toolInfo: { name?: string }, args: string, runId: string, _parent?: string, _tags?: string[], _metadata?: unknown, runName?: string) => {
      const toolName = runName ?? toolInfo.name ?? 'tool';
      toolStarts.set(runId, { name: toolName, args: clip(args, 240), at: Date.now() });
      if (toolName === 'read_file' || toolName === 'ls' || toolName === 'grep' || toolName === 'glob') {
        let parsed: Record<string, unknown> = {}; try { parsed = JSON.parse(args) as Record<string, unknown>; } catch { /* plain string */ }
        const target = String(parsed.file_path ?? parsed.path ?? '').replace(/^\/evidence\//, '').replace(/^\/notes\//, 'notes/');
        const what = toolName === 'grep' ? `Searched${target ? ` ${target}` : ''} for "${String(parsed.pattern ?? '').slice(0, 40)}"` : toolName === 'read_file' ? `Read ${target || 'a file'}` : `Listed ${target || 'files'}`;
        activity('read_evidence', 'Checking the saved search evidence', what);
      }
      if (toolName === 'write_file' || toolName === 'edit_file') activity('write_notes', 'Updating notes about your preferences', 'Kept for the rest of this conversation');
    },
    handleToolEnd: (output: unknown, runId: string) => {
      const begun = toolStarts.get(runId); if (!begun) return;
      const value = output && typeof output === 'object' && 'content' in (output as object) ? (output as { content: unknown }).content : output;
      emit({ kind: 'tool', name: begun.name, args: begun.args, result: clip(value, 400), ms: Date.now() - begun.at, ok: true, at: begun.at - started });
    },
    handleToolError: (error: unknown, runId: string) => {
      const begun = toolStarts.get(runId); if (!begun) return;
      emit({ kind: 'tool', name: begun.name, args: begun.args, result: clip(error instanceof Error ? error.message : error, 300), ms: Date.now() - begun.at, ok: false, at: begun.at - started });
    },
  }];

  const files = first ? evidenceFiles(context) : null;
  const opening = files ? `Saved evidence from the search (also at /evidence/summary.md):\n${String(files['/evidence/summary.md'].content)}\n\nQuestion: ${input.message}` : input.message;
  const result = await agent.invoke({
    messages: [{ role: 'user', content: opening }],
    ...(files ? { files } : {}),
  } as never, {
    configurable: { thread_id: input.threadId }, recursionLimit: 40, signal: input.signal ? AbortSignal.any([input.signal, AbortSignal.timeout(180_000)]) : AbortSignal.timeout(180_000), callbacks,
    runName: `Follow-up · ${context.location.split(',')[0]}`, tags: ['ultraviolet', 'follow-up'], metadata: { app: 'ultraviolet', thread: input.threadId, question: input.message },
  } as never) as { structuredResponse?: z.infer<typeof responseSchema> };
  seededThreads.add(input.threadId);
  const response = result.structuredResponse ?? { answer: 'I could not finish that answer. Try asking again.', showCandidateIds: null, viewLabel: null };
  const valid = response.showCandidateIds?.filter((id) => byId.has(id)) ?? null;
  return { ...response, showCandidateIds: valid && valid.length ? valid : null, viewLabel: valid && valid.length ? response.viewLabel : null, trace, ms: Date.now() - started };
}
