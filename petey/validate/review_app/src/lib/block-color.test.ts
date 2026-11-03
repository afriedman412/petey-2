// a block type's colour (Andrew, 2026-10-28): one per type by its number, never the orange of a field not yet accepted
import { describe, expect, it } from 'vitest';
import { BLOCK_COLORS, blockColor } from './util';

describe('blockColor', () => {
  it('gives each of a form\'s types its own colour, in number order, on every page', () => {
    const types = ['BT1', 'BT10', 'BT2', 'BT6'];
    expect(new Set(types.map(t => blockColor(t, types))).size).toBe(4);
    expect(blockColor('BT10', types)).toBe(BLOCK_COLORS[3]);                // after BT6, not after BT1
    expect(blockColor('BT6', types, ['BT6'])).toBe(BLOCK_COLORS[2]);        // the page's types don't matter
  });
  it('with more types than colours, no page repeats one', () => {
    const form = Array.from({ length: 10 }, (_, i) => `BT${i + 1}`);         // bm__sd_7834164: BT1 to BT10
    const page = ['BT1', 'BT2', 'BT6', 'BT7', 'BT9', 'BT10'];               // its p5
    expect(new Set(page.map(t => blockColor(t, form, page))).size).toBe(6);
  });
  it('agrees however the types are listed', () => {
    expect(blockColor('BT6', ['BT6', 'BT2', 'BT2'])).toBe(blockColor('BT6', ['BT2', 'BT6']));
  });
  it('never uses the colours that already mean something on the page', () => {
    for (const c of ['#d8572a', '#1e8e3e', '#c5221f', '#8a8a8a']) expect(BLOCK_COLORS).not.toContain(c);
  });
  it('gives a type it was not told about a colour from the palette', () => {
    expect(BLOCK_COLORS).toContain(blockColor('custom', ['BT1']));
  });
});
