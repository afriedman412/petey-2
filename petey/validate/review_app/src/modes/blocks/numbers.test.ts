import { describe, expect, it } from 'vitest';
import { lowestNumbers, type Parts } from './numbers';

const P = (subject: string, iteration = '', suffix = '', part = ''): Parts => ({ subject, suffix, iteration, part });
const names = (ss: Parts[]) => ss.map(s => [s.subject, s.iteration].filter(Boolean).join('_'));

describe('lowestNumbers', () => {
  it('numbers a set 1, 2 in order, whatever numbers it had', () => {
    expect(names(lowestNumbers([P('subtotal', '5'), P('subtotal', '6')]))).toEqual(['subtotal_1', 'subtotal_2']);
    expect(names(lowestNumbers([P('year'), P('year_6', '4')]))).toEqual(['year_1', 'year_2']);   // regular_corp_year_6_4
  });
  it('folds a number left on a subject into the set of the subject it leaves', () => {
    expect(names(lowestNumbers([P('depreciation', '5'), P('depreciation_2', '2')]))).toEqual(['depreciation_1', 'depreciation_2']);
  });
  it('leaves a position alone in its set unnumbered, and a subject not another position\'s as it is', () => {
    expect(names(lowestNumbers([P('total_tax', '3'), P('line_1065')]))).toEqual(['total_tax', 'line_1065']);
  });
  it('keeps sets apart by suffix and part', () => {
    const out = lowestNumbers([P('birth', '', 'dt', 'month'), P('birth', '', 'dt', 'day'), P('birth', '4', 'dt', 'month')]);
    expect(out.map(s => s.iteration)).toEqual(['1', '', '2']);
  });
});
