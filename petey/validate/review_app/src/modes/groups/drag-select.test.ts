// a drag over boxes on Groups selects them, and the group selected before is no longer lit (Andrew, 2026-10-31:
// "when you select a group of fields when one field is highlighted, that field stays highlighted")
import { describe, expect, it, vi } from 'vitest';
vi.mock('../../state/actions', () => ({ toast: () => {}, loadMode: async () => {}, syncSha: async () => {}, updateEntry: () => {} }));
import { selectArea, useGroups } from './store';

describe('selectArea', () => {
  it('takes the boxes in the area and drops the old selection', () => {
    useGroups.setState({ BP: { items: { a: { id: 'a', page: 1, rect: [10, 10, 18, 18] }, b: { id: 'b', page: 1, rect: [50, 10, 58, 18] } } } as never,
      units: [], selected: 7, picked: new Set(), showText: false });
    selectArea([0, 0, 30, 30], false);
    expect([...useGroups.getState().picked]).toEqual(['a']);
    expect(useGroups.getState().selected).toBeNull();
  });
});
