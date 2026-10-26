// What the frame does: open a form, change tab or page, load a tab's data, save or discard the working copy,
// follow a link, notice the file changing on disk. Every tab calls these; none of them draws anything.
import { j, mapi, send } from '../lib/api';
import type { Entry, ModeId } from '../lib/types';
import { MODE_IDS } from '../lib/types';
import { store } from '../lib/util';
import { MODES } from '../modes';
import { flushNote } from './notes';
import { entryOf, get, set } from './app';

export const def = () => MODES[get().mode];

let toastN = 0;
export function toast(msg: string) { set({ toast: { msg, n: ++toastN } }); }
export const toastText = () => get().toast?.msg || '';

export function updateEntry(e?: Entry | null) {
  if (!e) return;
  set({ list: get().list.map(b => (b.id === e.id ? e : b)) });
}

export function setHash() {
  const { home, mode, bid } = get();
  history.replaceState(null, '', home.on ? '#home' : '#' + encodeURIComponent(mode) + (bid ? '/' + encodeURIComponent(bid) : ''));
}

const parseHash = () => decodeURIComponent(location.hash.slice(1)).split('/') as [string?, string?, string?];

// the blueprint file can change under the page (an --apply, a loop run): reload the tab in place when it does
let shaSeen: string | null = null;
export async function syncSha() {
  const bid = get().bid; if (!bid) return;
  try { shaSeen = (await j(`/api/blueprints/${encodeURIComponent(bid)}/sha`)).sha; } catch { /* next time */ }
}
let checking = false;
export async function checkFresh() {
  const { bid, home } = get();
  if (!bid || checking || home.on) return;
  checking = true;
  try {
    const { sha } = await j(`/api/blueprints/${encodeURIComponent(bid)}/sha`);
    if (shaSeen && sha !== shaSeen) {
      set({ list: await j('/api/blueprints') });
      await loadMode();
      toast('The blueprint changed on disk; reloaded.');
    }
  } catch { /* the server is away: the next check */ } finally { checking = false; }
}

export async function refreshList() {
  try { set({ list: await j('/api/blueprints'), listError: null }); }
  catch (e) { set({ listError: (e as Error).message }); }
}

/** The tab's data for the form open, read again; a tab opened meanwhile, or another form, takes over. */
export async function loadMode() {
  const { mode: m, bid: form } = get();
  if (!form) return;
  const d = MODES[m];
  try {
    const [, ov] = await Promise.all([d.load(form), j(`/api/overlay/${encodeURIComponent(form)}`).catch(() => null)]);
    if (get().mode !== m || get().bid !== form) return;
    set({ overlay: ov });
  } catch (e) {
    if (get().mode === m && get().bid === form) set({ loadError: (e as Error).message, loaded: null });
    return;
  }
  await syncSha();
  if (get().mode !== m || get().bid !== form) return;
  const pages = d.pages();
  let page = get().page;
  if (!pages.some(p => p.page === page) || !d.pageLabel(page)) page = d.startPage() || pages[0]?.page || 1;
  set({ page, loaded: { mode: m, bid: form }, loadError: null });
}

async function leaveTab() {
  const { bid, mode } = get();
  if (bid) await MODES[mode].leave?.();
}

export async function setMode(m: ModeId) {
  if (!MODES[m] || m === get().mode) return;
  await leaveTab();
  set({ mode: m });
  store('br_mode', m);
  setHash();
  if (get().bid) await loadMode();
}

export async function showHome(on: boolean) {
  if (on) await leaveTab();
  set({ home: { ...get().home, on } });
  document.body.classList.toggle('home', on);
  setHash();
  if (!on) return;
  set({ chatOpen: false });
  await flushNote();
  set({ notesOpen: false });
  await refreshList();
}

export async function openBlueprint(id: string) {
  if (!id) return;
  const wasHome = get().home.on;
  await showHome(false);
  if (wasHome && id === get().bid) { setHash(); await loadMode(); return; }
  await leaveTab();
  await flushNote();
  set({ bid: id, loaded: null, loadError: null });
  setHash();
  await loadMode();
}

export function gotoPage(p: number) {
  set({ page: p });
  def().onPage?.();
}

export function setZoom(z: number) {
  const zoom = Math.min(6, Math.max(0.6, z));
  set({ zoom });
  store('br_zoom', zoom);
}

export function toggleWide() {
  const wide = !get().wide;
  set({ wide });
  store('br_wide', wide ? '1' : '0');
}

/** The form's working copy written into the blueprint (the header's save). */
export async function saveDraft() {
  await leaveTab();
  const d = entryOf(get().bid)?.draft; if (!d) return;
  if (!confirm(`Write ${d.changes} change(s) into the blueprint?\n\n${d.log.slice(0, 40).join('\n')}${d.log.length > 40 ? `\n… ${d.log.length - 40} more` : ''}`)) return;
  const bid = get().bid!;
  let out;
  try { out = await send('POST', mapi('draft', bid, '/save')); }
  catch (e) {
    const msg = (e as Error).message;
    if (!/changed on disk/.test(msg) || !confirm(msg + '\n\nOverwrite it with the working copy anyway?')) { alert('Not saved: ' + msg); return; }
    try { out = await send('POST', mapi('draft', bid, '/save'), { force: true }); }
    catch (e2) { alert('Not saved: ' + (e2 as Error).message); return; }
  }
  updateEntry(out.entry);
  await loadMode();
  toast(`Saved ${out.changes} change(s) to ${String(out.saved).split('/').pop()}.`);
}

export async function discardDraft() {
  const d = entryOf(get().bid)?.draft; if (!d) return;
  if (!confirm(`Throw away the working copy (${d.changes} change(s) since ${d.made})?\n\nVerdicts and notes made since then go with it.`)) return;
  let out;
  try { out = await send('POST', mapi('draft', get().bid!, '/discard')); }
  catch (e) { alert('Discard failed: ' + (e as Error).message); return; }
  updateEntry(out.entry);
  await loadMode();
  toast(`Discarded ${out.discarded} change(s); the blueprint is as it was.`);
}

// the reboot button: the server re-execs itself on the same port (edited Python loads, and this page is built again
// when its code changed); wait for it to answer again, re-indexing takes a while, then reload the page
export async function reboot(setLabel: (s: string | null) => void) {
  setLabel('rebooting…');
  try { await send('POST', '/api/restart'); }
  catch (e) { setLabel(null); alert('Reboot failed: ' + (e as Error).message); return; }
  await new Promise(r => setTimeout(r, 1000));
  for (let i = 0; i < 300; i++) {
    try { const r = await fetch('/api/blueprints', { cache: 'no-store' }); if (r.ok) { location.reload(); return; } } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 1000));
  }
  setLabel(null);
  alert('The server did not come back within 5 minutes; check the terminal it was started from.');
}

// a link to a field (Andrew, 2026-10-24): the form opens in its tab on the thing's page with it selected; and to what
// each tab lists (2026-10-25): #grids/<form>/p4-G3, #blocks/<form>/BT4-2, #groups/<form>/<group name>, a field name
export async function followLink() {
  const [hm, hb, hf] = parseHash();
  if (!hb || !get().list.some(b => b.id === hb)) return;
  if (hm && MODE_IDS.includes(hm as ModeId) && hm !== get().mode) await setMode(hm as ModeId);
  if (hb !== get().bid || get().home.on) await openBlueprint(hb);
  if (hf) def().focus?.(hf);
}

export async function init() {
  try { set({ list: await j('/api/blueprints') }); }
  catch (e) { set({ listError: (e as Error).message }); return; }
  const [hm, hb, hf] = parseHash();
  if (hm && MODE_IDS.includes(hm as ModeId)) set({ mode: hm as ModeId });
  if (hb && get().list.some(b => b.id === hb)) {
    await openBlueprint(hb);
    if (hf) def().focus?.(hf);
  } else await showHome(true);
}
