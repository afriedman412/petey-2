// The frame around the tabs: the mode bar and tabs, the page buttons, the sidebar (with its "show" toggles and the
// view buttons), the help menu and the toast.
import { useEffect, useRef, useState, type KeyboardEvent as RKeyboardEvent } from 'react';
import type { ModeId } from '../lib/types';
import { store } from '../lib/util';
import { gotoPage, setMode, setZoom, toggleWide } from '../state/actions';
import { copyText } from '../lib/dnd';
import { set, useApp, useEntry, type ShowKey } from '../state/app';
import { MODES } from '../modes';

// the page's reference (file_p3) before the tab's counts, on every tab: click to copy it (Andrew, 2026-10-27)
function PageRef() {
  const { bid, page } = useApp();
  const form = useEntry()?.form || (bid || '').split('__').pop();
  if (!form) return null;
  const ref = `${form}_p${page}`;
  return <code className="fid" id="pageref" style={{ cursor: 'pointer' }} title="click to copy the page reference (file_page)" onClick={() => copyText(ref)}>{ref}</code>;
}

export function ModeBar() {
  const { mode, bid, loaded } = useApp();
  const d = MODES[mode];
  const ready = !!bid && loaded?.mode === mode && loaded.bid === bid;
  return (
    <div id="modebarRow">
      <div id="modebar"><PageRef />{ready ? <d.Bar /> : <span className="progress" id="progress" />}</div>
      <span className="tabs" id="tabs">
        {(Object.keys(MODES) as ModeId[]).map((m, i) => (
          <button key={m} className={m === mode ? 'on' : ''} title={`Shift+${i + 1}`} onClick={() => setMode(m)}>{MODES[m].name}</button>
        ))}
      </span>
    </div>
  );
}

// p7 (not validated / total) of what the tab works on (Andrew, 2026-10-22); a page with nothing left in green. Every
// page on every tab, a page with no field at all greyed (Andrew, 2026-10-27: "instead of only showing the pages that
// have the relevant fields, can you show all the pages? and can you color the pages that have NO fields differently").
// Drawn anew for each tab: each tab's useData calls its own hooks, and React wants the same hooks on every draw.
export function Pages() {
  const mode = useApp(s => s.mode);
  return <PagesOf key={mode} />;
}
function PagesOf() {
  const { mode, page, bid, loaded } = useApp();
  const d = MODES[mode];
  d.useData();
  if (!bid || loaded?.mode !== mode || loaded.bid !== bid) return <div className="pages" id="pages" />;
  return (
    <div className="pages" id="pages">
      {d.pages().map(p => {
        const lab = d.pageLabel(p.page) || `p${p.page}`;
        const done = typeof lab !== 'string' && lab.done, empty = p.fields === 0;
        return <button key={p.page} className={(p.page === page ? 'on' : '') + (done ? ' done' : '') + (empty ? ' empty' : '')}
          title={empty ? 'no fields on this page' : undefined} onClick={() => gotoPage(p.page)}>{typeof lab === 'string' ? lab : lab.text}</button>;
      })}
    </div>
  );
}

// the sidebar keeps what you type (Andrew, 2026-10-22: "'return' and 'tab' should exit a field or go to the next one
// respectively in the sidebar"): Enter leaves a box (after its own Enter action, if it has one); Tab / Shift+Tab go
// to the next / previous box in the sidebar and stay in it. React redraws a box without replacing it, so the text
// typed in it stays without the old page's guard.
const FIELD_SEL = 'input:not([type=checkbox]):not([type=radio]):not([type=button]):not([disabled]), select:not([disabled]), textarea:not([disabled])';
function sidebarKeys(e: RKeyboardEvent<HTMLElement>) {
  const el = e.target as HTMLElement, side = e.currentTarget;
  if (!el.matches || !el.matches(FIELD_SEL)) return;
  if (e.key === 'Tab') {
    e.preventDefault(); e.stopPropagation();
    const all = [...side.querySelectorAll<HTMLElement>(FIELD_SEL)].filter(x => x.offsetParent !== null);
    const i = all.indexOf(el); if (i < 0 || all.length < 2) { el.blur(); return; }
    const nx = all[(i + (e.shiftKey ? -1 : 1) + all.length) % all.length];
    nx.focus(); if (nx instanceof HTMLInputElement) nx.select();
  } else if (e.key === 'Enter' && !e.shiftKey && el.tagName !== 'TEXTAREA' && !e.nativeEvent.isComposing) {
    setTimeout(() => { if (document.activeElement === el) el.blur(); }, 0);
  }
}

function ShowBar() {
  const { show, wide, zoom } = useApp();
  const toggle = (k: ShowKey, on: boolean) => { const s = { ...show, [k]: on }; set({ show: s }); store('br_show', JSON.stringify(s)); };
  return (
    <div id="showbar">
      <span className="ctl" id="showctl" title="what the other tabs have done, drawn on the page in every tab (each tab draws its own anyway)">show
        {(['valid', 'groups', 'grids', 'blocks'] as ShowKey[]).map(k => (
          <label key={k}> <input type="checkbox" checked={!!show[k]} onChange={e => toggle(k, e.target.checked)} /> {k === 'valid' ? 'validated' : k}</label>
        ))}
      </span>
      <span className="viewbtns">
        <button className={'btn' + (wide ? ' primary' : '')} id="wideBtn" title="the sidebar at 70% of the window, or back to its width (kept for every tab)" onClick={toggleWide}>{wide ? 'narrower' : 'wider'}</button>
        <span className="ctl" id="zoomctl">
          <button className="btn" title="zoom out (-)" onClick={() => setZoom(zoom / 1.25)}>-</button>{' '}
          <button className="btn" title="zoom in (+)" onClick={() => setZoom(zoom * 1.25)}>+</button>
        </span>
      </span>
    </div>
  );
}

// the sidebar's width: drag its left edge, kept per browser (Andrew, 2026-10-13); "wider" (70% of the window) and back,
// one setting for every tab (2026-10-22)
function useWinWidth() {
  const [w, setW] = useState(window.innerWidth);
  useEffect(() => { const f = () => setW(window.innerWidth); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f); }, []);
  return w;
}

export function Sidebar() {
  const { mode, bid, loaded, loadError, wide, sideW } = useApp();
  const d = MODES[mode];
  const winW = useWinWidth();
  const grip = useRef<HTMLDivElement>(null);
  const width = wide ? Math.round(winW * 0.7) : sideW;
  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault(); grip.current?.classList.add('drag');
    const move = (ev: MouseEvent) => set({ sideW: Math.max(280, Math.min(window.innerWidth - 320, window.innerWidth - ev.clientX)), wide: false });
    const up = () => {
      grip.current?.classList.remove('drag');
      window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up);
      store('br_side_w', useApp.getState().sideW); store('br_wide', '0');
    };
    window.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
  };
  const ready = !!bid && loaded?.mode === mode && loaded.bid === bid;
  return (
    <>
      <div id="sidegrip" ref={grip} title="drag to resize the sidebar" onMouseDown={startDrag} />
      <div id="sidecol">
        <ShowBar />
        <aside id="panel" style={d.wide ? undefined : { width }} onKeyDownCapture={sidebarKeys}>
          {!bid ? <p className="help">Pick a blueprint.</p>
            : loadError ? <p className="err">{loadError}</p>
            : ready ? <d.Panel />
            : <p className="help">loading…</p>}
        </aside>
      </div>
    </>
  );
}

// the help menu (2026-10-07): every key hint lives here, not in the bars and buttons; the current tab first
const GLOBAL_KEYS: [string, string][] = [['Shift+1 / 2 / 3 / 4 / 5 / 6', 'Review / Groups / Add / remove / Grids / Blocks / Audit'], ['1-9', 'go to that page'], ['+ / -', 'zoom in / out'], ['t', 'hide / show the tabs on the page'], ['?', 'this help']];
function Keys({ rows }: { rows: [string, string][] }) {
  return <table><tbody>{rows.map(([k, d]) => (
    <tr key={k}><td>{k.split(' / ').map((x, i) => <span key={i}>{i ? ' / ' : ''}<kbd>{x}</kbd></span>)}</td><td>{d}</td></tr>))}</tbody></table>;
}
export function HelpMenu() {
  const { helpOpen, mode } = useApp();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!helpOpen) return;
    const f = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) set({ helpOpen: false }); };
    document.addEventListener('click', f);
    return () => document.removeEventListener('click', f);
  }, [helpOpen]);
  if (!helpOpen) return <div id="helpmenu" hidden />;
  const h = MODES[mode].help;
  return (
    <div id="helpmenu" ref={ref}>
      <h4>{MODES[mode].name}</h4><Keys rows={h.keys} />
      {h.tips.length > 0 && <ul className="help">{h.tips.map(t => <li key={t}>{t}</li>)}</ul>}
      <h4>Everywhere</h4><Keys rows={GLOBAL_KEYS} />
    </div>
  );
}

export function Toast() {
  const t = useApp(s => s.toast);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!t) return;
    setOn(true);
    const h = setTimeout(() => setOn(false), 4000);
    return () => clearTimeout(h);
  }, [t]);
  return <div id="toast" className={on ? 'on' : ''}>{t?.msg}</div>;
}
