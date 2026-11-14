import { useMemo, useState } from 'react';
import { Brain, Building2, ChevronDown, CloudSun, Cpu, FileText, LoaderCircle, MessageSquare, Ruler, Search, Sun, Trophy, Wrench } from 'lucide-react';
import type { AgentTraceEvent } from '../../services/vexcel';

const TOOL_NAMES: Record<string, string> = {
  search_rooftop_imagery: 'Search aerial imagery',
  lookup_property_record: 'Look up property record',
  resolve_roof_geometry: 'Measure roof geometry',
  simulate_rooftop_sunlight: 'Simulate sunlight',
  predict_crop_suitability: 'Score crops with CropFit',
  write_todos: 'Write a plan',
  ls: 'List notes', read_file: 'Read notes', write_file: 'Write notes', edit_file: 'Edit notes',
  task: 'Delegate a task',
};
export const toolLabel = (name: string) => TOOL_NAMES[name] ?? (/^extract|structured|response/i.test(name) ? 'Write final answer' : name.replace(/_/g, ' '));
const seconds = (ms: number) => `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;

type Step =
  | { kind: 'llm'; event: Extract<AgentTraceEvent, { kind: 'llm' }> }
  | { kind: 'tools'; name: string; events: Array<Extract<AgentTraceEvent, { kind: 'tool' }>> };

/** Consecutive calls to the same tool collapse into one row (e.g. "Simulate sunlight × 8"). */
function steps(events: AgentTraceEvent[]): Step[] {
  const out: Step[] = [];
  for (const event of events) {
    if (event.kind === 'llm') out.push({ kind: 'llm', event });
    if (event.kind === 'tool') {
      const last = out.at(-1);
      if (last?.kind === 'tools' && last.name === event.name) last.events.push(event);
      else out.push({ kind: 'tools', name: event.name, events: [event] });
    }
  }
  return out;
}

export function AgentTrace({ events, model }: { events: AgentTraceEvent[]; model: string | null }) {
  const prompts = events.filter((event): event is Extract<AgentTraceEvent, { kind: 'prompt' }> => event.kind === 'prompt');
  const list = useMemo(() => steps(events), [events]);
  const llm = events.filter((event) => event.kind === 'llm') as Array<Extract<AgentTraceEvent, { kind: 'llm' }>>;
  const tools = events.filter((event) => event.kind === 'tool');
  const tokens = llm.reduce((sum, event) => sum + (event.tokens ?? 0), 0);
  const end = Math.max(0, ...events.map((event) => event.at + ('ms' in event ? event.ms : 0)));
  if (!events.length) return <div className="trace-empty"><p>This run was saved before the agent trace was recorded. Run the search again to see every prompt and tool call.</p></div>;
  return <div className="trace">
    <section className="trace-summary">
      <div><strong>{llm.length}</strong><span>model turns</span></div>
      <div><strong>{tools.length}</strong><span>tool calls</span></div>
      <div><strong>{seconds(end)}</strong><span>total time</span></div>
      <div><strong>{tokens ? `${Math.round(tokens / 1000)}k` : '—'}</strong><span>tokens</span></div>
      <div><strong>{model ?? '—'}</strong><span>model</span></div>
    </section>
    <section className="trace-prompts">
      {prompts.map((prompt) => <Prompt key={prompt.role} title={prompt.title} text={prompt.text} role={prompt.role} />)}
    </section>
    <ol className="trace-steps">
      {list.map((step, index) => step.kind === 'llm'
        ? <li key={index} className="trace-step llm">
          <span className="trace-icon"><Brain size={18} /></span>
          <div>
            <header><strong>Model turn</strong><span>{seconds(step.event.at)} · {seconds(step.event.ms)}{step.event.tokens ? ` · ${step.event.tokens.toLocaleString()} tokens` : ''}</span></header>
            {step.event.text && <p className="trace-thought">{step.event.text}</p>}
            {step.event.toolCalls.length > 0 && <p className="trace-decision">Decided to call {[...new Set(step.event.toolCalls.map((call) => toolLabel(call.name)))].map((name) => { const count = step.event.toolCalls.filter((call) => toolLabel(call.name) === name).length; return count > 1 ? `${name} × ${count}` : name; }).join(', ')}</p>}
          </div>
        </li>
        : <ToolStep key={index} name={step.name} events={step.events} />)}
    </ol>
  </div>;
}

function Prompt({ title, text, role }: { title: string; text: string; role: 'system' | 'user' }) {
  const [open, setOpen] = useState(role === 'user');
  return <article className={`trace-prompt ${role}`}>
    <button onClick={() => setOpen((value) => !value)}>{role === 'system' ? <FileText size={18} /> : <MessageSquare size={18} />}<strong>{title}</strong><ChevronDown size={18} className={open ? 'open' : ''} /></button>
    {open && <pre>{text}</pre>}
  </article>;
}

function ToolStep({ name, events }: { name: string; events: Array<Extract<AgentTraceEvent, { kind: 'tool' }>> }) {
  const [open, setOpen] = useState(false);
  const total = events.reduce((sum, event) => sum + event.ms, 0);
  const failed = events.filter((event) => !event.ok).length;
  return <li className={`trace-step tool${failed ? ' failed' : ''}`}>
    <span className="trace-icon"><Wrench size={17} /></span>
    <div>
      <button className="trace-tool-head" onClick={() => setOpen((value) => !value)}>
        <strong>{toolLabel(name)}{events.length > 1 ? ` × ${events.length}` : ''}</strong>
        <span>{seconds(events[0].at)} · {seconds(total)}{failed ? ` · ${failed} failed` : ''}</span>
        <ChevronDown size={16} className={open ? 'open' : ''} />
      </button>
      <code className="trace-fn">{name}({events[0].args.length > 90 ? `${events[0].args.slice(0, 90)}…` : events[0].args})</code>
      {open && <div className="trace-io">{events.map((event, index) => <div key={index}><span>Input</span><pre>{event.args}</pre><span>Result</span><pre>{event.result}</pre></div>)}</div>}
    </div>
  </li>;
}

/** Live, compact version for the loading screen: the last few things the agent did. */
export function AgentConsole({ events }: { events: AgentTraceEvent[] }) {
  const recent = events.filter((event) => event.kind !== 'prompt').slice(-5);
  if (!recent.length) return null;
  return <ol className="agent-console">{recent.map((event, index) => <li key={`${event.at}-${index}`} className={index === recent.length - 1 ? 'latest' : ''}>
    {event.kind === 'llm'
      ? <><Brain size={15} /><span>{event.toolCalls.length ? `Model decided: ${[...new Set(event.toolCalls.map((call) => toolLabel(call.name)))].join(', ')}` : event.text ? `Model: ${event.text.slice(0, 110)}${event.text.length > 110 ? '…' : ''}` : 'Model is thinking'}</span></>
      : event.kind === 'tool' ? <><Wrench size={15} /><span>{toolLabel(event.name)} <small>{(event.ms / 1000).toFixed(1)}s</small></span></> : null}
  </li>)}</ol>;
}

// ---- Live activity feed (Claude-style "Searching for …  · 12 results") -------
type Activity = Extract<AgentTraceEvent, { kind: 'activity' }>;
const ACTIVITY_ICON: Record<string, typeof Search> = {
  climate: CloudSun, search_rooftop_imagery: Search, lookup_property_record: Building2, resolve_roof_geometry: Ruler,
  simulate_rooftop_sunlight: Sun, predict_crop_suitability: Cpu, rank: Trophy, done: Trophy,
};
const GROUP_TITLE: Record<string, (items: Activity[]) => { title: string; summary: string }> = {
  lookup_property_record: (items) => { const hits = items.filter((item) => item.detail.startsWith('CoStar:')); return { title: `Looked up ${items.length} property records`, summary: hits.length ? `${hits.length} matched CoStar: ${hits.map((item) => item.detail.slice(8).split(' · ')[0]).slice(0, 3).join(', ')}` : 'No CoStar matches nearby' }; },
  resolve_roof_geometry: (items) => { const obstacles = items.reduce((sum, item) => sum + (Number(item.detail.match(/(\d+) obstacle/)?.[1]) || 0), 0); return { title: `Measured ${items.length} roofs in 3D`, summary: `${obstacles} obstacles found across them` }; },
  simulate_rooftop_sunlight: (items) => { const meets = items.filter((item) => item.detail.includes('meets your area')).length; return { title: `Simulated sunlight on ${items.length} roofs`, summary: `${meets} of ${items.length} have enough area in full sun` }; },
};

type FeedRow = { kind: 'activity'; tool: string; items: Activity[] } | { kind: 'thought'; event: Extract<AgentTraceEvent, { kind: 'llm' }> };

function feedRows(events: AgentTraceEvent[]): FeedRow[] {
  const rows: FeedRow[] = [];
  for (const event of events) {
    if (event.kind === 'activity') {
      const last = rows.at(-1);
      if (last?.kind === 'activity' && last.tool === event.tool && GROUP_TITLE[event.tool]) last.items.push(event);
      else rows.push({ kind: 'activity', tool: event.tool, items: [event] });
    }
    if (event.kind === 'llm' && event.toolCalls.length) rows.push({ kind: 'thought', event });
  }
  return rows;
}

export function ActivityFeed({ events, live = false }: { events: AgentTraceEvent[]; live?: boolean }) {
  const rows = feedRows(events);
  if (!rows.length) return <p className="feed-empty">{live ? 'Waiting for the agent’s first step…' : 'No activity was recorded for this run.'}</p>;
  return <ol className="feed">{rows.map((row, index) => {
    const latest = live && index === rows.length - 1;
    if (row.kind === 'thought') {
      const names = [...new Set(row.event.toolCalls.map((call) => toolLabel(call.name)))];
      return <li key={index} className={`feed-row thought${latest ? ' latest' : ''}`}><span className="feed-icon"><Brain size={15} /></span><div><strong>Thinking</strong><small>Next: {names.map((name) => { const count = row.event.toolCalls.filter((call) => toolLabel(call.name) === name).length; return count > 1 ? `${name.toLowerCase()} × ${count}` : name.toLowerCase(); }).join(', ')}</small></div>{latest && <LoaderCircle size={15} className="spin feed-spin" />}</li>;
    }
    const Icon = ACTIVITY_ICON[row.tool] ?? Wrench;
    const grouped = row.items.length > 1 && GROUP_TITLE[row.tool];
    const head = grouped ? GROUP_TITLE[row.tool](row.items) : { title: row.items[0].title, summary: row.items[0].detail };
    return <li key={index} className={`feed-row${latest ? ' latest' : ''}`}>
      <span className="feed-icon"><Icon size={15} /></span>
      <div>
        <strong>{head.title}</strong>
        <small>{head.summary}</small>
        {grouped && <details><summary>{row.items.length} results</summary><ul>{row.items.map((item, itemIndex) => <li key={itemIndex}><b>{item.title.split(' · ').slice(1).join(' · ') || item.title}</b> {item.detail}</li>)}</ul></details>}
      </div>
      {latest && <LoaderCircle size={15} className="spin feed-spin" />}
    </li>;
  })}</ol>;
}
