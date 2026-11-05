// The home list's sections, stages and possible duplicates (pure: tested in home-data.test.ts).
import type { Entry } from '../lib/types';

// the benchmark forms first (Andrew, 2026-10-27: "promote the 'passed the business cut' forms to their own section, at the top")
export const SECTIONS: Record<string, string> = {
  bm: 'flat-structure benchmark (passed the business cut)', mg: 'hand-picked forms (source_pdfs/manual_grabs)', fin: 'finance forms (scraped 2026-10-29)', pv: 'private-sector forms', nov3: 'added 2026-11-03 evening (hand-picked + big publishers)', focus: 'name-check follow-up (flags to confirm)', t1: 'launch T1', t2: 'launch T2', t3: 'launch T3', t4: 'launch T4',
  rerun: 'fresh runs of library forms (new code)', lib: 'library', je: 'judge-eval side copies', rl: 'relabels', fl: 'flat forms',
};
export const SECTION_SHORT: Record<string, string> = {
  focus: 'review queue', t1: 'launch T1', t2: 'launch T2', t3: 'launch T3', t4: 'launch T4', rerun: 'fresh run',
  lib: 'library', je: 'side copy', rl: 'relabel', fl: 'flat', bm: 'benchmark', mg: 'hand-picked', fin: 'finance', pv: 'private', nov3: 'Nov 3',
};
export const sectionOf = (x: Entry): string => x.focus != null ? 'focus' : x.launch ? 't' + x.launch : x.rerun ? 'rerun' : (x.source || '');
// a section's name in the menus; the review queue's is its batch's description when focus.json gives one (2026-11-03)
export const sectionName = (k: string, list: Entry[]): string => {
  const why = k === 'focus' ? list.find(b => b.focus != null && b.focus_why)?.focus_why : undefined;
  return why ? `review queue: ${why}` : SECTIONS[k];
};
export const SECTION_ORDER: Record<string, number> = Object.fromEntries(Object.keys(SECTIONS).map((k, i) => [k, i]));

// one status per form (Andrew, 2026-11-03: "we only need 3 statuses: validated, structure validated and generated"):
// VALIDATED = every name accepted, STRUCTURE VALIDATED = "accept structure" (fields, kinds, groups, grids, blocks), shown
// as a V and an S icon, a form with both showing both; GENERATED = everything else, never looked at fully or changed
// since its check (cleared, in review, needs work, changed since check, new fields to check went into it; why
// still says which). IGNORED (2026-11-03, the header's "ignore": a whole form too messy, filled in or otherwise not
// usable now) comes before them all; its reason is the why.
export type StatusK = 'generated' | 'structure' | 'validated' | 'both' | 'ignored';
export type Status = { k: StatusK; v: boolean; s: boolean; why?: string };
export function statusOf(b: Entry): Status {
  const c = b.checked;
  const v = !!c?.validated, s = !!b.structure && !b.structure.stale;
  if (b.ignored) return { k: 'ignored', v, s, why: b.ignored.reason };
  if (v || s) return { k: v && s ? 'both' : v ? 'validated' : 'structure', v, s };
  const why = c && (c.flagged || c.pending) ? `needs work: ${[c.flagged && `${c.flagged} flagged`, c.pending && `${c.pending} to apply`].filter(Boolean).join(', ')}`
    // once fully checked, then fields added or renamed (a sweep, an edit) still to check (2026-11-02)
    : b.new_fields ? `${b.new_fields} new field${b.new_fields === 1 ? '' : 's'} to check`
    : (c && c.stale) || b.structure?.stale ? 'changed since its check'
    : (b.accepted + b.flagged) > 0 ? `${b.accepted + b.flagged} of ${b.fields} fields reviewed` : undefined;
  return { k: 'generated', v, s, why };
}
export const STATUS_ORDER: Record<StatusK, number> = { generated: 0, structure: 1, validated: 2, both: 3, ignored: 4 };
export const STATUS_TEXT: Record<StatusK, string> = { generated: 'generated', structure: 'structure validated', validated: 'validated', both: 'validated + structure validated', ignored: 'ignored' };

// the home filter (2026-11-03: "filtering should be done with a dropdown"): show one kind, and hide any of the
// validated ones or the ignored ones ("ignored should be another status that can be hidden or shown by the filter"). The kinds are exact: "validated" is V without S, "both" is V and S.
export const SHOW: [string, string][] = [['', 'all'], ['generated', 'generated'], ['structure', 'structure validated'], ['validated', 'validated'],
  ['both', 'both'], ['ignored', 'ignored'], ['copy', 'unsaved copies'], ['dup', 'possible duplicates']];
export const HIDE: [StatusK, string][] = [['validated', 'validated'], ['structure', 'structure validated'], ['both', 'both'], ['ignored', 'ignored']];

// possible duplicates (Andrew, 2026-10-15: "so we can figure out what duplicates we have"): the same blank file, or
// the same description once years, revision dates and punctuation are left out (2024 / 2025 editions of one form)
export type Dups = Record<string, { key: string; others: { id: string; why: string }[] }>;
const MONTHS = 'january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec';
export const descKey = (t: string) => t.toLowerCase().replace(/\((rev|revised|ed|edition)[^)]*\)/g, ' ')
  .replace(new RegExp(`\\b(19|20)\\d\\d\\b|\\b(rev|revised|${MONTHS})\\b`, 'g'), ' ')
  .replace(/[^a-z0-9]+/g, ' ').trim();

export function findDups(list: Entry[]): Dups {
  const parent: Record<string, string> = {};
  const find = (x: string): string => (parent[x] === x ? x : (parent[x] = find(parent[x])));
  const seen: Record<string, string> = {};
  for (const b of list) parent[b.id] = b.id;
  for (const b of list) for (const k of [b.blank && 'h:' + b.blank, b.desc && b.desc.text && 'd:' + descKey(b.desc.text)]) {
    if (!k) continue;
    if (seen[k]) parent[find(b.id)] = find(seen[k]); else seen[k] = b.id;
  }
  const groups: Record<string, Entry[]> = {};
  for (const b of list) (groups[find(b.id)] ||= []).push(b);
  const of: Dups = {};
  for (const g of Object.values(groups)) {
    if (g.length < 2) continue;
    const key = g.map(b => b.form).sort()[0];
    for (const b of g) of[b.id] = { key, others: g.filter(o => o !== b).map(o => ({ id: o.id, why: o.blank && o.blank === b.blank ? 'same blank' : 'same description' })) };
  }
  return of;
}

export const homeMatch = (b: Entry, st: string, dups: Dups, hide: string[] = []) => {
  const k = statusOf(b).k;
  return (st === 'copy' ? !!b.draft : st === 'dup' ? !!dups[b.id] : !st || k === st) && (k === st || !hide.includes(k));
};
