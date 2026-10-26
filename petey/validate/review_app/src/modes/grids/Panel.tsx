// Grids' sidebar: a card per grid on the page (the selected one with its buttons, the last check's steps and its
// columns and rows, each with what its standardize or renumber button would do), the grids set aside as "not grids";
// and its bar (the counts).
import { useEffect, useRef, type MouseEvent as RMouseEvent, type ReactNode } from 'react';
import { copyText } from '../../lib/dnd';
import { useApp } from '../../state/app';
import {
  applyEdit, asidePage, cancelEdit, colorOf, done, live, onPage, prov, ref, renameList, run, runAll, say, sayFor,
  select, setAside, standardize, startEdit, status, stop, typeEdit, useGrids,
  type Line, type Plan, type Position, type Preview, type Table,
} from './store';

const s = (n: number, one: string, many = one + 's') => (n === 1 ? one : many);

/** The input a column's wording or a row's label turns into when clicked: Enter applies, Esc or leaving it cancels. */
function EditInput() {
  const e = useGrids(st => st.editing)!;
  const inp = useRef<HTMLInputElement>(null);
  useEffect(() => { inp.current?.focus(); inp.current?.select(); }, []);
  return (
    <input ref={inp} className="gedit-in" value={e.typed} size={Math.max(8, e.val.length + 2)} spellCheck={false}
      onChange={ev => typeEdit(ev.target.value)}
      onKeyDown={ev => { ev.stopPropagation(); if (ev.key === 'Enter') applyEdit(); else if (ev.key === 'Escape') cancelEdit(); }}
      onBlur={cancelEdit} onClick={ev => ev.stopPropagation()} />
  );
}

/** A column's wording or a row's label or number, click to edit it in place. */
function Editable({ tid, kind, at, val, title }: { tid: string; kind: 'pos' | 'line'; at: number; val: string; title: string }) {
  const e = useGrids(st => st.editing);
  if (e && e.tid === tid && e.kind === kind && e.at === at && e.val === val) return <EditInput />;
  return <code className="gedit" title={title} onClick={ev => { ev.stopPropagation(); startEdit(tid, kind, at, val); }}>{val}</code>;
}

// what a button would do, or why there is nothing for it to do
function PlanView({ tid, plan, what, onDo, picker }: { tid: string; plan?: Plan | null; what: string; onDo: () => void; picker?: ReactNode }) {
  const b = useGrids(st => !!st.busy[tid]);
  if (!plan) return picker ? <div className="gax-act">{picker}</div> : null;
  const n = plan.renames.length;
  return (
    <div className="gax-act">
      {n > 0 && <button className="btn mini" disabled={b} title={renameList(plan.renames)} onClick={onDo}>{what}: {n} {s(n, 'rename')}</button>}
      {picker}
      {plan.pulled.length > 0 && <span className="help" title={plan.pulled.join('\n')}>includes {plan.pulled.length} {s(plan.pulled.length, 'cell')} of other {what === 'renumber' ? 'rows' : 'columns'} that held the names</span>}
      {plan.left.map((l, i) => <div key={i} className="stale">{sayFor(tid, l)}</div>)}
      {!n && !plan.left.length && <span className="help">nothing to change</span>}
    </div>
  );
}

// a column whose cells split evenly between wordings: pick one, or type another
function Picker({ t, x, word, axis }: { t: Table; x: Position; word: string; axis: 'col' | 'row' }) {
  const onPick = (w0: string) => {
    let w = w0; if (!w) return;
    if (w === '?') { w = (prompt('The wording for every cell, with _# where the number goes (e.g. vehicle_#_make_txt):') || '').trim(); if (!w) return; }
    standardize(t.id, x.pos, null, w);
  };
  return (
    <select value="" title={`every cell of ${word} ${x.pos} under the wording you pick, each numbered as its ${axis === 'col' ? 'row' : 'column'}`}
      onChange={e => onPick(e.target.value)} onClick={e => e.stopPropagation()}>
      <option value="">or pick the wording…</option>
      {x.wordings.map(([w, n]) => <option key={w} value={w}>{w} ({n})</option>)}
      <option value="?">type another…</option>
    </select>
  );
}

function PosItem({ t, pv, x, word, axis }: { t: Table; pv: Preview; x: Position; word: string; axis: 'col' | 'row' }) {
  const b = useGrids(st => !!st.busy[t.id]);
  const ok = !x.plan && x.wordings.length < 2;
  const code = (w: string) => pv.keyed ? <code>{w}</code>
    : <Editable tid={t.id} kind="pos" at={x.pos} val={w}
      title={`click to edit: every cell of this ${word} under the wording you type, _# where the number goes; Enter applies, Esc cancels`} />;
  return (
    <div className={`gax-i ${ok ? 'ok' : 'off'}`}><b>{word} {x.pos}</b>{' '}
      {x.wordings.map(([w, n], i) => <span key={i}>{i ? ' · ' : ''}{code(w)}{x.wordings.length > 1 && <span className="help"> x{n}</span>}</span>)}
      {x.caption && <span className="help"> · printed "{x.caption}"</span>}{x.locked && <span className="help"> · printed line numbers, kept</span>}
      {!!x.off && <span className="stale"> · {x.off} {s(x.off, 'cell')} numbered off their {axis === 'col' ? 'rows' : 'columns'}</span>}{ok && <> <span className="good">✓</span></>}
      <PlanView tid={t.id} plan={x.plan} what="standardize" onDo={() => standardize(t.id, x.pos)}
        picker={x.wordings.length > 1 && !pv.keyed ? <Picker t={t} x={x} word={word} axis={axis} /> : undefined} />
      {x.alt && <div className="gax-act"><button className="btn mini" disabled={b} onClick={() => standardize(t.id, x.pos, null, x.alt!.wording)}
        title={`its names belong to another set on the page; under the grid's row subject instead:\n${renameList(x.alt.plan.renames)}`}>
        standardize as {x.alt.wording}: {x.alt.plan.renames.length} {s(x.alt.plan.renames.length, 'rename')}</button></div>}
    </div>
  );
}

function LineItem({ t, x, word }: { t: Table; x: Line; word: string }) {
  const off = x.plan && (x.plan.renames.length || x.plan.left.length);
  const ed = (v: string | number | null | undefined) => v
    ? <Editable tid={t.id} kind="line" at={x.line} val={String(v)}
      title={`click to edit: the ${word}'s ${x.label != null ? 'label' : 'number'} in each of its cells' names; Enter applies, Esc cancels`} />
    : <code>?</code>;
  const lab = x.label != null ? ed(x.label) : <>
    number {ed(x.number)}{(x.numbers || []).length > 1 && <> <span className="stale">also {x.numbers!.slice(1).join(', ')}</span></>}
    {x.plan && x.plan.renames.length > 0 && x.expect != null && x.number != null && String(x.expect) !== String(x.number) && <> <span className="stale">(should be {x.expect})</span></>}
    {x.note && <> <span className="help">· {x.note}</span></>}
  </>;
  return (
    <div className={`gax-i ${off ? 'off' : 'ok'}`}><b>{word} {x.line}</b> {lab} <span className="help">· {x.cells} cells</span>{off ? '' : <> <span className="good">✓</span></>}
      <PlanView tid={t.id} plan={x.plan} what="renumber" onDo={() => standardize(t.id, null, x.line)} />
    </div>
  );
}

// the grid's positions (its columns, or rows when it reads by rows) and its lines, as the page lays them out
function Axis({ t, pv, axis }: { t: Table; pv: Preview; axis: 'col' | 'row' }) {
  const isPos = pv.pos_axis === axis, word = axis === 'col' ? 'column' : 'row';
  const items = isPos ? pv.positions : pv.lines;
  const sub = isPos ? `each ${word} one wording` : pv.keyed ? `each ${word} named by its label` : `each ${word} one number: ${pv.summary || ''}`;
  return (
    <div className="gax" onClick={e => e.stopPropagation()}><h4>{axis === 'col' ? 'Columns' : 'Rows'} ({items.length}) <span className="help">· {sub}</span></h4>
      {isPos ? pv.positions.map(x => <PosItem key={x.pos} t={t} pv={pv} x={x} word={word} axis={axis} />)
        : pv.lines.map(x => <LineItem key={x.line} t={t} x={x} word={word} />)}
      {!isPos && (pv.aside || []).map((a, i) => <div key={'a' + i} className="gax-i help">{word} {a.row}: {a.why}, left out of the check</div>)}
    </div>
  );
}

function Card({ t }: { t: Table }) {
  const { selected, results, busy, runs, PV } = useGrids();
  const sel = selected === t.id, res = results[t.id], b = !!busy[t.id], pv = sel ? PV[t.id] : null;
  const stopHere = (e: RMouseEvent) => e.stopPropagation();
  const body = t.body ?? t.cells.length;
  const head = <>
    <div className="gttitle"><span className="gtidc" data-copy={t.id} title="click to copy the reference"
      onClick={e => { e.preventDefault(); e.stopPropagation(); copyText(ref(t.id)); }}>{t.id}</span>{t.title || 'grid'}
      {done(t) && <> <span className="pill validated" style={{ float: 'right' }}>validated</span></>}</div>
    <div className="help">{t.rows} {s(t.rows, 'row')} × {t.cols} {s(t.cols, 'column')} · {t.accepted} of {body} cells accepted · <span className={t.on_pattern || done(t) ? '' : 'stale'}>{status(t)}</span></div>
  </>;
  if (!sel) return <div className="gtcard" data-t={t.id} style={{ '--c': colorOf(t) } as React.CSSProperties} onClick={() => select(t.id)}>{head}</div>;
  const all = pv && pv.all && pv.all.renames.length;
  return (
    <div className="gtcard sel" data-t={t.id} style={{ '--c': colorOf(t) } as React.CSSProperties}>{head}
      <div className="gtprov">{prov(t)}</div>
      <div className="row gtbtns">
        <button className={'btn' + (done(t) ? '' : ' primary')} disabled={b} onClick={e => { stopHere(e); run(t.id); }}
          title="the code check, then the resolver, Jev and Opus only when still unclear; renames applied as Claude's, cells accepted">{b ? 'working…' : done(t) ? 'validated ✓ · check again' : 'check & validate'}</button>
        {b && !!runs[t.id] && <button className="btn" onClick={e => { stopHere(e); stop(t.id); }} title="stop this check: nothing is written after it, and a call to Opus under way is given up">cancel</button>}
        {!!all && <button className="btn" disabled={b} title={renameList(pv!.all!.renames)} onClick={e => { stopHere(e); standardize(t.id); }}>standardize all ({pv!.all!.renames.length})</button>}
        <button className="btn" onClick={e => { stopHere(e); setAside(t.id, true); }}
          title="hidden and kept out of 'check all'; a finder's grid is recorded as its mistake, a combined one gives its parts back; restore below">not a grid</button>
      </div>
      {res && <div className="gtres"><b>last: {res.status}</b>{res.status === 'proposed' ? ' · the proposals are in the chat' : ''}
        <ul className="gtsteps">{(res.steps || []).map((st, i) => <li key={i} className={st.startsWith('not accepted') ? 'stale' : undefined}>{say(t, st)}</li>)}</ul></div>}
      {!pv ? <p className="help">reading its columns and rows…</p> : pv.error ? <p className="err">{pv.error}</p> : <>
        {pv.keyed && <p className="help">Rows named by label (applicant, spouse): standardize does not apply; check & validate settles them.</p>}
        <Axis t={t} pv={pv} axis="col" />
        <Axis t={t} pv={pv} axis="row" />
      </>}
    </div>
  );
}

export function Panel() {
  const page = useApp(st => st.page);
  const { GD } = useGrids();
  if (!GD) return <p className="help">loading…</p>;
  const ts = onPage(page), aside = asidePage(page), nLive = live().length;
  return (
    <>
      <div className="help">Drag on an empty part of the page (or Shift+drag anywhere) to draw a grid around its fields; drag a grid onto another to combine them. Click a grid for its columns and rows.</div>
      {ts.length ? <>
        <div className="row"><button className="btn" id="gtAll" onClick={runAll}>check & validate all {ts.length} on this page</button></div>
        {ts.map(t => <Card key={t.id} t={t} />)}
      </> : <p className="help">No grid on this page{nLive ? ` (${nLive} on other pages)` : ''}.</p>}
      {aside.length > 0 && <div className="help" style={{ marginTop: 10 }}>Not grids: {aside.map((t, i) => (
        <span key={t.id}>{i ? ' · ' : ''}<span><b>{t.id}</b> {t.title || ''} ({t.rows} × {t.cols}, {t.aside_why || prov(t)}){' '}
          <a href="#" title={t.aside_why ? 'a grid after all: kept, whatever the rule says' : 'a grid after all'}
            onClick={e => { e.preventDefault(); setAside(t.id, false); }}>restore</a></span></span>))}</div>}
    </>
  );
}

export function Bar() {
  const { GD } = useGrids();
  if (!GD) return <span className="progress" id="progress" />;
  const ts = live(), v = ts.filter(done).length, ok = ts.filter(t => t.on_pattern).length, n = GD.tables.length - ts.length;
  return <span className="progress" id="progress"><b>{ts.length}</b> grids · {v} validated · {ok} on pattern{n ? ` · ${n} not grids` : ''}</span>;
}
