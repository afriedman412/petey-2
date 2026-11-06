// a suggested name that clashes is made free (Andrew, 2026-10-31: "any suggested duplicate name should just be
// converted to a non-clashing name, either by increasing the iteration value or by adding one")
import { describe, expect, it } from 'vitest';
import { freeName, freeSuggested, type AddData, type Proposal } from './store';

const P = (name: string, name_source = 'page text'): Proposal =>
  ({ kind: 'text', page: 1, rect: [0, 0, 10, 10], geometry: 'finder', options: [], name, name_source, name_options: [], evidence: [] }) as Proposal;
const BP = { fields: [{ name: 'sort_code', page: 1, rect: [0, 0, 10, 10] }, { name: 'x_line_2', page: 1, rect: [0, 0, 1, 1] }], field_specs: {} } as unknown as AddData;

describe('freeName', () => {
  const taken = (ns: string[]) => (n: string) => ns.includes(n);
  it('adds _2, or raises a trailing number', () => {
    expect(freeName('sort_code', taken(['sort_code']))).toBe('sort_code_2');
    expect(freeName('sort_code', taken(['sort_code', 'sort_code_2']))).toBe('sort_code_3');
    expect(freeName('x_line_2', taken(['x_line_2', 'x_line_3']))).toBe('x_line_4');
    expect(freeName('free', taken([]))).toBe('free');
  });
});

describe('freeSuggested', () => {
  it("renames a suggested name the blueprint or another card has, not one typed by hand", () => {
    const out = freeSuggested({ BP, added: [], removed: [], props: [P('sort_code'), P('x_line_2'), P('sort_code', 'hand')] });
    expect(out.map(p => p.name)).toEqual(['sort_code_2', 'x_line_3', 'sort_code']);
  });
  it('two cards with one new name: the newer one, on top, is renamed', () => {
    const out = freeSuggested({ BP, added: [], removed: [], props: [P('dob'), P('dob')] });
    expect(out.map(p => p.name)).toEqual(['dob_2', 'dob']);
  });
  it('the same array when nothing clashes', () => {
    const props = [P('a'), P('b')];
    expect(freeSuggested({ BP, added: [], removed: [], props })).toBe(props);
  });
});
