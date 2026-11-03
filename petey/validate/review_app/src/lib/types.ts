// What the server sends that more than one part of the page reads. Each tab's own data is typed in its folder.
import type { Rect } from './util';

export type ModeId = 'review' | 'groups' | 'add' | 'grids' | 'blocks' | 'audit';
// the tabs shown, in order (Shift+1..5); Audit is left out until it is built (Andrew, 2026-10-31: "audit will come
// back later when we implement it"): its code stays, no button, no key, a saved or linked #audit opens Review
export const MODE_IDS: ModeId[] = ['review', 'groups', 'add', 'grids', 'blocks'];

export interface Draft { changes: number; log: string[]; made: string; real_changed?: boolean }
export interface Structure { when?: string; by?: string; stale?: boolean }
export interface Checked { validated?: boolean; flagged?: number; pending?: number; stale?: boolean; when?: string }

/** A row of `/api/blueprints`: one blueprint the page can open. */
export interface Entry {
  id: string;
  form: string;
  fields: number;
  accepted: number;
  flagged: number;
  draft?: Draft | null;
  checked?: Checked | null;
  // fields awaiting a verdict on a form once fully checked (a sweep or an edit added them; 2026-11-02)
  new_fields?: number | null;
  // "accept structure" (2026-10-31): fields, kinds, groups, grids and blocks right, names not looked at
  structure?: Structure | null;
  // the whole form set aside, with a reason (the header's "ignore", 2026-11-03; ignored_forms.py)
  ignored?: { reason: string; when: string } | null;
  age?: { when?: string; by?: string } | null;
  check_errors?: number | null;
  check_suggestions?: number | null;
  page_check_flags?: number | null;
  focus?: number | null;
  launch?: number | string | null;
  rerun?: boolean | null;
  source?: string;
  desc?: { text: string; from: string } | null;
  blank?: string | null;
  collection?: string | null;
  pages?: number | null;
  groups?: { groups: number } | null;
  passes?: { when?: string; steps?: string[] } | null;
  touched?: string | null;
  note?: { text: string; updated: string } | null;
}

export interface PageInfo { page: number; w_pt: number; h_pt?: number; /** fields with a box on the page (0: none, the button greyed) */ fields?: number }

/** `/api/overlay/<form>`: what every tab draws besides its own. */
export interface Overlay {
  fields: { name: string; accepted?: boolean; group?: boolean; kind?: 'text' | 'printed' | 'choice'; rects: { page: number; rect: Rect }[] }[];
  grids: { id: string; page: number; bbox: Rect; validated?: boolean }[];
  blocks: { id: string; page: number; bbox: Rect; validated?: boolean; label?: string }[];
  /** Groups' entities (tagged text fields), drawn wherever groups are */
  entities?: { name: string; entity_type?: string | null; page: number; fields: string[]; rects: { page: number; rect: Rect }[] }[];
}

export type PageLabel = string | { text: string; done: boolean } | null;
