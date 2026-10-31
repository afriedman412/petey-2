// a group of one option is no group (Andrew, 2026-10-31: "the ability to group one field is confusing and not really
// useful"): a group left with one box is a loose box, as a text group left with one field is no text group
import { describe, expect, it } from 'vitest';
import { detach, isGroup, type Unit } from './store';

describe('detach', () => {
  it('a group left with one box is a loose checkbox under its name', () => {
    const us: Unit[] = [{ uid: 1, name: 'coverage', type: 'category', items: ['coverage::a', 'coverage::b'], origin: 'coverage' }];
    detach(us, 'coverage::b');
    expect(us).toHaveLength(1);
    expect(us[0]).toMatchObject({ name: 'coverage', type: 'boolean', items: ['coverage::a'] });
    expect(isGroup(us[0])).toBe(false);
  });
  it('a group of three keeps its kind with two left', () => {
    const us: Unit[] = [{ uid: 1, name: 'g', type: 'multi_category', items: ['g::a', 'g::b', 'g::c'], origin: 'g' }];
    detach(us, 'g::c');
    expect(us[0].type).toBe('multi_category');
  });
  it('a text group left with one field is gone', () => {
    const us: Unit[] = [{ uid: 1, kind: 'text', name: 'dob', type: 'string', items: ['m', 'd'] }];
    detach(us, 'd');
    expect(us).toHaveLength(0);
  });
});
