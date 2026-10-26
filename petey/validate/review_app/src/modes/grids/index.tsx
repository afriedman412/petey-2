// Grids on the page: each grid on this page in its own color, outlined in dots (solid once on pattern), its id tag
// (click copies the reference), its cells (green once accepted); click a grid to select it, drag one onto another to
// combine them, drag on an empty part of the page to draw one. And the tab's definition for the frame.
import { Box, Dots, useScale } from '../../components/Box';
import { dragProps, dropProps, copyText } from '../../lib/dnd';
import { grow } from '../../lib/util';
import { useApp } from '../../state/app';
import type { ModeDef } from '../types';
import { Bar, Panel } from './Panel';
import { colorOf, combine, create, done, focus, key, live, load, onPage, prov, ref, select, status, useGrids } from './store';

function Layer() {
  const page = useApp(s => s.page);
  const { GD, selected } = useGrids();
  const scale = useScale();
  if (!GD) return null;
  const out: React.ReactNode[] = [];
  for (const t of onPage(page)) {
    const r = grow(t.bbox, 6), c = colorOf(t);
    out.push(
      <Box key={'t' + t.id} className={'gtab' + (t.on_pattern ? ' ok' : '') + (selected === t.id ? ' sel' : '')} rect={r} color={c}
        title={`${t.id} · ${t.rows} × ${t.cols} · ${status(t)} · ${prov(t)}\ndrag onto another grid to combine them`}
        onClick={e => { e.stopPropagation(); select(t.id); }}
        {...dragProps('grid', t.id)}
        {...dropProps(['grid'], (_kind, src) => { if (src !== t.id) combine([src, t.id]); })}>
        <Dots w={(r[2] - r[0]) * scale} h={(r[3] - r[1]) * scale} />
        <span className="gtid" title="click to copy the reference" onClick={e => { e.stopPropagation(); copyText(ref(t.id)); }}>{t.id + (done(t) ? ' ✓' : '')}</span>
      </Box>);
    t.cells.forEach((x, i) => {
      if (x.rect) out.push(<Box key={`c${t.id}#${i}`} className={'gcell' + (x.accepted ? ' acc' : '')} rect={x.rect} color={c}
        title={x.name + (x.accepted ? ' · accepted' : '')} />);
    });
  }
  return <>{out}</>;
}

export const grids: ModeDef = {
  id: 'grids',
  name: 'Grids',
  own: ['grids'],
  help: {
    keys: [['n / p', 'next / previous grid'], ['Enter', 'check & validate the selected grid'], ['Delete', 'the selected grid is not a grid'], ['Esc', 'deselect']],
    tips: ['Drag on an empty part of the page, or Shift+drag anywhere, to draw a grid: the fields whose middle is inside become one.',
      'Drag a grid onto another on the same page to combine them; "not a grid" on the combined one gives them back.',
      'A selected grid lists its columns and rows. Click a column\'s wording, or a row\'s label or number, to edit it: Enter renames every cell of that column or row (as Claude\'s changes, nothing accepted). Each standardize or renumber button says how many renames it makes (hover for them); where there is nothing it can do, the reason is under it. A column whose cells split evenly between wordings has a picker: choose one, or type another.',
      'Check & validate: already on pattern, its cells are accepted; out of order, the renames are applied as Claude\'s and the cells accepted; unclear, Opus proposes in the chat and you tick.'],
  },
  load,
  pages: () => useGrids.getState().GD?.pages || [],
  startPage: () => live()[0]?.page || 1,
  // p7 (grids not validated / grids), Andrew 2026-10-22
  pageLabel(p) {
    const ts = onPage(p); if (!ts.length) return `p${p}`;
    const u = ts.filter(t => !done(t)).length;
    return { text: `p${p} (${u}/${ts.length})`, done: !u };
  },
  useData: () => useGrids(s => s.GD),
  Bar, Panel, Layer, key, focus,
  // the area dragged on the page, as Groups and Add draw it: on an empty part of the page, or anywhere with Shift
  drag: {
    start: e => e.button === 0 && ((e.target as HTMLElement | null)?.id === 'canvas' || e.shiftKey),
    end: rect => { if (rect) create(rect); },
  },
};
