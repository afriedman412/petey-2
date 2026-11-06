// What every tab gives the page: its data loader, its pages and their labels, its bar, sidebar and drawing on the
// page, its keys and its help. The old page's MODE.<tab> objects, as React components over a store per tab.
import type { FC } from 'react';
import type { ModeId, PageInfo, PageLabel } from '../lib/types';
import type { Rect } from '../lib/util';
import type { ShowKey } from '../state/app';

export interface Help { keys: [string, string][]; tips: string[] }

/** A drag on the page (an area drawn), handled by the frame: the tab says whether a mousedown starts one, and gets
 *  the area drawn (null for a click that drew nothing) with where the mouse went down. */
export interface AreaDrag {
  start(e: MouseEvent): boolean;
  end(rect: Rect | null, at: [number, number], down: { target: EventTarget | null; shiftKey: boolean }): void;
}

export interface ModeDef {
  id: ModeId;
  name: string;
  help: Help;
  /** the overlays this tab draws itself, left out of the "show" layer */
  own: ShowKey[];
  /** the cursor a crosshair over the page */
  drawable?: boolean;
  /** the page image hidden and the sidebar full width (Audit) */
  wide?: boolean;
  load(bid: string): Promise<void>;
  pages(): PageInfo[];
  startPage(): number;
  pageLabel(p: number): PageLabel;
  /** subscribes a component to the tab's data (the page buttons redraw with it) */
  useData(): unknown;
  Bar: FC;
  Panel: FC;
  Layer: FC;
  key?(e: KeyboardEvent): boolean;
  /** a link's field, grid, block or group (#<tab>/<form>/<key>) */
  focus?(key: string): void;
  /** leaving the tab (another tab or form, save, home) */
  leave?(): Promise<void>;
  /** a page picked by its button or key */
  onPage?(): void;
  drag?: AreaDrag;
}
