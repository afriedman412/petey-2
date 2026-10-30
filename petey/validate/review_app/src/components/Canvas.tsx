// The page image with what is drawn on it: the other tabs' work ("show"), the tab's own boxes, and an area being
// dragged. A drag is the frame's: the tab says whether a mousedown starts one and gets the area when it ends.
import { useEffect, useRef, useState } from 'react';
import { pngUrl } from '../lib/api';
import { blockColor, GROUP_COLORS, grow, hull, restoreScroll, type Rect } from '../lib/util';
import { useApp } from '../state/app';
import { MODES } from '../modes';
import { Box, ScaleContext } from './Box';

function ShowLayer() {
  const { overlay: o, show, page, mode } = useApp();
  if (!o) return null;
  const own = MODES[mode].own;
  const on = (k: keyof typeof show) => show[k] && !own.includes(k);
  const out: React.ReactNode[] = [];
  if (on('valid')) o.fields.forEach((f, i) => f.accepted && f.rects.forEach((r, k) => r.page === page && out.push(<Box key={`v${i}-${k}`} className="ovl valid" rect={r.rect} />)));
  if (on('groups')) {
    let gi = 0;
    o.fields.forEach((f, i) => {
      if (!f.group) return;
      const c = GROUP_COLORS[gi++ % GROUP_COLORS.length], rs = f.rects.filter(r => r.page === page).map(r => r.rect);
      if (rs.length) out.push(<Box key={`g${i}`} className="ovl group" rect={grow(hull(rs), 3)} color={c} />);
    });
    (o.entities || []).forEach((e, i) => {              // entities too, after the groups' colours (2026-10-28)
      const c = GROUP_COLORS[gi++ % GROUP_COLORS.length], rs = e.rects.filter(r => r.page === page).map(r => r.rect);
      if (rs.length) out.push(<Box key={`e${i}`} className="ovl group entity" rect={grow(hull(rs), 3)} color={c}
        title={`${e.name} (entity${e.entity_type ? ': ' + e.entity_type.replace(/_/g, ' ') : ''}, ${e.fields.length} fields)`} />);
    });
  }
  if (on('grids')) o.grids.forEach(g => g.page === page && out.push(
    <Box key={`t${g.id}`} className={'ovl grid' + (g.validated ? ' ok' : '')} rect={grow(g.bbox, 5)} color="#4fc3f7"><span>{g.id}{g.validated ? ' ✓' : ''}</span></Box>));
  const typeOf = (id: string) => id.replace(/-\d+$/, ''), types = o.blocks.map(b => typeOf(b.id));
  const onPage = o.blocks.filter(b => b.page === page).map(b => typeOf(b.id));
  if (on('blocks')) o.blocks.forEach(b => b.page === page && out.push(
    <Box key={`b${b.id}`} className={'ovl blk' + (b.validated ? ' ok' : '')} rect={grow(b.bbox, 3)} color={blockColor(typeOf(b.id), types, onPage)}><span>{b.id}{b.label ? ' ' + b.label : ''}{b.validated ? ' ✓' : ''}</span></Box>));
  return <>{out}</>;
}

// the stage (which scrolls) stays across tabs; what is in it is drawn anew for each tab: each tab's useData calls its
// own hooks, and React wants the same hooks on every draw
export function Canvas() {
  const mode = useApp(s => s.mode);
  return <div id="stage"><PageOf key={mode} /></div>;
}

function PageOf() {
  const { bid, page, zoom, mode, loaded } = useApp();
  const d = MODES[mode];
  d.useData();
  const ready = !!loaded && loaded.mode === mode && loaded.bid === bid;
  const canvas = useRef<HTMLDivElement>(null);
  const [area, setArea] = useState<Rect | null>(null);
  const drag = useRef<{ start: [number, number]; down: { target: EventTarget | null; shiftKey: boolean }; rect: Rect | null } | null>(null);

  const pt = (e: { clientX: number; clientY: number }): [number, number] => {
    const r = canvas.current!.getBoundingClientRect();
    return [(e.clientX - r.left) / zoom, (e.clientY - r.top) / zoom];
  };

  useEffect(() => {
    const move = (e: MouseEvent) => {
      const g = drag.current; if (!g) return;
      const q = pt(e), s = g.start;
      const r: Rect = [Math.min(s[0], q[0]), Math.min(s[1], q[1]), Math.max(s[0], q[0]), Math.max(s[1], q[1])];
      if (!g.rect && (r[2] - r[0]) * zoom < 4 && (r[3] - r[1]) * zoom < 4) return;
      g.rect = r; setArea(r);
    };
    const up = () => {
      const g = drag.current; if (!g) return;
      drag.current = null; setArea(null);
      MODES[mode].drag?.end(g.rect, g.start, g.down);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
  });

  const onMouseDown = (e: React.MouseEvent) => {
    if (!bid || !ready || !d.drag) return;
    const ne = e.nativeEvent;
    if (!d.drag.start(ne)) return;
    e.preventDefault();
    drag.current = { start: pt(e), down: { target: e.target, shiftKey: e.shiftKey }, rect: null };
  };

  const p = ready ? d.pages().find(x => x.page === page) : undefined;
  return (
    <div id="canvas" ref={canvas} className={d.drawable ? 'drawable' : ''} onMouseDown={onMouseDown}>
      {bid && p && <img id="img" alt="" src={pngUrl(bid, page)} style={{ width: p.w_pt * zoom }} draggable={false}
        onLoad={() => restoreScroll(page, true)} />}
      {bid && p && (
        <ScaleContext.Provider value={zoom}>
          <ShowLayer />
          <d.Layer />
          {area && <Box className="ov draw" rect={area} />}
        </ScaleContext.Provider>
      )}
    </div>
  );
}
