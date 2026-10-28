// Groups on the page: each group's hull in its color and its boxes, loose boxes dashed, text fields in teal (combined
// ones in a hull); a click selects, Shift- / Cmd-click picks a box for "group selected", and boxes and hulls drag
// onto each other (a group by the tab on its corner, 2026-10-27: its boxes cover the rest of it). And the tab's
// definition for the frame (an area dragged across the page picks the boxes in it).
import { Box, GroupTab } from '../../components/Box';
import { dragProps, dropProps } from '../../lib/dnd';
import { hull } from '../../lib/util';
import { useApp } from '../../state/app';
import type { ModeDef } from '../types';
import { Bar, Panel } from './Panel';
import {
  colorOf, dropped, firstItem, focus, isGroup, isText, item, key, label, leave, load, looseText, note, onPage, optUnits,
  pickOnPage, select, selectArea, togglePick, useGroups, type Item, type Target, type Unit,
} from './store';

const dropOn = (target: Target) => dropProps(['item', 'unit'], (kind, v) => dropped(kind, v, target));

function ItemBox({ it, u, c, sel, picked }: { it: Item; u: Unit | null; c: string; sel: boolean; picked: boolean }) {
  const cls = 'gi' + (it.kind === 'text' ? ' text' : '') + (u ? '' : ' loose') + (u && !isGroup(u) ? ' orphan' : '') + (sel ? ' sel' : '')
    + (u && u.locked ? ' locked' : '') + (picked ? ' picked' : '');
  const title = u ? `${u.name}${isGroup(u) ? ' · ' + label(it.id) : ''}${u.locked ? ' (locked: ' + u.locked + ')' : ''}` : `${it.field} (text field)`;
  const live = !(u && u.locked);
  return (
    <Box className={cls} rect={it.rect} min={6} color={c} title={title} data-item={it.id}
      onClick={e => {
        e.stopPropagation();
        if (e.shiftKey || e.metaKey || e.ctrlKey) return togglePick(it.id);
        if (u) select(u.uid, false); else note(`${it.field}: a text field; drag it onto another text field to combine them`);
      }}
      {...dragProps('item', it.id, live)} {...(live ? dropOn({ item: it.id }) : {})} />
  );
}

function Layer() {
  const page = useApp(s => s.page);
  const { BP, units, selected, picked, showText } = useGroups();
  if (!BP) return null;
  const out: React.ReactNode[] = [];
  const place = (u: Unit) => {
    const c = colorOf(u, units, page), sel = u.uid === selected, its = u.items.map(item).filter(it => it.page === page), text = isText(u);
    if (isGroup(u)) {
      const h = hull(its.map(i => i.rect)), pad = text ? 3 : 6;
      out.push(<Box key={'h' + u.uid} data-unit={u.name} className={'gh' + (text ? ' text' : '') + (sel ? ' sel' : '') + (u.confirmed ? ' ok' : '')}
        rect={h} pad={pad} min={6} color={c}
        title={text ? `${u.name} (combined text, ${u.items.length} boxes)` : `${u.name} (${u.items.length} options)`}
        onClick={() => select(u.uid, false)}
        {...dragProps('unit', u.uid, !u.locked)} {...(u.locked ? {} : dropOn({ unit: u.uid }))} />);
      if (!u.locked && !text) out.push(<GroupTab key={'t' + u.uid} at={[h[0] - pad, h[1] - pad]} color={c}
        title={`drag ${u.name} onto another group or a box to combine them`} {...dragProps('unit', u.uid)} {...dropOn({ unit: u.uid })} />);
    }
    for (const it of its) out.push(<ItemBox key={'i' + it.id} it={it} u={u} c={c} sel={sel} picked={picked.has(it.id)} />);
  };
  for (const u of optUnits(units).filter(x => onPage(x, page))) place(u);
  if (showText) {
    for (const u of units.filter(x => isText(x) && onPage(x, page))) place(u);
    for (const it of looseText(page, units)) out.push(<ItemBox key={'i' + it.id} it={it} u={null} c="var(--txt)" sel={false} picked={picked.has(it.id)} />);
  }
  return <>{out}</>;
}

export const groups: ModeDef = {
  id: 'groups',
  name: 'Groups',
  own: ['groups'],
  help: {
    keys: [['g', 'group the selected boxes'], ['Esc', 'clear the selection'], ['a', 'confirm the group'], ['n / →', 'next group'], ['p / ←', 'previous group'], ['z', 'undo'],
      ['u', 'ungroup the selected group'], ['Shift+U', 'unconfirmed only on / off'], ['Shift+T', 'text fields on / off']],
    tips: ['Select boxes with Shift-click (or Cmd-click), or drag across an area of the page (Shift+drag adds an area); g or "group selected" makes them one group; Esc clears the selection.',
      'Drag a box onto a group, onto another loose box, or onto the tray.', 'Drag a group by the tab on its corner onto another group or a loose box to combine them.', 'Teal text boxes combine the same way.'],
  },
  load,
  pages: () => useGroups.getState().BP?.pages || [],
  startPage() {
    const { BP } = useGroups.getState(); if (!BP) return 1;
    const ou = optUnits();
    return ou.length ? firstItem(ou[0]).page : ((Object.values(BP.items)[0] || {}).page || 1);
  },
  // p7 (groups not confirmed / groups), Andrew 2026-10-22; a page of loose boxes only is just p7
  pageLabel(p) {
    const { BP, showText } = useGroups.getState(); if (!BP) return null;
    const ou = optUnits().filter(u => onPage(u, p)), gs = ou.filter(isGroup);
    if (gs.length) { const left = gs.filter(u => !u.confirmed).length; return { text: `p${p} (${left}/${gs.length})`, done: !left }; }
    if (ou.length) return `p${p}`;
    if (showText && Object.values(BP.items).some(it => it.kind === 'text' && it.page === p)) return `p${p}`;
    return null;
  },
  // the whole store: the page buttons count groups and text fields
  useData: () => useGroups(),
  Bar, Panel, Layer, key, focus, leave,
  onPage: pickOnPage,
  // an area dragged across the page (Shift, or from the page itself rather than a box) picks the option boxes in it
  drag: {
    start: e => e.button === 0 && (e.shiftKey || (e.target as HTMLElement | null)?.id === 'canvas'),
    end(rect, _at, down) { if (rect) selectArea(rect, down.shiftKey); },
  },
};
