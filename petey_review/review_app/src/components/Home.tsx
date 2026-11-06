// Home (2026-10-15): every blueprint in one table, sortable by any column, filtered by section / domain / stage /
// text; a row opens the form in the current tab. Sort and filters are kept per browser.
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import type { Entry } from '../lib/types';
import { openBlueprint } from '../state/actions';
import { setHome, useApp } from '../state/app';
import {
  findDups, HIDE, homeMatch, SECTION_ORDER, SECTION_SHORT, SECTIONS, sectionName, sectionOf, SHOW, STATUS_ORDER, statusOf, type Dups,
} from './home-data';
import { StatusIcons } from './StatusIcons';

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
  // flagged, "to look at" and "page check" went 2026-11-03 (Andrew: "we don't need flagged, 'to look at', 'page check' on the index")
  { k: 'groups', head: 'groups', sort: b => b.groups?.groups ?? -1, cell: b => b.groups ? b.groups.groups : '—', num: true, tip: 'option groups in the blueprint' },
  { k: 'status', head: 'status', sort: b => STATUS_ORDER[statusOf(b).k], cell: b => <StatusIcons {...statusOf(b)} />,
    tip: 'V validated (every name accepted), S structure validated (fields, kinds, groups, grids and blocks accepted); neither is generated; I ignored (the whole form set aside)' },
  { k: 'copy', head: 'unsaved', sort: b => b.draft ? b.draft.changes : -1,
    cell: b => b.draft ? <span className="pill copy" title={'working copy made ' + b.draft.made}>{b.draft.changes} change{b.draft.changes === 1 ? '' : 's'}</span> : '',
    tip: 'a working copy with changes not saved into the blueprint yet' },
  // the light path's misses on the form's tuning-set pages, junk in the tooltip (2026-11-04); sorts most first
  { k: 'light', head: 'light misses', sort: b => b.light ? b.light.missed : -1,
    cell: b => b.light ? <span title={`${b.light.missed} key fields the light path missed, ${b.light.junk} junk boxes it kept (tuning-set pages)`}>{b.light.missed}</span> : dim(),
    tip: "key fields the light path missed on the form's tuning-set pages (the page's show bar has the layers)" },
  // Andrew, 2026-11-04: "can you also add an 'added' date to the index"
  { k: 'added', head: 'added', sort: b => b.added || '', cell: b => b.added || dim(), tip: 'the day the form came into the library: downloaded (scraped and hand-picked forms), first committed (library), else the file was made' },
  { k: 'made', head: 'made', sort: b => b.age?.when || '', cell: b => <span title={b.age?.by || ''}>{b.age?.when || '—'}</span>, tip: 'when and by what the blueprint was made' },
  { k: 'notes', head: 'notes', sort: b => b.note?.text || '~', cell: b => b.note ? <span title={b.note.text + '\n\n' + b.note.updated}>{b.note.text.split('\n')[0]}</span> : '', tip: 'your note on the form' },
  { k: 'touched', head: 'last review', sort: b => b.touched || '', cell: b => b.touched ? b.touched.slice(0, 16) : dim(), tip: 'the last verdict or note' },
];

export function Home() {
  const { list, home: H, bid } = useApp();
  const q = useRef<HTMLInputElement>(null);
  const dups = useMemo(() => findDups(list), [list]);
  const ALL = useMemo(() => cols(dups), [dups]);
  const hidden = new Set(H.hidden || []);
  const COLS = ALL.filter(c => c.k === 'form' || !hidden.has(c.k));
  if (!H.on) return <div id="home" />;
  // domain: null is any, '' the forms at the top of source_pdfs
  const inSection = list.filter(b => (!H.section || sectionOf(b) === H.section) && (H.domain == null || (b.collection ?? '') === H.domain));
  const qs = H.q.trim().toLowerCase();
  // the filter menu: one kind shown, any of the validated kinds hidden (2026-11-03)
  const hide = H.hide || [];
  const rows = inSection.filter(b => homeMatch(b, H.status, dups, hide)
    && (!qs || [b.form, b.id, b.collection, b.note?.text, b.desc?.text].some(s => String(s ?? '').toLowerCase().includes(qs))));
  const col = ALL.find(c => c.k === H.sort) || ALL[1], dir = H.asc ? 1 : -1;
  const cmp = (x: string | number, y: string | number) => typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
  rows.sort((a, b) => dir * cmp(col.sort(a), col.sort(b)) || a.form.localeCompare(b.form));
  const secs = Object.keys(SECTIONS).filter(k => list.some(b => sectionOf(b) === k));
  const dn: Record<string, number> = {};
  for (const b of list) if (!H.section || sectionOf(b) === H.section) dn[b.collection ?? ''] = (dn[b.collection ?? ''] || 0) + 1;
  const doms = Object.entries(dn).sort((a, b) => a[0].localeCompare(b[0]));
  const filtered = !!(H.q || H.section || H.domain != null || H.status || hide.length);
  return (
    <div id="home">
      {/* the counts (2026-11-03: "the 'review status' dropdown can just be text"); the filter menu picks */}
      <Counts list={inSection} dups={dups} />
      <div className="hctl">
        <input id="hq" ref={q} type="text" placeholder="search form, id, description, domain, notes (/)" value={H.q}
          onChange={e => setHome({ q: e.target.value })}
          onKeyDown={e => { if (e.key === 'Escape') q.current?.blur(); else if (e.key === 'Enter' && rows.length === 1) openBlueprint(rows[0].id); }} />
        <select id="hsec" value={H.section} onChange={e => setHome({ section: e.target.value })}>
          <option value="">all sections</option>
          {secs.map(k => <option key={k} value={k}>{sectionName(k, list)} ({list.filter(b => sectionOf(b) === k).length})</option>)}
        </select>
        <select id="hdom" value={H.domain == null ? '*' : H.domain} onChange={e => setHome({ domain: e.target.value === '*' ? null : e.target.value })}>
          <option value="*">all domains</option>
          {doms.map(([d, n]) => <option key={d} value={d}>{d === '' ? '(top of source_pdfs)' : d} ({n})</option>)}
        </select>
        <Filter />
        <Columns all={ALL} hidden={hidden} />
        {filtered && <button className="btn" onClick={() => setHome({ q: '', section: '', status: '', domain: null, hide: [] })}>clear filters</button>}
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

// which columns the table shows (Andrew, 2026-10-31: "can you add a dropdown to control which columns show up on the
// index page"): a checkbox a column, kept per browser with the other home settings; the form column always shows (it
// is the link). Closes on a click outside it or Escape.
function useMenu() {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent | KeyboardEvent) => {
      const d = ref.current;
      if (d?.open && (('key' in e && e.key === 'Escape') || (!('key' in e) && !d.contains(e.target as Node)))) d.open = false;
    };
    document.addEventListener('mousedown', close); document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, []);
  return ref;
}

function Columns({ all, hidden }: { all: Col[]; hidden: Set<string> }) {
  const ref = useMenu();
  const toggle = (k: string) => setHome({ hidden: hidden.has(k) ? [...hidden].filter(x => x !== k) : [...hidden, k] });
  const n = all.filter(c => c.k !== 'form' && hidden.has(c.k)).length;
  return (
    <details className="hcols" id="hcols" ref={ref}>
      <summary className="btn">columns</summary>
      <div className="hcols-menu">
        {all.filter(c => c.k !== 'form').map(c => (
          <label key={c.k} title={c.tip}><input type="checkbox" checked={!hidden.has(c.k)} onChange={() => toggle(c.k)} /> {c.head}</label>))}
        {n > 0 && <button className="btn" onClick={() => setHome({ hidden: [] })}>show all</button>}
      </div>
    </details>
  );
}

// the counts as one line of text: every blueprint, then how many are generated (neither icon), validated (V) and
// structure validated (S); a form with both counts under both; ignored forms count only as ignored
function Counts({ list, dups }: { list: Entry[]; dups: Dups }) {
  const st = list.map(statusOf);
  const n = (f: (i: number) => boolean) => st.filter((_, i) => f(i)).length;
  const both = n(i => st[i].k === 'both');
  return (
    <div className="hcounts" id="hcounts">
      <b>{list.length}</b> blueprints: <b>{n(i => st[i].k === 'generated')}</b> generated
      · <StatusIcons v s={false} /> <b>{n(i => st[i].v && st[i].k !== 'ignored')}</b> · <StatusIcons v={false} s /> <b>{n(i => st[i].s && st[i].k !== 'ignored')}</b>
      {both > 0 && <span className="dim"> ({both} with both)</span>}
      {' '}· <StatusIcons k="ignored" v={false} s={false} /> <b>{n(i => st[i].k === 'ignored')}</b> ignored
      · <b>{list.filter(b => b.draft).length}</b> unsaved copies · <b>{list.filter(b => dups[b.id]).length}</b> possible duplicates
    </div>
  );
}

// the filter menu (2026-11-03, where the "hide" checkboxes were): show one kind, hide any of the validated kinds
// (exact: "validated" is V without S, "both" V and S) or the ignored forms. A hidden kind still shows when it is the one picked to show.
function Filter() {
  const H = useApp(s => s.home);
  const ref = useMenu();
  const hide = H.hide || [];
  const toggle = (k: string) => setHome({ hide: hide.includes(k) ? hide.filter(x => x !== k) : [...hide, k] });
  const showing = SHOW.find(([k]) => k === H.status)?.[1];
  return (
    <details className="hcols hfilter" id="hfilter" ref={ref}>
      <summary className={'btn' + (H.status || hide.length ? ' on' : '')}>{H.status ? `show: ${showing}` : 'filter'}{hide.length ? ` · ${hide.length} hidden` : ''}</summary>
      <div className="hcols-menu">
        <div className="hm-l">show</div>
        {SHOW.map(([k, t]) => (
          <label key={k}><input type="radio" name="hshow" checked={H.status === k} onChange={() => setHome({ status: k })} /> {t}</label>))}
        <div className="hm-l">hide</div>
        {HIDE.map(([k, t]) => (
          <label key={k}><input type="checkbox" checked={hide.includes(k)} onChange={() => toggle(k)} /> {t}</label>))}
      </div>
    </details>
  );
}

/** "/" on the home page: to the search box. */
export const focusHomeSearch = () => (document.getElementById('hq') as HTMLInputElement | null)?.focus();
