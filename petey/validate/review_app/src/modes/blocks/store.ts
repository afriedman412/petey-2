// Blocks (block_types.py, 2026-10-21): block types and their blocks. An area dragged on the page is a block, of an
// existing type when its boxes pair with that type's template, else of a new type; a block dragged onto another
// becomes a block of that one's type (Andrew, 2026-10-22: like Groups). Block groups are gone (2026-10-21/22): a type
// and its blocks carry what they did. The tab's data and everything it does; Panel.tsx and index.tsx draw it.
import { create } from 'zustand';
import { j, mapi, send } from '../../lib/api';
import type { PageInfo } from '../../lib/types';
import { afterPaint, fileStem, stdPrint, type Rect } from '../../lib/util';
import { gotoPage, loadMode, toast, updateEntry } from '../../state/actions';
import { get as app } from '../../state/app';

/** a position of a type: its subject, suffix, iteration (its own number) and part */
export interface Slot { subject?: string | null; suffix?: string | null; iteration?: string | null; part?: string | null }
export interface Cell { name: string; rect: Rect; accepted: boolean }
export interface Differ { pos: number; name: string; want: string; held?: string | null }
export interface Block {
  n: number; code: string; page: number; bbox: Rect; template: boolean;
  names: (string | null)[]; cells: (Cell | null)[];
  prefix: string | null; iteration: string | null; by: string; parts_set: boolean;
  differs: Differ[]; kept: number[]; same_as: string[]; validated: boolean; start?: string;
}
export interface BType {
  id: string; label: string; auto: boolean; page: number; from?: string | null; boxes: number;
  blocks: Block[]; wordings: string[]; slots?: Slot[]; confirmed?: boolean | null;
}
export interface Loose { code: string; name: string; page: number; rect: Rect; kind: string }
export interface BlocksData { id: string; path: string; pages: PageInfo[]; sha?: string; types: BType[]; loose: Loose[] }

export const PKEYS = ['subject', 'suffix', 'iteration', 'part'] as const;   // block_types.SLOT_KEYS: a position's own number too (2026-10-25)
export type PKey = (typeof PKEYS)[number];
export type SlotText = Record<PKey, string>;

interface State {
  GD: BlocksData | null;
  /** the block clicked (its first box's code), open in the sidebar */
  selBlock: string | null;
  /** confirmed types whose parts are being edited again ("edit parts") */
  editing: Record<string, boolean>;
  tBusy: Record<string, boolean>;
  bBusy: Record<string, boolean>;
  /** a block just drawn as a new type: the type it nearly was, first in "assign to" */
  closestFor: Record<string, string | null | undefined>;
  /** the matrix's part boxes as typed, per type, with the saved parts they were typed over (nothing saved until
   *  "confirm"; a change to the saved parts shows those instead) */
  typed: Record<string, { base: string; slots: SlotText[] }>;
}

export const useBlocks = create<State>(() => ({
  GD: null, selBlock: null, editing: {}, tBusy: {}, bBusy: {}, closestFor: {}, typed: {},
}));
const S = useBlocks.getState, put = useBlocks.setState;
const bid = () => app().bid!;

// --------------------------------------------------------------------------------------------------- reading GD
export const allBlocks = (): Block[] => (S().GD?.types || []).flatMap(y => y.blocks);
export const blocksHere = (page: number) => (S().GD?.types || []).flatMap(y => y.blocks.filter(b => b.page === page).map(b => ({ y, b })));
export const typeOf = (tid: string) => (S().GD?.types || []).find(x => x.id === tid);
export const ref = (id: string) => `${fileStem(S().GD!.path)}_${id}`;
export const typeOff = (y: BType) => y.blocks.reduce((n, b) => n + (b.differs || []).filter(d => !d.held).length, 0);
export const typeSlots = (y: BType): Slot[] => y.slots || y.wordings.map(w => ({ subject: w }));
const str = (v: unknown) => (v == null ? '' : String(v));

export function blockState(y: BType, b: Block) {
  const acc = (b.cells || []).filter(x => x && x.accepted).length, n = (b.cells || []).filter(Boolean).length;
  if (b.validated) return 'validated ✓';
  const held = b.differs.filter(d => d.held).length, off = b.differs.length;
  const st = (b.same_as || []).length ? `same names as ${b.same_as.join(', ')}: set one's iteration` : !y.confirmed ? 'type not confirmed'
    : off ? `${off} name${off === 1 ? '' : 's'} off the type${held ? ` (${held} held by another field)` : ''}` : 'matches the type';
  return `${st} · ${acc} of ${n} accepted`;
}

// the type as a matrix (Andrew, 2026-10-22: block labels "work like the rest of the field names", the same inputs
// a standalone field has): a column per position with its subject / suffix / part, a row per block with its prefix
// and iteration, each cell the name it prints (block_types.block_ident + field_identifiers.print_name)
export function blockIdent(prefix: string | null | undefined, iteration: string | null | undefined, s: Slot) {
  const pt = (prefix || '').split('_').filter(Boolean); let st = (s.subject || '').split('_').filter(Boolean);
  while (pt.length && st.length && pt[pt.length - 1] === st[0] && (st.length > 1 || s.suffix)) st = st.slice(1);
  // the block's prefix and number lead (the naming standard, 2026-10-24; block_types.block_ident on the server)
  if (!pt.length) return { subject: [...st, ...(s.iteration ? [s.iteration] : [])].join('_'), suffix: s.suffix || '', iteration: iteration || '', part: s.part || '' };
  return { block_prefix: pt.join('_'), block_iteration: iteration || '', subject: st.join('_'), suffix: s.suffix || '', iteration: s.iteration || '', part: s.part || '' };
}
export const printIdent = (i: ReturnType<typeof blockIdent>) => stdPrint(i);

/** The matrix's part boxes for a type: as typed, while the saved parts are the ones they were typed over. */
export function shownSlots(y: BType): SlotText[] {
  const saved = typeSlots(y).map(s => Object.fromEntries(PKEYS.map(k => [k, str(s[k])])) as SlotText);
  const t = S().typed[y.id];
  return t && t.base === JSON.stringify(saved) ? t.slots : saved;
}
/** a part typed: the column's names reprint from it at once (nothing saved until "confirm") */
export function setSlot(tid: string, k: number, key: PKey, v: string) {
  const y = typeOf(tid); if (!y) return;
  const base = JSON.stringify(typeSlots(y).map(s => Object.fromEntries(PKEYS.map(x => [x, str(s[x])]))));
  const slots = shownSlots(y).map((s, i) => (i === k ? { ...s, [key]: v } : s));
  put({ typed: { ...S().typed, [tid]: { base, slots } } });
}
const dropTyped = (tid: string) => { const typed = { ...S().typed }; delete typed[tid]; put({ typed }); };

// ------------------------------------------------------------------------------------------------------ loading
export async function load(form: string) {
  const GD: BlocksData = await j(mapi('blocks', form));
  const sel = S().selBlock;
  put({ GD, selBlock: sel && GD.types.flatMap(y => y.blocks).some(b => b.code === sel) ? sel : null });
}

const scrollPanelTop = () => afterPaint(() => { const p = document.getElementById('panel'); if (p) p.scrollTop = 0; });
export function selectBlock(b: Block) {
  put({ selBlock: b.code });
  if (b.page !== app().page) gotoPage(b.page);
  scrollPanelTop();          // the open block's card is at the top
}
export const closeBlock = () => put({ selBlock: null });
export const editParts = (tid: string) => put({ editing: { ...S().editing, [tid]: true } });

// ------------------------------------------------------------------------------------------------------ actions
const setBusy = (k: 'tBusy' | 'bBusy', id: string, on: boolean) => put({ [k]: { ...S()[k], [id]: on } } as Partial<State>);

export async function typeValidate(tid: string) {
  let out;
  setBusy('tBusy', tid, true);
  try { out = await send('POST', mapi('blocks', bid(), '/tvalidate'), { type: tid }); }
  catch (e) { setBusy('tBusy', tid, false); alert((e as Error).message); return; }
  setBusy('tBusy', tid, false);
  if (out.entry) updateEntry(out.entry);
  await loadMode();
  toast(`${tid}: ${out.validated.length} block(s) validated` + (out.accepted ? `, ${out.accepted} cell(s) accepted` : '')
    + (out.off.length ? `; not validated: ${out.off.map((o: { block: string; off: number }) => `${o.block} (${o.off} name${o.off === 1 ? '' : 's'} off)`).join(', ')}` : '') + '.');
}

export async function typeFix(tid: string) {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/tfix'), { type: tid }); }
  catch (e) { alert((e as Error).message); return; }
  if (out.entry) updateEntry(out.entry);
  await loadMode();
  toast(renameNote(tid, out));
}

export async function blockParts(code: string, body: { prefix?: string; iteration?: string; by?: string }) {
  try { await send('POST', mapi('blocks', bid(), '/bparts'), { block: code, ...body }); }
  catch (e) { alert((e as Error).message); return; }
  await loadMode();
}

/** false when the server refused it (the checkbox goes back to what is saved) */
export async function typeAuto(tid: string, on: boolean): Promise<boolean> {
  try { await send('POST', mapi('blocks', bid(), '/tauto'), { type: tid, on }); }
  catch (e) { alert((e as Error).message); return false; }
  await loadMode();
  const y = typeOf(tid), n = y ? typeOff(y) : 0;
  if (on && y && y.confirmed && n && confirm(`${tid}: ${n} name(s) across its ${y.blocks.length} blocks do not print from its label and parts. Rename them all now (as Claude's renames, nothing accepted)?`)) typeFix(tid);
  return true;
}

export async function typeLabel(tid: string, label: string) {
  const y = typeOf(tid); if (!y || (y.label || '') === label.trim()) return;
  try { await send('POST', mapi('blocks', bid(), '/tlabel'), { type: tid, label }); }
  catch (e) { alert((e as Error).message); return; }
  const GD = S().GD; if (!GD) return;
  put({ GD: { ...GD, types: GD.types.map(x => (x.id === tid ? { ...x, label: label.trim() } : x)) } });
}

interface RenameOut { renamed: number; same?: string[]; held?: string[]; errors: string[] }
// what a rename did, with what it left: blocks coming to one name, names another field keeps
const renameNote = (tid: string, out: RenameOut) => `${tid ? tid + ': ' : ''}${out.renamed} rename(s) applied as Claude's.`
  + ((out.same || []).length ? ` Not renamed, same names: ${out.same!.join(', ')} (set one's iteration).` : '')
  + ((out.held || []).length ? ` Left, the name is another field's: ${out.held!.slice(0, 3).join('; ')}${out.held!.length > 3 ? ` and ${out.held!.length - 3} more` : ''}.` : '')
  + (out.errors.length ? ' Not applied: ' + out.errors.join('; ') : '');

export async function typeConfirm(tid: string) {
  const y0 = typeOf(tid); if (!y0) return;
  // the parts as typed in the matrix: an empty box is no part
  const slots = shownSlots(y0).map(t => { const s: Partial<SlotText> = {};
    PKEYS.forEach(key => { if (t[key].trim()) s[key] = t[key].trim(); });
    return s; });
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/confirm'), { type: tid, slots }); }
  catch (e) { alert((e as Error).message); return; }
  const editing = { ...S().editing }; delete editing[tid];
  put({ editing });
  dropTyped(tid);
  await loadMode();
  const y = typeOf(tid), n = y ? typeOff(y) : 0;
  toast(`${tid} confirmed: ${out.wordings.length} positions.` + ((out.numbered || []).length
    ? ` Positions ${out.numbered.join(', ')} were alike and are numbered (the iteration row): if one is another thing, give it its own subject.` : ''));
  if (n && confirm(`${tid}: ${n} name(s) across its ${y!.blocks.length} blocks do not print from these parts. Rename them all now (as Claude's renames, nothing accepted)?`)) typeFix(tid);
}

export async function blockValidate(code: string) {
  let out;
  setBusy('bBusy', code, true);
  try { out = await send('POST', mapi('blocks', bid(), '/bvalidate'), { block: code }); }
  catch (e) { setBusy('bBusy', code, false); alert((e as Error).message); return; }
  setBusy('bBusy', code, false);
  if (out.entry) updateEntry(out.entry);
  await loadMode();
  toast(out.ok ? `Validated against ${out.type}` + (out.accepted.length ? `: ${out.accepted.length} cell(s) accepted.` : ' (every cell already had a verdict).')
    : `${out.differs.length} name(s) off ${out.type}'s wordings; nothing accepted (rename them, cancel the renames that are wrong, or edit the type).`);
}

export async function blockKeep(code: string, pos: number, on: boolean) {
  try { await send('POST', mapi('blocks', bid(), '/bkeep'), { block: code, pos, on }); }
  catch (e) { alert((e as Error).message); return; }
  await loadMode();
}

export async function blockFix(code: string) {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/bfix'), { block: code }); }
  catch (e) { alert((e as Error).message); return; }
  if (out.entry) updateEntry(out.entry);
  await loadMode();
  toast(renameNote('', out));
}

// the header's "run finders" (it switches to Blocks first and says 'running…' itself)
export async function runFinders() {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/finders'), {}); }
  catch (e) { alert((e as Error).message); return; }
  await loadMode();
  const g: string[] = out.grids || [], sup: string[] = out.superseded || [], pr = out.primed || {};
  const fill = Object.values(pr.filled || {}).reduce((a: number, v) => a + (v as unknown[]).length, 0);
  const found = Object.values(pr.found || {}).reduce((a: number, v) => a + (v as unknown[]).length, 0);
  const grew = Object.entries(pr.grew || {}).map(([t, ns]) => `${t} +${(ns as unknown[]).length} position${(ns as unknown[]).length === 1 ? '' : 's'}`);
  const prim = [fill ? `${fill} empty position${fill === 1 ? '' : 's'} filled` : '', grew.join(', '), found ? `${found} more cop${found === 1 ? 'y' : 'ies'} found` : ''].filter(Boolean);
  const gm: { name: string }[] = out.groups_made || [];
  const gs = (gm.length ? ` Groups: ${gm.length} made first (${gm.slice(0, 6).map(x => x.name).join(', ')}${gm.length > 6 ? ', …' : ''}), new on the Groups tab; u there ungroups one.` : '')
    + (out.groups_error ? ` Groups not made: ${out.groups_error}` : '');
  // one message, the groups' sentence at its end (2026-10-26: it came a moment later as a second toast)
  toast((prim.length ? `Your blocks: ${prim.join('; ')}. ` : '') + (g.length ? `Grids: ${g.length} (${g.slice(0, 6).join(', ')}${g.length > 6 ? ', …' : ''})${sup.length ? `, in place of blocks ${sup.slice(0, 6).join(', ')}${sup.length > 6 ? ', …' : ''}` : ''}. ` : 'No grids. ')
    + (out.types.length ? `Blocks: ${out.types.length} new block type${out.types.length === 1 ? '' : 's'} (${out.types.join(', ')}), ${out.blocks} blocks, ${out.fields} fields.`
      : 'No new repeated blocks among the fields in no block or grid.') + gs);
}

export async function blockDetect() {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/rescan'), { page: app().page }); }
  catch (e) { alert((e as Error).message); return; }
  await loadMode();
  const lab = Object.entries(out.by_labels || {}).flatMap(([t, ns]) => (ns as number[]).map(n => `${t}-${n}`)), emp = Object.entries(out.empty || {});
  const grew = Object.entries(out.grew || {}).map(([t, v]) => { const ns = v as string[];
    return `${t} took in ${ns.length} field${ns.length === 1 ? '' : 's'} repeating in all its blocks (${ns.slice(0, 4).join(', ')}${ns.length > 4 ? ', …' : ''})`; });
  toast((grew.length ? grew.join('; ') + '. ' : '') + (out.n ? 'Found ' + Object.entries(out.found).map(([t, ns]) => (ns as number[]).map(n => `${t}-${n}`).join(', ')).join('; ') + '.'
    + (lab.length ? ` By their printed labels: ${lab.join(', ')}.` : '')
    + (emp.length ? ` With empty positions (drag the missing fields onto them): ${emp.map(([b, k]) => `${b} (${k})`).join(', ')}.` : '')
    : 'No new copies of a block type on this page.'));
}

export async function typeAssign(from: string, tid: string) {          // each block of `from` given type `tid`, one after another
  const y = typeOf(from); if (!y) return;
  const said: string[] = [];
  for (const b of y.blocks) {
    try { const out = await send('POST', mapi('blocks', bid(), '/assign'), { block: b.code, type: tid }); said.push(`${tid}-${out.block}`); }
    catch (e) { said.push(`${from}-${b.n}: ${(e as Error).message}`); }
  }
  await loadMode();
  toast(`${from} into ${tid}: ${said.join(', ')}.`);
}

export async function blockAssign(code: string, tid: string) {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/assign'), { block: code, type: tid }); }
  catch (e) { alert((e as Error).message); return; }
  await loadMode();
  toast((out.refit ? `${out.type}-${out.block} fitted again.` : `Now ${out.type}-${out.block} (was a block of ${out.was}).`) + (out.missing.length ? ` It has no box for ${out.type}'s position${out.missing.length === 1 ? '' : 's'} ${out.missing.join(', ')}.` : '')
    + (out.extra.length ? ` Left out (no place in ${out.type}): ${out.extra.join(', ')}.` : '')
    + (out.renamed ? ` ${out.renamed} name${out.renamed === 1 ? '' : 's'} put to ${out.type}'s wordings.` : '')
    + ((out.held || []).length ? ` Not renamed, another field has the name: ${out.held.join('; ')}.` : '')
    + ((out.same || []).length ? ` Not renamed, same names as ${out.same.join(', ')}: set one's iteration.` : '')
    + ((out.rename_errors || []).length ? ` Rename errors: ${out.rename_errors.join('; ')}` : ''));
}

// a block dragged onto another (Andrew, 2026-10-22, as in Groups): it becomes a block of that one's type
export function blockDropped(src: string, onto: Block, y: BType) {
  if (src === onto.code) return;
  const s = allBlocks().find(x => x.code === src), sy = s && (S().GD?.types || []).find(x => x.blocks.includes(s));
  if (!s) return;
  if (sy && sy.id === y.id) { toast(`Already a block of ${y.id}.`); return; }
  blockAssign(src, y.id);
}

// a field dropped on a block (Andrew, 2026-10-22: "can we drag fields on to a block to add them?")
export async function blockAddField(code: string, field: string) {
  let out;
  try {
    out = await send('POST', mapi('blocks', bid(), '/addfield'), { block: code, field });
    if (out.grow_needed) {          // no empty position of its kind: a new position of the type, if the person says so
      if (!confirm(`${out.why}. Add a new position to ${out.type} for it? (It stays empty in ${out.type}'s other blocks.)`)) return;
      out = await send('POST', mapi('blocks', bid(), '/addfield'), { block: code, field, grow: true });
    }
  } catch (e) { alert((e as Error).message); return; }
  put({ selBlock: out.code });
  await loadMode();
  toast(out.said.join('; ') + '.'
    + (out.renamed ? ` ${out.renamed} name${out.renamed === 1 ? '' : 's'} put to ${out.type}'s wordings.` : '')
    + ((out.held || []).length ? ` Not renamed, another field has the name: ${out.held.join('; ')}.` : '')
    + ((out.same || []).length ? ` Not renamed, same names as ${out.same.join(', ')}: set one's iteration.` : '')
    + ((out.rename_errors || []).length ? ` Rename errors: ${out.rename_errors.join('; ')}` : ''));
}

export async function blockOut(code: string) {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/out'), { block: code }); }
  catch (e) { alert((e as Error).message); return; }
  put({ selBlock: null });
  await loadMode();
  toast(out.said.join('; ') + '.');
}

export async function blockDraw(rect: Rect) {
  let out;
  try { out = await send('POST', mapi('blocks', bid(), '/draw'), { page: app().page, rect }); }
  catch (e) { alert('Could not make a block: ' + (e as Error).message); return; }
  if (out.code) put({ selBlock: out.code, closestFor: { ...S().closestFor, [out.code]: out.closest && out.closest.type } });
  await loadMode();
  toast(out.found ? `${out.type}: ${out.found} blocks in the area (${out.blocks.map((n: number) => out.type + '-' + n).join(', ')}), ${out.fresh} new.`
    : out.already ? `That is block ${out.block} of ${out.type} already.`
    : out.new ? `New block type ${out.type}.` + (out.closest ? ` Closest: ${out.closest.type} (${out.closest.differs}).` : '')
    : `${out.type}: block ${out.block} of ${out.of}.` + ((out.left || []).length ? ' ' + out.left.join('; ') + '.' : ''));
}

// ---------------------------------------------------------------------------------------------------------- keys
export function key(e: KeyboardEvent): boolean {
  const sel = S().selBlock;
  const all = allBlocks().slice().sort((a, b) => a.page - b.page || a.bbox[1] - b.bbox[1] || a.bbox[0] - b.bbox[0]);
  if ((e.key === 'n' || e.key === 'p') && all.length) {
    const k = all.findIndex(b => b.code === sel); selectBlock(all[(k + (e.key === 'n' ? 1 : -1) + all.length) % all.length]); return true;
  }
  if ((e.key === 'Delete' || e.key === 'Backspace') && sel) { blockOut(sel); return true; }
  if (e.key === 'Enter' && sel) { blockValidate(sel); return true; }
  if (e.key === 'Escape' && sel) { closeBlock(); return true; }
  return false;
}

// a link's block: BT4-2 (BT4 its first block), its code, or the block holding a field
export function focus(k: string) {
  const GD = S().GD; if (!GD) return;
  const m = /^(BT\d+)(?:-(\d+))?$/.exec(k), y = m && (GD.types || []).find(t => t.id === m[1]);
  const b = (y && (m![2] ? y.blocks.find(x => String(x.n) === m![2]) : y.blocks[0]))
    || allBlocks().find(x => x.code === k || (x.names || []).includes(k));
  if (b) selectBlock(b);
}
