// What the server sends that more than one part of the page reads. Each tab's own data is typed in its folder.
import type { Rect } from './util';

export type ModeId = 'review' | 'groups' | 'add' | 'grids' | 'blocks' | 'audit';
export const MODE_IDS: ModeId[] = ['review', 'groups', 'add', 'grids', 'blocks', 'audit'];

export interface Draft { changes: number; log: string[]; made: string; real_changed?: boolean }
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

export interface PageInfo { page: number; w_pt: number; h_pt?: number }

/** `/api/overlay/<form>`: what every tab draws besides its own. */
export interface Overlay {
  fields: { name: string; accepted?: boolean; group?: boolean; rects: { page: number; rect: Rect }[] }[];
  grids: { id: string; page: number; bbox: Rect; validated?: boolean }[];
  blocks: { id: string; page: number; bbox: Rect; validated?: boolean; label?: string }[];
}

export type PageLabel = string | { text: string; done: boolean } | null;
