// The page's pure helpers: the naming standard's printing, the home list's stages and duplicates.
import { describe, expect, it } from 'vitest';
import { descKey, findDups, SECTION_ORDER, sectionOf, statusOf } from '../components/home-data';
import type { Entry } from './types';
import { holdsPickerFocus, overlap, putScrollBack, stdPrint } from './util';

describe('stdPrint', () => {
  it('prints the parts in the standard order, empty parts left out', () => {
    expect(stdPrint({ subject: 'birth', suffix: 'dt', part: 'month' })).toBe('birth_dt_month');
    expect(stdPrint({ block_prefix: 'child', block_iteration: 2, subject: 'birth', suffix: 'dt' })).toBe('child_2_birth_dt');
  });
  it('shortens the long suffixes, from the subject too', () => {
    expect(stdPrint({ subject: 'first', suffix: 'name' })).toBe('first_nm');
    expect(stdPrint({ subject: 'zip_code' })).toBe('zip_cd');
    expect(stdPrint({ block_prefix: 'employer', subject: 'name' })).toBe('employer_nm');
    expect(stdPrint({ subject: 'name' })).toBe('name');                 // a bare subject with no block stays
  });
  it('writes a numbered part as one word', () => {
    expect(stdPrint({ subject: 'ssn', suffix: 'nbr', part: 'part 2' })).toBe('ssn_nbr_part2');
  });
});

const entry = (e: Partial<Entry>): Entry => ({ id: 'x', form: 'x', fields: 10, accepted: 0, flagged: 0, ...e });

describe('statusOf', () => {
  it('runs generated -> cleared -> in review -> validated', () => {
    expect(statusOf(entry({})).k).toBe('generated');
    expect(statusOf(entry({ passes: { when: '2026-10-15' } })).k).toBe('cleared');
    expect(statusOf(entry({ passes: { when: '2026-10-15' }, accepted: 3, touched: '2026-10-16' })).k).toBe('progress');
    expect(statusOf(entry({ accepted: 3, touched: '2026-10-16' })).k).toBe('generated');    // verdicts before the passes
    expect(statusOf(entry({ checked: { flagged: 1 } })).k).toBe('work');
    expect(statusOf(entry({ checked: { validated: true } })).k).toBe('validated');
  });
});

describe('duplicates', () => {
  it('leaves years and revision dates out of a description', () => {
    expect(descKey('Form 1040 (Rev. January 2024)')).toBe(descKey('Form 1040 2025'));
  });
  it('groups the same blank or the same description', () => {
    const d = findDups([
      entry({ id: 'a', form: 'f1040', desc: { text: 'U.S. Individual Income Tax Return 2024', from: '' } }),
      entry({ id: 'b', form: 'f1040_25', desc: { text: 'U.S. Individual Income Tax Return 2025', from: '' } }),
      entry({ id: 'c', form: 'w9', blank: 'h1' }), entry({ id: 'd', form: 'fw9', blank: 'h1' }),
      entry({ id: 'e', form: 'alone' }),
    ]);
    expect(d.a.others.map(o => o.id)).toEqual(['b']);
    expect(d.c.others).toEqual([{ id: 'd', why: 'same blank' }]);
    expect(d.e).toBeUndefined();
  });
});

describe('overlap', () => {
  it('is the share of the smaller box in common', () => {
    expect(overlap([0, 0, 10, 10], [5, 0, 15, 10])).toBeCloseTo(0.5);
    expect(overlap([0, 0, 10, 10], [20, 20, 30, 30])).toBe(0);
  });
});

describe('holdsPickerFocus', () => {
  it('the form menu and the home search let go of the keyboard once a form is open', () => {
    expect(holdsPickerFocus({ id: 'pick' })).toBe(true);
    expect(holdsPickerFocus({ id: 'hq' })).toBe(true);
  });
  it('a field being edited keeps it', () => {
    expect(holdsPickerFocus({ id: 'eName' })).toBe(false);
    expect(holdsPickerFocus(null)).toBe(false);
  });
});

describe('putScrollBack', () => {
  const stage = (scrollHeight: number) => ({ scrollTop: 0, scrollLeft: 0, scrollHeight, clientHeight: 800 });
  it('puts the scroll back on the same page, done once the page is tall enough', () => {
    const s = stage(2400);
    expect(putScrollBack({ page: 3, top: 900, left: 40 }, 3, s)).toBe(true);
    expect([s.scrollTop, s.scrollLeft]).toEqual([900, 40]);
  });
  it('keeps waiting while the image is not laid out yet', () => {
    expect(putScrollBack({ page: 3, top: 900, left: 0 }, 3, stage(800))).toBe(false);
  });
  it('leaves the top alone when the new tab opened on another page', () => {
    const s = stage(2400);
    expect(putScrollBack({ page: 3, top: 900, left: 0 }, 1, s)).toBe(true);
    expect(s.scrollTop).toBe(0);
  });
});

describe('home sections', () => {
  it('lists the benchmark forms first (2026-10-27)', () => {
    const bm = sectionOf(entry({ source: 'bm' })), lib = sectionOf(entry({ source: 'lib' }));
    expect(SECTION_ORDER[bm]).toBe(0);
    expect(SECTION_ORDER[bm]).toBeLessThan(SECTION_ORDER[sectionOf(entry({ focus: 1 }))]);
    expect(SECTION_ORDER[bm]).toBeLessThan(SECTION_ORDER[lib]);
  });
});
