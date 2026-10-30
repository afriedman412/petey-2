// Grids (grid_check.py, 2026-10-16): every numbered grid, outlined in dots (option groups are dashed); one click checks
// and validates one: the code check, then the resolver (the name-check model against the shared caption), then Jev for
// a column it cannot settle, then Opus (its proposals land in the chat to tick). As in Groups (Andrew, 2026-10-22):
// drag on an empty part of the page to draw a grid, drag a grid onto another to combine them. A selected grid's card
// lists its columns and rows, each with what its standardize button would do, or why there is nothing it can do ("it
// often doesn't work and never says why clearly"): grid_check.preview, a dry run of every button.
// The tab's data and everything it does; Panel.tsx and index.tsx draw it.
import { create as zustand } from 'zustand';
import { j, mapi, send } from '../../lib/api';
import type { Entry, PageInfo } from '../../lib/types';
import { fileStem, GROUP_COLORS, scrollToSel, type Rect } from '../../lib/util';
import { gotoPage, loadMode, setMode, toast, updateEntry } from '../../state/actions';
import { get as app } from '../../state/app';
import { addGridTurn, type ChatOut } from '../../state/chat';

export interface Cell { name: string; rect?: Rect | null; accepted?: boolean }
export interface Table {
  id: string; page: number; bbox: Rect; rows: number; cols: number; cells: Cell[];
  accepted: number; body?: number | null; on_pattern?: boolean; why?: string; title?: string;
  source?: 'person' | 'combined' | 'edited' | string; from?: string[];
  by?: 'names' | 'geometry' | 'both' | null;      // which test found a finder grid (2026-10-27)
  jev?: number | null;                             // Jev's "is it a table" on a geometry-only grid
  dismissed?: boolean; aside_why?: string; reading?: 'rows' | 'cols' | string;
}
export interface GridsData { path: string; pages: PageInfo[]; tables: Table[] }

/** What a standardize or renumber button would do: its renames, the cells of other columns or rows it takes in, and
 *  why it leaves the rest. */
export interface Plan { renames: [string, string][]; pulled: string[]; left: string[] }
export interface Position {
  pos: number; wordings: [string, number][]; plan?: Plan | null; caption?: string | null; locked?: boolean; off?: number;
  alt?: { wording: string; plan: Plan } | null;
}
export interface Line {
  line: number; label?: string | null; number?: string | number | null; numbers?: (string | number)[];
  expect?: string | number | null; note?: string | null; cells: number; plan?: Plan | null;
}
export interface Preview {
  error?: string; all?: Plan | null; keyed?: boolean; pos_axis?: 'col' | 'row'; positions: Position[]; lines: Line[];
  summary?: string; aside?: { row: number; why: string }[];
}
export interface Result { status: string; steps?: string[]; left?: string[]; entry?: Entry; proposals?: ChatOut; id?: string; cells?: number }

/** A column's wording or a row's label being edited in place: which, and what is typed. */
export interface Editing { tid: string; kind: 'pos' | 'line'; at: number; val: string; typed: string }

interface State {
  GD: GridsData | null;
  /** the form GD is for: everything below is keyed by grid id, and ids (p1-G1) repeat across forms */
  gdFor: string | null;
  selected: string | null;
  results: Record<string, Result>;
  PV: Record<string, Preview>;
  busy: Record<string, boolean>;
  pvBusy: Record<string, boolean>;
  /** the token of the check running on a grid; null once it is answered or cancelled */
  runs: Record<string, object | null>;
  editing: Editing | null;
}

export const useGrids = zustand<State>(() => ({
  GD: null, gdFor: null, selected: null, results: {}, PV: {}, busy: {}, pvBusy: {}, runs: {}, editing: null,
}));
const S = useGrids.getState, put = useGrids.setState;
const setBusy = (tid: string, on: boolean) => { const busy = { ...S().busy }; if (on) busy[tid] = true; else delete busy[tid]; put({ busy }); };
const setRun = (tid: string, token: object | null) => put({ runs: { ...S().runs, [tid]: token } });
const setResult = (tid: string, out: Result) => put({ results: { ...S().results, [tid]: out } });

// ------------------------------------------------------------------------------------------------ the grids' words
export const prov = (t: Table) => t.source === 'person' ? 'drawn by you' : t.source === 'combined' ? `combined from ${(t.from || []).join(' + ')}`
  : t.source === 'edited' ? `the finder's ${(t.from || []).join(' + ')}, less fields another grid took`
  // the geometric test is tentative (2026-10-27): a grid only it found says so, for keeping or "not a grid"
  : t.by === 'geometry' ? `found by the finder (geometry only, tentative${t.jev != null ? `; Jev ${t.jev.toFixed(2)}` : ''})`
  : t.by === 'both' ? 'found by the finder (names and geometry)'
  : 'found by the finder';
export const live = () => { const GD = S().GD; return GD ? GD.tables.filter(t => !t.dismissed) : []; };   // "not a grid": hidden, restorable
export const onPage = (p: number) => live().filter(t => t.page === p);
export const asidePage = (p: number) => { const GD = S().GD; return GD ? GD.tables.filter(t => t.dismissed && t.page === p) : []; };
export const done = (t: Table) => t.accepted >= (t.body ?? t.cells.length);              // every cell accepted (a totals row aside)
export const colorOf = (t: Table) => GROUP_COLORS[Math.max(0, S().GD!.tables.findIndex(x => x.id === t.id)) % GROUP_COLORS.length];
export const ref = (tid: string) => `${fileStem(S().GD?.path || app().bid || '')}_${tid}`;
const T = (tid: string): Partial<Table> => S().GD?.tables.find(x => x.id === tid) || {};
const posWord = (t: Partial<Table>) => t.reading === 'rows' ? 'row' : 'column';
const lineWord = (t: Partial<Table>) => t.reading === 'rows' ? 'column' : 'row';
/** the other columns or rows a standardize (positions) or renumber (lines) button takes cells from, as the grid reads */
export const pulledWord = (tid: string, what: string) => (what === 'renumber' ? lineWord(T(tid)) : posWord(T(tid))) + 's';
// the code check's reason in the grid's own terms: positions are its columns (or rows, read the other way round)
function plainWhy(t: Table) {
  if (t.on_pattern) return 'on pattern';
  return String(t.why || '').replace(/\bposition (\d+)/g, `${posWord(t)} $1`).replace(/\bline (\d+)/g, `${lineWord(t)} $1`)
    .replace(/\blines numbered/g, `${lineWord(t)}s numbered`).replace(/\ba line without/g, `a ${lineWord(t)} without`)
    .replace(/_N(?=_|$)/g, '_#');
}
export const status = (t: Table) => done(t) ? 'validated' : t.on_pattern ? 'on pattern, not validated yet' : plainWhy(t);
// the code's "position 3" / "line 2" as the page shows them: a column / row (or the other way round)
export const say = (t: Partial<Table>, text: string) => String(text).replace(/\bposition (\d+)/g, `${posWord(t)} $1`).replace(/\bline (\d+)/g, `${lineWord(t)} $1`)
  .replace(/\bevery position\b/g, `every ${posWord(t)}`).replace(/_N(?=_|$)/g, '_#');
export const sayFor = (tid: string, text: string) => say(T(tid), text);
export const renameList = (rs: [string, string][], n = 12) => rs.slice(0, n).map(([o, x]) => `${o} -> ${x}`).join('\n') + (rs.length > n ? `\n... ${rs.length - n} more` : '');
// a field is in one grid at most (2026-10-20): what it left when it joined this one
const leftNote = (out: { left?: string[] }) => (out.left || []).length ? ' ' + out.left!.join('; ') + '.' : '';

// ------------------------------------------------------------------------------------------------------- loading
// each read of the tab's data starts a new generation of previews: one asked for before it (a rename since, another
// form) is dropped when it lands, not kept over the new names (2026-10-26)
let pvGen = 0;
export async function load(bid: string) {
  const GD: GridsData = await j(mapi('grids', bid));
  pvGen++;
  // another form: nothing of the last one's grids carries over, its ids being this one's too (2026-10-26: a check's
  // "last:" line showed on the next form's grid of the same id)
  const fresh = S().gdFor !== bid;
  let selected = fresh ? null : S().selected;
  if (selected && !GD.tables.some(t => t.id === selected && !t.dismissed)) selected = null;
  put({ GD, gdFor: bid, PV: {}, pvBusy: {}, selected,
    ...(fresh ? { results: {}, busy: {}, runs: {}, editing: null } : {}) });
  if (selected) loadPreview(selected);
}
// the old page's reload() kept the results across loadMode(); load() leaves them alone, so they stay
const reload = () => loadMode();

export function select(tid: string) {
  const t = live().find(x => x.id === tid);
  put({ selected: tid, ...(S().editing?.tid !== tid ? { editing: null } : {}) });
  if (t && t.page !== app().page) gotoPage(t.page);
  if (t) loadPreview(tid);
  scrollToSel(`.gtcard[data-t="${CSS.escape(tid)}"]`, 'nearest');
}
export const deselect = () => put({ selected: null, editing: null });

export async function loadPreview(tid: string) {
  if (S().PV[tid] || S().pvBusy[tid]) return;
  const gen = pvGen;
  put({ pvBusy: { ...S().pvBusy, [tid]: true } });
  let pv: Preview;
  try { pv = await send('POST', mapi('grids', app().bid!, '/preview'), { table: tid }); }
  catch (e) { pv = { error: (e as Error).message, positions: [], lines: [] }; }
  if (gen !== pvGen) return;                     // read again meanwhile: this one is stale
  const pvBusy = { ...S().pvBusy }; delete pvBusy[tid];
  put({ PV: { ...S().PV, [tid]: pv }, pvBusy });
}

// ------------------------------------------------------------------------------------------- editing in place
// a column's wording or a row's label edited in place (Andrew, 2026-10-23: "can we add the ability to edit grid
// labels ... from the grid page"): the column through standardize with the wording typed, the row through relabel
export function startEdit(tid: string, kind: 'pos' | 'line', at: number, val: string) { put({ editing: { tid, kind, at, val, typed: val } }); }
export function typeEdit(typed: string) { const e = S().editing; if (e) put({ editing: { ...e, typed } }); }
export const cancelEdit = () => put({ editing: null });
export function applyEdit() {
  const e = S().editing; if (!e) return;
  put({ editing: null });
  const v = e.typed.trim();
  if (!v || v === e.val) return;
  if (e.kind === 'pos') standardize(e.tid, e.at, null, v);
  else relabel(e.tid, e.at, v);
}

// ---------------------------------------------------------------------------------------------------- the actions
export async function relabel(tid: string, line: number, label: string) {
  const form = app().bid!; setBusy(tid, true);
  let out: Result;
  try { out = await send('POST', mapi('grids', form, '/relabel'), { table: tid, line: +line, label }); }
  catch (e) { out = { status: 'error', steps: ['relabel failed: ' + (e as Error).message] }; }
  setBusy(tid, false); if (app().bid !== form) return;
  setResult(tid, out); if (out.entry) updateEntry(out.entry);
  await reload();
  toast(`${tid}: ${out.status}.` + ((out.left || []).length ? ` ${out.left!.length} left, see the card.` : ''));
}

export async function standardize(tid: string, pos?: number | null, line?: number | null, wording?: string | null) {
  const form = app().bid!; setBusy(tid, true);
  let out: Result;
  try { out = await send('POST', mapi('grids', form, '/standardize'), { table: tid, pos: pos ?? null, line: line ?? null, wording: wording || null }); }
  catch (e) { out = { status: 'error', steps: ['standardize failed: ' + (e as Error).message] }; }
  setBusy(tid, false); if (app().bid !== form) return;
  setResult(tid, out); if (out.entry) updateEntry(out.entry);
  await reload();
  toast(`${tid}: ${out.status}.` + ((out.left || []).length ? ` ${out.left!.length} left, see the card.` : ''));
}

export async function create(rect: Rect) {
  let out;
  try { out = await send('POST', mapi('grids', app().bid!, '/create'), { page: app().page, rect }); }
  catch (e) { alert('Could not make a grid: ' + (e as Error).message); return; }
  put({ selected: out.id }); await reload(); loadPreview(out.id);
  toast(`New grid ${out.id}: ${out.cells} fields.${leftNote(out)}`);
}

export async function combine(ids: string[]) {
  let out;
  try { out = await send('POST', mapi('grids', app().bid!, '/combine'), { tables: ids }); }
  catch (e) { alert('Could not combine: ' + (e as Error).message); return; }
  put({ selected: out.id }); await reload(); loadPreview(out.id);
  toast(`${ids.join(' + ')} combined into ${out.id} ("not a grid" on it gives them back).${leftNote(out)}`);
}

export async function setAside(tid: string, on: boolean) {
  let out;
  try { out = await send('POST', mapi('grids', app().bid!, '/dismiss'), { table: tid, on }); }
  catch (e) { alert('Could not save: ' + (e as Error).message); return; }
  if (on && S().selected === tid) put({ selected: null });
  await reload();
  toast((on ? `${tid}: not a grid.` : `${tid} restored.`) + leftNote(out));
}

// a check runs on while you go to another tab or page; its result brings this tab back up at the grid's page
// (2026-10-20). Cancel stops it (2026-10-21): the card is free at once, the server writes nothing after it, and the
// check stops waiting for the server's answer, so "check & validate all" stops at once too (2026-10-26)
const cancels = new Map<string, () => void>();
export async function stop(tid: string) {
  if (!S().busy[tid]) return;
  cancels.get(tid)?.(); cancels.delete(tid);
  setRun(tid, null); setBusy(tid, false);
  setResult(tid, { status: 'cancelled', steps: ['cancelled: nothing written after the cancel'] });
  try { await send('POST', mapi('grids', app().bid!, '/cancel'), { table: tid }); } catch { /* nothing to undo */ }
  toast(`${tid}: check cancelled.`);
}

export async function run(tid: string): Promise<Result> {
  const form = app().bid!, pg = app().page, token = {};
  setRun(tid, token); setBusy(tid, true);
  let out: Result;
  const cancelled = new Promise<Result>(res => cancels.set(tid, () => res({ status: 'cancelled' })));
  const check = send<Result>('POST', mapi('grids', form, '/check'), { table: tid })
    .catch(e => ({ status: 'error', steps: ['the check failed: ' + (e as Error).message] }));
  out = await Promise.race([check, cancelled]);
  if (cancels.get(tid) && S().runs[tid] === token) cancels.delete(tid);
  if (S().runs[tid] !== token) { if (out.entry && app().bid === form) updateEntry(out.entry); return { status: 'cancelled' }; }
  setRun(tid, null); setBusy(tid, false); if (app().bid !== form) return out;
  setResult(tid, out); if (out.entry) updateEntry(out.entry);
  // Opus: its proposals go to the chat, ticked, nothing applied
  if (out.proposals) addGridTurn(form, `grids: ${tid} (Opus)`, pg, out.proposals);
  if (app().mode === 'grids') await loadMode(); else await setMode('grids');
  put({ selected: tid }); loadPreview(tid);
  const t = live().find(x => x.id === tid);
  if (t && t.page !== app().page) gotoPage(t.page);
  toast(`${tid}: ${out.status}.`);
  return out;
}

/** "check & validate all" on the page: stops if you open another form, or a check is cancelled. */
export async function runAll() {
  const form = app().bid;
  for (const t of onPage(app().page)) {
    if (app().bid !== form) break;
    const out = await run(t.id);
    if (out && out.status === 'cancelled') break;
  }
}

// ---------------------------------------------------------------------------------------------------------- keys
export function key(e: KeyboardEvent): boolean {
  const ts = live(), { selected } = S(), i = ts.findIndex(t => t.id === selected);
  if (e.key === 'n' || e.key === 'p') { const t = ts[(i + (e.key === 'n' ? 1 : -1) + ts.length) % ts.length]; if (t) select(t.id); return true; }
  if (e.key === 'Enter' && selected) { run(selected); return true; }
  if ((e.key === 'Delete' || e.key === 'Backspace') && selected) { setAside(selected, true); return true; }
  if (e.key === 'Escape' && selected) { deselect(); return true; }
  return false;
}

// a link's grid: by its id, or the grid holding a field; one set aside opens its page (its line under "Not grids")
export function focus(k: string) {
  const GD = S().GD; if (!GD) return;
  const t = GD.tables.find(x => x.id === k) || live().find(x => x.cells.some(c => c.name === k));
  if (t && t.dismissed) gotoPage(t.page); else if (t) select(t.id);
}
