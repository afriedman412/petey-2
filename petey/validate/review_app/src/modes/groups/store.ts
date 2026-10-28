// Groups: confirm option groups, drag boxes to regroup; combine text fields (group_review.py).
// The tab's data and everything it does; Panel.tsx and index.tsx draw it. An edit works on a copy of the units (the
// old page's code, run on the copy) and puts the copy into the store; the undo stack keeps JSON snapshots as before.
import { create } from 'zustand';
import { j, mapi, send } from '../../lib/api';
import type { PageInfo } from '../../lib/types';
import { afterPaint, localNow, store, type Rect } from '../../lib/util';
import { loadMode, toast, updateEntry } from '../../state/actions';
import { get as app, set as setApp } from '../../state/app';

/** One box: an option of a group (`<field>::<key>`), a loose option box (`<field>`), or a text field (`kind: text`). */
export interface Item {
  id: string; field: string; key: string | null; kind?: 'text'; page: number; rect: Rect;
  caption?: string | null; on_state?: string | null; path?: string | null; widget_type?: string | null;
  appearances?: number | null; type?: string | null; semantic_type?: string | null; description?: string | null;
}
/** A group, a loose box (a group of one boolean), or a combined text field (`kind: text`). */
export interface Unit {
  uid: number; name: string; type: string; items: string[]; origin?: string | null; confirmed?: boolean;
  description?: string | null; locked?: string; kind?: 'text'; when?: string; name_from?: string;
  captions?: Record<string, string>;
}
export interface Suggestion { page: number; items: string[]; why: string; name?: string | null; captions?: (string | null)[] }
export interface Plan { changes: string[]; errors: string[] }
export interface GroupsData {
  id: string; path: string; blank?: string | null; sha?: string; pages: PageInfo[];
  items: Record<string, Item>; units: Omit<Unit, 'uid'>[];
  base: { name: string; type: string; items: string[] }[];
  other_names: string[]; codes?: Record<string, string>;
  suggested?: Suggestion[]; auto_grouped?: { name: string; page: number }[];
  info: { stale?: boolean; applied?: { when: string } | null; updated?: string; suggest_error?: string };
}
/** Where a box or a unit was dropped: on a box, on a unit (a hull or a card), on the tray. */
export interface Target { item?: string; unit?: number; tray?: boolean; inTray?: boolean }

interface State {
  BP: GroupsData | null;
  units: Unit[];
  selected: number | null;
  unconfOnly: boolean;
  showText: boolean;
  undoStack: string[];
  /** the boxes picked for "group selected" */
  picked: Set<string>;
  PLAN: Plan | null;
  /** requests in flight per unit */
  busy: Record<number, { label?: boolean; caps?: boolean }>;
  notes: string[];
  /** "rescan page" running: the number of groups it rescans (0 when not) */
  rescanning: number;
  /** the box hovered in the sidebar (an item id), lit on the page */
  hover: string | null;
}

export const useGroups = create<State>(() => ({
  BP: null, units: [], selected: null, unconfOnly: false, showText: store('gr_text') !== '0',
  undoStack: [], picked: new Set(), PLAN: null, busy: {}, notes: [], rescanning: 0, hover: null,
}));
const S = useGroups.getState, put = useGroups.setState;

let nextUid = 1, planTimer: ReturnType<typeof setTimeout> | undefined;

export const PALETTE = ['#1a73e8', '#d93025', '#188038', '#e37400', '#9334e6', '#c5221f', '#b06000', '#3f51b5', '#a142f4', '#795548'];
export const item = (id: string) => S().BP!.items[id];
export const unitOf = (id: string, us = S().units) => us.find(u => u.items.includes(id));
export const unitByUid = (uid: number | null | undefined, us = S().units) => us.find(u => u.uid === uid);
export const isText = (u?: Unit | null) => !!u && u.kind === 'text';
export const isTextItem = (id: string) => item(id).kind === 'text';
export const optUnits = (us = S().units) => us.filter(u => !isText(u));
export const isGroup = (u: Unit) => isText(u) || u.items.length > 1 || u.type !== 'boolean';
const orderKey = (it: Item) => [it.page, Math.round(it.rect[1] / 6), it.rect[0]];
const cmpKey = (a: number[], b: number[]) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i]; return 0; };
export const firstItem = (u: Unit, items = S().BP!.items) => u.items.map(id => items[id]).sort((a, b) => cmpKey(orderKey(a), orderKey(b)))[0];
function sortUnits(us: Unit[], items = S().BP!.items) {
  for (const u of us) u.items.sort((a, b) => cmpKey(orderKey(items[a]), orderKey(items[b])));
  us.sort((a, b) => cmpKey(orderKey(firstItem(a, items)), orderKey(firstItem(b, items))));
}
export const onPage = (u: Unit, p = app().page) => u.items.some(id => item(id).page === p);
export const label = (id: string, us = S().units) => {
  const it = item(id), u = unitOf(id, us), c = u && u.captions && u.captions[id];
  return it.kind === 'text' ? it.field : (c || it.caption || (it.key ?? it.field));
};
export const looseText = (p = app().page, us = S().units) =>
  Object.values(S().BP!.items).filter(it => it.kind === 'text' && it.page === p && !unitOf(it.id, us));
export function colorOf(u: Unit, us = S().units, p = app().page) {
  if (isText(u)) return 'var(--txt)';
  if (!isGroup(u)) return 'var(--orphan)';
  const gs = optUnits(us).filter(x => isGroup(x) && onPage(x, p)); const i = gs.indexOf(u);
  return PALETTE[(i < 0 ? 0 : i) % PALETTE.length];
}
export const baseOf = (u: Unit) => !isText(u) && u.origin ? S().BP!.base.find(b => b.name === u.origin) : null;
export function status(u: Unit) {
  const b = baseOf(u); if (!b) return 'new';
  return b.name === u.name && b.type === u.type && [...b.items].sort().join('|') === [...u.items].sort().join('|') ? 'as blueprint' : 'edited';
}
/** `except`: the unit (by uid) whose own name does not count */
function takenNames(us: Unit[], except: number | null) {
  const members = new Set(us.filter(isText).flatMap(u => u.items));      // combined text fields free their names
  return new Set([...S().BP!.other_names.filter(n => !members.has(n)), ...us.filter(u => u.uid !== except).map(u => u.name)]);
}
function uniqueName(us: Unit[], base: string, except: number | null) { const taken = takenNames(us, except); let n = base, k = 2; while (taken.has(n)) n = `${base}_${k++}`; return n; }
function suggestName(us: Unit[], ids: string[]) {
  const parts = ids.map(id => item(id).field.split('_')), pre: string[] = [];
  for (let i = 0; i < Math.min(...parts.map(p => p.length)); i++) { if (parts.every(p => p[i] === parts[0][i])) pre.push(parts[0][i]); else break; }
  let base = pre.join('_');
  if (!/^[a-z][a-z0-9_]*$/.test(base) || base.length < 3) base = `group_p${item(ids[0]).page}`;
  return uniqueName(us, base, null);
}
// a combined text field's name: the members' shared leading words without part / line numbers, plus a shared suffix
function suggestTextName(us: Unit[], ids: string[]) {
  const parts = ids.map(id => item(id).field.split('_')), pre: string[] = [];
  for (let i = 0; i < Math.min(...parts.map(p => p.length)); i++) { if (parts.every(p => p[i] === parts[0][i])) pre.push(parts[0][i]); else break; }
  while (pre.length && (/^\d+$/.test(pre[pre.length - 1]) || ['part', 'pt', 'line', 'ln', 'row', 'col'].includes(pre[pre.length - 1]))) pre.pop();
  const last = parts.map(p => p[p.length - 1]);
  const suffix = last.every(x => x === last[0]) && ['txt', 'nm', 'amt', 'dt', 'cd', 'num'].includes(last[0]) && pre[pre.length - 1] !== last[0] ? last[0] : null;
  let base = pre.join('_') + (suffix ? '_' + suffix : '');
  if (!pre.length || !/^[a-z][a-z0-9_]*$/.test(base)) base = item(ids[0]).field + '_combined';
  return uniqueName(us, base, null);
}
export function nameCheck(u: Unit) {
  return !/^[a-z0-9][a-z0-9_]*$/.test(u.name) ? 'not a field name (lower case, digits, underscores)' : takenNames(S().units, u.uid).has(u.name) ? 'another field already has this name' : '';
}
export function note(msg: string) { put({ notes: [msg] }); }

// ------------------------------------------------------------------------------------------- editing the units
/** the units to edit: a copy, put into the store by afterEdit */
const draft = (): Unit[] => JSON.parse(JSON.stringify(S().units));
const drop = (us: Unit[], u: Unit) => { const i = us.indexOf(u); if (i >= 0) us.splice(i, 1); };
const strip = (us: Unit[]) => us.map(({ uid: _uid, ...u }) => u);

// a step undone: the units before it, and the boxes it recorded as not a group (an ungroup), so the undo takes that
// record back too (Andrew, 2026-10-26: else the finder never suggested the group again)
function snapshot(notGroup?: string[]) {
  const st = [...S().undoStack, JSON.stringify({ units: S().units, notGroup })];
  if (st.length > 200) st.shift();
  put({ undoStack: st });
}
export function undo() {
  const st = S().undoStack; if (!st.length) return;
  const { units: us, notGroup }: { units: Unit[]; notGroup?: string[] } = JSON.parse(st[st.length - 1]);
  put({ undoStack: st.slice(0, -1) });
  if (notGroup) send('PUT', mapi('groups', app().bid!, '/notgroup'), { items: notGroup, on: false })
    .catch(e => note('could not take back the record of the boxes as not a group: ' + (e as Error).message));
  let sel = S().selected;
  if (!unitByUid(sel, us)) sel = optUnits(us).length ? optUnits(us)[0].uid : null;
  afterEdit(us, sel);
}
async function afterEdit(us: Unit[], selected = S().selected) {
  sortUnits(us);
  put({ units: us, selected, notes: [] });
  await save();
  schedulePlan();
}
function detach(us: Unit[], id: string) {
  const u = unitOf(id, us)!; u.items = u.items.filter(x => x !== id); u.confirmed = false;
  if (!u.items.length || (isText(u) && u.items.length < 2)) drop(us, u);   // a combination of one is no combination
  return u;
}

// select several boxes, then group them in one step (Andrew, 2026-10-07: instead of dragging each box): Shift- or
// Cmd-click toggles a box, dragging across an area selects the option boxes in it (Shift+drag adds); "group selected"
// or g makes them one group. They leave the units they were in; a unit emptied that way hands its name and place
// to the new group. Option boxes only (text combining stays drag-and-drop).
export function togglePick(id: string) {
  if (isTextItem(id)) return note('Only option boxes can be selected for grouping.');
  const p = new Set(S().picked);
  if (p.has(id)) p.delete(id); else p.add(id);
  put({ picked: p });
}
export const clearPicked = () => put({ picked: new Set() });
// an option hovered anywhere in the sidebar lights its box on the page (Andrew, 2026-10-27: "rolling over a group
// option anywhere in the groups tab highlights the corresponding field")
export const setHover = (id: string | null) => { if (S().hover !== id) put({ hover: id }); };
export const hoverProps = (id: string) => ({ onMouseEnter: () => setHover(id), onMouseLeave: () => setHover(null) });
export function selectArea(r: Rect, add: boolean) {
  const p = add ? new Set(S().picked) : new Set<string>(), page = app().page;
  for (const it of Object.values(S().BP!.items)) {
    const cx = (it.rect[0] + it.rect[2]) / 2, cy = (it.rect[1] + it.rect[3]) / 2;
    if (it.page === page && it.kind !== 'text' && cx >= r[0] && cx <= r[2] && cy >= r[1] && cy <= r[3]) p.add(it.id);
  }
  put({ picked: p });
  toast(`${p.size} box${p.size === 1 ? '' : 'es'} selected${p.size > 1 ? ': g groups them, Esc clears' : ''}`);
}
export function groupPicked() {
  const ids = [...S().picked].filter(id => S().BP!.items[id]);
  if (ids.length < 2) return note('Select two or more boxes first (Shift-click, or drag across an area).');
  const us = draft();
  if (ids.some(id => unitOf(id, us)?.locked)) return note('A selected box belongs to a locked group.');
  const same = unitOf(ids[0], us);
  if (same && same.items.length === ids.length && ids.every(id => unitOf(id, us) === same)) { put({ picked: new Set(), selected: same.uid }); return; }
  snapshot();
  const from = new Map<Unit, number>();                       // source unit -> boxes taken from it
  for (const id of ids) { const u = unitOf(id, us); if (u) from.set(u, (from.get(u) || 0) + 1); }
  for (const id of ids) if (unitOf(id, us)) detach(us, id);
  const heir = [...from.keys()].filter(u => !us.includes(u) && isGroup(u)).sort((a, b) => from.get(b)! - from.get(a)!)[0];
  const g: Unit = {
    uid: nextUid++, name: heir ? heir.name : suggestName(us, ids), type: heir && heir.type !== 'boolean' ? heir.type : 'category',
    items: ids, origin: heir ? heir.origin : null, confirmed: false,
  };
  us.push(g); put({ picked: new Set() });
  afterEdit(us, g.uid);
  toast(`${ids.length} boxes grouped: ${g.name} (z undoes)`);
}

const MIX = 'text boxes combine only with text boxes; option boxes group only with option boxes';
const PAGES = 'a combined text field stays on one page';
function moveText(id: string, target: Target) {
  const us = draft(), src = unitOf(id, us);
  if (target.inTray) target = { tray: true };               // anywhere in the tray means out
  if (target.tray) { if (!src) return; snapshot(); detach(us, id); return afterEdit(us, us.includes(src) ? src.uid : S().selected); }
  let t: Unit | undefined;
  if (target.item) {
    if (target.item === id) return;
    if (!isTextItem(target.item)) return note(MIX);
    if (item(target.item).page !== item(id).page) return note(PAGES);
    t = unitOf(target.item, us);
    if (!t) {                                             // loose onto loose: a new combined field
      snapshot(); if (src) detach(us, id);
      const u: Unit = { uid: nextUid++, kind: 'text', name: suggestTextName(us, [target.item, id]), type: 'string', items: [target.item, id], origin: null, confirmed: false, when: localNow() };
      us.push(u); return afterEdit(us, u.uid);
    }
  } else if (target.unit) {
    t = unitByUid(target.unit, us); if (!t) return;
    if (!isText(t)) return note(MIX);
    if (item(t.items[0]).page !== item(id).page) return note(PAGES);
  }
  if (!t || t === src) return;
  snapshot(); if (src) detach(us, id); t.items.push(id); afterEdit(us, t.uid);
}
export function moveItem(id: string, target: Target): void | Promise<void> {
  if (isTextItem(id)) return moveText(id, target);
  if ((target.item && isTextItem(target.item)) || (target.unit && isText(unitByUid(target.unit)))) return note(MIX);
  const us = draft();
  const src = unitOf(id, us); if (!src || src.locked) return;
  if (target.item && target.inTray && isGroup(src)) target = { tray: true };
  let sel = S().selected;
  if (target.item) {
    if (target.item === id) return;
    const t = unitOf(target.item, us)!; if (t.locked) return;
    if (isGroup(t)) return moveItem(id, { unit: t.uid });
    if (t === src) return;
    snapshot(); detach(us, id); drop(us, t);
    const g: Unit = { uid: nextUid++, name: suggestName(us, [target.item, id]), type: 'category', items: [target.item, id], origin: null, confirmed: false };
    us.push(g); sel = g.uid;
  } else if (target.unit) {
    const t = unitByUid(target.unit, us); if (!t || t === src || t.locked) return;
    if (!isGroup(t)) return moveItem(id, { item: t.items[0] });
    snapshot(); detach(us, id); t.items.push(id); t.confirmed = false; sel = t.uid;
  } else if (target.tray) {
    if (!isGroup(src)) return;
    snapshot(); detach(us, id);
    const u = looseOf(us, src, id);
    us.push(u); sel = us.includes(src) ? src.uid : u.uid;
  }
  afterEdit(us, sel);
}
// "group them" on a suggestion: the boxes one group, as a drag makes it (applied with the rest when Groups is left)
export function groupSuggested(x?: Suggestion) {
  const us = draft();
  if (!x || !x.items.every(id => { const v = unitOf(id, us); return v && !isGroup(v) && !v.locked; })) return note('Those boxes are no longer all loose.');
  snapshot();
  for (const id of x.items) detach(us, id);
  const g: Unit = { uid: nextUid++, name: x.name ? uniqueName(us, x.name, null) : suggestName(us, x.items), type: 'category', items: [...x.items], origin: null, confirmed: false };
  us.push(g);
  afterEdit(us, g.uid);
}
export async function notGroup(i: number) {
  const x = S().BP?.suggested?.[i]; if (!x) return;
  try { await send('PUT', mapi('groups', app().bid!, '/notgroup'), { items: x.items }); }
  catch (e) { alert((e as Error).message); return; }
  const BP = S().BP!;
  put({ BP: { ...BP, suggested: (BP.suggested || []).filter((_, k) => k !== i) } });
}
// a box taken out of group `src`: a loose box of its own, under its field's name or the group's name and its key
function looseOf(us: Unit[], src: Unit, id: string): Unit {
  const it = item(id), own = it.key === null;
  return {
    uid: nextUid++, name: own ? it.field : uniqueName(us, `${src.name}_${String(it.key).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'option'}`, null),
    type: 'boolean', items: [id], origin: own ? it.field : null, confirmed: false,
  };
}
// u (Andrew, 2026-10-20): the selected group's boxes all loose; a combined text field separated again
export function ungroup() {
  const us = draft(), u = unitByUid(S().selected, us);
  if (!u || !isGroup(u)) return note('Select a group first.');
  if (u.locked) return note(`${u.name} is locked: ${u.locked}`);
  if (isText(u)) return separate(u.uid);
  // the finder groups these boxes as the tab loads (2026-10-25): ungrouped, they are recorded as not a group
  send('PUT', mapi('groups', app().bid!, '/notgroup'), { items: [...u.items] }).catch(e => note('could not record the boxes as not a group: ' + (e as Error).message));
  snapshot([...u.items]);
  const loose: Unit[] = [];
  for (const id of [...u.items]) { detach(us, id); const x = looseOf(us, u, id); us.push(x); loose.push(x); }
  afterEdit(us, loose[0].uid); note(`${u.name} ungrouped: ${loose.length} loose boxes (z to undo)`);      // afterEdit clears the notes
}
export function moveUnit(uid: number, target: Target) {
  const us = draft();
  const s = unitByUid(uid, us); if (!s || s.locked) return;
  if (isText(s)) {
    if (target.tray) return;
    if (target.item && !isTextItem(target.item)) return note(MIX);
    const t = target.item ? unitOf(target.item, us) : unitByUid(target.unit, us);
    if (target.item && !t) {                              // a combined field onto a loose text box: take it in
      if (item(target.item).page !== item(s.items[0]).page) return note(PAGES);
      snapshot(); s.items.push(target.item); return afterEdit(us, s.uid);
    }
    if (!t || t === s) return;
    if (!isText(t)) return note(MIX);
    if (item(t.items[0]).page !== item(s.items[0]).page) return note(PAGES);
    snapshot(); t.items.push(...s.items); drop(us, s); return afterEdit(us, t.uid);
  }
  if ((target.item && isTextItem(target.item)) || (target.unit && isText(unitByUid(target.unit, us)))) return note(MIX);
  if (target.item) { const t = unitOf(target.item, us); if (!t || t === s) return; target = { unit: t.uid }; }
  const t = unitByUid(target.unit, us); if (!t || t === s || t.locked) return;
  snapshot();
  let sel: number;
  if (isGroup(t)) { t.items.push(...s.items); t.confirmed = false; drop(us, s); sel = t.uid; }
  else { s.items.push(...t.items); s.confirmed = false; drop(us, t); sel = s.uid; }
  afterEdit(us, sel);
}
/** what a drop on a box, a unit or the tray does with the box or unit dropped */
export function dropped(kind: string, value: string, target: Target) {
  if (kind === 'item') moveItem(value, target);
  else if (kind === 'unit' && !target.tray) moveUnit(Number(value), target);
}
export function confirmUnit(uid: number, on?: boolean) {
  const us = draft(), u = unitByUid(uid, us); if (!u || isText(u)) return;
  snapshot(); u.confirmed = on ?? !u.confirmed; const adv = u.confirmed;
  afterEdit(us); if (adv) next(1);
}
export function rename(uid: number, name: string, from: string | null = null) {
  const us = draft(), u = unitByUid(uid, us); name = name.trim(); if (!u || name === u.name) return;
  snapshot(); u.name = name; if (from) u.name_from = from; else delete u.name_from;
  afterEdit(us);
}

// the labeler names a group or combined field the way it names a field in Add (`field_add.labeler_name`): one call
// with the page's words, the box (the hull of the unit's boxes on its first page) and, for a group, the captions
// requests in flight per unit (2026-10-14: a redraw, e.g. picking 'any of', reset the button while the call ran)
export const busyOn = (busy: State['busy'], u: Unit, k: 'label' | 'caps') => !!(busy[u.uid] || {})[k];
function setBusy(uid: number, k: 'label' | 'caps', on: boolean) {
  const busy = S().busy;
  put({ busy: { ...busy, [uid]: { ...(busy[uid] || {}), [k]: on } } });
}
// the captions sent are the ones the group shows (a re-read caption before the box's own)
function labelerProposal(u: Unit, caps: Record<string, string> = u.captions || {}) {
  const first = firstItem(u), its = u.items.map(item).filter(it => it.page === first.page);
  const rect = [Math.min(...its.map(i => i.rect[0])), Math.min(...its.map(i => i.rect[1])), Math.max(...its.map(i => i.rect[2])), Math.max(...its.map(i => i.rect[3]))];
  return isText(u) ? { kind: 'text', page: first.page, rect }
    : isGroup(u) ? { kind: 'group', page: first.page, rect, options: u.items.map(id => ({ key: String(item(id).key ?? item(id).field), caption: caps[id] || item(id).caption || null })) }
    : { kind: 'option', page: first.page, rect, widget: { path: first.path } };
}
export async function askLabeler(uid: number) {
  const u = unitByUid(uid); if (!u) return;
  const proposal = labelerProposal(u);
  setBusy(uid, 'label', true);
  try {
    const r = await send('POST', mapi('add', app().bid!, '/labeler'), { proposal, from: 'groups' });
    setBusy(uid, 'label', false);
    if (r.name) { rename(uid, uniqueName(S().units, r.name, uid), 'labeler'); note(`${r.model}: ${r.name}`); }
    else note('the labeler returned no name');
  } catch (e) { setBusy(uid, 'label', false); note('labeler failed: ' + (e as Error).message); }
}
// "re-read captions" (Andrew, 2026-10-13): the page's best caption per box for this group's name and keys; kept
// with the unit and written when the grouping is applied
interface CapReading { caption?: string | null; current?: string | null; locked?: boolean; source?: string }
const newCaptions = (r: { captions: Record<string, CapReading> }): Record<string, string> =>
  Object.fromEntries(Object.entries(r.captions).filter(([, c]) => c.caption && !c.locked && c.caption !== c.current).map(([id, c]) => [id, c.caption!]));
export async function rereadCaptions(uid: number) {
  const u = unitByUid(uid); if (!u) return;
  setBusy(uid, 'caps', true);
  try {
    const r = await send('POST', mapi('groups', app().bid!, '/captions'), { name: u.name, items: u.items });
    setBusy(uid, 'caps', false);
    const caps = newCaptions(r);
    const kept = Object.values<CapReading>(r.captions).filter(c => c.locked).length;
    if (!Object.keys(caps).length) { note(`captions: nothing better on the page${kept ? ` (${kept} locked)` : ''}`); return; }
    snapshot();
    const us = draft(), cur = unitByUid(uid, us);
    if (cur) cur.captions = { ...(cur.captions || {}), ...caps };
    const src = (Object.values<CapReading>(r.captions)[0] || {}).source;
    afterEdit(us);                                       // it clears the notes: the note after it (2026-10-26)
    note(`captions: ${Object.keys(caps).length} re-read${src ? ' by ' + src : ''}${kept ? `, ${kept} locked kept` : ''}`);
  } catch (e) { setBusy(uid, 'caps', false); note('captions failed: ' + (e as Error).message); }
}
// "rescan page" (Andrew, 2026-10-25: "would re-scanning group captions and/or group labels in bulk be faster?"):
// every open group on this page (not confirmed, not locked) has its captions re-read, one call per group all at
// once (each sees its own strip of the page), then the labeler names them all in one call with those captions.
// Only a group not yet in the blueprint and not named by hand takes the labeler's name (on N-400 p2 the labeler's
// would_like_to_legally_change_name replaced the blueprint's legal_name_change); the rest are context for it.
// Nothing is saved to the blueprint; one undo takes the whole rescan back.
export async function rescanPage() {
  const p = app().page, gs = optUnits().filter(u => onPage(u, p) && isGroup(u) && !u.locked && !u.confirmed);
  if (!gs.length) return note(`p${p}: no open groups to rescan (confirmed and locked groups are left alone)`);
  put({ rescanning: gs.length });
  gs.forEach(u => { setBusy(u.uid, 'caps', true); setBusy(u.uid, 'label', true); });
  const done = () => { put({ rescanning: 0 }); gs.forEach(u => { setBusy(u.uid, 'caps', false); setBusy(u.uid, 'label', false); }); };
  const capsBy: Record<number, Record<string, string>> = {}, fails: string[] = [];
  await Promise.all(gs.map(async u => {
    try { capsBy[u.uid] = newCaptions(await send('POST', mapi('groups', app().bid!, '/captions'), { name: u.name, items: u.items })); }
    catch (e) { fails.push(`captions for ${u.name}: ${(e as Error).message}`); }
  }));
  // edits made while it ran stand
  const live = gs.map(u => unitByUid(u.uid)).filter((u): u is Unit => !!u && !u.locked && !u.confirmed);
  let names: (string | null)[] = [], model = '';
  try {
    const r = await send('POST', mapi('add', app().bid!, '/labeler_page'), { proposals: live.map(u => labelerProposal(u, { ...(u.captions || {}), ...(capsBy[u.uid] || {}) })) });
    names = r.names; model = r.model;
  } catch (e) { fails.push('labeler: ' + (e as Error).message); }
  done();
  let nCaps = 0, nGroupsCapped = 0, nNamed = 0;
  const us = draft();
  live.forEach((u0, i) => {
    const u = unitByUid(u0.uid, us); if (!u) return;
    const caps = capsBy[u.uid] || {};
    if (Object.keys(caps).length) { u.captions = { ...(u.captions || {}), ...caps }; nCaps += Object.keys(caps).length; nGroupsCapped++; }
    const n = names[i] && !baseOf(u) && u.name_from !== 'hand' && uniqueName(us, names[i]!, u.uid);
    if (n && n !== u.name) { u.name = n; u.name_from = 'labeler'; nNamed++; }
  });
  if (nCaps || nNamed) snapshot();                      // nothing changed: nothing to undo
  await afterEdit(us);
  note(`p${p}, ${live.length} group${live.length === 1 ? '' : 's'}: ${nCaps} caption${nCaps === 1 ? '' : 's'} re-read on ${nGroupsCapped}, ${nNamed} renamed${model ? ' by ' + model : ''}${nCaps || nNamed ? ' (z undoes)' : ''}${fails.length ? '. Failed: ' + fails.join('; ') : ''}`);
}
// merge a group into another on any page (Andrew, 2026-10-14: I-485 item 56 runs from page 18 onto page 19); the
// boxes keep their order, the other group's name and type stand
export function mergeInto(uid: number, toUid: number) {
  const us = draft(), u = unitByUid(uid, us), t = unitByUid(toUid, us); if (!u || !t || t === u) return;
  snapshot();
  t.items.push(...u.items); t.confirmed = false;
  if (u.captions) t.captions = { ...(t.captions || {}), ...u.captions };
  drop(us, u);
  afterEdit(us, t.uid);                                  // it clears the notes: the note after it (2026-10-26)
  note(`${u.name} merged into ${t.name} (${t.items.length} boxes)`);
}
export function setDesc(uid: number, d: string) { const us = draft(), u = unitByUid(uid, us); if (!u || (u.description || '') === d) return; snapshot(); u.description = d; afterEdit(us); }
export function setType(uid: number, type: string) { const us = draft(), u = unitByUid(uid, us); if (!u || u.type === type) return; snapshot(); u.type = type; u.confirmed = false; afterEdit(us); }
export function separate(uid: number) {
  const us = draft(), u = unitByUid(uid, us); if (!u) return;
  snapshot(); drop(us, u);
  afterEdit(us, optUnits(us).length ? optUnits(us)[0].uid : null);
}
export function revert(uid: number) {
  const us = draft(), u = unitByUid(uid, us); if (!u) return;
  const b = baseOf(u); if (!b) return;
  snapshot();
  for (const id of b.items) { const cur = unitOf(id, us); if (cur && cur !== u) detach(us, id); }
  for (const id of u.items.filter(id => !b.items.includes(id))) {
    const it = item(id); u.items = u.items.filter(x => x !== id);
    us.push({
      uid: nextUid++, name: it.key === null ? it.field : uniqueName(us, `${u.name}_${it.key}`.toLowerCase().replace(/[^a-z0-9_]+/g, '_'), null),
      type: 'boolean', items: [id], origin: it.key === null ? it.field : null, confirmed: false,
    });
  }
  if (!us.includes(u)) us.push(u);
  u.items = [...b.items]; u.name = b.name; u.type = b.type; u.confirmed = false;
  afterEdit(us);
}

// ------------------------------------------------------------------------------------------- saving and the plan
// one save at a time, in order: each PUT waits for the one before
let saving: Promise<void> = Promise.resolve();
function save() {
  const body = { units: strip(S().units) }, bid = app().bid!;
  saving = saving.then(async () => {
    try {
      const out = await send('PUT', mapi('groups', bid, '/units'), body);
      updateEntry(out.entry);
      const BP = S().BP;
      if (BP && BP.id === bid) put({ BP: { ...BP, info: { ...BP.info, stale: false, updated: out.saved } } });
    } catch (e) { alert('Save failed: ' + (e as Error).message); }
  });
  return saving;
}
function schedulePlan() {
  clearTimeout(planTimer);
  planTimer = setTimeout(async () => {
    let PLAN: Plan;
    try { PLAN = await send('POST', mapi('groups', app().bid!, '/plan'), { units: strip(S().units) }); }
    catch (e) { PLAN = { changes: [], errors: ['plan failed: ' + (e as Error).message] }; }
    put({ PLAN });
  }, 300);
}
export async function applyPlan() {
  clearTimeout(planTimer);
  await save();                          // apply reads the saved record, so it must hold the last edit
  let out;
  try { out = await send('POST', mapi('groups', app().bid!, '/apply')); }
  catch (e) { alert('Apply failed: ' + (e as Error).message); return; }
  updateEntry(out.entry);
  await loadMode();
  toast(`${out.changes.length} change(s) went into the working copy.`);
}
// leaving Groups (another mode, another form, the header's save): the regrouping goes into the working copy when it
// plans cleanly, so the other modes read it; with errors it stays recorded, and save refuses until they are fixed
export async function leave() {
  const { BP, undoStack, PLAN } = S();
  if (!BP || !undoStack.length && !(PLAN && PLAN.changes.length)) return;
  clearTimeout(planTimer);
  await save();
  const bid = app().bid!;
  let pl: Plan;
  try { pl = await send('POST', mapi('groups', bid, '/plan'), { units: strip(S().units) }); } catch { return; }
  if (!pl.changes.length) return;
  if (pl.errors.length) { toast(`Groups not applied: ${pl.errors.length} error(s) to fix first.`); return; }
  try { const out = await send('POST', mapi('groups', bid, '/apply')); updateEntry(out.entry); toast(`Groups: ${out.changes.length} change(s) went into the working copy.`); }
  catch (e) { toast('Groups not applied: ' + (e as Error).message); }
}

// a checkbox or a group dragged on Review's page (Andrew, 2026-10-27: "can we add dragging bools to combine to the
// review page? and add dragging groups to combine to both?"): Groups' data read fresh for the form, the move made as
// a drag here makes it, and put into the working copy at once, as leaving Groups does. A move the plan refuses is
// taken back. The name of the group the boxes are in after it, or null.
export interface ReviewBox { field: string; opt: string | null }
/** Review's box (a field and its option's on-state, null for a checkbox or the group as a whole) as Groups' item */
export function itemOf(b: ReviewBox, items: Record<string, Item> = S().BP!.items) {
  const its = Object.values(items).filter(it => it.field === b.field && it.kind !== 'text');
  return b.opt === null ? its[0] : its.find(it => it.key === b.opt);
}
export async function combineFromReview(what: ReviewBox, whole: boolean, onto: ReviewBox): Promise<string | null> {
  return fromReview(async () => {
    const a = itemOf(what), t = itemOf(onto);
    if (!a || !t) { toast('Only checkboxes and option groups combine.'); return undefined; }
    const src = unitOf(a.id);
    if (whole && src) moveUnit(src.uid, { item: t.id }); else await moveItem(a.id, { item: t.id });
    return t.id;
  }, 'Nothing to combine.', 'combined');
}
// g and u on Review's page (Andrew, 2026-10-28: "can we make u/g for ungroup/group work on the review tab?"): the boxes
// Shift-clicked there grouped, or the selected group taken apart (recorded as not a group), as g and u do here
export async function groupFromReview(boxes: ReviewBox[]): Promise<string | null> {
  return fromReview(() => {
    const ids = boxes.map(b => itemOf(b)?.id).filter((x): x is string => !!x);
    if (ids.length < boxes.length) { toast('Only checkboxes and option groups group.'); return undefined; }
    put({ picked: new Set(ids) });
    groupPicked();
    return ids[0];
  }, 'Nothing to group.', 'grouped');
}
export async function ungroupFromReview(field: string): Promise<string | null> {
  return fromReview(() => {
    const it = itemOf({ field, opt: null }), u = it && unitOf(it.id);
    if (!u) { toast('Only option groups ungroup.'); return undefined; }
    put({ selected: u.uid });
    ungroup();
    return null;
  }, 'Nothing to ungroup.', 'ungrouped');
}
/** Groups' data read fresh, `edit` made as here, and put into the working copy at once, as leaving Groups does; taken
 *  back when the plan refuses it. `edit` gives the box whose group's name to report (null: none), undefined to stop. */
async function fromReview(edit: () => Promise<string | null | undefined> | string | null | undefined, nothing: string, done: string): Promise<string | null> {
  const bid = app().bid!;
  let before: Unit[] | null = null;
  try {
    await load(bid, false);                    // without the finder's groups: only this change goes in (2026-10-28)
    const steps = S().undoStack.length;
    before = S().units;
    const at = await edit();
    if (at === undefined) return null;
    if (S().undoStack.length === steps) { toast(S().notes[0] || nothing); return null; }
    const name = at ? unitOf(at)?.name || null : null;
    await save();
    clearTimeout(planTimer);
    const pl: Plan = await send('POST', mapi('groups', bid, '/plan'), { units: strip(S().units) });
    if (pl.errors.length) { put({ units: before }); await save(); toast(`Not ${done}: ${pl.errors[0]}`); return null; }
    const out = await send('POST', mapi('groups', bid, '/apply'));
    updateEntry(out.entry);
    await loadMode();
    toast(`${name ? name + ': ' : ''}${out.changes.length} change(s) went into the working copy.`);
    return name;
  } catch (e) {
    if (before && S().BP?.id === bid) { put({ units: before }); await save(); }
    toast(`Not ${done}: ` + (e as Error).message);
    return null;
  }
}

// ------------------------------------------------------------------------------------------- loading and moving
export async function load(bid: string, auto = true) {
  const BP: GroupsData = await j(mapi('groups', bid) + (auto ? '' : '?auto=0'));   // auto: the finder's groups made
  const units: Unit[] = BP.units.map(u => ({ ...u, uid: nextUid++ }));
  let notes: string[] = [];
  const ag = BP.auto_grouped || [];
  if (ag.length) notes = [`The finder grouped ${ag.length} set${ag.length === 1 ? '' : 's'} of loose boxes: ${ag.slice(0, 8).map(x => `${x.name} (p${x.page})`).join(', ')}${ag.length > 8 ? ', …' : ''}. "ungroup" (u) takes one apart for good.`];
  sortUnits(units, BP.items);
  const ou = optUnits(units), was = S(), same = was.BP?.id === bid;
  // the group selected before, read again (a save, a reload); else the first on the page shown, else the first
  // (2026-10-26: the card showed a group from another page); boxes picked stay picked only on the same form
  const keep = same ? unitByUid(was.selected, was.units) : undefined;
  const sel = (keep && ou.find(u => u.name === keep.name)) || ou.find(u => u.items.some(id => BP.items[id]?.page === app().page)) || ou[0];
  const picked = new Set(same ? [...was.picked].filter(id => BP.items[id]) : []);
  put({ BP, units, undoStack: [], PLAN: null, notes, picked, selected: sel ? sel.uid : null, hover: null });
  schedulePlan();
}

function scrollSel() {
  afterPaint(() => {
    const el = document.querySelector('.gh.sel') || document.querySelector('.gi.sel');
    if (el) el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
    const card = document.querySelector('.gcard.sel'); if (card) card.scrollIntoView({ block: 'nearest' });
  });
}
export function select(uid: number, scroll = true) {
  put({ selected: uid }); const u = unitByUid(uid); if (!u) return;
  if (!onPage(u)) { setApp({ page: firstItem(u).page }); scrollSel(); return; }
  if (scroll) scrollSel();
}
export function next(step: number) {
  const ou = optUnits(); if (!ou.length) return;
  const { selected, unconfOnly } = S();
  const k = ou.findIndex(u => u.uid === selected);
  if (unconfOnly) {
    const after = step > 0 ? ou.slice(k + 1).concat(ou.slice(0, Math.max(k, 0))) : ou.slice(0, Math.max(k, 0)).reverse().concat(ou.slice(k + 1).reverse());
    const t = after.find(u => !u.confirmed); if (t) select(t.uid); return;
  }
  select(ou[(k + step + ou.length) % ou.length].uid);
}
/** a page picked by its button or key: its first unconfirmed unit (unconfirmed only), else its first */
export function pickOnPage() {
  const ou = optUnits(), { unconfOnly } = S();
  const u = ou.find(x => onPage(x) && (!unconfOnly || !x.confirmed)) || ou.find(x => onPage(x));
  if (u) put({ selected: u.uid });
}
export const setUnconfOnly = (on: boolean) => put({ unconfOnly: on });
export function setShowText(on: boolean) { put({ showText: on }); store('gr_text', on ? '1' : '0'); }

export function key(e: KeyboardEvent): boolean {
  const { selected, picked } = S();
  if (e.key === 'g') { groupPicked(); return true; }
  if (e.key === 'Escape' && picked.size) { clearPicked(); return true; }
  if (e.key === 'a' && selected) confirmUnit(selected, true);
  else if (e.key === 'n' || e.key === 'ArrowRight') next(1);
  else if (e.key === 'p' || e.key === 'ArrowLeft') next(-1);
  else if (e.key === 'z') undo();
  else if (e.key === 'u') ungroup();
  else if (e.key === 'U') setUnconfOnly(!S().unconfOnly);
  else if (e.key === 'T') setShowText(!S().showText);
  else return false;
  return true;
}

// a link's group: by its name, or the group holding a field
export function focus(k: string) {
  const { units, BP } = S(); if (!BP) return;
  const u = units.find(x => x.name === k) || units.find(x => x.items.some(id => BP.items[id]?.field === k));
  if (u) select(u.uid);
}
