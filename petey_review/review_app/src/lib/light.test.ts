// the light path's misses and junk on one page (2026-11-04)
import { describe, expect, it } from 'vitest';
import { causeSummary, lightOnPage } from './light';
import type { LightLayer } from './types';

const l: LightLayer = {
  missed: [{ page: 1, rect: [0, 0, 10, 10], cause: 'no box', code: 'a' }, { page: 1, rect: [0, 20, 10, 30], cause: 'jev', code: 'b' },
           { page: 1, rect: [0, 40, 10, 50], cause: 'no box', code: 'c' }, { page: 2, rect: [0, 0, 10, 10], cause: 'one box', code: 'd' }],
  junk: [{ page: 1, rect: [50, 50, 90, 60], jev: 0.83 }, { page: 2, rect: [50, 50, 90, 60], jev: null }],
};

describe('lightOnPage', () => {
  it("keeps the page's misses and junk and counts the causes", () => {
    const p1 = lightOnPage(l, 1);
    expect(p1.missed.map(m => m.code)).toEqual(['a', 'b', 'c']);
    expect(p1.junk).toHaveLength(1);
    expect(p1.byCause).toEqual({ 'no box': 2, jev: 1 });
  });
  it('a form off the tuning set has nothing', () => {
    expect(lightOnPage(null, 1)).toMatchObject({ missed: [], junk: [], byCause: {} });
  });
});

describe('causeSummary', () => {
  it('total first, causes in a fixed order', () => {
    expect(causeSummary({ jev: 1, 'no box': 2 })).toBe('3: no box 2, Jev out 1');
    expect(causeSummary({})).toBe('0');
  });
});
