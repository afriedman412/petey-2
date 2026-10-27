// Review on the page: each field's boxes in its verdict's color, option groups in a dashed hull (as in Groups),
// clashing names outlined while the clashes button is on; and the tab's definition for the frame.
import { Box, GroupTab } from '../../components/Box';
import { dragProps, dropProps } from '../../lib/dnd';
import { GROUP_COLORS, hull } from '../../lib/util';
import { useApp } from '../../state/app';
import type { ModeDef } from '../types';
import { combineFromReview } from '../groups/store';
import { Bar, Panel } from './Panel';
import { clashGroups, focus, isRemoved, key, load, select, useReview, verdictOf, type RField } from './store';

// checkboxes and groups combine by dragging, as in Groups (Andrew, 2026-10-27: "can we add dragging bools to combine to
// the review page? and add dragging groups to combine to both?"): a checkbox onto a checkbox makes a group, onto a
// group joins it, a group (by the tab on its corner) onto a group merges them; the change goes into the working copy
const isBool = (f: RField) => !f.options.length && f.type === 'boolean';
const isOption = (f: RField) => f.options.length > 0 || isBool(f);
const dropOnto = (f: RField, opt: string | null) => dropProps(['rvbox', 'rvgroup'], (kind, from) => {
  if (from === f.name) return;
  combineFromReview({ field: from, opt: null }, kind === 'rvgroup', { field: f.name, opt })
    .then(name => { if (name) select(name, false); });
});

function Layer() {
  const page = useApp(s => s.page), showGroups = useApp(s => s.show.groups);
  const { BP, selected, selOpt, clashOn, removed } = useReview();
  if (!BP) return null;
  const cl = clashOn ? clashGroups(BP, removed) : {};
  const out: React.ReactNode[] = [];
  // option groups drawn as in Groups (2026-10-13, Andrew): a dashed hull in the group's color around its boxes on this
  // page, solid when the field is selected; the boxes keep their verdict colors
  let gi = 0;
  for (const f of BP.fields) {
    if (f.options.length < 2 || !showGroups) continue;
    const c = GROUP_COLORS[gi++ % GROUP_COLORS.length], rs = f.rects.filter(r => r.page === page).map(r => r.rect);
    if (!rs.length) continue;
    const h = hull(rs, 4);
    out.push(<Box key={'h' + f.name} className={'gh rvg' + (selected === f.name ? ' sel' : '')} rect={h} color={c}
      title={`${f.id ? f.id + ' · ' : ''}${f.name} (${f.options.length} options)`} onClick={() => select(f.name, false)}
      {...dragProps('rvgroup', f.name)} {...dropOnto(f, f.options[0].on_state)} />);
    out.push(<GroupTab key={'t' + f.name} at={[h[0], h[1]]} color={c} title={`drag ${f.name} onto another group or a checkbox to combine them`}
      {...dragProps('rvgroup', f.name)} {...dropOnto(f, f.options[0].on_state)} />);
  }
  for (const f of BP.fields) f.rects.forEach((r, i) => {
    if (r.page !== page) return;
    const opt = f.options.length && f.options[i] ? f.options[i].on_state : null;
    const sel = selected === f.name, c = cl[f.name];
    const cls = 'rv ' + verdictOf(f.name) + (f.tier === 'contested' ? ' contested' : '') + (isRemoved(f.name) ? ' removed' : '')
      + (sel ? ' sel pulse' : '') + (sel && opt && opt === selOpt ? ' optsel' : '') + (c ? ' clash' : '');
    const title = `${f.id ? f.id + ' · ' : ''}${f.name}${f.options.length && f.options[i] ? ' · ' + (f.options[i].caption || f.options[i].on_state) : ''}${c ? ` · clashes on ${c.to}` : ''}`;
    // a box of a group: its key / caption row lights up
    out.push(<Box key={`${f.name}#${i}`} className={cls} rect={r.rect} title={title} vars={c ? { '--cc': c.color } : undefined}
      data-f={f.name} data-o={opt || ''} onClick={() => select(f.name, false, opt)}
      {...(isOption(f) ? { ...dragProps('rvbox', f.name, isBool(f)), ...dropOnto(f, opt) } : {})} />);
  });
  return <>{out}</>;
}

export const review: ModeDef = {
  id: 'review',
  name: 'Review',
  own: ['valid', 'groups'],
  help: {
    keys: [['a', 'accept, then the next field'], ['f', 'flag, then the next field'], ['c', 'clear the verdict'],
      ['d', 'remove the field / keep it'], ['e', 'edit the field name'], ['n / →', 'next field'], ['p / ←', 'back to the field you were on before'],
      ['u', 'unreviewed only on / off']],
    tips: ['Edit the field\'s name, type, semantic type, pattern or option captions in place: Enter, "save correction" or accept saves the changes; Esc undoes them. Empty a semantic type or pattern box to clear it.',
      'Saving a correction accepts the field and puts it into the working copy; "save" in the header writes the working copy into the blueprint.',
      'Flag a field you cannot or do not want to fix yourself, with a note saying what is wrong: "review edits" sends flags with notes to the agent.',
      'The note saves when you leave the box or press Enter; Shift+Enter for a new line.',
      'Drag a checkbox onto another to make a group, or onto a group to add it; drag a group by the tab on its corner onto another group to merge them. The change goes into the working copy.'],
  },
  load,
  pages: () => useReview.getState().BP?.pages || [],
  startPage: () => useReview.getState().BP?.fields[0]?.page || 1,
  // p7 (fields not accepted / fields): a field counts on every page it has a box on (CMS-855A pp. 8-9, 2026-10-14)
  pageLabel(p) {
    const BP = useReview.getState().BP; if (!BP) return null;
    const fs = BP.fields.filter(f => f.rects.some(r => r.page === p)); if (!fs.length) return null;
    const u = fs.filter(f => verdictOf(f.name) !== 'accept').length;
    return { text: `p${p} (${u}/${fs.length})`, done: !u };
  },
  useData: () => useReview(s => s.BP),
  Bar, Panel, Layer, key, focus,
};
