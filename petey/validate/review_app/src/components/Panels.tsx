// The floating panels: the form's notes and the chat.
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { loadMode, toast, updateEntry } from '../state/actions';
import { set, useApp, useEntry } from '../state/app';
import { applyChat, chatItems, clearChat, sendChat, tick, useChat, type ChatOut, type Item } from '../state/chat';
import { flushNote, loadNote, noteTyped, useNote } from '../state/notes';

export function Notes() {
  const { notesOpen, bid } = useApp();
  const entry = useEntry();
  const n = useNote();
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (notesOpen) loadNote(); }, [notesOpen, bid]);
  // the cursor goes to the notes when the panel opens, not on every form opened while it is open (that took the page
  // keys: a "2" went into the notes, 2026-10-27)
  useEffect(() => { if (notesOpen) box.current?.focus(); }, [notesOpen]);
  if (!notesOpen) return <div id="notes" hidden />;
  return (
    <div id="notes">
      <div className="chead"><b>Notes</b><span className="help">{bid ? entry?.form || bid : ''}</span>
        <button className="btn" onClick={() => { flushNote(); set({ notesOpen: false }); }}>close</button></div>
      <textarea id="notesIn" ref={box} disabled={!bid} value={n.text} placeholder="anything about this form: what's left, what to ask, what you decided"
        onChange={e => noteTyped(e.target.value)} onBlur={() => flushNote()} />
      <div className="help" id="notesState">{n.status}</div>
    </div>
  );
}

const C = ({ children }: { children: ReactNode }) => <code>{children}</code>;
function describeEdit(field: string, e: Record<string, any>) {
  const parts: ReactNode[] = [];
  if (e.name) parts.push(<>→ <C>{e.name}</C></>);
  if (e.type) parts.push(<>type {e.type}</>);
  if (e.semantic_type) parts.push(<>semantic {e.semantic_type}</>);
  if (e.pattern) parts.push(<>pattern <C>{e.pattern}</C></>);
  for (const [k, o] of Object.entries<any>(e.options || {}))
    parts.push(<>option <C>{k}</C>{o.key ? <> → <C>{o.key}</C></> : null}{'caption' in o ? ` "${o.caption}"` : ''}</>);
  return <><C>{field}</C> {parts.map((p, i) => <Fragment key={i}>{i ? ', ' : ''}{p}</Fragment>)}</>;
}
function itemView(out: ChatOut, it: Item): { body: ReactNode; why?: string } {
  if (it.kind === 'edit') { const e = out.edits[it.i]; return { body: describeEdit(e.field, e.edit), why: e.why }; }
  if (it.kind === 'group') {
    const g = out.groups[it.i];
    return { body: <>group <C>{g.name}</C> ({g.type === 'multi_category' ? 'any of' : 'one of'}): {g.fields.map((f, i) => <Fragment key={f}>{i ? ', ' : ''}<C>{f}</C></Fragment>)}</>, why: g.why };
  }
  const r = out.remove[it.i]; return { body: <>remove <C>{r.field}</C></>, why: r.why };
}

export function Chat() {
  const { chatOpen, bid } = useApp();
  const conv = useChat(s => (bid ? s.by[bid] : undefined));
  const [text, setText] = useState('');
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (chatOpen) input.current?.focus(); }, [chatOpen]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [conv]);
  if (!chatOpen) return <div id="chat" hidden />;
  const go = () => { const t = text; setText(''); sendChat(t); };
  const after = async (out: any) => { updateEntry(out.entry); await loadMode(); };
  const turns = conv?.turns || [];
  return (
    <div id="chat">
      <div className="chead"><b>Chat</b><span className="help">{bid || 'no form open'}</span>
        <button className="btn" title="start a new conversation for this form" onClick={() => bid && clearChat(bid)}>new</button>
        <button className="btn" onClick={() => set({ chatOpen: false })}>close</button></div>
      <div id="chatLog" ref={log}>
        {!bid ? <p className="help">Open a form first.</p>
          : !turns.length ? <p className="help">Ask for edits to this form in plain words. Each request is one call to Opus 5 with the pages and the field list; it proposes, nothing changes until you apply.</p>
          : turns.map((t, ti) => {
            let a: ReactNode;
            if (t.err) a = <div className="ca"><div className="cerr">{t.err}</div></div>;
            else if (!t.out) a = <div className="ca help">thinking…</div>;
            else {
              const items = chatItems(t.out);
              a = (
                <div className="ca">{t.out.reply}
                  {items.length > 0 && <ul className="cprop">{items.map(it => {
                    const v = itemView(t.out!, it);
                    return <li key={it.k}><input type="checkbox" checked={t.picked.has(it.k)} disabled={t.applied}
                      onChange={e => tick(bid, ti, it.k, e.target.checked)} /><span>{v.body}{v.why && <div className="cwhy">{v.why}</div>}</span></li>;
                  })}</ul>}
                  {t.out.errors.length > 0 && <div className="cerr">left out: {t.out.errors.join('; ')}</div>}
                  {t.result ? <div className="cfoot">applied: {t.result.changes.length} change(s){t.result.errors.length > 0 && <> · <span className="cerr">{t.result.errors.join('; ')}</span></>}</div>
                    : items.length && !t.applied ? <div className="cfoot"><button className="btn primary" disabled={t.applying} onClick={() => applyChat(ti, after, toast)}>{t.applying ? 'applying…' : 'apply ticked'}</button><span>${t.out.cost_usd}</span></div>
                    : <div className="cfoot"><span>${t.out.cost_usd}</span></div>}
                  {(t.accepted || []).length > 0 && <div className="cfoot">accepted {t.accepted!.length} grid cell(s) the check confirmed (note: grid check)</div>}
                  {(t.refused || []).map((x, i) => <div key={i} className="cerr">not accepted: {x.grid || 'a grid'}: {x.why}</div>)}
                </div>);
            }
            return <Fragment key={ti}><div className="cq">{t.req}</div>{a}</Fragment>;
          })}
      </div>
      <div className="cin">
        <textarea id="chatIn" ref={input} value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(); } }}
          placeholder="e.g. rename every _txt box in Part 3 to end in _nbr; group 12–15 as one question (Enter sends, Shift+Enter a new line)" />
        <button className="btn primary" onClick={go}>send</button>
      </div>
    </div>
  );
}
