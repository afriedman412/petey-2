// Identical pages (Andrew, 2026-10-31: "can you try to leverage existing pages to fill in the info on identical
// pages"; "everything should carry over"): each page's identical pages that hold fields, this form's copies or another
// form's (petey/validate/same_pages.py), and "fill from" one into the working copy.
import { create } from 'zustand';
import { j, mapi, send } from '../lib/api';
import { MODES } from '../modes';
import { loadMode, toast, updateEntry } from './actions';
import { get } from './app';

export interface Same { form: string; page: number; fields: number; done: boolean; same_form: boolean }
interface State { bid: string | null; pages: Record<string, Same[]>; busy: boolean }

export const useSame = create<State>(() => ({ bid: null, pages: {}, busy: false }));

export async function loadSame(bid: string) {
  if (useSame.getState().bid === bid) return;
  useSame.setState({ bid, pages: {} });
  try {
    const { pages } = await j(mapi('same', bid));
    if (useSame.getState().bid === bid) useSame.setState({ pages });
  } catch { /* the page works without it */ }
}

/** what the picker says of a source page */
export const sameLabel = (s: Same) =>
  `${s.same_form ? '' : s.form + ' '}p${s.page} (${s.fields} field${s.fields === 1 ? '' : 's'}${s.done ? ', structure accepted' : ''})`;

export async function fillSame(page: number, s: Same) {
  const { bid, mode } = get();
  if (!bid || useSame.getState().busy) return;
  useSame.setState({ busy: true });
  try {
    await MODES[mode].leave?.();                     // the tab's own changes first (Groups applies its record)
    const out = await send('POST', mapi('same', bid, '/fill'), { page, form: s.form, from_page: s.page });
    updateEntry(out.entry);
    useSame.setState({ bid: null });                 // the page's fields changed: read again
    await loadSame(bid);
    await loadMode();
    toast(out.changes[0] + (out.left.length ? `; ${out.left.length} field(s) not on it kept and flagged` : ''));
  } catch (e) { alert('Fill failed: ' + (e as Error).message); }
  finally { useSame.setState({ busy: false }); }
}
