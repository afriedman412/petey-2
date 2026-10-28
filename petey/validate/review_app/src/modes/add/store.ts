// Add / remove: suggestions and drawn areas -> fields (field_add.py); a field of the blueprint picked to be removed.
// The tab's data and everything it does; Panel.tsx and index.tsx draw it.
import { create } from 'zustand';
import { j, mapi, send } from '../../lib/api';
import type { Entry, PageInfo } from '../../lib/types';
import { localNow, overlap, scrollToSel, type Rect } from '../../lib/util';
import { gotoPage, syncSha, toast, updateEntry } from '../../state/actions';
import { get as app, set as setApp } from '../../state/app';

export interface Suggestion { sid: string; page: number; rect: Rect; source: string; copy?: boolean; what?: string }
export interface Option { key: string; caption?: string | null; page: number; rect: Rect; widget_type?: string; path?: string | null; on_state?: string | null }
export interface NameOption { name: string; source: string; types?: Partial<Pick<Proposal, 'type' | 'semantic_type' | 'pattern'>>; twin?: string }
export interface Proposal {
  kind: 'text' | 'option' | 'group'; page: number; rect: Rect; geometry: string;
  widget?: { page: number; rect: Rect; widget_type: string; path?: string | null; on_state?: string };
  options: Option[]; keyed_by?: string;
  name: string; name_source?: string; name_options: NameOption[]; twin?: string;
  type?: string | null; semantic_type?: string | null; pattern?: string | null; description?: string | null;
  caption?: string | null; page_class?: string | null; entity?: string | null; evidence: string[];
  /** the page's own key for a proposal (React's key; never sent to the server) */
  _k?: number;
  /** the suggestion it came from, and whether n / p brought it (its card gives way to the next one's) */
  _sid?: string; _nav?: boolean;
  [more: string]: unknown;
}
export type Added = Proposal & { when: string };
export interface Dismissed { sid: string; page: number; rect: Rect; source: string; what?: string; when: string }
export interface Removal { name: string; page: number; rect: Rect; when: string; from: string }
export interface Plan { errors: string[]; skipped?: string[]; changes: string[]; applied?: string[]; apply_error?: string | null; entry?: Entry }
export interface AddData {
  path: string; stale?: boolean; has_widgets?: boolean; finder: string; classifier: string; label_model: string;
  pages: PageInfo[]; suggestions: Suggestion[]; fields: { name: string; page: number; rect: Rect }[];
  field_specs?: Record<string, { x_petey_id?: string; type?: string; semantic_type?: string; description?: string }>;
  semantic_types: string[]; added: Added[]; dismissed: Dismissed[]; removed?: Removal[]; plan?: Plan | null;
}

interface State {
  BP: AddData | null;
  props: Proposal[]; notes: string[]; curSid: string | null;
  added: Added[]; dismissed: Dismissed[]; removed: Removal[];
  picked: string | null; PLAN: Plan | null;
  /** the blueprint's fields clicked to remove, collected as the additions are, until "remove all" */
  rmPicks: string[];
  showFields: boolean; showSug: boolean; copies: boolean;
  /** the proposals whose "ask the labeler" is waiting (by _k), and the finder running */
  asking: Record<number, boolean>; finderRunning: boolean;
}

export const useAdd = create<State>(() => ({
  BP: null, props: [], notes: [], curSid: null, added: [], dismissed: [], removed: [], picked: null, PLAN: null, rmPicks: [],
  showFields: true, showSug: true, copies: false, asking: {}, finderRunning: false,
}));
const S = useAdd.getState, put = useAdd.setState;

const bid = () => app().bid!;
let nextK = 1;
const keyed = (ps: Proposal[], sid?: string, nav = false) => ps.map(p => ({ ...p, _k: nextK++, ...(sid ? { _sid: sid, _nav: nav } : {}) }));
const bare = ({ _k: _, _sid: _s, _nav: _n, ...p }: Proposal): Proposal => p as Proposal;

export const isRemoved = (n: string | null) => !!n && S().removed.some(r => r.name === n);
/** The picked box (card i, its box o) under a point on the page, if any. */
export function pickedAt(props: Proposal[], page: number, [x, y]: [number, number]): { i: number; o: number } | null {
  for (let i = 0; i < props.length; i++) {
    const o = boxesOf(props[i]).findIndex(b => b.page === page && b.rect[0] <= x && x <= b.rect[2] && b.rect[1] <= y && y <= b.rect[3]);
    if (o >= 0) return { i, o };
  }
  return null;
}
export const boxesOf = (p: Proposal) => p.kind === 'group' ? p.options.map(o => ({ page: o.page, rect: o.rect })) : [{ page: p.page, rect: (p.widget || p).rect }];
const covered = (s: Suggestion) => S().added.some(a => boxesOf(a).some(b => b.page === s.page && overlap(b.rect, s.rect) >= 0.5));
export function remaining(): Suggestion[] {
  const { BP, dismissed, copies } = S();
  if (!BP) return [];
  const gone = new Set(dismissed.map(d => d.sid));
  return BP.suggestions.filter(s => !gone.has(s.sid) && (!s.copy || copies) && !covered(s));
}
export const NAME_RE = /^[a-z0-9][a-z0-9_]*$/;
const sameBoxes = (p: Proposal, q: Proposal) =>
  boxesOf(p).some(b => boxesOf(q).some(c => c.page === b.page && overlap(b.rect, c.rect) >= 0.5));
/** The cards after a proposal (Andrew, 2026-10-27: "when you select a field to add, it stays added"; a second click
 *  replaced the first): new cards join those waiting, n / p's card (`nav`) takes the place of the last one n / p
 *  brought, and a box already waiting is not proposed twice (`dup`, the cards left out). */
export function mergeProps(old: Proposal[], fresh: Proposal[], nav = false): { props: Proposal[]; dup: number } {
  const keep = nav ? old.filter(p => !p._nav) : old;
  const add = fresh.filter(p => !keep.some(q => sameBoxes(p, q)));
  return { props: [...keep, ...add], dup: fresh.length - add.length };
}

// ------------------------------------------------------------------------------------------------------- loading
export async function load(form: string) {
  const BP: AddData = await j(mapi('add', form));
  curAt = null;
  put({ BP, added: BP.added, dismissed: BP.dismissed, removed: BP.removed || [], props: [], notes: [], curSid: null, picked: null, rmPicks: [], PLAN: BP.plan || null });
}

// ------------------------------------------------------------------------------------------- moving and proposing
// the next suggestion after the one in hand, in reading order; one just added or set aside has left the list, so
// the next is found from where it was (Andrew, 2026-10-20: adding a field on a later page jumped back to page 1)
let curAt: Suggestion | null = null;
const at = (s: Suggestion): [number, number, number] => [s.page, Math.round(s.rect[1]), s.rect[0]];
const before = (a: number[], b: number[]) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
export async function gotoSuggestion(step: number) {
  const list = remaining(); if (!list.length) { put({ notes: ['no suggestions left'] }); return; }
  let i = list.findIndex(s => s.sid === S().curSid);
  if (i >= 0) i = (i + step + list.length) % list.length;
  else {              // from where the last one was, or with none in hand from this page (its first, or its last)
    const k = curAt ? at(curAt) : [app().page, step > 0 ? -Infinity : Infinity, 0], by = [...list].sort((x, y) => before(at(x), at(y)));
    const t = step > 0 ? by.find(s => before(at(s), k) > 0) || by[0] : [...by].reverse().find(s => before(at(s), k) < 0) || by[by.length - 1];
    i = list.indexOf(t);
  }
  await proposeSid(list[i], true);
}
export async function proposeSid(s: Suggestion, nav = false) {
  put({ curSid: s.sid }); curAt = s;
  if (s.page !== app().page) setApp({ page: s.page });
  // a removed field's box with no widget or finder box behind it (field_add.with_removed): proposed as an area drawn
  await propose(s.source === 'removed_box' ? { page: s.page, rect: s.rect } : { page: s.page, sid: s.sid }, nav);
  scrollToSel('.ov.sug.cur');
}
let busy = false;
async function propose(body: { page: number; sid?: string; rect?: Rect }, nav = false) {
  if (busy) return; busy = true; put({ picked: null });
  try {
    const taken = [...S().added, ...S().props].map(a => a.name);
    const r = await send('POST', mapi('add', bid(), '/propose'), { ...body, taken });
    const { props, dup } = mergeProps(S().props, keyed(r.proposals, body.sid, nav), nav);
    put({ props, notes: [...(r.notes || []), ...(dup ? ['that box is proposed already'] : [])] });
  }
  catch (e) { put({ notes: ['proposal failed: ' + (e as Error).message] }); }
  busy = false;
}

/** An area drawn on the page, or a click (no area) on what the mouse went down on. */
export function dragEnd(rect: Rect | null, s: [number, number], target: EventTarget | null) {
  const page = app().page;
  if (rect) { curAt = null; put({ curSid: null, picked: null }); propose({ page, rect }); return; }
  // a click on a box already picked drops it (Andrew, 2026-10-28: "if you click a selected field it removes it"): a
  // group's box leaves the group, the card goes with its last box
  const hit = pickedAt(S().props, page, s);
  if (hit) { if (S().props[hit.i].kind === 'group') dropOption(hit.i, hit.o); else skipProp(hit.i); put({ notes: [] }); return; }
  const d = target instanceof HTMLElement ? target.dataset : undefined;
  if (d && d.sid) { const sg = S().BP!.suggestions.find(x => x.sid === d.sid); if (sg) { proposeSid(sg); return; } }
  // a field of the blueprint: collected to remove, or dropped from the collection; one already recorded for removal
  // opens on its own, to keep it (Andrew, 2026-10-28: "let's collect fields to remove the same way we collect fields
  // to add (with the same buttons)")
  if (d && d.field) { curAt = null; if (isRemoved(d.field)) put({ curSid: null, notes: [], picked: d.field }); else toggleRmPick(d.field); return; }
  if (d && d.added !== undefined) { put({ notes: [`${S().added[+d.added].name} is recorded to be added (remove it from the list below)`] }); return; }
  curAt = null; put({ curSid: null }); propose({ page, rect: [s[0] - 1, s[1] - 1, s[0] + 1, s[1] + 1] });
}

// ------------------------------------------------------------------------------------------- the proposal cards
function editProp(i: number, f: (p: Proposal) => Proposal) {
  put({ props: S().props.map((p, k) => (k === i ? f(p) : p)) });
}
/** a card's box typed in: kept in the proposal at once, so nothing typed is lost */
export function setPropField(i: number, k: 'name' | 'type' | 'semantic_type' | 'pattern' | 'description', v: string) {
  editProp(i, p => ({ ...p, [k]: v || null, ...(k === 'name' ? { name_source: 'hand' } : {}) }));
}
export function setOptField(i: number, o: number, ok: 'key' | 'caption', v: string) {
  editProp(i, p => ({ ...p, options: p.options.map((x, k) => (k === o ? { ...x, [ok]: v } : x)), ...(ok === 'key' ? { keyed_by: 'hand' } : {}) }));
}
/** a box left out of a group; the group goes when none is left */
export function dropOption(i: number, o: number) {
  const p = S().props[i], options = p.options.filter((_, k) => k !== o);
  put({ props: options.length ? S().props.map((q, k) => (k === i ? { ...q, options } : q)) : S().props.filter((_, k) => k !== i) });
}
/** one of the names offered: its types come with it */
export function pickName(i: number, k: number) {
  editProp(i, p0 => {
    const o = p0.name_options[k];
    const { type: _t, semantic_type: _s, pattern: _p, twin: _w, ...p } = p0;
    return { ...p, name: o.name, name_source: o.source, ...(o.types || {}), ...(o.twin ? { twin: o.twin } : {}) } as Proposal;
  });
}
export const skipProp = (i: number) => put({ props: S().props.filter((_, k) => k !== i) });

const indexOfK = (k: number | undefined) => S().props.findIndex(p => p._k === k);
// a text box made a checkbox, or back (2026-10-20): renamed (_ind) and typed again on the server
export async function switchKind(i: number, kind: string) {
  const { props, added } = S(), k = props[i]._k;
  const taken = [...added.map(a => a.name), ...props.filter((_, n) => n !== i).map(q => q.name)];
  try {
    const r = await send('POST', mapi('add', bid(), '/kind'), { proposal: bare(props[i]), kind, taken });
    const at = indexOfK(k);                       // the card may have gone meanwhile (cancelled, added)
    if (at >= 0) editProp(at, () => ({ ...r.proposal, _k: k }));
  } catch (e) { put({ notes: ['could not change the box: ' + (e as Error).message] }); }
}
export async function askLabeler(i: number) {
  const k = S().props[i]._k!;
  put({ asking: { ...S().asking, [k]: true } });
  try {
    const r = await send('POST', mapi('add', bid(), '/labeler'), { proposal: bare(S().props[i]) });
    const at = indexOfK(k);
    if (at < 0) return;
    if (r.name) {
      const { props, added } = S(), taken = new Set([...added.map(a => a.name), ...props.filter((_, n) => n !== at).map(q => q.name)]);
      let n = r.name, c = 2; while (taken.has(n)) n = `${r.name}_${c++}`;
      editProp(at, p => ({ ...p, name_options: p.name_options.filter(o => o.source !== 'labeler').concat([{ name: n, source: 'labeler', types: {} }]),
        name: n, name_source: 'labeler' }));
    } else put({ notes: ['the labeler returned no name'] });
  } catch (e) { put({ notes: ['labeler failed: ' + (e as Error).message] }); }
  finally { const a = { ...S().asking }; delete a[k]; put({ asking: a }); }
}

export const addAll = () => addProps(S().props.map((_, i) => i));
export function addProps(idx: number[]) {
  const { props } = S();
  const bad = idx.map(i => props[i]).filter(p => !NAME_RE.test(p.name || ''));
  if (bad.length) { put({ notes: [`not a field name: ${bad.map(p => p.name).join(', ')}`] }); return; }
  const now = localNow();
  const left = props.filter((_, i) => !idx.includes(i));
  put({ added: [...S().added, ...idx.map(i => ({ ...bare(props[i]), when: now }))], props: left });
  if (!left.length) { put({ notes: [] }); save().then(() => { if (S().curSid && remaining().length) gotoSuggestion(1); else put({ curSid: null }); }); }
  else save();
}
export const cancel = () => put({ props: [], notes: [], picked: null, rmPicks: [] });
/** the blueprint field picked to remove, put away; the cards waiting stay */
export const closePicked = () => put({ picked: null });

// ------------------------------------------------------------------------------------------------------ removing
export function toggleRmPick(name: string) {
  const ps = S().rmPicks;
  put({ curSid: null, notes: [], picked: null, rmPicks: ps.includes(name) ? ps.filter(x => x !== name) : [...ps, name] });
}
/** the collected fields (or `names` of them, one card's "remove this field") recorded for removal, in one save */
export function removeAll(names = S().rmPicks) {
  const { rmPicks, BP, removed } = S(); if (!names.length) return;
  const now = localNow(), add = names.map(n => BP!.fields.find(x => x.name === n)).filter(f => f && !isRemoved(f.name))
    .map(f => ({ name: f!.name, page: f!.page, rect: f!.rect, when: now, from: 'add' }));
  put({ removed: [...removed, ...add], rmPicks: rmPicks.filter(n => !names.includes(n)) });
  save();
}
export function toggleRemove() {
  const { picked, BP, removed } = S();
  if (!picked) return;
  if (isRemoved(picked)) put({ removed: removed.filter(r => r.name !== picked) });
  else { const f = BP!.fields.find(x => x.name === picked)!; put({ removed: [...removed, { name: picked, page: f.page, rect: f.rect, when: localNow(), from: 'add' }] }); }
  save();
}

// ------------------------------------------------------------------------------------------- the lists below
export function unAdd(i: number) { put({ added: S().added.filter((_, k) => k !== i) }); save(); }
export function keepRemoved(i: number) { put({ removed: S().removed.filter((_, k) => k !== i) }); save(); }
export function unDismiss(i: number) { put({ dismissed: S().dismissed.filter((_, k) => k !== i) }); save(); }
/** a field recorded for removal, picked again (its page shown) */
export function pickRemoved(i: number) {
  const x = S().removed[i]; put({ picked: x.name });
  if (x.page !== app().page) gotoPage(x.page);
}
export const goto = (p: number) => { if (p !== app().page) gotoPage(p); };

// ------------------------------------------------------------------------------------------------------- saving
// a save goes into the working copy when it plans cleanly: added fields become fields, removed ones go, and the
// page reads the copy again (the suggestions follow)
export async function save() {
  const form = bid();
  try {
    const { added, dismissed, removed } = S();
    const PLAN: Plan = await send('PUT', mapi('add', form, '/record'), { added, dismissed, removed });
    put({ PLAN, BP: { ...S().BP!, stale: false } }); updateEntry(PLAN.entry);
    if (PLAN.applied && PLAN.applied.length) {
      const d: AddData = await j(mapi('add', form));
      const picked = S().picked;
      put({ BP: d, added: d.added, dismissed: d.dismissed, removed: d.removed || [], picked: picked && !(d.field_specs || {})[picked] ? null : picked });
      await syncSha();
      toast(PLAN.applied.length === 1 ? `Working copy: ${PLAN.applied[0]}` : `${PLAN.applied.length} changes went into the working copy.`);
    }
    if (PLAN.apply_error) put({ notes: ['not applied: ' + PLAN.apply_error] });
  }
  catch (e) { alert('Save failed: ' + (e as Error).message); }
}
export async function runFinder() {
  put({ finderRunning: true });
  try { const BP: AddData = await send('POST', mapi('add', bid(), '/finder')); put({ BP, added: BP.added, dismissed: BP.dismissed, removed: BP.removed || [] }); }
  catch (e) { put({ notes: ['finder failed: ' + (e as Error).message] }); }
  finally { put({ finderRunning: false }); }
}

// ---------------------------------------------------------------------------------------------------------- keys
export const setShow = (p: Partial<Pick<State, 'showFields' | 'showSug' | 'copies'>>) => put(p);
export function key(e: KeyboardEvent): boolean {
  const { props, picked, showFields, showSug } = S();
  if (e.key === 'n') gotoSuggestion(1);
  else if (e.key === 'p') gotoSuggestion(-1);
  else if ((e.key === 'Enter' || e.key === 'a') && props.length) addAll();   // a: as Review's accept
  else if (e.key === 'Escape') cancel();
  else if (e.key === 'd' && S().rmPicks.length) removeAll();
  else if (e.key === 'd' && picked) toggleRemove();
  else if (e.key === 'f') put({ showFields: !showFields });
  else if (e.key === 's') put({ showSug: !showSug });
  else return false;
  return true;
}
