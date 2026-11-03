// the Add card says a name is taken before "add this field", not after the save refuses it
// (Andrew, 2026-10-29: fin__pb_358ecead701f's third sort-code field named sort_code, the first one's name)
import { describe, expect, it } from 'vitest';
import { nameClash, type AddData, type Proposal } from './store';

const P = (name: string): Proposal =>
  ({ kind: 'text', page: 1, rect: [0, 0, 10, 10], geometry: 'finder', options: [], name, name_options: [], evidence: [] });
const BP = { fields: [{ name: 'sort_code', page: 1, rect: [0, 0, 10, 10] }], field_specs: { sort_code: {}, no_box: {} } } as unknown as AddData;

describe('nameClash', () => {
  it("a blueprint field's name is taken", () => {
    expect(nameClash('sort_code', 0, { BP, added: [], props: [P('sort_code')], removed: [] })).toBe('blueprint');
    expect(nameClash('no_box', 0, { BP, added: [], props: [P('no_box')], removed: [] })).toBe('blueprint');
  });
  it('a field recorded for removal frees its name', () => {
    const removed = [{ name: 'sort_code', page: 1, rect: [0, 0, 10, 10] as [number, number, number, number], when: '', from: 'add' }];
    expect(nameClash('sort_code', 0, { BP, added: [], props: [P('sort_code')], removed })).toBeNull();
  });
  it('another addition with the name is a clash; a new name is none', () => {
    expect(nameClash('x', 0, { BP, added: [], props: [P('x'), P('x')], removed: [] })).toBe('pending');
    expect(nameClash('sort_code_3', 0, { BP, added: [], props: [P('sort_code_3')], removed: [] })).toBeNull();
  });
});
