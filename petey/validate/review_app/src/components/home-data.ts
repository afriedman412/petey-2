// The home list's sections, stages and possible duplicates (pure: tested in home-data.test.ts).
import type { Entry } from '../lib/types';

// the benchmark forms first (Andrew, 2026-10-27: "promote the 'passed the business cut' forms to their own section, at the top")
export const SECTIONS: Record<string, string> = {
  bm: 'flat-structure benchmark (passed the business cut)', mg: 'hand-picked forms (source_pdfs/manual_grabs)', fin: 'finance forms (scraped 2026-10-29)', focus: 'name-check follow-up (flags to confirm)', t1: 'launch T1', t2: 'launch T2', t3: 'launch T3', t4: 'launch T4',
  rerun: 'fresh runs of library forms (new code)', lib: 'library', je: 'judge-eval side copies', rl: 'relabels', fl: 'flat forms',
};
export const SECTION_SHORT: Record<string, string> = {
  focus: 'review queue', t1: 'launch T1', t2: 'launch T2', t3: 'launch T3', t4: 'launch T4', rerun: 'fresh run',
  lib: 'library', je: 'side copy', rl: 'relabel', fl: 'flat', bm: 'benchmark', mg: 'hand-picked', fin: 'finance',
};
export const sectionOf = (x: Entry): string => x.focus != null ? 'focus' : x.launch ? 't' + x.launch : x.rerun ? 'rerun' : (x.source || '');
export const SECTION_ORDER: Record<string, number> = Object.fromEntries(Object.keys(SECTIONS).map((k, i) => [k, i]));

// one status per form, the worst first. The pipeline (Andrew, 2026-10-16): generated (the generation pipeline and its
// loops) -> cleared (the automated passes, recorded by eval/passes_record.py) -> validated (the manual check: in
// review, needs work, changed since check, validated). A form is in review only once cleared, with verdicts made after
// that; without the passes it is generated, unless it was fully checked before they existed.
export type Status = { k: 'validated' | 'work' | 'recheck' | 'progress' | 'cleared' | 'generated'; t: string };
export function statusOf(b: Entry): Status {
  const c = b.checked;
  if (c && c.validated) return { k: 'validated', t: 'validated' };
  if (c && (c.flagged || c.pending)) return { k: 'work', t: 'needs work' };
  if (c && c.stale) return { k: 'recheck', t: 'changed since check' };
  const reviewed = !!b.passes && (b.accepted + b.flagged) > 0 && (b.touched || '') > (b.passes.when || '');
  if (reviewed) return { k: 'progress', t: 'in review' };
  if (b.passes) return { k: 'cleared', t: 'cleared' };
  return { k: 'generated', t: 'generated' };
}
export const STATUS_ORDER: Record<Status['k'], number> = { generated: 0, cleared: 1, progress: 2, work: 3, recheck: 4, validated: 5 };

export const HSTAGES: [string | null, [string, string][]][] = [
  [null, [['', 'blueprints']]],
  ['automated', [['generated', 'generated'], ['cleared', 'cleared']]],
  ['validation (manual)', [['progress', 'in review'], ['work', 'needs work'], ['recheck', 'changed since check'], ['validated', 'validated']]],
  [null, [['copy', 'unsaved copies'], ['dup', 'possible duplicates']]],
];

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

export const homeMatch = (b: Entry, st: string, dups: Dups) =>
  st === 'copy' ? !!b.draft : st === 'dup' ? !!dups[b.id] : !st || statusOf(b).k === st;
