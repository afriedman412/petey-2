// Add / remove on the page: the blueprint's fields (purple; red dashed when to be removed), the suggestions left
// (orange: solid an unclaimed widget, dashed a finder box), the fields added (green, with their name), and what is
// proposed; and the tab's definition for the frame.
import { Box } from '../../components/Box';
import { useApp } from '../../state/app';
import type { ModeDef } from '../types';
import { Bar, Panel } from './Panel';
import { boxesOf, dragEnd, isRemoved, key, load, remaining, useAdd } from './store';

function Layer() {
  const page = useApp(s => s.page);
  const { BP, picked, curSid, added, props, showFields, showSug } = useAdd();
  if (!BP) return null;
  const out: React.ReactNode[] = [];
  if (showFields) BP.fields.forEach((f, i) => f.page === page && out.push(
    <Box key={`f${i}`} className={'ov field' + (isRemoved(f.name) ? ' removed' : '') + (picked === f.name ? ' picked' : '')} rect={f.rect} title={f.name} data-field={f.name} />));
  if (showSug) for (const s of remaining()) if (s.page === page) out.push(
    <Box key={`s${s.sid}`} className={`ov sug ${s.source}${s.copy ? ' copy' : ''}${s.sid === curSid ? ' cur' : ''}`} rect={s.rect} title={s.what} data-sid={s.sid} />);
  added.forEach((a, i) => boxesOf(a).filter(b => b.page === page).forEach((b, k) => out.push(
    <Box key={`a${i}-${k}`} className="ov added" rect={b.rect} title={a.name} data-added={i}>{k === 0 && <span className="tag">{a.name}</span>}</Box>)));
  props.forEach((p, i) => boxesOf(p).forEach((b, k) => b.page === page && out.push(<Box key={`p${i}-${k}`} className="ov prop" rect={b.rect} />)));
  return <>{out}</>;
}

export const add: ModeDef = {
  id: 'add',
  name: 'Add / remove',
  own: [],
  drawable: true,
  help: {
    keys: [['n', 'next suggestion'], ['p', 'previous suggestion'], ['a / Enter', 'add what is proposed'], ['x', 'not a field'],
      ['d', 'remove the clicked field / keep it'], ['Esc', 'cancel all'], ['f', 'fields on / off'], ['s', 'suggestions on / off']],
    tips: ['Drag over an area of the page, or click a box, to propose a field; each one you pick stays until you add it or cancel it ("cancel" on its card, Esc for all).',
      'Click a purple field (one the blueprint has) to remove it.'],
  },
  load,
  pages: () => useAdd.getState().BP?.pages || [],
  startPage: () => remaining()[0]?.page || 1,
  pageLabel(p) { const n = remaining().filter(s => s.page === p).length; return `p${p}${n ? ` (${n})` : ''}`; },
  // the page buttons count the suggestions left, which follow the data, the lists and the copies setting
  useData() { useAdd(s => s.dismissed); useAdd(s => s.added); useAdd(s => s.copies); return useAdd(s => s.BP); },
  Bar, Panel, Layer, key,
  // a drag over an area proposes it; a click proposes what it is on (a suggestion), picks a blueprint field to remove,
  // notes an added one, or proposes a small box round the point
  drag: {
    start: e => e.button === 0,
    end: (rect, at, down) => dragEnd(rect, at, down.target),
  },
};
