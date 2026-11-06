// remove cards go on top of the pile as add cards do (Andrew, 2026-11-01: "can you also fix it so remove cards are
// added to the pile at the top (like how add cards are)")
import { describe, expect, it } from 'vitest';
import { pile, type Proposal } from './store';

const P = (k: number) => ({ _k: k, kind: 'text', name: `p${k}` }) as unknown as Proposal;
const order = (x: ReturnType<typeof pile>) => x.map(c => ('rm' in c ? c.rm : c.prop.name));

describe('pile', () => {
  it('newest first, remove cards among the add cards by when they came', () => {
    const keys: Record<string, number> = { a: 2, b: 5 };
    expect(order(pile([P(6), P(4), P(1)], ['b', 'a'], n => keys[n]))).toEqual(['p6', 'b', 'p4', 'a', 'p1']);
  });
  it('remove cards alone, the last collected on top', () => {
    const keys: Record<string, number> = { a: 1, b: 2 };
    expect(order(pile([], ['a', 'b'], n => keys[n]))).toEqual(['b', 'a']);
  });
});
