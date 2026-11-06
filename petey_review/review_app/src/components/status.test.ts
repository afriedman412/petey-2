// the home list's status (Andrew, 2026-11-03: "we only need 3 statuses: validated, structure validated and
// generated"; "a little V icon and/or a little S icon"): V validated, S structure validated, both icons when both,
// everything else generated with the reason kept for its tooltip
import { describe, expect, it } from 'vitest';
import type { Entry } from '../lib/types';
import { homeMatch, sectionName, SECTIONS, statusOf } from './home-data';

const e = (x: Partial<Entry>) => ({ id: 'bm__x', source: 'bm', form: 'x', fields: 3, accepted: 0, flagged: 0, ...x }) as Entry;

describe('statusOf', () => {
  it('structure validated, validated, and both icons on one form', () => {
    expect(statusOf(e({ structure: { when: 'now', stale: false } }))).toMatchObject({ k: 'structure', v: false, s: true });
    expect(statusOf(e({ checked: { validated: true } }))).toMatchObject({ k: 'validated', v: true, s: false });
    expect(statusOf(e({ structure: { stale: false }, checked: { validated: true } }))).toMatchObject({ k: 'both', v: true, s: true });
  });
  it('a stale structure stamp drops the S', () => {
    expect(statusOf(e({ structure: { stale: true }, checked: { validated: true } })).k).toBe('validated');
    expect(statusOf(e({ structure: { stale: true } }))).toMatchObject({ k: 'generated', why: 'changed since its check' });
  });
  it('needs work, new fields and changed since check are generated, with why', () => {
    expect(statusOf(e({ checked: { flagged: 2 } }))).toMatchObject({ k: 'generated', why: 'needs work: 2 flagged' });
    expect(statusOf(e({ new_fields: 7 }))).toMatchObject({ k: 'generated', why: '7 new fields to check' });
    expect(statusOf(e({ checked: { stale: true } })).why).toBe('changed since its check');
    expect(statusOf(e({})).why).toBeUndefined();
  });
  it('validated and structure validated come before new fields', () => {
    expect(statusOf(e({ new_fields: 2, checked: { validated: true } })).k).toBe('validated');
    expect(statusOf(e({ new_fields: 2, structure: { stale: false } })).k).toBe('structure');
  });
});

describe('the filter', () => {
  const g = e({}), v = e({ checked: { validated: true } }), s = e({ structure: { stale: false } }),
    b = e({ checked: { validated: true }, structure: { stale: false } });
  const shown = (st: string, hide: string[] = []) => [g, v, s, b].map(x => homeMatch(x, st, {}, hide));
  it('shows one kind, exactly', () => {
    expect(shown('')).toEqual([true, true, true, true]);
    expect(shown('generated')).toEqual([true, false, false, false]);
    expect(shown('validated')).toEqual([false, true, false, false]);
    expect(shown('both')).toEqual([false, false, false, true]);
  });
  it('hides any of the validated kinds; the kind picked to show still shows', () => {
    expect(shown('', ['validated', 'both'])).toEqual([true, false, true, false]);
    expect(shown('', ['structure'])).toEqual([true, true, false, true]);
    expect(shown('both', ['both'])).toEqual([false, false, false, true]);
  });
});

describe('ignored (2026-11-03)', () => {
  const ig = { reason: 'too messy', when: '2026-11-03 12:00:00' };
  it('a whole form ignored is its own status, ahead of V and S, its reason the why', () => {
    expect(statusOf(e({ ignored: ig }))).toMatchObject({ k: 'ignored', why: 'too messy' });
    expect(statusOf(e({ ignored: ig, checked: { validated: true }, structure: { stale: false } })).k).toBe('ignored');
  });
  it('the filter shows or hides it', () => {
    const f = e({ ignored: ig }), g = e({});
    expect([f, g].map(x => homeMatch(x, 'ignored', {}))).toEqual([true, false]);
    expect([f, g].map(x => homeMatch(x, '', {}, ['ignored']))).toEqual([false, true]);
  });
});

describe('light-path misses filter', () => {
  it('shows the forms whose tuning-set pages have misses, not those with none or off the tuning set', () => {
    const m = e({ light: { missed: 3, junk: 1 } }), z = e({ light: { missed: 0, junk: 4 } }), off = e({});
    expect([m, z, off].map(x => homeMatch(x, 'light', {}))).toEqual([true, false, false]);
  });
});

describe('sectionName', () => {
  it("the review queue is named by its batch's description, the old name when there is none", () => {
    expect(sectionName('focus', [e({ focus: 0, focus_why: 'thin topics, batch 1' })])).toBe('review queue: thin topics, batch 1');
    expect(sectionName('focus', [e({ focus: 0 })])).toBe(SECTIONS.focus);
    expect(sectionName('bm', [e({ focus_why: 'x' })])).toBe(SECTIONS.bm);
  });
});
