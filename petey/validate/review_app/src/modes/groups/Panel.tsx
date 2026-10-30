// Groups' sidebar: the selected unit's card, the suggestions, the groups on the page, the tray of loose boxes, the
// entities and what applying would change; and its bar (the counts and the buttons).
import { useState } from 'react';
import { dragProps, dropProps } from '../../lib/dnd';
import { fileStem } from '../../lib/util';
import { toast } from '../../state/actions';
import { useApp } from '../../state/app';
import {
  applyPlan, askLabeler, baseOf, entityPicked, busyOn, clearPicked, colorOf, confirmUnit, dropped, groupPicked, groupSuggested, hoverProps, isConverted,
  isGroup, isText, isTextItem, item, label, looseText, mergeInto, moveItem, nameCheck, notGroup, onPage, optUnits, rename,
  ENTITY_TYPES, rereadCaptions, rescanPage, revert, select, separate, setDesc, setEntityType, setShowText, setType, setUnconfOnly,
  status, toBool, toText,
  undo, ungroup, unitOf, useGroups, type Target, type Unit,
} from './store';

const dropOn = (target: Target) => dropProps(['item', 'unit'], (kind, v) => dropped(kind, v, target));

function Badge({ u }: { u: Unit }) {
  const st = status(u);
  return <>{u.confirmed && <span className="badge ok">confirmed</span>}
    {st === 'new' ? <span className="badge new">new</span> : st === 'edited' ? <span className="badge edit">edited</span> : null}</>;
}

/** the name box: what is typed stays until Enter or leaving the box renames the unit */
function NameBox({ u, text }: { u: Unit; text?: boolean }) {
  const [v, setV] = useState(u.name);
  return <input id="uname" type={text ? 'text' : undefined} value={v} disabled={!text && !!u.locked} spellCheck={text ? undefined : false}
    onChange={e => setV(e.target.value)}
    onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') rename(u.uid, v, 'hand'); }}
    onBlur={() => rename(u.uid, v, 'hand')} />;
}
function DescBox({ u }: { u: Unit }) {
  const [v, setV] = useState(u.description || '');
  return <textarea id="udesc" placeholder="description (left empty: the members' descriptions)" value={v}
    onChange={e => setV(e.target.value)} onKeyDown={e => e.stopPropagation()} onBlur={() => setDesc(u.uid, v.trim())} />;
}

function TextCard({ u }: { u: Unit }) {
  const busy = useGroups(s => s.busy);
  const bad = nameCheck(u), asking = busyOn(busy, u, 'label');
  return (
    <div className="gcur">
      <h2>Entity of {u.items.length} fields <Badge u={u} /></h2>
      <NameBox key={u.uid + '\n' + u.name} u={u} text />{' '}
      <button className="btn" id="gLabel" title="one call to the labeler with the words on this page" disabled={asking} onClick={() => askLabeler(u.uid)}>{asking ? 'asking…' : 'ask the labeler'}</button>
      {u.name_from === 'labeler' && <> <span className="help">(from the labeler)</span></>}
      {bad && <div className="warn">{bad}</div>}
      <div className="frow"><label>entity type{' '}
        <select id="gEntityType" value={u.entity_type || ''} onChange={e => setEntityType(u.uid, e.target.value)}
          onKeyDown={e => e.stopPropagation()}>
          <option value="">(none)</option>
          {ENTITY_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select></label></div>
      <DescBox key={u.uid + '\n' + (u.description || '')} u={u} />
      <ol>{u.items.map(id => { const it = item(id);
        return <li key={id} {...hoverProps(id)}>{it.field} <span className="help">{it.type || ''}{it.semantic_type ? '/' + it.semantic_type : ''}{it.path ? ' · ' + it.path.split('.').pop() : ''}</span></li>; })}</ol>
      <div className="help">One value over these fields, in this order. The fields stay as they are (names, boxes, paths); each is tagged with the entity.</div>
      <div className="row"><button className="btn" id="gSplit" onClick={() => separate(u.uid)}>separate again</button></div>
    </div>
  );
}

// text fields picked (a click, Shift-click, an area): made checkboxes with one button (Andrew, 2026-10-27: "bring
// them up in the side panel (either as a group or solo) and provide a button that says 'convert to bool'")
function PickedText() {
  const picked = useGroups(s => s.picked), units = useGroups(s => s.units);
  const ids = [...picked].filter(id => isTextItem(id, units));
  if (!ids.length) return null;
  const one = ids.length === 1;
  return (
    <div className="fcard sect gcur" id="gPickedText">
      <h4>Selected text field{one ? '' : 's'} <span className="help">{ids.length}</span></h4>
      <ul>{ids.map(id => { const it = item(id);
        return <li key={id} {...hoverProps(id)}><code>{it.field}</code> <span className="help">→ {it.ind_name || it.field + '_ind'}{it.type ? ` · now ${it.type}${it.semantic_type ? '/' + it.semantic_type : ''}` : ''}</span></li>; })}</ul>
      <div className="frow">
        {!one && <button className="btn ok" id="gEntity" title="make the selected text fields one entity (g)" onClick={() => entityPicked()}>make entity ({ids.length})</button>}
        {!one && <select id="gEntityPick" value="" title="make the selected text fields one entity of this type"
          onChange={e => entityPicked(e.target.value)} onKeyDown={e => e.stopPropagation()}>
          <option value="">make entity of type…</option>
          {ENTITY_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>}
        <button className="btn ok" id="gToBool" onClick={() => toBool(ids)}>convert to bool</button>
        <button className="btn" onClick={clearPicked}>clear</button>
      </div>
      <div className="help">Each becomes a checkbox (boolean, indicator) on its own box, its suffix made _ind. {one ? '' : 'They stay selected: g makes them one group. '}It goes into the working copy with the regrouping; z undoes.</div>
    </div>
  );
}

// laid out as Review's selected-field card, without the field data (Andrew, 2026-10-24: "group panel should
// basically be the same as the review panel but without the field data"; "group panel needs the full field id too")
function Current({ u }: { u?: Unit }) {
  const { BP, units, busy } = useGroups();
  const page = useApp(s => s.page);
  if (!u) return <p className="help">Nothing selected on this page.</p>;
  if (isText(u)) return <TextCard u={u} />;
  const group = isGroup(u), b = baseOf(u), bad = nameCheck(u);
  const was = b && b.name !== u.name ? <span className="help">was <code>{b.name}</code></span> : null;
  const code = (BP!.codes || {})[u.origin || ''] || (BP!.codes || {})[item(u.items[0]).field];
  const ref = code ? `${fileStem(BP!.path)}_${code}` : '';
  const pages = [...new Set(u.items.map(id => item(id).page))].sort((x, y) => x - y);
  const copyRef = async () => {
    if (!code) return;
    try { await navigator.clipboard.writeText(ref); toast(`Copied ${ref}`); } catch { /* no clipboard: the id is on screen */ }
  };
  const first = item(u.items[0]);
  const asking = busyOn(busy, u, 'label'), reading = busyOn(busy, u, 'caps');
  return (
    <div className="fcard sect gcur">
      <h4 id="gref" title="click to copy the field reference (file_page_n)" onClick={copyRef}>{group ? 'Selected group' : 'Selected box'} {ref && <code className="fid">{ref}</code>}
        <span className="help">page {pages.join(', ')} · {group ? u.items.length + ' options' : 'loose'}</span> <Badge u={u} /></h4>
      {u.locked && <div className="warn">{u.locked}</div>}
      <div className="fgrid">
        <label>Field name</label>
        <span className="namerow"><NameBox key={u.uid + '\n' + u.name} u={u} />
          {!u.locked && <button className="btn parts" id="gLabel" title="one call to the labeler with the words on this page" disabled={asking} onClick={() => askLabeler(u.uid)}>{asking ? 'asking…' : 'ask the labeler'}</button>}</span>
        {(u.name_from === 'labeler' || was) && <><span></span><span>{u.name_from === 'labeler' && <><span className="help">from the labeler</span> </>}{was}</span></>}
        {bad && <><span></span><span className="warn">{bad}</span></>}
        {u.locked ? null : group ? <>
          <span className="lbl">Kind</span>
          <span className="gkind">
            <label><input type="radio" name="ty" value="category" checked={u.type === 'category'} onChange={() => setType(u.uid, 'category')} /> one of</label>
            <label><input type="radio" name="ty" value="multi_category" checked={u.type === 'multi_category'} onChange={() => setType(u.uid, 'multi_category')} /> any of</label>
            {u.items.length === 1 && <span className="warn">a group of one option</span>}
          </span>
        </> : <>
          <span className="lbl">Box</span>
          <span className="help">{isConverted(first.id, units) ? <>the text field <code>{first.field}</code> made a checkbox{first.converted ? ' (applied)' : '; it changes when the regrouping is applied'}. </>
            : <>a {first.widget_type} field of its own{first.appearances ? `, drawn in ${first.appearances} places` : ''}. </>}
            Confirm it if it stands alone; drag it onto its group or onto another loose box if not.</span>
        </>}
        {group && <>
          <span className="lbl">Options<br /><span className="help">key · caption</span></span>
          <span className="otable">{u.items.map(id => { const it = item(id);
            return (
              <span key={id} className="orow" {...hoverProps(id)}>
                <input className="okey" value={it.key !== null ? it.key : it.kind === 'text' ? (it.ind_name || it.field) : it.field} readOnly
                  title={`the value extraction returns for this box${it.on_state ? '; the PDF stores ' + it.on_state : ''}${it.page !== page ? ' (page ' + it.page + ')' : ''}`} />
                <input className="ocap" value={label(id, units)} readOnly placeholder="no caption" title="the text printed at this box" />
              </span>);
          })}</span>
        </>}
      </div>
      <div className="frow">
        <button className={'btn ok' + (u.confirmed ? ' on' : '')} id="gConfirm" onClick={() => confirmUnit(u.uid)}>{u.confirmed ? 'confirmed' : (group ? 'group is right' : 'stands alone')}</button>
        {group && !u.locked && <button className="btn" id="gCaps" disabled={reading} onClick={() => rereadCaptions(u.uid)}
          title="read each box's printed caption again (one call to the review agent with the page image, a few seconds); captions from the PDF's form data or set by hand stay">{reading ? 'reading…' : 're-read captions'}</button>}
        {b && status(u) !== 'as blueprint' && <button className="btn" id="gRevert" title="put this unit back as the blueprint has it" onClick={() => revert(u.uid)}>back to blueprint</button>}
        {!group && isConverted(first.id, units) && <button className="btn" id="gToText" title="make it a text field again" onClick={() => toText(u.uid)}>back to text</button>}
        {group && !isText(u) && !u.locked && <button className="btn" id="gUngroup" title="every box of this group loose again (u); the finder will not group these boxes again; z undoes" onClick={ungroup}>ungroup</button>}
        {group && !u.locked && (
          <select id="gMergeTo" value="" title="move this group's boxes into another group, on any page (a question that runs onto the next page)"
            onKeyDown={e => e.stopPropagation()} onChange={e => mergeInto(u.uid, Number(e.target.value))}>
            <option value="">merge into another group…</option>
            {optUnits(units).filter(x => x !== u && isGroup(x) && !x.locked).map(x => (
              <option key={x.uid} value={x.uid}>{x.name} ({x.items.length}, p{[...new Set(x.items.map(i => item(i).page))].join(',')})</option>))}
          </select>)}
      </div>
    </div>
  );
}

function Chip({ id, u }: { id: string; u: Unit }) {
  const selected = useGroups(s => s.selected), units = useGroups(s => s.units);
  const page = useApp(s => s.page);
  const it = item(id), orphan = !isGroup(u), cu = unitOf(id, units)!;
  const drop = !u.locked && !isGroup(cu) ? dropOn({ item: id, inTray: true }) : {};
  return (
    <span className={'gchip' + (orphan ? ' orphan' : '') + (u.uid === selected ? ' sel' : '')} data-item={id}
      title={`${it.field}${it.key !== null ? ' · ' + it.key : ''}${it.on_state ? ' · on ' + it.on_state : ''}`}
      onClick={() => select(cu.uid)} {...hoverProps(id)} {...dragProps('item', id, !u.locked)} {...drop}>
      <span className="gl">{orphan ? u.name : label(id, units)}{it.page !== page && <> <span className="help">p{it.page}</span></>}</span>
      {!orphan && !u.locked && <span className="x" title={isText(u) ? 'take it out of the entity' : 'take it out of the group'}
        onClick={e => { e.stopPropagation(); moveItem(id, { tray: true }); }}>×</span>}
    </span>
  );
}

function UnitCard({ g }: { g: Unit }) {
  const selected = useGroups(s => s.selected), units = useGroups(s => s.units);
  const page = useApp(s => s.page);
  return (
    <div className={'gcard' + (g.uid === selected ? ' sel' : '') + (g.confirmed ? ' ok' : '')} data-unit={g.uid}
      style={{ '--c': colorOf(g, units, page) } as React.CSSProperties} {...(g.locked ? {} : dropOn({ unit: g.uid }))}>
      <h3 onClick={() => select(g.uid)}><span className="grip" title={`drag the whole ${isText(g) ? 'entity' : 'group'}`} {...dragProps('unit', g.uid, !g.locked)}>⠿</span>{g.name} <Badge u={g} /></h3>
      <div className="gchips">{g.items.map(id => <Chip key={id} id={id} u={g} />)}</div>
    </div>
  );
}

// suggested groups among the loose boxes (group_finder, 2026-10-25): made as the tab loads, so shown here only
// when that failed
function Suggestions() {
  const BP = useGroups(s => s.BP)!, units = useGroups(s => s.units);
  const page = useApp(s => s.page);
  const sugg = (BP.suggested || []).map((x, i) => ({ ...x, i }))
    .filter(x => x.page === page && x.items.every(id => { const v = unitOf(id, units); return v && !isGroup(v); }));
  if (!sugg.length) return null;
  return (
    <div className="gsugg"><h4>Suggested groups on page {page} ({sugg.length})</h4>
      {sugg.map(x => (
        <div key={x.i} className="gcard"><div className="help">{x.why}{x.name && <> · <code>{x.name}</code></>}</div>
          <div className="gchips">{x.items.map((id, k) => <span key={id} className="gchip" {...hoverProps(id)}>{(x.captions || [])[k] || item(id).field} <span className="help">{item(id).field}</span></span>)}</div>
          <div className="row">
            <button className="btn ok mini" onClick={() => groupSuggested(BP.suggested![x.i])}>group them</button>
            <button className="btn mini" title="these boxes are not one question: the suggestion stays away" onClick={() => notGroup(x.i)}>not a group</button>
          </div></div>))}
    </div>
  );
}

function Changes() {
  const PLAN = useGroups(s => s.PLAN);
  if (!PLAN) return <div className="changes" id="gChanges" />;
  const any = PLAN.errors.length || PLAN.changes.length;
  return (
    <div className="changes" id="gChanges">
      <h4>What applying would change in the working copy ({PLAN.changes.length})</h4>
      {any ? <ul>{PLAN.errors.map((e, i) => <li key={'e' + i} className="err">{e}</li>)}{PLAN.changes.map((c, i) => <li key={'c' + i}>{c}</li>)}</ul>
        : <p className="help">nothing: the grouping is the working copy's</p>}
      {PLAN.changes.length > 0 && <button className="btn ok" id="gApply" disabled={PLAN.errors.length > 0} title={PLAN.errors.length ? 'fix the errors first' : undefined} onClick={applyPlan}>apply to working copy</button>}
      <div className="help">The regrouping goes into the working copy when you leave Groups (another mode or form, or "save blueprint"), or now with the button; "save blueprint" in the header writes the blueprint.</div>
    </div>
  );
}

export function Panel() {
  const { BP, units, selected, notes, unconfOnly, showText } = useGroups();
  const page = useApp(s => s.page);
  if (!BP) return null;
  if (!units.length && !Object.values(BP.items).length) return <><div className="help">{BP.path}</div><p className="help">This blueprint has no option boxes or text fields.</p></>;
  const u = units.find(x => x.uid === selected);
  const listed = optUnits(units).filter(x => onPage(x, page) && (!unconfOnly || !x.confirmed || x.uid === selected));
  const groups = listed.filter(isGroup), loose = listed.filter(x => !isGroup(x));
  const combos = units.filter(x => isText(x) && onPage(x, page)), nLoose = looseText(page, units).length;
  return (
    <>
      <div className="help">{BP.path}{BP.info.stale && <> <span className="stale">· the saved grouping predates this file; rebased onto it</span></>}{BP.info.applied && ` · last applied ${BP.info.applied.when}`}</div>
      {notes.length > 0 && <div className="warn">{notes.map((n, i) => <span key={i}>{i ? <br /> : null}{n}</span>)}</div>}
      <PickedText />
      <Current u={u} />
      <Suggestions />
      <div><h4>Groups on page {page} ({groups.length}) · drop a box on a group to add it</h4>
        {groups.length ? groups.map(g => <UnitCard key={g.uid} g={g} />) : <p className="help">none</p>}</div>
      <div className="tray" id="tray" {...dropOn({ tray: true })}><h4>Loose boxes on page {page} ({loose.length}) · drop a box here to take it out of its group or entity; drop one loose box on another to group them</h4>
        <div className="gchips">{loose.map(o => <Chip key={o.uid} id={o.items[0]} u={o} />)}</div></div>
      <div><h4>Entities on page {page} ({combos.length})</h4>
        {combos.map(g => <UnitCard key={g.uid} g={g} />)}
        <p className="help">{showText ? `Drag a teal text field onto another to make them one entity: one value over several fields, a date, a name, a signature and its date (${nLoose} text fields on this page). The fields stay as they are.` : 'Text fields are hidden; press Shift+T to show them.'}</p></div>
      <Changes />
    </>
  );
}

export function Bar() {
  const { BP, units, PLAN, unconfOnly, showText, undoStack, picked, rescanning } = useGroups();
  let progress = null;
  if (BP) {
    const ou = optUnits(units), n = ou.length, ok = ou.filter(x => x.confirmed).length, g = ou.filter(isGroup).length, t = units.filter(isText).length;
    progress = <>
      <b>{ok}</b> of {n} confirmed · {g} groups, {n - g} loose{t ? ` · ${t} entit${t === 1 ? 'y' : 'ies'}` : ''}
      {PLAN && <> · <b>{PLAN.changes.length}</b> change{PLAN.changes.length === 1 ? '' : 's'}{PLAN.errors.length > 0 && <> <span className="stale">({PLAN.errors.length} to fix)</span></>}</>}
      {/* the apply button in the bar as well as under the change list (2026-10-13: saved groups that never reached the
          blueprint, because the only button sat at the bottom of the sidebar) */}
      {PLAN && PLAN.changes.length > 0 && <> <button className="btn ok" id="gApplyBar" disabled={PLAN.errors.length > 0}
        title={PLAN.errors.length ? 'fix the errors first' : 'put the regrouping into the working copy now (leaving Groups does it too)'}
        onClick={applyPlan}>apply {PLAN.changes.length} change{PLAN.changes.length === 1 ? '' : 's'} to working copy</button></>}
    </>;
  }
  return (
    <>
      <span className="progress" id="progress">{progress}</span>
      <label className="help"><input type="checkbox" id="gUnconf" checked={unconfOnly} onChange={e => setUnconfOnly(e.target.checked)} /> unconfirmed only</label>
      <label className="help"><input type="checkbox" id="gText" checked={showText} onChange={e => setShowText(e.target.checked)} /> text fields</label>
      <button className="btn" id="gUndo" disabled={!undoStack.length} onClick={undo}>undo</button>
      <button className="btn" id="gGroup" disabled={picked.size < 2} title="make the selected boxes one group (g)" onClick={groupPicked}>group selected ({picked.size})</button>
      <button className="btn" id="gRescan" disabled={rescanning > 0} onClick={rescanPage}
        title={'every group on this page that is not confirmed or locked: its captions read again (one call per group to the review agent with the page image, all at once; captions from the PDF\'s form data or set by hand stay), then the labeler names them all in one call with the page\'s words: a name it gives replaces only a group not yet in the blueprint and not named by hand. Nothing is saved; z undoes'}>
        {rescanning ? `rescanning ${rescanning}…` : 'rescan page'}</button>
    </>
  );
}
