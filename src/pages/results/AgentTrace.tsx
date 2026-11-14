import { useMemo, useState } from 'react';
import { Brain, ChevronDown, FileText, MessageSquare, Wrench } from 'lucide-react';
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
