// The floating panel: the form's notes (the chat went 2026-11-03: "let's get rid of chat").
import { useEffect, useRef } from 'react';
import { set, useApp, useEntry } from '../state/app';
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
