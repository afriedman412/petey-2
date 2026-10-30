// The review page: the old blueprint_review.html's layout, element for element (its styles depend on the ids), drawn
// by React from the stores in state/ and the tabs in modes/.
import { useEffect } from 'react';
import { Canvas } from './components/Canvas';
import { HelpMenu, ModeBar, Pages, Sidebar, Toast } from './components/Frame';
import { Header } from './components/Header';
import { focusHomeSearch, Home } from './components/Home';
import { Chat, Notes } from './components/Panels';
import { MODE_IDS } from './lib/types';
import { checkFresh, def, followLink, gotoPage, init, setMode, setZoom } from './state/actions';
import { get, set, setTabsHidden, useApp } from './state/app';

function onKey(e: KeyboardEvent) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target as HTMLInputElement | null;
  if (t && ['TEXTAREA', 'INPUT', 'SELECT'].includes(t.tagName) && t.type !== 'checkbox' && t.type !== 'radio') return;
  const { helpOpen, home, bid, zoom } = get();
  if (e.key === '?') { set({ helpOpen: !helpOpen }); e.preventDefault(); return; }
  if (e.key === 'Escape' && helpOpen) { set({ helpOpen: false }); e.preventDefault(); return; }
  if (home.on) { if (e.key === '/') { focusHomeSearch(); e.preventDefault(); } return; }
  if (e.shiftKey && /^Digit[123456]$/.test(e.code)) { setMode(MODE_IDS[+e.code.slice(5) - 1]); e.preventDefault(); return; }
  if (!bid) return;
  const d = def();
  if (e.key === '+' || e.key === '=') setZoom(zoom * 1.25);
  else if (e.key === '-') setZoom(zoom / 1.25);
  else if (/^[1-9]$/.test(e.key)) { const p = +e.key; if (d.pages().some(x => x.page === p)) gotoPage(p); }
  else if (e.key === 't') setTabsHidden(!get().tabsHidden);      // Groups' text fields moved to Shift+T (2026-10-28)
  else if (!d.key?.(e)) return;
  e.preventDefault();
}

export function App() {
  const mode = useApp(s => s.mode);
  const listError = useApp(s => s.listError);
  useEffect(() => {
    init();
    window.addEventListener('keydown', onKey);
    window.addEventListener('hashchange', followLink);         // a link followed in a page already open
    window.addEventListener('focus', checkFresh);
    const vis = () => { if (!document.hidden) checkFresh(); };
    document.addEventListener('visibilitychange', vis);
    const tick = setInterval(vis, 20000);
    return () => {
      window.removeEventListener('keydown', onKey); window.removeEventListener('hashchange', followLink);
      window.removeEventListener('focus', checkFresh); document.removeEventListener('visibilitychange', vis); clearInterval(tick);
    };
  }, []);
  useEffect(() => { document.body.classList.toggle('audit', mode === 'audit'); }, [mode]);
  return (
    <>
      <Header />
      <ModeBar />
      <Home />
      <HelpMenu />
      <main>
        <div id="left">
          <Pages />
          <Canvas />
        </div>
        {listError ? <aside id="panel"><p className="err">Could not load the blueprint list: {listError}</p></aside> : <Sidebar />}
      </main>
      <Toast />
      <Notes />
      <Chat />
    </>
  );
}
