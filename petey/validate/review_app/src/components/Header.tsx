// The top bar: home, the form menu, the working copy's save / discard, the whole-form actions and the panels.
import { useEffect, useState } from 'react';
import type { Entry } from '../lib/types';
import { store } from '../lib/util';
import { discardDraft, openBlueprint, reboot, saveDraft, setMode, showHome } from '../state/actions';
import { set, useApp, useEntry } from '../state/app';
import { reviewActions, useHeaderCounts } from '../modes/review/store';
import { runFinders } from '../modes/blocks/actions';
import { SECTIONS, sectionOf } from './home-data';

function pickerText(b: Entry) {
  // short (Andrew, 2026-10-13: the long rows widened the menu and pushed the header buttons onto a second line):
  // fields, reviewed, VALIDATED; a * marks an unsaved working copy
  const bits = [`${b.fields} fields`, `${b.accepted + b.flagged} reviewed`];
  if (b.checked?.validated) bits.push('VALIDATED');
  return `${b.form}${b.draft ? ' *' : ''}  (${bits.join(', ')})`;
}

function Picker() {
  const { list, bid, listOrder, listError } = useApp();
  if (listError) return <select id="pick" />;
  if (!list.length) return <select id="pick"><option>loading blueprints…</option></select>;
  // most errors first (Andrew, 2026-10-07): the page check's errors, then its suggestions, within each section; a
  // blueprint with no page check sorts last
  const errs = (x: Entry) => x.check_errors ?? (x.page_check_flags ?? -1), sugs = (x: Entry) => x.check_suggestions ?? 0;
  const order = listOrder === 'oldest' ? (a: Entry, b: Entry) => (a.age?.when || '').localeCompare(b.age?.when || '') || a.form.localeCompare(b.form)
    : listOrder === 'errors' ? (a: Entry, b: Entry) => (errs(b) - errs(a)) || (sugs(b) - sugs(a)) || a.form.localeCompare(b.form)
    : (a: Entry, b: Entry) => a.form.localeCompare(b.form);
  const groups = Object.keys(SECTIONS).map(src => {
    const items = list.filter(x => sectionOf(x) === src);
    // the top section follows the menu too (2026-10-15); "most errors first" means the most fields to look at
    items.sort(src === 'focus' && listOrder === 'errors' ? (a, b) => ((b.focus ?? 0) - (a.focus ?? 0)) || a.form.localeCompare(b.form) : order);
    return { src, items };
  }).filter(g => g.items.length);
  return (
    <select id="pick" value={bid || ''} onChange={e => openBlueprint(e.target.value)}>
      <option value="">pick a blueprint…</option>
      {groups.map(({ src, items }) => (
        <optgroup key={src} label={`${SECTIONS[src]} (${items.filter(x => x.checked?.validated).length} of ${items.length} validated)`}>
          {items.map(b => <option key={b.id} value={b.id}>{pickerText(b)}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

// the working copy (2026-10-13, Andrew: "everything should be reading from the same source"): every change goes into
// one copy of the blueprint that all the tabs read; this bar saves it over the blueprint or throws it away
function DraftBar() {
  const d = useEntry()?.draft;
  if (!d) return null;
  return (
    <span id="draftBar">
      {d.real_changed && <span className="stale" title="a loop run or an edit by hand changed the blueprint after the working copy was made">file changed on disk</span>}
      <button className="btn ok" onClick={saveDraft}
        title={'save the working copy into the blueprint\n\n' + (d.log.length ? d.log.join('\n') : 'no changes to the blueprint yet (verdicts only)')}>save ({d.changes})</button>
      <button className="btn" onClick={discardDraft} title={`throw the working copy away (made ${d.made}); verdicts and notes since then go with it`}>discard</button>
    </span>
  );
}

export function Header() {
  const { bid, listOrder, mode, notesOpen, chatOpen, helpOpen } = useApp();
  const entry = useEntry();
  const counts = useHeaderCounts();
  const [rebootLabel, setRebootLabel] = useState<string | null>(null);
  const [finding, setFinding] = useState(false);
  // the tabs on the page (groups' grab tabs, grid ids, block labels, added fields' names) hidden when they cover printed
  // text (Andrew, 2026-10-27: "sometimes the tabs ... cover important text"); remembered across reloads
  const [tabsHidden, setTabsHidden] = useState(() => store('br_hidetabs') === '1');
  useEffect(() => { document.body.classList.toggle('notabs', tabsHidden); store('br_hidetabs', tabsHidden ? '1' : '0'); }, [tabsHidden]);
  const inReview = mode === 'review' && counts.loaded;
  return (
    <header>
      <div className="brand" id="brand" title="home: every blueprint in one list" onClick={() => showHome(true)}>
        <h1>Petey<span className="dot">.</span></h1><span className="sub">Blueprint review</span>
      </div>
      <Picker />
      <label className="ctl" title="order of the form menu">
        <select id="listorder" value={listOrder} onChange={e => { store('br_listorder', e.target.value); set({ listOrder: e.target.value }); }}>
          <option value="name">by name</option><option value="oldest">oldest first</option><option value="errors">most to look at first</option>
        </select>
      </label>
      <button className={'btn' + (counts.clashOn ? ' primary' : '')} id="clashBtn" disabled={!counts.clashes}
        title={counts.clashTitle || 'fields that would share a name once saved corrections are applied (apply refuses them): click to outline each set in its own color, in Review'}
        onClick={async () => { if (get_mode() !== 'review') await setMode('review'); reviewActions.toggleClashes(); }}>
        {counts.loaded ? `clashes (${counts.clashes})` : 'clashes'}
      </button>
      <DraftBar />
      <span className="spacer" />
      {/* the form's whole-form actions in the top bar (Andrew, 2026-10-23); each opens the tab it works in */}
      <button className="btn" id="hdrFinders" disabled={!bid || finding}
        title="the whole form: the clear groups among the loose checkboxes first (Yes / No pairs, boxes under a printed 'check one' or 'check the applicable box'; new on the Groups tab, which also makes them as it opens; ungroup takes one apart), then the grid finder (a grid replaces the blocks inside it), then repeated blocks among the fields in no block and no grid (SIA), each saved as a new block type marked 'from the finder'. Opens Blocks. Keep what's right; 'not a block' on the rest"
        onClick={async () => { if (get_mode() !== 'blocks') await setMode('blocks'); setFinding(true); try { await runFinders(); } finally { setFinding(false); } }}>
        {finding ? 'running…' : 'run finders'}
      </button>
      <button className="btn" id="bulk" disabled={!bid || (inReview && !counts.settledLeft)}
        title="accept every unreviewed field that two or more witnesses back and none disputes (opens Review)"
        onClick={async () => { if (get_mode() !== 'review') await setMode('review'); reviewActions.bulkAccept(); }}>
        {inReview ? `accept settled (${counts.settledLeft})` : 'accept settled'}
      </button>
      <button className={'btn' + (tabsHidden ? ' has' : '')} id="tabsBtn" title="hide the tabs drawn on the page (group grab tabs, grid ids, block labels, added fields' names) when they cover printed text; the boxes stay clickable"
        onClick={() => setTabsHidden(!tabsHidden)}>{tabsHidden ? 'show tabs' : 'hide tabs'}</button>
      <button className="btn" id="acceptAll" disabled={!bid}
        title="TEMPORARY: accept every unreviewed field on this form at once (for the benchmark forms); undo with reset validation (opens Review)"
        onClick={async () => { if (get_mode() !== 'review') await setMode('review'); reviewActions.acceptAll(); }}>accept all</button>
      <button className="btn" id="resetV" disabled={!bid}
        title="clear every verdict on this form (accepted, flagged, notes), to check it again from scratch; the old record is kept aside (opens Review)"
        onClick={async () => { if (get_mode() !== 'review') await setMode('review'); reviewActions.resetValidation(); }}>reset validation</button>
      <a className="btn" href="/extract" title="drop filled PDFs and get their data (petey.web)">extract</a>
      <button className={'btn' + (entry?.note ? ' has' : '')} id="notesBtn" title="your notes on this form (saved as you type, shown on the home page)"
        onClick={() => set({ notesOpen: !notesOpen })}>{entry?.note ? 'notes •' : 'notes'}</button>
      <button className="btn" id="chatBtn" title="ask for batch edits to this form in plain words; it proposes, you tick and apply (one Opus call per request)"
        onClick={() => set({ chatOpen: !chatOpen })}>chat</button>
      <button className="btn" id="reboot" disabled={!!rebootLabel} title="restart the server so edited code loads (and this page, built again), then reload this page"
        onClick={() => reboot(setRebootLabel)}>{rebootLabel || 'reboot'}</button>
      <button className="btn" id="helpBtn" title="keyboard shortcuts and how this mode works"
        onClick={e => { e.stopPropagation(); set({ helpOpen: !helpOpen }); }}>help</button>
    </header>
  );
}

const get_mode = () => useApp.getState().mode;
