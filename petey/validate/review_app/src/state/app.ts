// The page's own state: the blueprint list, the form open, its page, zoom, tab, the home list's filters and the
// view settings. Kept per browser where the old page kept them (the same localStorage keys, so both pages share them).
import { create } from 'zustand';
import type { Entry, ModeId, Overlay } from '../lib/types';
import { MODE_IDS } from '../lib/types';
import { store, storeJson } from '../lib/util';

export interface HomeState {
  on: boolean; sort: string; asc: boolean; q: string; section: string; domain: string | null; status: string; hideVal: boolean;
}
export type ShowKey = 'valid' | 'groups' | 'grids' | 'blocks';

export interface AppState {
  list: Entry[];
  listError: string | null;
  listOrder: string;
  bid: string | null;
  mode: ModeId;
  page: number;
  zoom: number;
  home: HomeState;
  show: Record<ShowKey, boolean>;
  wide: boolean;
  sideW: number;
  overlay: Overlay | null;
  /** the tab and form whose data is loaded (the sidebar and the page draw only once they match) */
  loaded: { mode: ModeId; bid: string } | null;
  loadError: string | null;
  helpOpen: boolean;
  notesOpen: boolean;
  chatOpen: boolean;
  /** the tabs drawn on the page hidden ("hide tabs" in the header, or t) */
  tabsHidden: boolean;
  toast: { msg: string; n: number } | null;
}

const savedMode = store('br_mode') as ModeId | null;

export const useApp = create<AppState>(() => ({
  list: [],
  listError: null,
  listOrder: store('br_listorder') || 'name',
  bid: null,
  mode: savedMode && MODE_IDS.includes(savedMode) ? savedMode : 'review',
  page: 1,
  zoom: parseFloat(store('br_zoom') || '') || 1.6,
  home: { ...storeJson('br_home', { sort: 'section', asc: true, q: '', section: '', domain: null as string | null, status: '', hideVal: false }), on: false },
  show: storeJson('br_show', { valid: true, groups: true, grids: true, blocks: true }),
  wide: store('br_wide') === '1',
  sideW: +(store('br_side_w') || 0) || 460,
  overlay: null,
  loaded: null,
  loadError: null,
  helpOpen: false,
  notesOpen: false,
  chatOpen: false,
  tabsHidden: store('br_hidetabs') === '1',
  toast: null,
}));

export const set = useApp.setState;
export const get = useApp.getState;

export const entryOf = (id: string | null) => (id ? get().list.find(b => b.id === id) : undefined);
export const useEntry = () => useApp(s => (s.bid ? s.list.find(b => b.id === s.bid) : undefined));

export function setHome(patch: Partial<HomeState>) {
  const home = { ...get().home, ...patch };
  set({ home });
  const { on: _on, ...keep } = home;
  store('br_home', JSON.stringify(keep));
}

// the tabs on the page (groups' grab tabs, grid ids, block labels, added fields' names) hidden when they cover printed
// text (Andrew, 2026-10-27: "sometimes the tabs ... cover important text"), by the header's button or t (2026-10-28:
// "can we set 't' to toggle tabs?"); remembered across reloads
export function setTabsHidden(on: boolean) {
  set({ tabsHidden: on });
  document.body.classList.toggle('notabs', on);
  store('br_hidetabs', on ? '1' : '0');
}
