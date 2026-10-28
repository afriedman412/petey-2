// Small helpers shared by the tabs, as the old page had them.

export type Rect = [number, number, number, number];

/** localStorage, never throwing (a private window, blocked site data): a read gives null, a write is dropped. */
export function store(k: string, v?: string | number): string | null {
  try {
    if (v === undefined) return localStorage.getItem(k);
    localStorage.setItem(k, String(v));
  } catch { /* nothing kept */ }
  return null;
}

export function storeJson<T>(k: string, fallback: T): T {
  try { return { ...fallback, ...JSON.parse(store(k) || '{}') }; } catch { return fallback; }
}

// the naming standard's printing (petey/naming.py, 2026-10-24): [block prefix]_[block iteration]_[subject]_[suffix]_
// [iteration]_[part]; the short suffix (first_name -> first_nm, zip_code -> zip_cd); a part part_1 -> part1
const SHORT_SUF: Record<string, string> = { name: 'nm', number: 'nbr', code: 'cd' };
export const PART_KEYS = ['block_prefix', 'block_iteration', 'subject', 'suffix', 'iteration', 'part'] as const;
export type PartKey = (typeof PART_KEYS)[number];
export type Parts = Partial<Record<PartKey, string | number | null>>;

export function stdPrint(p0: Parts): string {
  const p: Record<string, string> = Object.fromEntries(
    Object.entries(p0).map(([k, v]) => [k, v == null ? '' : String(v).trim()]));
  if (SHORT_SUF[(p.suffix || '').toLowerCase()]) p.suffix = SHORT_SUF[p.suffix.toLowerCase()];
  else if (!p.suffix && p.subject) {
    const w = p.subject.split('_');
    if (w.length > 1 && SHORT_SUF[w[w.length - 1]]) { p.suffix = SHORT_SUF[w.pop()!]; p.subject = w.join('_'); }
    else if (w.length === 1 && SHORT_SUF[w[0]] && p.block_prefix) { p.suffix = SHORT_SUF[w[0]]; p.subject = ''; }
  }
  if (p.part) p.part = p.part.replace(/^part[\s_]+(\d+)$/, 'part$1');
  return PART_KEYS.map(k => p[k]).filter(Boolean).join('_');
}

export function localNow(): string {
  const d = new Date(), z = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}

/** The share of the smaller box that the two boxes have in common. */
export function overlap(a: Rect, b: Rect): number {
  const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])), iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const i = ix * iy; if (i <= 0) return 0;
  return i / Math.min(Math.max((a[2] - a[0]) * (a[3] - a[1]), 1e-6), Math.max((b[2] - b[0]) * (b[3] - b[1]), 1e-6));
}

export const hull = (rs: Rect[], pad = 0): Rect => [
  Math.min(...rs.map(r => r[0])) - pad, Math.min(...rs.map(r => r[1])) - pad,
  Math.max(...rs.map(r => r[2])) + pad, Math.max(...rs.map(r => r[3])) + pad];

export const grow = (r: Rect, d: number): Rect => [r[0] - d, r[1] - d, r[2] + d, r[3] + d];

export const fileStem = (path: string) => String(path || '').split('/').pop()!.replace(/\.bpt$/, '');

export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;

/** After React has drawn the change and the browser has laid it out (scrolling to a box just selected). */
// the form pickers (the header's form menu, the home search): once a form is open they let go of the keyboard, or the
// page keys (1-9 for pages, the tabs' keys) went to them (Andrew, 2026-10-27: "when you load a new doc, the keys to
// switch pages dont work")
export const PICKER_IDS = ['pick', 'hq'];
export const holdsPickerFocus = (el: { id?: string } | null | undefined) => !!el && PICKER_IDS.includes(el.id || '');

export const afterPaint = (fn: () => void) => requestAnimationFrame(() => requestAnimationFrame(fn));

// the page keeps its scroll across a tab switch (Andrew, 2026-10-27: "when you change views, it reloads the top of the
// page of the current file"): the image is gone while the new tab loads, so the stage falls back to the top; it is put
// back once the image is laid out again, unless the new tab opened on another page
export interface HeldScroll { page: number; top: number; left: number }
export interface Scroller { scrollTop: number; scrollLeft: number; scrollHeight: number; clientHeight: number }
let heldScroll: HeldScroll | null = null;
export function holdScroll(page: number) {
  const s = document.getElementById('stage');
  heldScroll = s ? { page, top: s.scrollTop, left: s.scrollLeft } : null;
}
/** Put the held scroll back on `s`; true when it is done with (put back in full, or on another page). */
export function putScrollBack(h: HeldScroll, page: number, s: Scroller) {
  if (h.page !== page) return true;
  s.scrollTop = h.top; s.scrollLeft = h.left;
  return s.scrollHeight - s.clientHeight >= h.top;
}
/** After the tab has drawn (`final` once its image has loaded: nothing taller is coming). */
export function restoreScroll(page: number, final = false) {
  const h = heldScroll, s = document.getElementById('stage');
  if (!h || !s) return;
  if (putScrollBack(h, page, s) || final) heldScroll = null;
}

export function scrollToSel(selector: string, block: ScrollLogicalPosition = 'center') {
  afterPaint(() => {
    const el = document.querySelector(selector);
    if (el) el.scrollIntoView({ block, inline: 'center', behavior: 'smooth' });
  });
}

// one palette for the things drawn around boxes: option groups (Review, Groups) and tables / block groups (Grids, Blocks)
export const GROUP_COLORS = ['#4fc3f7', '#ba68c8', '#81c784', '#ffb74d', '#f06292', '#4db6ac', '#9575cd', '#dce775'];

// a block type's colour (Andrew, 2026-10-28: "every block type is a diff color ... most importantly it needs to be a
// diff color than the 'unvalidated' outline"): none of the colours that already mean something on the page (orange
// not yet accepted, green accepted, red flagged, grey in no block), each dark enough for the white page. By the type's
// place among the form's types that have blocks, in number order (BT1, BT2, BT6, ...): one colour per type on every
// page and tab. A form with more types than colours (6 of 709 forms with blocks) ranks the page's types instead, so
// no page repeats a colour.
export const BLOCK_COLORS = ['#0288d1', '#8e24aa', '#00897b', '#d81b60', '#3949ab', '#00acc1', '#37474f', '#795548'];
const typeNum = (t: string) => { const m = /(\d+)$/.exec(t); return m ? +m[1] : Infinity; };
const ranked = (ts: string[]) => [...new Set(ts)].sort((a, b) => typeNum(a) - typeNum(b) || a.localeCompare(b));
export function blockColor(type: string, formTypes: string[], pageTypes: string[] = []): string {
  let order = ranked(formTypes);
  if (order.length > BLOCK_COLORS.length && pageTypes.length) order = ranked(pageTypes);
  return BLOCK_COLORS[Math.max(0, order.indexOf(type)) % BLOCK_COLORS.length];
}
