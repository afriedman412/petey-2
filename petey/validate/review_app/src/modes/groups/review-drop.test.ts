// Review's page hands a dragged checkbox or group to Groups by its field and option (2026-10-27)
import { describe, expect, it } from 'vitest';
import { itemOf, type Item } from './store';

const it_ = (id: string, field: string, key: string | null, kind?: 'text'): Item => ({ id, field, key, kind, page: 1, rect: [0, 0, 1, 1] });
const items = Object.fromEntries([
  it_('status::quote_ind', 'status', 'quote_ind'), it_('status::renew_ind', 'status', 'renew_ind'),
  it_('agree_ind', 'agree_ind', null), it_('name', 'name', null, 'text'),
].map(x => [x.id, x]));

describe('itemOf', () => {
  it("finds a group's box by its on-state, and the group by any of its boxes", () => {
    expect(itemOf({ field: 'status', opt: 'renew_ind' }, items)?.id).toBe('status::renew_ind');
    expect(itemOf({ field: 'status', opt: null }, items)?.field).toBe('status');
  });
  it('finds a checkbox by its field', () => {
    expect(itemOf({ field: 'agree_ind', opt: null }, items)?.id).toBe('agree_ind');
  });
  it('finds no text field and no option that is not there', () => {
    expect(itemOf({ field: 'name', opt: null }, items)).toBeUndefined();
    expect(itemOf({ field: 'status', opt: 'cancel_ind' }, items)).toBeUndefined();
  });
});
