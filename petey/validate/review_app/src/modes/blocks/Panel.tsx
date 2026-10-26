// Blocks' sidebar: the open block's card, the block types with their matrix, the page's blocks; and its bar (the counts).
// Every box typed in keeps what is typed across a reload (component state, or the store for the matrix's parts) and
// shows the saved value again once the server's changes.
import { useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { copyText } from '../../lib/dnd';
import { toggleWide } from '../../state/actions';
import { useApp } from '../../state/app';
import {
  blockAssign, blockDetect, blockFix, blockIdent, blockKeep, blockOut, blockParts, blockState, blockValidate, blocksHere,
  editParts, printIdent, PKEYS, ref, selectBlock, setSlot, shownSlots, typeAssign, typeAuto, typeConfirm, typeFix,
  typeLabel, typeOff, typeSlots, typeValidate, useBlocks,
  type Block, type BType, type Slot,
} from './store';

/** A box's value: what is typed, until the saved value changes; then the saved one. */
function useSynced<T>(saved: T): [T, (v: T) => void] {
  const [v, setV] = useState(saved);
  const [base, setBase] = useState(saved);
  if (base !== saved) { setBase(saved); setV(saved); }
  return [v, setV];
}

const stop = (e: { stopPropagation(): void }) => e.stopPropagation();
const copyRef = (id: string) => (e: MouseEvent) => { e.preventDefault(); e.stopPropagation(); copyText(ref(id)); };
/** Enter leaves the box (its blur saves it) */
const enterBlurs = (e: React.KeyboardEvent<HTMLInputElement>) => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur(); };

const ITER_TITLE_PREFIX = 'told apart by its prefix: a number only when another block of the type has this prefix, or you type one';
const BY_TITLE = 'told apart by number (a block alone with its prefix is 1) or by its prefix (no number unless another block shares the prefix)';

// the other types, the closest one (if any) first
function TypeOptions({ not, first }: { not: string; first?: string | null }) {
  const types = useBlocks(s => s.GD)?.types || [];
  return <>{types.filter(x => x.id !== not).sort((a, b) => Number(b.id === first) - Number(a.id === first)).map(x => (
    <option key={x.id} value={x.id}>{x.id}{x.label ? ' ' + x.label : ''} ({x.boxes} boxes, {x.blocks.length} block{x.blocks.length === 1 ? '' : 's'}){x.id === first ? ' · closest' : ''}</option>))}</>;
}

// the clicked block, at the top of the sidebar (Andrew, 2026-10-22: "why can't I edit individual blocks anymore?"
// and "I'm clicking on BT1-2 and it brings up BT5": every unconfirmed type's matrix was open, the block's row
// somewhere below them): its prefix, iteration and how it is told apart; its names now and as its type prints them
function OpenBlock({ y, b }: { y: BType; b: Block }) {
  const { GD, bBusy, closestFor } = useBlocks();
  const ss = typeSlots(y);
  // the open block's own boxes: prefix, iteration and how it is told apart, saved on leaving a box or Enter
  const [pre, setPre] = useSynced(b.prefix || '');
  const [it, setIt] = useSynced(b.iteration || '');
  const [by, setBy] = useSynced(b.by !== 'prefix' ? 'number' : 'prefix');
  const save = (over?: { by?: string }) => {
    const p = pre.trim(), i = it.trim(), y2 = over?.by ?? by;
    if (p === (b.prefix || '') && i === (b.iteration || '') && y2 === (b.by || 'number')) return;
    // a new prefix with the iteration left as it was: the next number free among the blocks with that prefix
    // (Andrew, 2026-10-22: "updating the prefix doesn't automatically populate the iteration")
    const renumber = y2 !== (b.by || 'number') || (p !== (b.prefix || '') && i === (b.iteration || ''));
    blockParts(b.code, { prefix: p, iteration: renumber ? '' : i, by: y2 });
  };
  const nOff = (b.differs || []).filter(d => !d.held).length;
  const busy = !!bBusy[b.code];
  return (
    <div className="gcur btopen">
      <h2><b className="gtidc" data-copy={`${y.id}-${b.n}`} title="click to copy the reference" onClick={copyRef(`${y.id}-${b.n}`)}>{y.id}-{b.n}</b>{y.label ? ' ' + y.label : ''}{' '}
        <span className="help">p{b.page} · {b.n} of {y.blocks.length} · {blockState(y, b)}</span></h2>
      <div className="row btparts">prefix <input type="text" value={pre} title="the start of every name in this block"
        onChange={e => setPre(e.target.value)} onBlur={() => save()} />
        {' '}iteration <input type="text" className="btit" value={it} placeholder={b.by === 'prefix' ? 'none' : 'next'}
          title={b.by === 'prefix' ? ITER_TITLE_PREFIX : "this block's number among its type's blocks with this prefix; empty, the next number free; - for none"}
          onChange={e => setIt(e.target.value)} onBlur={() => save()} />
        {' '}<select value={by} title={BY_TITLE} onChange={e => { setBy(e.target.value); save({ by: e.target.value }); }}>
          <option value="number">by number</option><option value="prefix">by prefix</option></select>
        {b.parts_set && <> <a href="#" title="back to the prefix and iteration read from the names" onClick={e => { e.preventDefault(); e.stopPropagation(); blockParts(b.code, {}); }}>reset</a></>}</div>
      <table className="btnames"><tbody>{b.names.map((n, k) => {
        if (n == null) return <tr key={k}><td className="help">{k + 1}</td><td className="help" colSpan={2}>no box at {y.id}'s position {k + 1} ({(y.wordings || [])[k] || ''})</td></tr>;
        const want = printIdent(blockIdent(b.prefix, b.iteration, ss[k] || {})), kept = (b.kept || []).includes(k + 1);
        const d = (b.differs || []).find(x => x.pos === k + 1), acc = (b.cells || [])[k]?.accepted;
        const chg = want && want !== n && !kept && !(b.same_as || []).length;
        return (
          <tr key={k}><td className="help">{k + 1}</td><td><code className={acc ? 'accd' : ''}>{n}</code>{acc ? ' ✓' : ''}</td><td>{chg
            ? <>→ <code>{want}</code>{d && d.held ? <> <span className="help">held by {d.held === 'no block' ? 'a field in no block' : d.held}</span></> : null}{' '}
              <a href="#" className="x" title="cancel this rename: the name stays as it is" onClick={e => { e.preventDefault(); e.stopPropagation(); blockKeep(b.code, k + 1, true); }}>×</a></>
            : kept ? <span className="help">kept as is · <a href="#" onClick={e => { e.preventDefault(); e.stopPropagation(); blockKeep(b.code, k + 1, false); }}>undo</a></span>
            : <span className="help">as its type prints it</span>}</td></tr>);
      })}</tbody></table>
      <div className="row">{y.confirmed
        ? <button className={'btn mini ' + (b.validated ? '' : 'primary')} disabled={busy} onClick={e => { e.stopPropagation(); blockValidate(b.code); }}>
          {busy ? 'checking…' : b.validated ? 'validated ✓ · check again' : 'check & validate'}</button>
        : <span className="help">confirm {y.id}'s parts (below) to validate its blocks</span>}
        {nOff > 0 && <> <button className="btn mini" title="the names marked → put to the type's parts, as Claude's renames; nothing accepted" onClick={e => { e.stopPropagation(); blockFix(b.code); }}>rename ({nOff})</button></>}
        {' '}<button className="btn mini" title={`this area is not a block: its fields leave ${y.id}`} onClick={e => { e.stopPropagation(); blockOut(b.code); }}>not a block</button>
        {b.names.some(n => n == null) && <> <button className="btn mini" title="fitted again from the boxes in and round it (place, size and label)" onClick={e => { e.stopPropagation(); blockAssign(b.code, y.id); }}>re-fit to {y.id}</button></>}
        {(GD?.types || []).some(x => x.id !== y.id) && <> <select value="" onClick={stop} onKeyDown={stop} onChange={e => { if (e.target.value) blockAssign(b.code, e.target.value); }}>
          <option value="">assign to type…</option><TypeOptions not={y.id} first={closestFor[b.code]} /></select></>}</div>
      <div className="help">Its type's parts, and every block of {y.id} side by side: {y.id} below.</div>
    </div>
  );
}

function BlocksList() {
  const { GD, selBlock } = useBlocks();
  const page = useApp(s => s.page);
  const here = blocksHere(page);
  const find = (GD?.types || []).length ? <button className="btn mini" id="btDetect" onClick={e => { e.stopPropagation(); blockDetect(); }}
    title="each block type with a block on this page takes in the fields in no block that sit at the same place in every one of its blocks (cancel a grid first if it holds them); then every type's copies on the page are added as its blocks: exact copies of its layout, then places where its printed labels repeat (those can lack a box: drag it on); boxes already in a block are left">rescan this page</button> : null;
  if (!here.length) return <div className="btlist">{find}</div>;
  return (
    <div className="btlist"><h4>Blocks on page {page} ({here.length}) {find}</h4>{here.map(({ y, b }) => (
      <div key={b.code} className={'btrow' + (b.code === selBlock ? ' sel' : '')} data-blk={b.code} onClick={() => selectBlock(b)}>
        <b className="gtidc" data-copy={`${y.id}-${b.n}`} title="click to copy the reference (file_id)" onClick={copyRef(`${y.id}-${b.n}`)}>{y.id}-{b.n}</b>{' '}
        <span className="help">{y.label ? y.label + ' · ' : ''}{b.template ? 'the type\'s template · ' : ''}{blockState(y, b)}</span>
      </div>))}</div>
  );
}

// a cell of the matrix: the name its block prints at that position from the parts (as typed, while editing)
function MxCell({ y, b, k, s }: { y: BType; b: Block; k: number; s: Slot }) {
  const n = b.names[k];
  if (n == null) return <td className="help" title={`this block has no box at ${y.id}'s position ${k + 1}`}>no box</td>;
  const want = printIdent(blockIdent(b.prefix, b.iteration, s)), kept = (b.kept || []).includes(k + 1);
  const d = (b.differs || []).find(x => x.pos === k + 1), acc = (b.cells || [])[k]?.accepted;
  const chg = want && want !== n && !kept && !(b.same_as || []).length;
  return (
    <td className={chg ? 'chg' : ''}>
      <code className={'mxname' + (acc ? ' accd' : '')} title={acc ? 'accepted' : 'not accepted yet'}>{kept ? n : want || n}</code>{acc ? ' ✓' : ''}
      {chg && <span className="was" title="its name now">{n}</span>}
      {d && d.held && <span className="help" title="another field has that name and keeps it">held by {d.held === 'no block' ? 'a field in no block' : d.held}</span>}
      {d && !kept && <a href="#" className="x" title="cancel this rename: the name stays as it is" onClick={e => { e.preventDefault(); e.stopPropagation(); blockKeep(b.code, k + 1, true); }}>×</a>}
      {kept && <span className="help">kept · <a href="#" onClick={e => { e.preventDefault(); e.stopPropagation(); blockKeep(b.code, k + 1, false); }}>undo</a></span>}
    </td>
  );
}

// a block's row: its prefix and iteration, saved on Enter or leaving the box (both sent, so one edit keeps the other)
function MxRow({ y, b, ss, sel }: { y: BType; b: Block; ss: Slot[]; sel: boolean }) {
  const [pre, setPre] = useSynced(b.prefix || '');
  const [it, setIt] = useSynced(b.iteration || '');
  const [by, setBy] = useSynced(b.by !== 'prefix' ? 'number' : 'prefix');
  const save = () => {
    const p = pre.trim(), i = it.trim();
    if (p === (b.prefix || '') && i === (b.iteration || '')) return;
    const renumber = p !== (b.prefix || '') && i === (b.iteration || '');      // a new prefix: the next number free
    blockParts(b.code, { prefix: p, iteration: renumber ? '' : i, by: b.by });
  };
  return (
    <tr className={sel ? 'sel' : ''}>
      <th className="mxl"><b className="gtidc" title={`show this block (p${b.page})`} onClick={() => selectBlock(b)}>{y.id}-{b.n}</b>{' '}
        <span className="help" title={blockState(y, b)}>p{b.page}{b.validated ? ' ✓' : (b.differs || []).length ? ` · ${b.differs.length} off` : ''}{(b.same_as || []).length ? ' · same names!' : ''}</span><br />
        <input type="text" className="mxpre" value={pre} placeholder="prefix" title="the block's prefix: the start of every subject in this block"
          onClick={stop} onKeyDown={enterBlurs} onChange={e => setPre(e.target.value)} onBlur={save} />
        {' '}<input type="text" className="btit" value={it} placeholder={b.by === 'prefix' ? 'none' : 'next'}
          title={b.by === 'prefix' ? ITER_TITLE_PREFIX : "the block's iteration among the type's blocks with this prefix; empty, the next number free; - for none"}
          onClick={stop} onKeyDown={enterBlurs} onChange={e => setIt(e.target.value)} onBlur={save} />
        {' '}<select value={by} title={BY_TITLE} onClick={stop} onKeyDown={stop}
          onChange={e => { setBy(e.target.value); blockParts(b.code, { prefix: b.prefix || '', iteration: '', by: e.target.value }); }}>
          <option value="number">#</option><option value="prefix">pre</option></select>
        {b.parts_set && <> <a href="#" title="back to the prefix and iteration read from the names" onClick={e => { e.preventDefault(); e.stopPropagation(); blockParts(b.code, {}); }}>reset</a></>}</th>
      {ss.map((s, k) => <MxCell key={k} y={y} b={b} k={k} s={s} />)}
    </tr>
  );
}

function Matrix({ y, edit }: { y: BType; edit: boolean }) {
  const selBlock = useBlocks(s => s.selBlock);
  useBlocks(s => s.typed);
  // while editing, the cells print from the parts as typed (trimmed), so typing a part reprints its column at once
  const typed = shownSlots(y);
  const ss: Slot[] = edit ? typed.map(t => Object.fromEntries(PKEYS.map(k => [k, t[k].trim()]))) : typeSlots(y);
  const saved = typeSlots(y);
  const cols = saved.map((_, k) => k);
  const part = (k: number, key: (typeof PKEYS)[number]) => edit
    ? <input type="text" value={typed[k]?.[key] ?? ''} placeholder={key} onClick={stop} onKeyDown={stop} onChange={e => setSlot(y.id, k, key, e.target.value)} />
    : <code>{saved[k][key] || ''}</code>;
  return (
    <div className="btmx"><table>
      <thead><tr><th className="mxl">position</th>{cols.map(k => <th key={k}>{k + 1}</th>)}</tr>
        {PKEYS.map(key => <tr key={key} className="mxp"><th className="mxl">{key}</th>{cols.map(k => <td key={k}>{part(k, key)}</td>)}</tr>)}</thead>
      <tbody>{y.blocks.map(b => <MxRow key={b.code} y={y} b={b} ss={ss} sel={b.code === selBlock} />)}</tbody>
    </table></div>
  );
}

// block types (Andrew, 2026-10-21: "what happened to block types?"): each type, its wordings (editable until
// confirmed) and its blocks on every page, clickable
function TypeCard({ y, only }: { y: BType; only: boolean }) {
  const { GD, selBlock, editing, tBusy, closestFor } = useBlocks();
  const wide = useApp(s => s.wide);
  const edit = !y.confirmed || !!editing[y.id], mine = y.blocks.some(b => b.code === selBlock);
  // open when it holds the open block or is being edited (or is the form's only type with no block open); otherwise
  // the person's open / close stands
  const want = mine || !!editing[y.id] || (!selBlock && only);
  const det = useRef<HTMLDetailsElement>(null);
  useLayoutEffect(() => { if (want && det.current) det.current.open = true; }, [want, selBlock]);
  const [label, setLabel] = useSynced(y.label || '');
  const [auto, setAuto] = useSynced(!!y.auto);
  const allVal = y.blocks.every(b => b.validated), off = typeOff(y), busy = !!tBusy[y.id];
  return (
    <details className="bttype" ref={det} onClick={stop}>
      <summary><b className="gtidc" data-copy={y.id} title="click to copy the reference (file_id)" onClick={copyRef(y.id)}>{y.id}</b>{y.label ? ` ${y.label}` : ''}{' '}
        <span className="help">{y.boxes} boxes · {y.blocks.length} block{y.blocks.length === 1 ? '' : 's'} · {y.confirmed ? 'confirmed' : 'not confirmed'}{(y.from || '').includes('finder') ? ' · from the finder' : ''}</span></summary>
      <div className="row" style={{ margin: '2px 0 4px' }}><input type="text" className="btlabel" value={label} placeholder="label (e.g. US address)"
        title={`your name for ${y.id}; Enter or leaving the box saves it`} onClick={stop} onKeyDown={enterBlurs}
        onChange={e => setLabel(e.target.value)} onBlur={() => typeLabel(y.id, label)} /></div>
      <label className="help" title={`every block's prefix the label as a name and its iteration its number in ${y.id} (1 to ${y.blocks.length}, the PDF's order); a block's own prefix or iteration, set by hand, still wins`}>
        <input type="checkbox" checked={auto} disabled={!y.label} onClick={stop}
          onChange={e => { const on = e.target.checked, was = !!y.auto; setAuto(on); typeAuto(y.id, on).then(ok => { if (!ok) setAuto(was); }); }} />
        {' '}name its blocks {y.label ? `${y.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}_1, _2, …` : 'from the label (give it one first)'}</label>
      <div className="row help"><span title="A column per position: its subject, suffix, iteration (its own number, after the suffix: other_opts_txt_2) and part. A row per block: its prefix and iteration (empty: the next number free; - none; # told apart by number, pre by its prefix: no number unless another block shares it).">Names print as every field's: [prefix + subject]_[suffix]_[iteration]_[part]; names that will change are marked.</span>{' '}
        <button className="btn mini" title="the sidebar wider, for types with many positions" onClick={e => { e.preventDefault(); e.stopPropagation(); toggleWide(); }}>{wide ? 'narrower' : 'wider'}</button></div>
      <Matrix y={y} edit={edit} />
      <div className="row">{edit
        ? <button className="btn mini primary" onClick={e => { e.stopPropagation(); typeConfirm(y.id); }}>confirm {y.id}</button>
        : <a href="#" onClick={e => { e.preventDefault(); editParts(y.id); }}>edit parts</a>}
        {y.confirmed && <> <button className={'btn mini ' + (allVal ? '' : 'primary')} disabled={busy} onClick={e => { e.stopPropagation(); typeValidate(y.id); }}
          title={`check & validate every block of ${y.id}: the cells of each block that follows these wordings accepted; the others said, nothing of theirs accepted`}>
          {busy ? 'checking…' : allVal ? 'all validated ✓ · check again' : `validate all ${y.blocks.length}`}</button></>}
        {y.confirmed && off > 0 && <> <button className="btn mini" onClick={e => { e.stopPropagation(); typeFix(y.id); }}
          title={`every block of ${y.id} printed from these parts (each block's prefix and iteration; cancelled renames left), as Claude's renames, the parts stored on each field; nothing accepted`}>rename every block ({off})</button></>}</div>
      {(GD?.types || []).length > 1 && <div className="row"><select value="" onClick={stop} onKeyDown={stop} onChange={e => { if (e.target.value) typeAssign(y.id, e.target.value); }}
        title={`every block of ${y.id} given another type, each fitted by best fit (place, size, label); ${y.id} is then dropped`}>
        <option value="">assign {y.blocks.length === 1 ? 'its block' : `its ${y.blocks.length} blocks`} to…</option>
        <TypeOptions not={y.id} first={y.blocks.length === 1 ? closestFor[y.blocks[0].code] : null} /></select></div>}
    </details>
  );
}

function Types() {
  const GD = useBlocks(s => s.GD);
  const ys = GD?.types || [];
  if (!ys.length) return null;
  return <div className="btlist"><h4>Block types ({ys.length})</h4>{ys.map(y => <TypeCard key={y.id} y={y} only={ys.length === 1} />)}</div>;
}

export function Panel() {
  const { GD, selBlock } = useBlocks();
  if (!GD) return <p className="help">loading…</p>;
  const y = (GD.types || []).find(t => t.blocks.some(b => b.code === selBlock));
  const b = y?.blocks.find(x => x.code === selBlock);
  return (
    <>
      <div className="help">Drag on an empty part of the page (or Shift+drag anywhere) around one block to make it a block: of an existing block type when its boxes match one, several blocks when the area holds several copies, else a new type. Drag a block onto another to make it a block of that one's type. Click a block to open it; Delete removes it; n / p step through the blocks; Enter validates the open one.</div>
      {y && b && <OpenBlock key={b.code} y={y} b={b} />}
      <Types />
      <BlocksList />
    </>
  );
}

export function Bar() {
  const GD = useBlocks(s => s.GD);
  if (!GD) return <span className="progress" id="progress" />;
  const ys = GD.types || [], bs = ys.flatMap(y => y.blocks);
  return <span className="progress" id="progress"><b>{ys.length}</b> block types · {bs.length} blocks · {bs.filter(b => b.validated).length} validated</span>;
}
