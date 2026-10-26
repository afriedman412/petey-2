// Review: accept / flag / note per field, a correction edited in place in the field card (hand_review.py).
// The tab's data and everything it does; Panel.tsx and Layer.tsx draw it.
import { create } from 'zustand';
import { j, mapi, send } from '../../lib/api';
import type { Checked, PageInfo } from '../../lib/types';
import { fileStem, localNow, PART_KEYS, scrollToSel, stdPrint, store, type PartKey, type Parts, type Rect } from '../../lib/util';
import { loadMode, syncSha, toast, updateEntry } from '../../state/actions';
import { entryOf, get as app, set as setApp, useApp } from '../../state/app';

export type Tier = 'contested' | 'unknown' | 'single' | 'settled';
export interface Why { kind: 'error' | 'suggestion'; text: string; fix?: { name?: string; type?: string; pattern?: string; options?: OptEdits } }
export type OptEdits = Record<string, { key?: string; caption?: string }>;
export interface Edit {
  name?: string; type?: string; semantic_type?: string; pattern?: string; options?: OptEdits; identifiers?: Record<string, string>;
}
export interface Agent {
  action: 'edit' | 'remove' | 'regroup' | 'none' | string; reason?: string; for_note?: string;
  name?: string; type?: string; semantic_type?: string; pattern?: string; description?: string; options?: OptEdits;
}
export interface Verdict { verdict: 'accept' | 'flag'; note?: string; edit?: Edit; applied?: boolean; agent?: Agent }
export interface RField {
  name: string; id?: string; page: number; rects: { page: number; rect: Rect }[];
  options: { on_state: string; caption?: string | null }[];
  choices?: { key: string; caption?: string | null; stored?: string | null }[];
  type?: string; semantic_type?: string; pattern?: string; description?: string; values?: string[];
  tier?: Tier; why?: Why[]; witnesses?: Record<string, [boolean | null, string]>; path?: string;
  loop?: { changed?: string[]; old_name?: string; reason?: string };
  adjudication?: { verdict: string; proposed: string; reason?: string };
  claude?: { kind: string; from?: string; why?: string };
  identifiers?: Parts & { grid?: string }; identifiers_stored?: boolean; identifier_flags?: string[];
  idx: number;
}
export interface Made {
  labeler?: { method?: string; model?: string; when?: string };
  origin?: { repo: string; first: { when: string; who: string }; last: { when: string; who: string } };
  git_first?: { when: string; who: string; commit: string; subject: string };
  git_last?: { when: string; who: string; commit: string; subject: string }; git_commits?: number;
  uncommitted?: boolean; file_time?: string; loop_edits?: Record<string, number>; validated?: { run?: string; when?: string };
}
export interface ReviewData {
  path: string; blank?: string | null; build?: { finder: string } | null; made?: Made | null;
  pages: PageInfo[]; fields: RField[]; verdicts: Record<string, Verdict>; semantic_types?: string[];
  stale?: boolean; checked?: Checked | null; witness_error?: string | null; agent_running?: boolean; agent_todo?: number;
}
export interface Removal { name: string; page: number; rect: Rect; when: string; from: string }

/** What the field card's boxes hold: the saved correction over the blueprint, then what the person typed. */
export interface Boxes {
  name: string; type: string; semantic_type: string; pattern: string;
  options: Record<string, { key: string; caption: string }>;
  parts: Record<PartKey, string>;
}

interface State {
  BP: ReviewData | null; bpFor: string | null; removed: Removal[];
  selected: string | null; selOpt: string | null;
  unrevOnly: boolean; flagOnly: boolean; claudeOnly: boolean; order: string; clashOn: boolean; idsOpen: boolean;
  boxes: Boxes | null; boxesBase: string; note: string; noteBase: string;
  busy: Record<string, boolean>; justChecked: boolean;
}

let order0 = store('hr_order') || 'risk', claude0 = store('hr_claude') === '1';
if (order0 === 'claude') { order0 = 'risk'; claude0 = true; }

export const useReview = create<State>(() => ({
  BP: null, bpFor: null, removed: [], selected: null, selOpt: null,
  unrevOnly: false, flagOnly: false, claudeOnly: claude0, order: order0, clashOn: false,
  idsOpen: store('ids_open') !== '0',
  boxes: null, boxesBase: '', note: '', noteBase: '', busy: {}, justChecked: false,
}));
const S = useReview.getState, put = useReview.setState;

export const TIER_RANK: Record<string, number> = { contested: 0, unknown: 1, single: 2, settled: 3 };
export const TIER_LETTER: Record<string, string> = { contested: '!', unknown: '?', single: '1', settled: '2+' };
export const verdictOf = (n: string) => S().BP?.verdicts[n]?.verdict || '';
export const isRemoved = (n: string | null) => !!n && S().removed.some(r => r.name === n);
export const fieldOf = (n: string | null) => S().BP?.fields.find(f => f.name === n);
export const fieldRef = (f: RField) => `${fileStem(S().BP!.path)}_${f.id}`;

// p / ←: back through the fields actually visited, like a browser's back button (Andrew, 2026-10-14)
let visited: string[] = [], goingBack = false, visitedFor: string | null = null;

// ------------------------------------------------------------------------------------------- the field card's boxes
// the field name is printed from its parts (docs/NAMING.md "Identifiers", 2026-10-19): the name box is read-only and
// the parts are what the person edits; a block's prefix and number lead (the naming standard, 2026-10-24)
export const printParts = (p: Partial<Record<PartKey, string>>) => stdPrint(Object.fromEntries(PART_KEYS.map(k => [k, p[k] || ''])));
export function partsShown(f: RField, v?: Verdict): Record<PartKey, string> {
  const src: Record<string, unknown> = v && v.edit && !v.applied && v.edit.identifiers ? v.edit.identifiers : (f.identifiers || {});
  return Object.fromEntries(PART_KEYS.map(k => [k, src[k] == null ? '' : String(src[k])])) as Record<PartKey, string>;
}
// a group's boxes, or a dropdown's entries (2026-10-14: dropdown options look and are corrected like group options)
export const optList = (f: RField) => f.options.length ? f.options.map(x => ({ k: x.on_state, caption: x.caption, stored: undefined as string | null | undefined }))
  : (f.choices || []).map(c => ({ k: c.key, caption: c.caption, stored: c.stored }));
const orig = (f: RField) => ({ name: f.name, type: f.type || '', semantic_type: f.semantic_type || '', pattern: f.pattern || '' });
/** What the boxes show for a field: the saved correction over the blueprint. */
export function shown(f: RField, v?: Verdict): Boxes {
  const e = (v && v.edit) || {}, o = orig(f), un = (x: string) => (x === 'none' ? '' : x);
  const eo = e.options || {};
  return {
    name: e.name || o.name, type: e.type || o.type,
    semantic_type: e.semantic_type ? un(e.semantic_type) : o.semantic_type, pattern: e.pattern ? un(e.pattern) : o.pattern,
    options: Object.fromEntries(optList(f).map(x => { const d = eo[x.k] || {};
      return [x.k, { key: d.key || x.k, caption: 'caption' in d ? d.caption ?? '' : (x.caption || '') }]; })),
    parts: partsShown(f, v),
  };
}
/** The boxes as they were drawn for the selected field, or kept when the saved state has not changed. */
function syncBoxes(force = false) {
  const { BP, selected, boxesBase, noteBase } = S();
  const f = selected ? BP?.fields.find(x => x.name === selected) : undefined;
  if (!f) { put({ boxes: null, boxesBase: '', note: '', noteBase: '' }); return; }
  const v = BP!.verdicts[f.name], s = shown(f, v), key = f.name + '\n' + JSON.stringify(s);
  if (force || key !== boxesBase) put({ boxes: s, boxesBase: key });
  const nb = f.name + '\n' + (v?.note || '');
  if (force || nb !== noteBase) put({ note: v?.note || '', noteBase: nb });
}

/** Which boxes differ from what the field has (amber), and whether any does. */
export function dirtyOf(): { any: boolean; keys: Set<string> } {
  const { BP, selected, boxes, idsOpen } = S();
  const f = fieldOf(selected), keys = new Set<string>();
  if (!f || !boxes || !BP) return { any: false, keys };
  const was = shown(f, BP.verdicts[f.name]);
  for (const k of ['name', 'type', 'semantic_type', 'pattern'] as const) if (boxes[k].trim() !== was[k]) keys.add(k);
  for (const k of Object.keys(boxes.options)) for (const w of ['key', 'caption'] as const)
    if (boxes.options[k][w].trim() !== was.options[k]?.[w]) keys.add(`o:${k}:${w}`);
  if (idsOpen) for (const k of PART_KEYS) if (boxes.parts[k].trim() !== was.parts[k]) keys.add(`p:${k}`);
  return { any: keys.size > 0, keys };
}

export function setBox(k: 'type' | 'semantic_type' | 'pattern' | 'name', v: string) { const b = S().boxes; if (b) put({ boxes: { ...b, [k]: v } }); }
export function setOpt(ok: string, w: 'key' | 'caption', v: string) {
  const b = S().boxes; if (!b) return;
  put({ boxes: { ...b, options: { ...b.options, [ok]: { ...b.options[ok], [w]: v } } } });
}
/** a part typed: the name reprinted from the parts at once */
export function setPart(k: PartKey, v: string) {
  const b = S().boxes; if (!b) return;
  const parts = { ...b.parts, [k]: v };
  put({ boxes: { ...b, parts, name: printParts(Object.fromEntries(PART_KEYS.map(x => [x, parts[x].trim()]))) } });
}
export function fillOptions(opts?: OptEdits) {
  let n = 0;
  for (const [k, d] of Object.entries(opts || {})) {
    if (!S().boxes?.options[k]) continue;
    if (d.key) setOpt(k, 'key', d.key);
    if ('caption' in d) setOpt(k, 'caption', d.caption ?? '');
    n++;
  }
  return n;
}
export const resetBoxes = () => syncBoxes(true);

// ------------------------------------------------------------------------------------------------------- loading
export async function load(bid: string) {
  if (visitedFor !== bid) { visited = []; visitedFor = bid; }
  const keep = S().selected;
  const BP: ReviewData = await j(mapi('review', bid));
  const removed: Removal[] = (await j(mapi('review', bid, '/removals'))).removed;
  BP.fields.forEach((f, i) => { f.idx = i; });
  BP.checked = entryOf(bid)?.checked || BP.checked;
  const sameForm = S().bpFor === bid;
  put({ BP, bpFor: bid, removed, selected: sameForm && BP.fields.some(f => f.name === keep) ? keep : null, ...(sameForm ? {} : { selOpt: null }) });
  syncBoxes();
}
/** the page reads the working copy again after a change went into it (a correction, a removal) */
async function reload() { await load(app().bid!); await syncSha(); }

// ------------------------------------------------------------------------------------------- the list and moving
// Claude's changes, the riskiest first (Andrew, 2026-10-13): wrong names, added boxes, suggestions, then the rest
const CLAUDE_RANK: Record<string, number> = { wrong: 0, add: 1, caption: 3, type: 4, clarity: 5, suffix: 6 };
const claudeRank = (f: RField) => f.claude ? (CLAUDE_RANK[f.claude.kind] ?? 5) : (f.why || []).some(w => /^Claude:/.test(w.text)) ? 2 : 9;
export function ordered(): RField[] {
  const { BP, unrevOnly, flagOnly, claudeOnly, order } = S();
  if (!BP) return [];
  const list = BP.fields.filter(f => (!unrevOnly || !verdictOf(f.name)) && (!flagOnly || verdictOf(f.name) === 'flag') && (!claudeOnly || claudeRank(f) < 9));
  if (claudeOnly && order === 'risk') return list.sort((a, b) => (claudeRank(a) - claudeRank(b)) || (a.idx - b.idx));
  if (order === 'risk') list.sort((a, b) => ((TIER_RANK[a.tier!] ?? 1) - (TIER_RANK[b.tier!] ?? 1)) || (a.idx - b.idx));
  else if (order === 'name') list.sort((a, b) => a.name.localeCompare(b.name));
  return list;
}

export function select(name: string, scroll = true, opt: string | null = null) {
  const { selected } = S();
  if (selected && selected !== name && !goingBack) { visited.push(selected); if (visited.length > 500) visited.shift(); }
  put({ selected: name, selOpt: opt });
  syncBoxes();
  const f = fieldOf(name);
  if (f && !f.rects.some(r => r.page === app().page)) setApp({ page: f.page });
  if (scroll) scrollToSel('.rv.sel');
}
function back() {
  while (visited.length) {
    const n = visited.pop()!;
    if (n !== S().selected && S().BP!.fields.some(f => f.name === n)) { goingBack = true; try { select(n); } finally { goingBack = false; } return; }
  }
  next(-1);                                  // nothing visited yet on this form: the previous field in the list
}
export function next(step = 1) {
  const list = ordered(), { selected, BP } = S();
  // the last one in the list (unreviewed only, Claude's changes only): stay, but show the verdict that was just saved
  if (!list.length || (list.length === 1 && list[0].name === selected)) { toast('No more fields in this list.'); return; }
  let i = list.findIndex(f => f.name === selected);
  if (i < 0) { const all = BP!.fields, j0 = all.findIndex(f => f.name === selected); i = list.findIndex(f => all.indexOf(f) > j0) - 1; }
  i = (i + step + list.length) % list.length;
  select(list[i].name);
}
export function setFilter(p: Partial<Pick<State, 'unrevOnly' | 'flagOnly' | 'claudeOnly' | 'order'>>) {
  if (p.unrevOnly) p.flagOnly = false;
  if (p.flagOnly) p.unrevOnly = false;
  put(p);
  if (p.order !== undefined) store('hr_order', p.order);
  if (p.claudeOnly !== undefined) store('hr_claude', p.claudeOnly ? '1' : '0');
}
export function toggleIds() { const idsOpen = !S().idsOpen; put({ idsOpen }); store('ids_open', idsOpen ? '1' : '0'); }

// ----------------------------------------------------------------------------------------------------- verdicts
// a correction goes into the working copy as it is saved; one that would take a name another field still has is
// held back (apply_error) until that field is renamed
async function putV(verdicts: Record<string, Partial<Verdict> | null>) {
  const bid = app().bid!;
  const out = await send('PUT', mapi('review', bid, '/verdicts'), { verdicts });
  const BP = S().BP!;
  const was = !!BP.checked;
  put({ BP: { ...BP, verdicts: out.verdicts, stale: false, checked: out.entry ? out.entry.checked : null } });
  updateEntry(out.entry);
  if (out.applied && out.applied.length) await reload(); else syncBoxes();
  if (out.apply_error) alert('Saved, but held back from the working copy: ' + out.apply_error + '\n\nRename the other field first (the clashes button shows both); then both go in.');
  if (!was && S().BP!.checked) { put({ justChecked: true }); setTimeout(() => put({ justChecked: false }), 2500); }
  return out;
}

export async function setVerdict(verdict: 'accept' | 'flag' | null) {
  const { selected, BP, note } = S();
  if (!selected || !BP) return;
  // accept with unsaved changes in the field card saves them first, as the correction (Andrew, 2026-10-07)
  if (verdict === 'accept' && dirtyOf().any) return saveFix();
  const edit = verdict ? BP.verdicts[selected]?.edit : undefined;   // accept and flag keep a correction
  await putV({ [selected]: verdict ? { verdict, note, edit } : null });
  if (verdict) next();
}
export async function saveNote() {
  const { selected, BP, note } = S();
  if (!selected || !BP) return;
  const v = BP.verdicts[selected];
  if (v && (v.note || '') !== note) await putV({ [selected]: { verdict: v.verdict, note, edit: v.edit } });
}
export const setNote = (note: string) => put({ note });

let fixing = false;          // one save at a time: a second one while the first reloads re-sends the old name
export async function saveFix() {
  if (fixing) return;
  fixing = true;
  try { await saveFixOnce(); } finally { fixing = false; }
}
async function saveFixOnce() {
  const { selected, BP, boxes, note, idsOpen } = S();
  const f = fieldOf(selected); if (!f || !boxes || !BP) return;
  const v = BP.verdicts[f.name] || ({} as Partial<Verdict>), o = orig(f);
  const now = { name: boxes.name.trim(), type: boxes.type.trim(), semantic_type: boxes.semantic_type.trim(), pattern: boxes.pattern.trim() };
  const cleared = (k: 'semantic_type' | 'pattern') => (now[k] === o[k] ? '' : (now[k] || 'none'));
  const edit: Edit = { name: now.name, type: now.type, semantic_type: cleared('semantic_type'), pattern: cleared('pattern') };
  const opts: OptEdits = {};
  for (const x of optList(f)) {
    const b = boxes.options[x.k]; if (!b) continue;
    const d: { key?: string; caption?: string } = {};
    if (b.key.trim() && b.key.trim() !== x.k) d.key = b.key.trim();
    if (b.caption.trim() !== (x.caption || '')) d.caption = b.caption.trim();
    if (Object.keys(d).length) opts[x.k] = d;
  }
  if (Object.keys(opts).length) edit.options = opts;
  if (idsOpen) {                                  // the parts changed: the server prints the name from them
    const pp = Object.fromEntries(PART_KEYS.map(k => [k, boxes.parts[k].trim()]));
    if (JSON.stringify(pp) !== JSON.stringify(partsShown(f, BP.verdicts[f.name]))) edit.identifiers = pp;
  }
  const same = now.name === o.name && now.type === o.type && !edit.semantic_type && !edit.pattern && !edit.options && !edit.identifiers;
  if (same && !v.edit) { toast('Nothing changed.'); return; }
  // the verdicts (Andrew, 2026-10-07): accept = the field is good to go, a saved correction included; flag = "I can't
  // or don't want to fix this myself", the note says what is wrong and "review edits" sends it on
  let out;
  try { out = await putV({ [f.name]: same ? { verdict: v.verdict || 'accept', note } : { verdict: 'accept', note, edit } }); }
  catch (e) { alert('Could not save the correction: ' + (e as Error).message); return; }
  if (same) { toast('Correction withdrawn: the field is back to what the blueprint has.'); return; }
  if (out.applied && out.applied.length && edit.name !== f.name && S().BP!.fields.some(x => x.name === edit.name)) {
    put({ selected: edit.name! }); visited = visited.map(n => (n === f.name ? edit.name! : n));
    syncBoxes(true);
  }
  next();
}

// ------------------------------------------------------------------------------------------------------ removing
// removing a field is recorded with the field-add record (Add / remove mode); a field removed here also gets an
// accept with the note "removed" when it has no verdict, so the review stays complete
async function putRemovals() {
  const out = await send('PUT', mapi('review', app().bid!, '/removals'), { removed: S().removed });
  updateEntry(out.entry);
  return out;
}
export async function removeField() {
  const f = fieldOf(S().selected); if (!f || isRemoved(f.name)) return;
  const list = ordered(), after = list[(list.indexOf(f) + 1) % list.length];
  put({ removed: [...S().removed, { name: f.name, page: f.page, rect: f.rects[0].rect, when: localNow(), from: 'review' }] });
  const out = await putRemovals();
  if (out.applied && out.applied.length) {             // gone from the working copy
    await reload();
    if (after && after !== f && S().BP!.fields.some(x => x.name === after.name)) select(after.name);
    toast(`Removed ${f.name} from the working copy.`); return;
  }
  if (out.apply_error || (out.errors && out.errors.length)) toast('Recorded, not removed yet: ' + (out.apply_error || out.errors.join('; ')));
  if (!verdictOf(f.name)) await putV({ [f.name]: { verdict: 'accept', note: 'removed' } });   // removing it is the fix
  next();
}
export async function keepField() {
  const f = fieldOf(S().selected); if (!f) return;
  put({ removed: S().removed.filter(r => r.name !== f.name) });
  await putRemovals();
  const v = S().BP!.verdicts[f.name];
  if (v && v.note === 'removed') await putV({ [f.name]: null });
}

// ------------------------------------------------------------------------------------------- the agent's help
const setBusy = (k: string, on: boolean) => put({ busy: { ...S().busy, [k]: on } });

// "improve name" (Andrew, 2026-10-14): one call to the review agent with the box outlined on the page, its tooltip
// and the naming conventions; the name it proposes goes into the name box (and its parts), and the person saves
const NAME_NOTE = 'Propose a better field name: snake_case, saying what the box holds (not an item or line number, '
  + 'not a bare section label), taken from the tooltip and the text printed at the box. Shape: description, then a '
  + 'number when there are several (parent_1_nm, parent_2_nm), then the suffix: _nm any name, _nbr identifiers and '
  + 'numbers, _dt dates, _amt money, _cnt or _qty counts, _pct percentages, _cd codes (state_cd), _ind a single '
  + 'checkbox, _txt free text, _signature; parts of one value go after the suffix (birth_dt_month, phone_nbr_area). '
  + 'Keep the form\'s own words for the description. An option group (one of / any of) is named for its question, with '
  + 'no suffix. Change nothing but the name.';
export async function improveName(f: RField) {
  setBusy('improve', true);
  try {
    const out = await send('POST', mapi('review', app().bid!, '/agent_field'), { name: f.name, note: NAME_NOTE });
    if (S().selected !== f.name) return;
    if (out.name && out.name !== f.name) {
      // the parts too (Andrew, 2026-10-25: '"improve name" should also change "subject"'): the name prints from them
      if (out.identifiers && S().idsOpen) for (const k of PART_KEYS) setPart(k, out.identifiers[k] || '');
      else setBox('name', out.name);
      toast(`Proposed: ${S().boxes?.name}. Check it and save. ${out.reason || ''}`);
    } else toast(`No better name proposed. ${out.reason || ''}`);
  } catch (e) { alert('The agent failed: ' + (e as Error).message); }
  finally { setBusy('improve', false); }
}
// "re-read captions" on a group, as in Groups (Andrew, 2026-10-15): the captions that would change fill the boxes
export async function rereadCaptions(f: RField) {
  setBusy('caps', true);
  try {
    const out = await send('POST', mapi('review', app().bid!, '/captions'), { name: f.name });
    if (S().selected !== f.name) return;
    const n = fillOptions(out.options);
    toast(n ? `${n} caption(s) re-read${out.source ? ' by ' + out.source : ''}; check them and save.` : `Nothing better on the page${out.locked ? ` (${out.locked} locked)` : ''}.`);
  } catch (e) { alert('Re-reading failed: ' + (e as Error).message); }
  finally { setBusy('caps', false); }
}
// "fix captions" (Andrew, 2026-10-07): one agent call for this field, the page check's reason included
export async function fixCaptions(f: RField) {
  setBusy('fixcaps', true);
  try {
    const out = await send('POST', mapi('review', app().bid!, '/agent_field'), { name: f.name, note: 'Fix the option keys and captions so each box has the caption printed beside it.' });
    if (S().selected !== f.name) return;
    const n = fillOptions(out.options);
    toast(n ? `${n} option(s) filled; check them and save. ${out.reason || ''}` : `No caption changes proposed. ${out.reason || ''}`);
  } catch (e) { alert('The agent failed: ' + (e as Error).message); }
  finally { setBusy('fixcaps', false); }
}
/** "use" on a reason's fix or the agent's proposal: it fills the boxes; the person still saves (2026-10-07) */
export function useFix(fix: Why['fix'] | Agent) {
  if (!fix) return;
  const un = (x: string) => (x === 'none' ? '' : x);
  if ('action' in fix && fix.action === 'remove') { removeField(); return; }
  if (fix.name) setBox('name', fix.name);
  if (fix.type) setBox('type', fix.type);
  if ('semantic_type' in fix && fix.semantic_type) setBox('semantic_type', un(fix.semantic_type));
  if (fix.pattern) setBox('pattern', un(fix.pattern));
  fillOptions(fix.options);
  (document.getElementById('eName') as HTMLInputElement | null)?.focus();
}

// "review edits" (Andrew, 2026-10-07): the flags with notes go to the agent (flag_agent.py) in the background; the
// page polls until it is done, then shows its proposals on the fields
export async function reviewEdits() {
  const id = app().bid!;
  try { await send('POST', mapi('review', id, '/agent')); } catch (e) { alert('Could not start: ' + (e as Error).message); return; }
  await loadMode();
  const poll = async () => {
    if (app().bid !== id || app().mode !== 'review') return;
    const d = await j(mapi('review', id));
    if (d.agent_running) { setTimeout(poll, 3000); return; }
    await loadMode(); toast('The agent has reviewed your edits: see "Agent proposes" on the flagged fields.');
  };
  setTimeout(poll, 3000);
}
export async function applyCorrections() {                      // a retry for corrections held back by a clash
  let out;
  try { out = await send('POST', mapi('review', app().bid!, '/apply')); }
  catch (e) { alert('Apply failed: ' + (e as Error).message); return; }
  updateEntry(out.entry);
  if (out.apply_error) { alert('Still held back: ' + out.apply_error); return; }
  await reload();
  toast(`${(out.applied || []).length} correction(s) went into the working copy.`);
}

// --------------------------------------------------------------------------------------- whole-form actions
// every verdict cleared (Andrew, 2026-10-22: "a button to reset validations? (and a 'are you sure?' screen)")
async function resetValidation() {
  const bid = app().bid!, n = Object.keys(S().BP?.verdicts || {}).length;
  if (!n) { alert('This form has no verdicts to clear.'); return; }
  if (!confirm(`Reset validation on ${bid}?\n\nThis clears all ${n} verdicts (accepted, flagged and their notes), so every field is unreviewed again. The old record is kept in runs/hand_review/_reset/, not deleted.`)) return;
  let out;
  try { out = await send('PUT', mapi('review', bid, '/reset'), {}); }
  catch (e) { alert((e as Error).message); return; }
  updateEntry(out.entry); await loadMode();
  toast(`Validation reset: ${out.cleared} verdicts cleared (kept in ${String(out.backup).split('/').pop()}).`);
}
async function bulkAccept() {
  const BP = S().BP; if (!BP) return;
  const todo = BP.fields.filter(f => f.tier === 'settled' && !verdictOf(f.name));
  if (!todo.length) { alert('No unreviewed settled fields.'); return; }
  if (!confirm(`Accept ${todo.length} settled field(s) without looking at them? Each is saved with the note "bulk: settled".`)) return;
  await putV(Object.fromEntries(todo.map(f => [f.name, { verdict: 'accept' as const, note: 'bulk: settled' }])));
}

// names two or more fields would have once saved corrections are applied (Andrew, 2026-10-13); each set gets its own
// color while the clashes button is on
const CLASH_COLORS = ['#e37400', '#9334e6', '#1a73e8', '#188038', '#d93025', '#00838f', '#b06000', '#c2185b'];
export function clashGroups(BP: ReviewData | null, removed: Removal[]): Record<string, { to: string; color: string }> {
  const by: Record<string, string[]> = {}, out: Record<string, { to: string; color: string }> = {};
  if (!BP) return out;
  for (const f of BP.fields) {
    if (removed.some(r => r.name === f.name)) continue;
    const v = BP.verdicts[f.name];
    const to = v && v.edit && v.edit.name && !v.applied ? v.edit.name : f.name;
    (by[to] ||= []).push(f.name);
  }
  let i = 0;
  for (const [to, names] of Object.entries(by)) if (names.length > 1) {
    const color = CLASH_COLORS[i++ % CLASH_COLORS.length]; names.forEach(n => { out[n] = { to, color }; });
  }
  return out;
}
function toggleClashes() {
  const cl = clashGroups(S().BP, S().removed), names = Object.keys(cl);
  const clashOn = !S().clashOn && names.length > 0;
  put({ clashOn });
  if (!clashOn) return;
  // go to a clashing field: one on this page if there is one, else the first (they may all be on another page)
  const here = names.find(n => fieldOf(n)?.page === app().page);
  select(here || names[0]);
}
export const reviewActions = { toggleClashes, bulkAccept, resetValidation };

/** What the header shows from Review: the clash count and the settled fields left. */
export function useHeaderCounts() {
  const bid = useApp(s => s.bid);
  const { BP, bpFor, removed, clashOn } = useReview();
  if (!BP || bpFor !== bid) return { loaded: false, clashes: 0, clashOn: false, clashTitle: '', settledLeft: 0 };
  const cl = clashGroups(BP, removed), sets: Record<string, string[]> = {};
  Object.entries(cl).forEach(([n, x]) => (sets[x.to] ||= []).push(n));
  const nc = Object.keys(sets).length;
  return {
    loaded: true, clashes: nc, clashOn: clashOn && nc > 0,
    clashTitle: nc ? Object.entries(sets).map(([to, ns]) => `${ns.join(' + ')} -> ${to}`).join('\n') : 'no two fields would share a name once saved corrections are applied',
    settledLeft: BP.fields.filter(f => f.tier === 'settled' && !BP.verdicts[f.name]?.verdict).length,
  };
}

// ---------------------------------------------------------------------------------------------------------- keys
export function key(e: KeyboardEvent): boolean {
  const { selected } = S();
  if (e.key === 'a') setVerdict('accept');
  else if (e.key === 'f') setVerdict('flag');
  else if (e.key === 'e') { const el = document.getElementById('eName') as HTMLInputElement | null; if (el) { el.focus(); el.select(); } }
  else if (e.key === 'c') setVerdict(null);
  else if (e.key === 'd') { if (isRemoved(selected)) keepField(); else removeField(); }
  else if (e.key === 'n' || e.key === 'ArrowRight') next(1);
  else if (e.key === 'p' || e.key === 'ArrowLeft') back();
  else if (e.key === 'u') setFilter({ unrevOnly: !S().unrevOnly });
  else return false;
  return true;
}

export function focus(k: string) { const f = S().BP?.fields.find(x => String(x.id) === k || x.name === k); if (f) select(f.name); }
