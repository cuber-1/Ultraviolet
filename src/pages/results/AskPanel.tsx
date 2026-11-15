import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ChevronDown, Loader2, Sparkles } from 'lucide-react';
import { ActivityFeed } from './AgentTrace';
import { askFollowUp, type AgentTraceEvent } from '../../services/vexcel';
import './AskPanel.css';

type Turn = { id: number; question: string; events: AgentTraceEvent[]; answer: string | null; error: string | null; viewLabel: string | null; ms: number | null };

const SUGGESTIONS = ['Try December instead', 'Only show active listings', 'Why is #2 ranked below #1?', 'Which roof is lowest maintenance?'];

/** Follow-up chat on a finished search. The Deep Agent keeps this conversation's memory on the server. */
export default function AskPanel({ threadId, context, onView }: { threadId: string; context: unknown; onView: (ids: string[] | null, label: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' }); }, [turns]);

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

  return <div className={open ? 'ask open' : 'ask'}>
    {open && <section className="ask-panel" aria-label="Ask Ultraviolet">
      <header><span><Sparkles size={16} /> Ask Ultraviolet</span><small>The Deep Agent remembers this conversation and re-runs only what your question needs.</small><button onClick={() => setOpen(false)} aria-label="Collapse"><ChevronDown size={18} /></button></header>
      <div className="ask-turns" ref={scroller}>
        {!turns.length && <p className="ask-empty">Ask about these roofs: try other months, narrow the list, or compare two roofs.</p>}
        {turns.map((turn) => <article key={turn.id} className="ask-turn">
          <p className="ask-q">{turn.question}</p>
          {(turn.events.some((event) => event.kind === 'activity') || !turn.answer) && <div className="ask-feed"><ActivityFeed events={turn.events} live={!turn.answer && !turn.error} /></div>}
          {!turn.answer && !turn.error && <p className="ask-thinking"><Loader2 size={15} className="spin" /> Working…</p>}
          {turn.answer && <div className="ask-a"><p>{turn.answer}</p>{(turn.viewLabel || turn.ms) && <small>{turn.viewLabel ? `Deck now shows: ${turn.viewLabel} · ` : ''}{turn.ms ? `${Math.round(turn.ms / 1000)}s` : ''}</small>}</div>}
          {turn.error && <p className="ask-error">{turn.error}</p>}
        </article>)}
      </div>
    </section>}
    <form className="ask-bar" onSubmit={(event) => { event.preventDefault(); void ask(draft); }}>
      <Sparkles size={18} />
      <input value={draft} onChange={(event) => setDraft(event.target.value)} onFocus={() => turns.length && setOpen(true)} placeholder="Ask Ultraviolet about these roofs…" disabled={busy} />
      <button type="submit" disabled={busy || !draft.trim()} aria-label="Ask">{busy ? <Loader2 size={18} className="spin" /> : <ArrowUp size={18} />}</button>
    </form>
    {!turns.length && !busy && <div className="ask-chips">{SUGGESTIONS.map((text) => <button key={text} onClick={() => void ask(text)}>{text}</button>)}</div>}
  </div>;
}
