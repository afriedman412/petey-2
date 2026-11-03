// Pages left out of the benchmark, each with a reason (Andrew, 2026-10-31: an "ignore this page" tag "along with a
// field to provide a reason"): the server's record (petey/validate/ignored_pages.py), keyed `<review id>__p<page>`.
import { create } from 'zustand';
import { j, send } from '../lib/api';

export interface Ignored { reason: string; when: string }
interface State { rec: Record<string, Ignored>; open: boolean }

export const useIgnored = create<State>(() => ({ rec: {}, open: false }));
export const pageId = (bid: string, page: number) => `${bid}__p${page}`;

let loaded = false;
export async function loadIgnored() {
  if (loaded) return;
  loaded = true;
  try { useIgnored.setState({ rec: await j('/api/ignored-pages') }); } catch { loaded = false; /* the page works without it */ }
}

/** the reasons given so far, most used first (offered as you type) */
export const reasonsUsed = (rec: Record<string, Ignored>) => {
  const n: Record<string, number> = {};
  Object.values(rec).forEach(e => { n[e.reason] = (n[e.reason] || 0) + 1; });
  return Object.keys(n).sort((a, b) => n[b] - n[a] || a.localeCompare(b));
};

export async function setIgnored(pid: string, ignore: boolean, reason = ''): Promise<boolean> {
  try { useIgnored.setState({ rec: await send('PUT', `/api/ignored-pages/${encodeURIComponent(pid)}`, { ignore, reason }), open: false }); }
  catch (e) { alert((e as Error).message); return false; }
  return true;
}
