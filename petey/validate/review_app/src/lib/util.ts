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
export const afterPaint = (fn: () => void) => requestAnimationFrame(() => requestAnimationFrame(fn));

export function scrollToSel(selector: string, block: ScrollLogicalPosition = 'center') {
  afterPaint(() => {
    const el = document.querySelector(selector);
    if (el) el.scrollIntoView({ block, inline: 'center', behavior: 'smooth' });
  });
}

// one palette for the things drawn around boxes: option groups (Review, Groups) and tables / block groups (Grids, Blocks)
export const GROUP_COLORS = ['#4fc3f7', '#ba68c8', '#81c784', '#ffb74d', '#f06292', '#4db6ac', '#9575cd', '#dce775'];
