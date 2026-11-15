import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Loader2, MessageCircle, Sparkles, X } from 'lucide-react';
import { ActivityFeed } from './AgentTrace';
import { askFollowUp, type AgentTraceEvent } from '../../services/vexcel';
import './AskPanel.css';

type Turn = { id: number; question: string; events: AgentTraceEvent[]; answer: string | null; error: string | null; viewLabel: string | null; ms: number | null };

const SUGGESTIONS = ['Which roof has the fewest rooftop obstacles?', 'Only show active listings', 'Why is #2 ranked below #1?', 'Try December instead'];

/** Chat with the Deep Agent about a finished search. It keeps this conversation's memory on the server. */
export default function AskPanel({ threadId, context, onView }: { threadId: string; context: unknown; onView: (ids: string[] | null, label: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' }); }, [turns]);
  useEffect(() => {
    if (!open) return;
    field.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setOpen(true); setDraft(''); setBusy(true);
    const id = Date.now();
    setTurns((items) => [...items, { id, question, events: [], answer: null, error: null, viewLabel: null, ms: null }]);
    const update = (patch: Partial<Turn> | ((turn: Turn) => Partial<Turn>)) => setTurns((items) => items.map((turn) => turn.id === id ? { ...turn, ...(typeof patch === 'function' ? patch(turn) : patch) } : turn));
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await askFollowUp({ threadId, message: question, context }, (event) => update((turn) => ({ events: [...turn.events, event] })), controller.signal);
      update({ answer: result.answer, viewLabel: result.viewLabel, ms: result.ms });
      if (result.showCandidateIds) onView(result.showCandidateIds, result.viewLabel);
    } catch (reason) {
      if (!controller.signal.aborted) update({ error: reason instanceof Error ? reason.message : 'The agent could not answer right now.' });
    } finally { setBusy(false); }
  };

  return <>
    {!open && <button className="ask-launcher" onClick={() => setOpen(true)} aria-label="Open the Ultraviolet agent chat">
      {busy ? <Loader2 size={20} className="ask-spin" /> : <MessageCircle size={20} />}
      <span>Ask the agent</span>
      {turns.length > 0 && <i>{turns.length}</i>}
    </button>}
    <aside className={open ? 'ask-side open' : 'ask-side'} aria-label="Ask Ultraviolet" aria-hidden={!open}>
      <header>
        <div><span><Sparkles size={16} /> Ask Ultraviolet</span><small>Deep Agent · remembers this conversation and re-runs only what a question needs</small></div>
        <button onClick={() => setOpen(false)} aria-label="Close chat"><X size={18} /></button>
      </header>
      <div className="ask-turns" ref={scroller}>
        {!turns.length && <div className="ask-empty">
          <p>Ask about these roofs: try another month, narrow the list, or compare two roofs.</p>
          <div className="ask-chips">{SUGGESTIONS.map((text) => <button key={text} onClick={() => void ask(text)}>{text}</button>)}</div>
        </div>}
        {turns.map((turn) => <article key={turn.id} className="ask-turn">
          <p className="ask-q">{turn.question}</p>
          {(turn.events.some((event) => event.kind === 'activity') || !turn.answer) && <details className="ask-feed" open={!turn.answer}>
            <summary>{turn.answer ? 'What the agent did' : 'Working…'}</summary>
            <ActivityFeed events={turn.events} live={!turn.answer && !turn.error} />
          </details>}
          {!turn.answer && !turn.error && <p className="ask-thinking"><Loader2 size={15} className="ask-spin" /> Thinking…</p>}
          {turn.answer && <div className="ask-a"><p>{turn.answer}</p>{(turn.viewLabel || turn.ms) && <small>{turn.viewLabel ? `Roof list now shows: ${turn.viewLabel} · ` : ''}{turn.ms ? `${Math.round(turn.ms / 1000)}s` : ''}</small>}</div>}
          {turn.error && <p className="ask-error">{turn.error}</p>}
        </article>)}
      </div>
      <form className="ask-input" onSubmit={(event) => { event.preventDefault(); void ask(draft); }}>
        <textarea ref={field} value={draft} rows={1} onChange={(event) => setDraft(event.target.value)} placeholder={busy ? 'The agent is working…' : 'Ask about these roofs…'} disabled={busy}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void ask(draft); } }} />
        <button type="submit" disabled={busy || !draft.trim()} aria-label="Send">{busy ? <Loader2 size={18} className="ask-spin" /> : <ArrowUp size={18} />}</button>
      </form>
    </aside>
  </>;
}
