// the home list's status (Andrew, 2026-10-31): "accept structure" makes a form STRUCTURE VALIDATED, superseded by
// VALIDATED once every name is accepted; a structure stamp on a changed file is "changed since check"
import { describe, expect, it } from 'vitest';
import type { Entry } from '../lib/types';
import { statusOf } from './home-data';

const e = (x: Partial<Entry>) => ({ id: 'bm__x', source: 'bm', form: 'x', fields: 3, accepted: 0, flagged: 0, ...x }) as Entry;

describe('statusOf', () => {
  it('structure validated, then validated', () => {
    expect(statusOf(e({ structure: { when: 'now', stale: false } })).k).toBe('structure');
    expect(statusOf(e({ structure: { stale: false }, checked: { validated: true } })).k).toBe('validated');
  });
  it('a stale structure stamp is changed since check', () => {
    expect(statusOf(e({ structure: { stale: true } })).k).toBe('recheck');
  });
});
