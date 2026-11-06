// Audit's sidebar (the whole width; the page image hides): this form's versions and history, or the batch table of
// the forms at the top of the menu; and its bar (the view buttons).
import type { ReactNode } from 'react';
import { useApp } from '../../state/app';
import { openAudit, openInReview, setView, useAudit, type BatchData, type HistEvent, type Version } from './store';

const n = (x: unknown, d = 0) => x === null || x === undefined ? '' : (typeof x === 'number' ? x.toFixed(d) : String(x));
const pp = (x: number | null | undefined, pages: number | undefined) => x === null || x === undefined ? ''
  : <>{x} <span className="help">({(x / Math.max(1, pages || 0)).toFixed(2)}/p)</span></>;
const money = (x: number | null | undefined) => x === null || x === undefined ? '' : '$' + x.toFixed(x < 1 ? 3 : 2);
const Help = ({ children }: { children: ReactNode }) => <span className="help">{children}</span>;

function VerRows({ vs }: { vs: Version[] }) {
  const row = (label: string, f: (v: Version) => ReactNode) => <tr key={label}><th>{label}</th>{vs.map(v => <td key={v.id}>{f(v)}</td>)}</tr>;
  const pc = (v: Version) => v.page_check || ({} as NonNullable<Version['page_check']>), jv = (v: Version) => v.jev || ({} as NonNullable<Version['jev']>), rv = (v: Version) => v.review || {};
  return (
    <table><tbody>
      <tr><th></th>{vs.map(v => <th key={v.id}>{v.kind}<br /><code>{v.id}</code><br /><button className="btn" onClick={() => openInReview(v.id)}>open in Review</button></th>)}</tr>
      {row('file', v => <Help>{v.path}</Help>)}
      {row('built', v => v.build ? <>{v.build.when || ''} <Help>{v.build.classifier_model || v.build.basis || ''}</Help>{v.stable === false && <> <span className="warnc">not stable</span></>}</> : <Help>no build stamp (petey-master)</Help>)}
      {row('pages with fields', v => n(v.pages))}
      {row('fields', v => <>{v.fields} <Help>({(v.per_page || {}).fields ?? ''}/p)</Help></>)}
      {row('no text layer', v => v.no_text_pages && v.no_text_pages.length ? <span className="bad">pages {v.no_text_pages.join(', ')}</span> : <Help>none</Help>)}
      {row('page check: name flags', v => v.page_check ? pp(pc(v).name_flags, v.pages) : <Help>not run</Help>)}
      {row('page check: all flags', v => v.page_check ? <>{pp(pc(v).flags, v.pages)} <Help>{Object.entries(pc(v).problems || {}).map(([k, c]) => k + ' ' + c).join(', ')}</Help></> : '')}
      {row('page check: run', v => v.page_check ? <Help>{pc(v).model || ''} · {pc(v).when || ''} · judged {pc(v).judged}/{v.fields}</Help> : '')}
      {row('Jev below 0.3', v => v.jev ? pp(jv(v).below_03, v.pages) : <Help>not run</Help>)}
      {row('Jev below 0.5', v => v.jev ? <>{pp(jv(v).below_05, v.pages)} <Help>{jv(v).when}</Help></> : '')}
      {row('name-check errors', v => v.name_errors !== undefined ? <>{pp(v.name_errors, v.pages)}{v.name_errors_from && <> <Help>as of {v.name_errors_from}</Help></>}</> : '')}
      {row('boxes no field covers', v => v.unclaimed !== undefined ? n(v.unclaimed) : (v.unclaimed_error ? <Help>{v.unclaimed_error}</Help> : <Help>(open this version)</Help>))}
      {row('mechanical pass', v => v.mechanical ? <Help>{v.mechanical.when} · fixed {JSON.stringify(v.mechanical.fixed)}</Help> : <Help>not run</Help>)}
      {row('hand review', v => <>{rv(v).verdicts} verdicts, {rv(v).looked_at} looked at, {rv(v).flags} flagged{rv(v).checked?.validated && <> · <span className="good">VALIDATED</span></>}</>)}
      {row('corrections on fields', v => Object.entries(v.corrections || {}).map(([k, c]) => k + ' ' + c).join(', ') || <Help>none</Help>)}
    </tbody></table>
  );
}

function HistRows({ ev }: { ev: HistEvent[] }) {
  return (
    <table><tbody>
      <tr><th>when</th><th>what</th><th></th><th className="n">cost</th><th className="n">per page</th><th className="n">min/page</th></tr>
      {ev.map((e, i) => (
        <tr key={i}>
          <td><Help>{e.when}</Help></td><td><span className="kind">{e.kind}</span></td>
          <td><details><summary>{e.title}</summary><pre>{JSON.stringify(e.detail || {}, null, 1)}</pre></details></td>
          <td className="n">{money(e.cost)}</td><td className="n">{money(e.cost_per_page)}</td><td className="n">{n(e.minutes_per_page, 1)}</td>
        </tr>))}
    </tbody></table>
  );
}

function FormView() {
  const A = useAudit(s => s.A);
  if (!A) return <p className="help">Pick a form.</p>;
  return (
    <>
      <h3>{A.form}</h3><div className="help">{A.versions.length} version{A.versions.length === 1 ? '' : 's'}; the one picked is checked in full (name checks, uncovered boxes)</div>
      <h4>Versions</h4><VerRows vs={A.versions} /><h4>History ({A.history.length})</h4><HistRows ev={A.history} />
    </>
  );
}

interface Tot { pages: number; fields: number; nf: number; af: number; j3: number; ne: number; pcp: number; jp: number; nep: number }
function BatchView({ B }: { B: BatchData }) {
  const bid = useApp(s => s.bid);
  const rows = B.rows, tot: Record<string, Tot> = {};
  for (const r of rows) {
    const t = tot[r.kind!] = tot[r.kind!] || { pages: 0, fields: 0, nf: 0, af: 0, j3: 0, ne: 0, pcp: 0, jp: 0, nep: 0 };
    t.pages += r.pages || 0; t.fields += r.fields || 0;
    if (r.page_check) { t.nf += r.page_check.name_flags; t.af += r.page_check.flags; t.pcp += r.pages!; }
    if (r.jev) { t.j3 += r.jev.below_03; t.jp += r.pages!; }
    if (r.name_errors !== undefined) { t.ne += r.name_errors; t.nep += r.pages!; }
  }
  const per = (x: number, p: number) => p ? (x / p).toFixed(2) : '';
  return (
    <>
      <h3>Batch: the forms at the top of the menu</h3><div className="help">{B.why || ''}</div>
      <h4>Totals, per page (pooled over pages)</h4>
      <table><tbody>
        <tr><th>version</th><th className="n">pages</th><th className="n">fields/p</th><th className="n">page-check name flags/p</th><th className="n">all flags/p</th><th className="n">Jev &lt;0.3/p</th><th className="n">name-check errors/p</th></tr>
        {Object.entries(tot).map(([k, t]) => (
          <tr key={k}><td>{k}</td><td className="n">{t.pages}</td><td className="n">{per(t.fields, t.pages)}</td><td className="n">{per(t.nf, t.pcp)}</td><td className="n">{per(t.af, t.pcp)}</td><td className="n">{per(t.j3, t.jp)}</td><td className="n">{per(t.ne, t.nep)}</td></tr>))}
      </tbody></table>
      <h4>Every version (click a row for its audit)</h4>
      <table><tbody>
        <tr><th>form</th><th>version</th><th className="n">pages</th><th className="n">fields</th><th className="n">page-check name flags</th><th className="n">all flags</th><th className="n">Jev &lt;0.3</th><th className="n">name-check errors</th><th>text layer</th><th>review</th></tr>
        {rows.map((r, i) => r.error
          ? <tr key={i}><td>{r.form}</td><td><code>{r.id}</code></td><td colSpan={8} className="bad">{r.error}</td></tr>
          : <tr key={i} className={'click ' + (r.id === bid ? 'cur' : '')} onClick={() => openAudit(r.id)}>
            <td>{r.form}</td><td><span className="kind">{r.kind}</span></td><td className="n">{r.pages}</td><td className="n">{r.fields}</td>
            <td className="n">{r.page_check ? pp(r.page_check.name_flags, r.pages) : <Help>not run</Help>}</td>
            <td className="n">{r.page_check ? pp(r.page_check.flags, r.pages) : ''}</td>
            <td className="n">{r.jev ? pp(r.jev.below_03, r.pages) : <Help>not run</Help>}</td>
            <td className="n">{r.name_errors !== undefined ? pp(r.name_errors, r.pages) : ''}</td>
            <td>{r.no_text_pages && r.no_text_pages.length ? <span className="bad">none on p{r.no_text_pages.join(', ')}</span> : 'yes'}</td>
            <td>{r.review?.checked?.validated ? <span className="good">VALIDATED</span> : `${r.review?.verdicts || 0} verdicts`}</td>
          </tr>)}
      </tbody></table>
    </>
  );
}

export function Panel() {
  const { view, B } = useAudit();
  return <div className="aud">{view === 'batch' ? (B ? <BatchView B={B} /> : <p className="help">loading the batch…</p>) : <FormView />}</div>;
}

export function Bar() {
  const { A, view } = useAudit();
  return (
    <>
      <span className="progress" id="progress">{A && view === 'form' && <><b>{A.form}</b> · {A.versions.length} versions · {A.history.length} events</>}</span>{' '}
      <label className="help"><input type="radio" name="audv" value="form" checked={view === 'form'} onChange={() => setView('form')} /> this form</label>{' '}
      <label className="help"><input type="radio" name="audv" value="batch" checked={view === 'batch'} onChange={() => setView('batch')} /> batch (the forms at the top)</label>
    </>
  );
}
