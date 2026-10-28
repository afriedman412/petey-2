// Add / remove's sidebar: the blueprint's finder and suggestions left, the proposal cards (or the field picked to
// remove), the notes, and the lists of what is to be added, removed, or is not a field; and its bar.
import type { KeyboardEvent } from 'react';
import {
  addAll, addProps, askLabeler, cancel, closePicked, dropOption, goto, isRemoved, keepRemoved, NAME_RE, pickName, pickRemoved,
  remaining, runFinder, save, setOptField, setPropField, setShow, skipProp, switchKind, toggleRemove, toggleRmPick, removeAll, unAdd, unDismiss, useAdd,
  gotoSuggestion, type Proposal,
} from './store';

const TYPES = ['string', 'number', 'integer', 'date', 'boolean', 'category', 'multi_category'];

/** a card's box: Enter (not in the description) adds all that is proposed, Esc cancels */
function cardKeys(e: KeyboardEvent<HTMLElement>) {
  e.stopPropagation();
  if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'TEXTAREA') addAll();
  if (e.key === 'Escape') cancel();
}

function Options({ p, i }: { p: Proposal; i: number }) {
  return (
    <>
      <table className="opts"><tbody>
        <tr><th className="help">key</th><th className="help">caption</th><th></th></tr>
        {p.options.map((o, k) => (
          <tr key={k}>
            <td><input type="text" value={o.key ?? ''} onChange={e => setOptField(i, k, 'key', e.target.value)} onKeyDown={e => e.stopPropagation()} /></td>
            <td><input type="text" value={o.caption || ''} onChange={e => setOptField(i, k, 'caption', e.target.value)} onKeyDown={e => e.stopPropagation()} /></td>
            <td><span className="achip" title="leave this box out" onClick={() => dropOption(i, k)}>×</span></td>
          </tr>))}
      </tbody></table>
      <div className="help">keyed by {p.keyed_by}{p.options.some(o => o.on_state) ? '; on-states ' + p.options.map(o => o.on_state || '?').join(', ') : ''}</div>
    </>
  );
}

function Card({ p, i }: { p: Proposal; i: number }) {
  const { BP, added, props, asking } = useAdd();
  const sem = ['', ...BP!.semantic_types];
  const what = p.kind === 'group' ? `group of ${p.options.length} options` : p.kind === 'option' ? `${p.widget?.widget_type}` : 'text box';
  const clash = added.some(a => a.name === p.name) || props.some((q, k) => k !== i && q.name === p.name);
  return (
    <div className="acard">
      <h3>{what} on p{p.page} <span className="help">· {p.geometry} geometry</span></h3>
      <input type="text" value={p.name || ''} onChange={e => setPropField(i, 'name', e.target.value)} onKeyDown={cardKeys} />
      {!NAME_RE.test(p.name || '') ? <div className="err help">not a field name (lower case, digits, underscores)</div>
        : clash ? <div className="err help">another field has this name</div> : null}
      <div className="achips">
        {p.name_options.map((o, k) => (
          <span key={k} className={'achip' + (o.name === p.name ? ' on' : '')} onClick={() => pickName(i, k)}>{o.name}<span className="src">{o.source}</span></span>))}
        <span className="achip" title={`one call to ${BP!.label_model} with this page's words`} onClick={() => askLabeler(i)}>{asking[p._k!] ? 'asking…' : 'ask the labeler'}</span>
      </div>
      <div className="grid">
        {p.kind !== 'group' && <>
          <label>box</label>
          <select value={p.kind} title="what the page shows: what was under the box decides, and can be wrong" onChange={e => switchKind(i, e.target.value)}>
            <option value="text">text box</option><option value="option">checkbox</option></select>
        </>}
        <label>type</label>
        <select value={p.type || ''} onChange={e => setPropField(i, 'type', e.target.value)} onKeyDown={cardKeys}>{TYPES.map(t => <option key={t}>{t}</option>)}</select>
        {p.kind === 'text' && <>
          <label>semantic</label>
          <select value={p.semantic_type || ''} onChange={e => setPropField(i, 'semantic_type', e.target.value)} onKeyDown={cardKeys}>
            {sem.map(t => <option key={t} value={t}>{t || '(none)'}</option>)}</select>
          <label>pattern</label>
          <input type="text" value={p.pattern || ''} disabled={p.type !== 'string'} onChange={e => setPropField(i, 'pattern', e.target.value)} onKeyDown={cardKeys} />
        </>}
        <label>description</label>
        <textarea value={p.description || ''} onChange={e => setPropField(i, 'description', e.target.value)} onKeyDown={cardKeys} />
      </div>
      {p.kind === 'group' && <Options p={p} i={i} />}
      {p.page_class && <div className="help">classifier: {p.page_class}{p.entity ? ' for ' + p.entity : ''} (shown, not applied)</div>}
      <ul className="ev">{p.evidence.map((e, k) => <li key={k}>{e}</li>)}</ul>
      <div className="arow"><button className="btn primary" onClick={() => addProps([i])}>add this field</button>{' '}
        <button className="btn" title="drop this one; the others stay" onClick={() => skipProp(i)}>cancel</button></div>
    </div>
  );
}

function Picked({ name }: { name: string }) {
  const BP = useAdd(s => s.BP)!;
  useAdd(s => s.removed);
  const f = (BP.field_specs || {})[name] || {}, gone = isRemoved(name);
  return (
    <div className="acard"><h3>{f.x_petey_id && <><code className="fid">{f.x_petey_id}</code> </>}{name} <span className="help">· a field of the blueprint</span></h3>
      <div className="help">{f.type || ''}{f.semantic_type ? '/' + f.semantic_type : ''}{f.description ? ' · ' + f.description : ''}</div>
      {gone && <div className="rbanner">recorded for removal, not removed yet (see the list below)</div>}
      <div className="arow">{gone ? <button className="btn" id="aKeep" onClick={toggleRemove}>keep it</button>
        : <button className="btn warn" id="aRemove" onClick={toggleRemove}>remove this field</button>}{' '}
        <button className="btn" id="cancel" onClick={closePicked}>close</button></div></div>
  );
}

/** add all / remove all / cancel all, above the cards and below them */
function AllButtons({ top = false }: { top?: boolean }) {
  const { props, rmPicks } = useAdd(), n = props.length + rmPicks.length;
  return (
    <div className="arow">
      {props.length > 1 && <><button className="btn primary" onClick={addAll}>add all {props.length}</button>{' '}</>}
      {rmPicks.length > 0 && <><button className="btn warn" id={top ? 'rmAllTop' : 'rmAll'} onClick={() => removeAll()}>{rmPicks.length > 1 ? `remove all ${rmPicks.length}` : 'remove it'}</button>{' '}</>}
      <button className="btn" id={top ? 'cancelTop' : 'cancel'} onClick={cancel}>{n > 1 ? 'cancel all' : 'cancel'}</button>
    </div>
  );
}

/** a field of the blueprint collected to remove; clicked again on the page, or "cancel", it leaves the collection */
function RmCard({ name }: { name: string }) {
  const BP = useAdd(s => s.BP)!;
  const f = (BP.field_specs || {})[name] || {}, at = BP.fields.find(x => x.name === name);
  return (
    <div className="acard rmcard"><h3>{f.x_petey_id && <><code className="fid">{f.x_petey_id}</code> </>}{name} <span className="help">· to remove{at ? ` · p${at.page}` : ''}</span></h3>
      <div className="help">{f.type || ''}{f.semantic_type ? '/' + f.semantic_type : ''}{f.description ? ' · ' + f.description : ''}</div>
      <div className="arow"><button className="btn warn" onClick={() => removeAll([name])}>remove this field</button>{' '}
        <button className="btn" onClick={() => toggleRmPick(name)}>cancel</button></div></div>
  );
}

function Changes() {
  const { PLAN, added, removed } = useAdd();
  if (!PLAN || (!added.length && !removed.length)) return <div className="changes" id="aChanges" />;
  const errors = PLAN.errors || [], changes = PLAN.changes || [];
  return (
    <div className="changes" id="aChanges">
      <h4>Not in the working copy yet</h4>
      <ul>
        {errors.map((e, k) => <li key={'e' + k} className="err">{e}</li>)}
        {(PLAN.skipped || []).map((e, k) => <li key={'s' + k} className="help">skip {e}</li>)}
        {changes.map((c, k) => <li key={'c' + k}>{c}</li>)}
      </ul>
      {changes.length > 0 && <button className="btn ok" id="aApply" disabled={errors.length > 0} title={errors.length ? 'fix the errors first' : undefined} onClick={applyAdds}>apply to working copy</button>}
      <div className="help">Additions and removals go into the working copy as they are saved, unless something above stops them.</div>
    </div>
  );
}
async function applyAdds() { await save(); }

export function Panel() {
  const { BP, props, notes, picked, rmPicks, added, removed, dismissed, copies, finderRunning } = useAdd();
  if (!BP) return null;
  const left = remaining();
  return (
    <>
      <div className="help">{BP.path}{BP.stale && <> <span className="stale">· recorded against an earlier version of this file</span></>}</div>
      <div className="help">{BP.has_widgets ? 'form layer: yes' : 'no form layer (flat)'} · finder: {BP.finder}
        {BP.finder !== 'cached' && <> <button className="btn" id="runFinder" title="step2flat on this blank, local CPU, cached afterwards" disabled={finderRunning} onClick={runFinder}>{finderRunning ? 'running (local CPU)…' : 'run it'}</button></>} · classifier map: {BP.classifier}</div>
      <div><b>{left.length}</b> suggestion{left.length === 1 ? '' : 's'} left <span className="help">({left.filter(s => s.source === 'widget').length} widgets, {left.filter(s => s.source === 'finder').length} finder boxes{BP.suggestions.some(s => s.copy) && !copies ? '; repeated copies hidden' : ''})</span>{' '}
        <button className="btn" id="nextSug" onClick={() => gotoSuggestion(1)}>next suggestion</button></div>
      {picked && <Picked name={picked} />}
      {props.length + rmPicks.length ? <>
        {/* several proposals or fields to remove: the buttons above them too, not only after the last card (Andrew,
            2026-10-23; 2026-10-28: "let's have the 'cancel all' button at the top and the bottom"; removals collected
            as additions are, "with the same buttons") */}
        {props.length + rmPicks.length > 1 && <AllButtons top />}
        {props.map((p, i) => <Card key={p._k} p={p} i={i} />)}
        {rmPicks.map(n => <RmCard key={'r' + n} name={n} />)}
        <AllButtons />
      </> : !picked && <p className="help">Drag a box over an area of the page, click a box, or go to the next suggestion. Orange: suggestions (solid: an unclaimed widget; dashed: a finder box). Purple: fields the blueprint has (hover for the name; click to collect them for removal). Green: fields you have added; red dashed: fields to remove.</p>}
      {notes.length > 0 && <div className="notes">{notes.map((n, k) => <div key={k}>{n}</div>)}</div>}
      <div><h4>To add ({added.length})</h4><div className="alist">{added.length ? added.map((x, i) => (
        <div key={i} onClick={() => goto(x.page)}><span>p{x.page} · {x.name} <span className="help">{x.kind === 'group' ? 'group' : x.type}</span></span>
          <span className="x" title="remove" onClick={e => { e.stopPropagation(); unAdd(i); }}>×</span></div>))
        : <p className="help">nothing yet</p>}</div></div>
      {removed.length > 0 && <div><h4>To remove ({removed.length})</h4><div className="alist">{removed.map((x, i) => (
        <div key={i} onClick={() => pickRemoved(i)}><span>p{x.page} · {x.name} <span className="help">from {x.from || '?'}</span></span>
          <span className="x" title="keep it" onClick={e => { e.stopPropagation(); keepRemoved(i); }}>×</span></div>))}</div></div>}
      {dismissed.length > 0 && <div><h4>Not fields ({dismissed.length})</h4><div className="alist">{dismissed.map((x, i) => (
        <div key={i} onClick={() => goto(x.page)}><span>p{x.page} · {x.what || x.sid}</span>
          <span className="x" title="put it back" onClick={e => { e.stopPropagation(); unDismiss(i); }}>×</span></div>))}</div></div>}
      <Changes />
    </>
  );
}

export function Bar() {
  const { BP, added, removed, dismissed, showFields, showSug, copies } = useAdd();
  return (
    <>
      <span className="progress" id="progress">{BP && <><b>{added.length}</b> to add · <b>{removed.length}</b> to remove · <b>{dismissed.length}</b> not fields · <b>{remaining().length}</b> suggestions left</>}</span>{' '}
      <label className="help"><input type="checkbox" id="aFields" checked={showFields} onChange={e => setShow({ showFields: e.target.checked })} /> fields</label>{' '}
      <label className="help"><input type="checkbox" id="aSug" checked={showSug} onChange={e => setShow({ showSug: e.target.checked })} /> suggestions</label>{' '}
      <label className="help"><input type="checkbox" id="aCopies" checked={copies} onChange={e => setShow({ copies: e.target.checked })} /> repeated copies</label>
    </>
  );
}
