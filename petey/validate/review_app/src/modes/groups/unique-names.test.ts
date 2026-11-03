// no group or loose box is given a name already in use (Andrew, 2026-11-01, bm__mu_009291445aab p3_o4: "no field or
// group should ever be given a name that is already in use"): a box taken out of a group under its field's name
// takes the next free one when a unit already has it
import { describe, expect, it } from 'vitest';
import { looseOf, useGroups, type Unit } from './store';

const box = (field: string, key: string | null) => ({ id: key === null ? field : `${field}::${key}`, field, key, page: 1, rect: [0, 0, 1, 1] });

describe('looseOf', () => {
  it("a box of its own taken out of a group keeps its field's name, or the next free one", () => {
    useGroups.setState({ BP: { items: { p3_f7: box('p3_f7', null), 'g::a': box('g', 'a') }, other_names: ['notes'] } } as never);
    const src: Unit = { uid: 1, name: 'g', type: 'category', items: ['p3_f7', 'g::a'], origin: 'g' };
    expect(looseOf([src], src, 'p3_f7').name).toBe('p3_f7');
    const clash: Unit = { uid: 2, name: 'p3_f7', type: 'category', items: [], origin: null };
    expect(looseOf([src, clash], src, 'p3_f7').name).toBe('p3_f7_2');
  });
  it("an option taken out is named group_key, past a field's name", () => {
    useGroups.setState({ BP: { items: { 'g::a': box('g', 'a') }, other_names: ['g_a'] } } as never);
    const src: Unit = { uid: 1, name: 'g', type: 'category', items: ['g::a'], origin: 'g' };
    expect(looseOf([src], src, 'g::a').name).toBe('g_a_2');
  });
});
