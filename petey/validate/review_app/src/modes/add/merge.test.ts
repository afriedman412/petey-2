// Add / remove keeps every field picked until it is added or cancelled (2026-10-27)
import { describe, expect, it } from 'vitest';
import { mergeProps, type Proposal } from './store';

const P = (name: string, x: number, extra: Partial<Proposal> = {}): Proposal =>
  ({ kind: 'text', page: 1, rect: [x, 0, x + 50, 12], geometry: 'drawn', options: [], name, name_options: [], evidence: [], ...extra });

describe('mergeProps', () => {
  it('a second pick joins the first', () => {
    expect(mergeProps([P('a', 0)], [P('b', 100)]).props.map(p => p.name)).toEqual(['a', 'b']);
  });
  it('a box already waiting is not proposed twice', () => {
    const got = mergeProps([P('a', 0)], [P('a2', 2)]);
    expect(got.props.map(p => p.name)).toEqual(['a']);
    expect(got.dup).toBe(1);
  });
  it("n / p's card takes the place of the last one n / p brought; picked cards stay", () => {
    const old = [P('clicked', 0), P('sug1', 100, { _sid: 's1', _nav: true })];
    expect(mergeProps(old, [P('sug2', 200, { _sid: 's2', _nav: true })], true).props.map(p => p.name)).toEqual(['clicked', 'sug2']);
  });
});
