// the card's type (Andrew, 2026-11-03: "let's have type be 'text, choice, printed'"; "field type determines semantic
// type. a choice shouldn't be able to be a string or a number")
import { describe, expect, it } from 'vitest';
import { fieldTypeOf, semanticTypes, type RField } from './store';

const f = (x: Partial<RField>) => ({ name: 'x', page: 1, rects: [], options: [], idx: 0, ...x }) as RField;

describe('field type', () => {
  it('reads text, printed and choice from the printed flag (null on a choice)', () => {
    expect(fieldTypeOf(f({ printed: false }))).toBe('text');
    expect(fieldTypeOf(f({ printed: true }))).toBe('printed');
    expect(fieldTypeOf(f({ printed: null }))).toBe('choice');
  });
  it('offers the semantic types of its field type', () => {
    expect(semanticTypes(f({ printed: false }))).toEqual(['string', 'number', 'integer', 'date']);
    expect(semanticTypes(f({ printed: true }))).toEqual(['string', 'number', 'integer', 'date']);
    expect(semanticTypes(f({ printed: null, options: [{ on_state: 'Yes' }] }))).toEqual(['boolean', 'category', 'multi_category']);
    expect(semanticTypes(f({ printed: null, options: [{ on_state: 'A' }, { on_state: 'B' }] }))).toEqual(['category', 'multi_category']);
  });
});
