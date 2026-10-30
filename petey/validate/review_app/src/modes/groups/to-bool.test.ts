// a text field in an option unit is being made a checkbox; one loose or in an entity is still text
// (Andrew, 2026-10-27: "convert fields from text to bool/ind in groups")
import { describe, expect, it } from 'vitest';
import { textIn, type Item, type Unit } from './store';

const it_ = (id: string, kind?: 'text'): Item => ({ id, field: id, key: null, kind, page: 1, rect: [0, 0, 1, 1] });
const items = Object.fromEntries([it_('day_txt', 'text'), it_('evening', 'text'), it_('notes_txt', 'text'), it_('other_ind')].map(x => [x.id, x]));
const units: Unit[] = [
  { uid: 1, name: 'day_ind', type: 'boolean', items: ['day_txt'], origin: 'day_txt' },
  { uid: 2, kind: 'text', name: 'evening_notes_txt', type: 'string', items: ['evening', 'notes_txt'] },
  { uid: 3, name: 'other_ind', type: 'boolean', items: ['other_ind'], origin: 'other_ind' },
];

describe('textIn', () => {
  it('a text field in an option unit is no longer text', () => expect(textIn('day_txt', units, items)).toBe(false));
  it('a text field loose or in an entity is text', () => {
    expect(textIn('day_txt', [], items)).toBe(true);
    expect(textIn('evening', units, items)).toBe(true);
  });
  it('a checkbox is never text', () => expect(textIn('other_ind', units, items)).toBe(false));
});
