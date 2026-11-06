// Blocks on the page: each block's outline with its tag (click copies the reference), its cells, and the fields in no
// block (dragged onto a block to add them); a block dragged onto another takes that one's type. And the tab's
// definition for the frame: an area dragged on the page is a block.
import { Box } from '../../components/Box';
import { copyText, dragProps, dropProps } from '../../lib/dnd';
import { blockColor } from '../../lib/util';
import { useApp } from '../../state/app';
import type { ModeDef } from '../types';
import { Bar, Panel } from './Panel';
import { allBlocks, blockAddField, blockDraw, blockDropped, focus, key, load, ref, selectBlock, useBlocks } from './store';

function Layer() {
  const page = useApp(s => s.page);
  const { GD, selBlock, hover } = useBlocks();
  if (!GD) return null;
  const out: React.ReactNode[] = [];
  // as the "show blocks" layer counts them: the form's types with blocks, and those with one on this page
  const types = (GD.types || []).filter(y => y.blocks.length).map(y => y.id);
  const onPage = (GD.types || []).filter(y => y.blocks.some(b => b.page === page)).map(y => y.id);
  for (const y of GD.types || []) {
    for (const b of y.blocks.filter(b => b.page === page)) {
      const tag = `${y.id}-${b.n}${y.label ? ' ' + y.label : ''}`;
      out.push(
        <Box key={'b' + b.code} className={'btb' + (b.code === selBlock ? ' sel' : '')} rect={b.bbox} pad={3} title={tag} color={blockColor(y.id, types, onPage)}
          onClick={e => { e.stopPropagation(); selectBlock(b); }}
          // dragged onto another block (Andrew, 2026-10-22, as in Groups): it becomes a block of that one's type;
          // a field dropped on it (Andrew, 2026-10-22: "can we drag fields on to a block to add them?")
          {...dragProps('block', b.code)}
          {...dropProps(['block', 'field'], (kind, id) => (kind === 'block' ? blockDropped(id, b, y) : blockAddField(b.code, id)))}>
          {/* as a field's name and a grid's id */}
          <span title="click to copy the reference" onClick={e => { e.stopPropagation(); copyText(ref(`${y.id}-${b.n}`)); }}>{tag}{b.validated ? ' ✓' : ''}</span>
        </Box>);
      // each field of the block, accepted or not, as the Grids tab shows a grid's cells
      (b.cells || []).forEach((x, i) => {
        if (x) out.push(<Box key={`c${b.code}#${i}`} className={'gcell' + (x.accepted ? ' acc' : '') + (hover === `${b.code}#${i}` ? ' hl' : '')} rect={x.rect}
          title={x.name + (x.accepted ? ' · accepted' : ' · not accepted yet')} vars={{ '--c': 'var(--accent)' }} />);
      });
    }
  }
  // the fields in no block, above the block outlines so one left out of a block can still be picked up
  for (const x of (GD.loose || []).filter(x => x.page === page)) {
    out.push(<Box key={'f' + x.code} className="bfield" rect={x.rect} title={`${x.name} (${x.kind}, in no block): drag onto a block to add it`}
      {...dragProps('field', x.code)} />);
  }
  return <>{out}</>;
}

export const blocks: ModeDef = {
  id: 'blocks',
  name: 'Blocks',
  own: ['blocks'],
  help: {
    keys: [['n / p', 'next / previous block'], ['Enter', 'check & validate the open block'], ['Delete', 'the open block is not a block'], ['Esc', 'close the open block']],
    tips: ['Drag on an empty part of the page, or Shift+drag anywhere, around one block: a block of the type it matches, else a new type.',
      'Drag a block onto another: it becomes a block of that one\'s type, its boxes paired by place and its names put to the type\'s parts.',
      'Click a name in the open block to edit its parts: they are its type\'s, so saving renames the field in every block of the type (asked first when there are others). Hover a name to light its field on the page.',
      '"reset numbers" in the open block numbers its type\'s names from 1 again: names with the same subject _1, _2, … in order, one alone none; then its blocks are renamed (asked first when the type has others).',
      'Fields in no block show as grey dashed boxes: drag one onto a block to add it, into the empty position of its kind nearest it (or a new position of the type, if it has none).'],
  },
  load,
  pages: () => useBlocks.getState().GD?.pages || [],
  startPage: () => allBlocks()[0]?.page || 1,
  // p7 (blocks not validated / blocks), Andrew 2026-10-22
  pageLabel(p) {
    const bs = allBlocks().filter(b => b.page === p); if (!bs.length) return `p${p}`;
    const u = bs.filter(b => !b.validated).length;
    return { text: `p${p} (${u}/${bs.length})`, done: !u };
  },
  useData: () => useBlocks(s => s.GD),
  Bar, Panel, Layer, key, focus,
  // the area dragged: on an empty part of the page, or Shift+drag anywhere
  drag: {
    start: e => e.button === 0 && ((e.target as HTMLElement | null)?.id === 'canvas' || e.shiftKey),
    end: rect => { if (rect) blockDraw(rect); },
  },
};
