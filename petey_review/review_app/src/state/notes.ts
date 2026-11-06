// One note per form, saved as you type (runs/hand_review/form_notes.json; a discard does not touch it). The text
// lives here, not in the box, so leaving the form or the page can still save what was typed.
import { create } from 'zustand';
import { send } from '../lib/api';
import { entryOf, get as app, set as setApp } from './app';

interface NoteState { bid: string | null; text: string; dirty: boolean; status: string }
export const useNote = create<NoteState>(() => ({ bid: null, text: '', dirty: false, status: '' }));

let timer: ReturnType<typeof setTimeout> | undefined;

/** The note box shows the open form's note (called when the box opens or the form changes). */
export function loadNote() {
  const bid = app().bid, n = entryOf(bid)?.note;
  useNote.setState({ bid, text: n ? n.text : '', dirty: false, status: n ? `saved ${n.updated}` : bid ? 'no note yet' : 'open a form first' });
}

export function noteTyped(text: string) {
  useNote.setState({ text, dirty: true, status: 'typing…' });
  clearTimeout(timer);
  timer = setTimeout(flushNote, 700);
}

export async function flushNote() {
  clearTimeout(timer);
  const { dirty, bid: form, text } = useNote.getState();
  if (!dirty || !form) return;
  useNote.setState({ dirty: false });
  try {
    const out = await send('PUT', `/api/form/${encodeURIComponent(form)}/note`, { text });
    if (out.entry) setApp({ list: app().list.map(b => (b.id === out.entry.id ? out.entry : b)) });
    if (useNote.getState().bid === form) useNote.setState({ status: out.note.text ? `saved ${out.note.updated}` : 'note cleared' });
  } catch (e) { useNote.setState({ dirty: true, status: 'not saved: ' + (e as Error).message }); }
}
