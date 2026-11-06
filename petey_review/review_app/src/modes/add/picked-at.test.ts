// a click on a box already picked in Add / remove drops it (Andrew, 2026-10-28)
import { describe, expect, it } from 'vitest';
import { pickedAt, type Proposal } from './store';

const text = { kind: 'text', page: 2, rect: [10, 10, 100, 20] } as unknown as Proposal;
const group = { kind: 'group', options: [{ page: 2, rect: [10, 40, 20, 50] }, { page: 2, rect: [30, 40, 40, 50] }] } as unknown as Proposal;

describe('pickedAt', () => {
  it('finds the card and the box of a group under the click', () => {
    expect(pickedAt([text, group], 2, [50, 15])).toEqual({ i: 0, o: 0 });
    expect(pickedAt([text, group], 2, [35, 45])).toEqual({ i: 1, o: 1 });
  });
  it('is nothing off the boxes or on another page', () => {
    expect(pickedAt([text, group], 2, [25, 45])).toBeNull();
    expect(pickedAt([text, group], 3, [50, 15])).toBeNull();
  });
});
