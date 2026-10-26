// Home (2026-10-15): every blueprint in one table, sortable by any column, filtered by section / domain / stage /
// text; a row opens the form in the current tab. Sort and filters are kept per browser.
import { useMemo, useRef, type ReactNode } from 'react';
import type { Entry } from '../lib/types';
import { openBlueprint } from '../state/actions';
import { setHome, useApp } from '../state/app';
import {
  findDups, homeMatch, HSTAGES, SECTION_ORDER, SECTION_SHORT, SECTIONS, sectionOf, STATUS_ORDER, statusOf, type Dups,
} from './home-data';

type Col = { k: string; head: string; sort: (b: Entry) => string | number; cell: (b: Entry) => ReactNode; num?: boolean; tip?: string };
const dim = (s: string = '—') => <span className="dim">{s}</span>;

const cols = (dups: Dups): Col[] => [
  { k: 'form', head: 'form', sort: b => b.form,
    cell: b => <><a href={`#review/${encodeURIComponent(b.id)}`}>{b.form}</a><span className="fid">{b.id}</span></> },
  { k: 'desc', head: 'description', sort: b => b.desc?.text || '~',
    cell: b => b.desc ? <span title={b.desc.text + '\n\nfrom the blank: ' + b.desc.from}>{b.desc.text}</span> : dim(),
    tip: "what the form is: the blank's PDF title and subject, and the largest print on page 1 when the title is thin" },
  { k: 'dups', head: 'dups', sort: b => dups[b.id] ? dups[b.id].key : '~',
    cell: b => { const d = dups[b.id]; return d ? <span title={d.others.map(o => `${o.id} (${o.why})`).join('\n')}>{d.others.length}</span> : ''; },
    tip: 'other forms on the same blank, or with the same description once years and revision dates are left out; sorting groups them' },
  { k: 'section', head: 'section', sort: b => SECTION_ORDER[sectionOf(b)] ?? 99, cell: b => SECTION_SHORT[sectionOf(b)] || sectionOf(b) },
  { k: 'collection', head: 'domain', sort: b => b.collection ?? '~', cell: b => b.collection === '' ? dim('(top)') : (b.collection ?? '—'),
    tip: 'domain: the source_pdfs folder the blank is in' },
  { k: 'pages', head: 'pages', sort: b => b.pages ?? -1, cell: b => b.pages ?? '—', num: true },
  { k: 'fields', head: 'fields', sort: b => b.fields, cell: b => b.fields, num: true },
  { k: 'reviewed', head: 'reviewed', sort: b => b.fields ? (b.accepted + b.flagged) / b.fields : 0, num: true,
    cell: b => {
      const a = b.fields ? 100 * b.accepted / b.fields : 0, f = b.fields ? 100 * b.flagged / b.fields : 0;
      return <><span className="pbar"><i className="a" style={{ width: `${a}%` }} /><i className="f" style={{ width: `${f}%` }} /></span>{b.accepted + b.flagged}<span className="dim">/{b.fields}</span></>;
    }, tip: 'fields with a verdict (orange accepted, red flagged)' },
  { k: 'flagged', head: 'flagged', sort: b => b.flagged, cell: b => b.flagged || dim('0'), num: true },
  { k: 'queue', head: 'to look at', sort: b => b.focus ?? -1, cell: b => b.focus ?? dim(), num: true, tip: 'review-queue count (focus.json): fields to look at' },
  { k: 'check', head: 'page check', sort: b => b.check_errors ?? b.page_check_flags ?? -1, num: true, tip: 'page check: errors / suggestions',
    cell: b => b.check_errors == null ? (b.page_check_flags == null ? dim() : b.page_check_flags)
      : <>{b.check_errors}<span className="dim"> / {b.check_suggestions}</span></> },
  { k: 'groups', head: 'groups', sort: b => b.groups?.groups ?? -1, cell: b => b.groups ? b.groups.groups : '—', num: true, tip: 'option groups in the blueprint' },
  { k: 'status', head: 'stage', sort: b => STATUS_ORDER[statusOf(b).k],
    cell: b => { const s = statusOf(b), p = b.passes;
      return <span className={`pill ${s.k}`} title={p ? `cleared ${p.when}: ${(p.steps || []).join(', ')}` : 'not cleared: the automated passes have not run'}>{s.t}</span>; },
    tip: 'generated (the generation pipeline) -> cleared (the automated passes) -> validated (the manual check)' },
  { k: 'copy', head: 'unsaved', sort: b => b.draft ? b.draft.changes : -1,
    cell: b => b.draft ? <span className="pill copy" title={'working copy made ' + b.draft.made}>{b.draft.changes} change{b.draft.changes === 1 ? '' : 's'}</span> : '',
    tip: 'a working copy with changes not saved into the blueprint yet' },
  { k: 'made', head: 'made', sort: b => b.age?.when || '', cell: b => <span title={b.age?.by || ''}>{b.age?.when || '—'}</span>, tip: 'when and by what the blueprint was made' },
  { k: 'notes', head: 'notes', sort: b => b.note?.text || '~', cell: b => b.note ? <span title={b.note.text + '\n\n' + b.note.updated}>{b.note.text.split('\n')[0]}</span> : '', tip: 'your note on the form' },
  { k: 'touched', head: 'last review', sort: b => b.touched || '', cell: b => b.touched ? b.touched.slice(0, 16) : dim(), tip: 'the last verdict or note' },
];

export function Home() {
  const { list, home: H, mode, bid } = useApp();
  const q = useRef<HTMLInputElement>(null);
  const dups = useMemo(() => findDups(list), [list]);
  const COLS = useMemo(() => cols(dups), [dups]);
  if (!H.on) return <div id="home" />;
  // domain: null is any, '' the forms at the top of source_pdfs
  const inSection = list.filter(b => (!H.section || sectionOf(b) === H.section) && (H.domain == null || (b.collection ?? '') === H.domain));
  const qs = H.q.trim().toLowerCase();
  // hide validated (Andrew, 2026-10-15); the validated tile still shows them
  const rows = inSection.filter(b => homeMatch(b, H.status, dups) && !(H.hideVal && H.status !== 'validated' && statusOf(b).k === 'validated')
    && (!qs || [b.form, b.id, b.collection, b.note?.text, b.desc?.text].some(s => String(s ?? '').toLowerCase().includes(qs))));
  const col = COLS.find(c => c.k === H.sort) || COLS[1], dir = H.asc ? 1 : -1;
  const cmp = (x: string | number, y: string | number) => typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
  rows.sort((a, b) => dir * cmp(col.sort(a), col.sort(b)) || a.form.localeCompare(b.form));
  const secs = Object.keys(SECTIONS).filter(k => list.some(b => sectionOf(b) === k));
  const dn: Record<string, number> = {};
  for (const b of list) if (!H.section || sectionOf(b) === H.section) dn[b.collection ?? ''] = (dn[b.collection ?? ''] || 0) + 1;
  const doms = Object.entries(dn).sort((a, b) => a[0].localeCompare(b[0]));
  const filtered = H.q || H.section || H.domain != null || H.status;
  return (
    <div id="home">
      <div className="hstats">{HSTAGES.map(([label, tiles], i) => (
        <div className="hstage" key={i}><div className="hstage-l">{label || ' '}</div>
          <div className="hstage-t">{tiles.map(([k, t]) => (
            <div key={k} className={'hstat' + (H.status === k ? ' on' : '')} onClick={() => setHome({ status: H.status === k ? '' : k })}>
              <b>{inSection.filter(b => homeMatch(b, k, dups)).length}</b><span>{t}</span>
            </div>))}
          </div>
        </div>))}
      </div>
      <div className="hctl">
        <input id="hq" ref={q} type="text" placeholder="search form, id, description, domain, notes (/)" value={H.q}
          onChange={e => setHome({ q: e.target.value })}
          onKeyDown={e => { if (e.key === 'Escape') q.current?.blur(); else if (e.key === 'Enter' && rows.length === 1) openBlueprint(rows[0].id); }} />
        <select id="hsec" value={H.section} onChange={e => setHome({ section: e.target.value })}>
          <option value="">all sections</option>
          {secs.map(k => <option key={k} value={k}>{SECTIONS[k]} ({list.filter(b => sectionOf(b) === k).length})</option>)}
        </select>
        <select id="hdom" value={H.domain == null ? '*' : H.domain} onChange={e => setHome({ domain: e.target.value === '*' ? null : e.target.value })}>
          <option value="*">all domains</option>
          {doms.map(([d, n]) => <option key={d} value={d}>{d === '' ? '(top of source_pdfs)' : d} ({n})</option>)}
        </select>
        <label className="ctl"><input type="checkbox" checked={H.hideVal} onChange={e => setHome({ hideVal: e.target.checked })} /> hide validated</label>
        {filtered && <button className="btn" onClick={() => setHome({ q: '', section: '', status: '', domain: null })}>clear filters</button>}
        <span className="help">{rows.length} of {list.length} · click a row to open it in {mode}
          {bid && <> · <a href="#" onClick={e => { e.preventDefault(); openBlueprint(bid); }}>back to {list.find(b => b.id === bid)?.form || bid}</a></>}</span>
      </div>
      <table className="home">
        <thead><tr>{COLS.map(c => (
          <th key={c.k} title={c.tip} className={`${c.num ? 'num' : ''} ${c.k === H.sort ? 'sorted' + (H.asc ? ' asc' : '') : ''}`}
            onClick={() => H.sort === c.k ? setHome({ asc: !H.asc }) : setHome({ sort: c.k, asc: !c.num })}>{c.head}</th>))}</tr></thead>
        <tbody>{rows.map(b => (
          <tr key={b.id} className={'r' + (b.id === bid ? ' cur' : '')}
            onClick={e => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); openBlueprint(b.id); }}>
            {COLS.map(c => <td key={c.k} className={`${c.k} ${c.num ? 'num' : ''}`}>{c.cell(b)}</td>)}
          </tr>))}
        </tbody>
      </table>
    </div>
  );
}

/** "/" on the home page: to the search box. */
export const focusHomeSearch = () => (document.getElementById('hq') as HTMLInputElement | null)?.focus();
