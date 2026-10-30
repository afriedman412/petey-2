// The chat (form_chat.py): one conversation per form, kept in the page; each request is one Opus call that PROPOSES
// edits, the person ticks and applies them (Andrew, 2026-10-15). The Grids tab's check puts Opus's proposals here too.
import { create } from 'zustand';
import { mapi, send } from '../lib/api';
import { get as app, set as setApp } from './app';

export interface ChatEdit { field: string; edit: Record<string, any>; why?: string }
export interface ChatOut {
  reply: string; raw: string; cost_usd: number | string; errors: string[];
  edits: ChatEdit[]; groups: { name: string; type: string; fields: string[]; why?: string }[]; remove: { field: string; why?: string }[];
  confirmed?: unknown[]; request?: string;
}
export interface Turn {
  req: string; out?: ChatOut; err?: string; picked: Set<string>; applied?: boolean; applying?: boolean;
  result?: { changes: string[]; errors: string[] }; accepted?: unknown[]; refused?: { grid?: string; why: string }[]; gridPage?: number;
}
interface Conv { history: { role: string; content: string }[]; turns: Turn[] }

export const useChat = create<{ by: Record<string, Conv> }>(() => ({ by: {} }));

const conv = (bid: string): Conv => useChat.getState().by[bid] || { history: [], turns: [] };
function put(bid: string, c: Conv) { useChat.setState({ by: { ...useChat.getState().by, [bid]: { history: [...c.history], turns: [...c.turns] } } }); }
export const clearChat = (bid: string) => { const by = { ...useChat.getState().by }; delete by[bid]; useChat.setState({ by }); };

export type Item = { k: string; kind: 'edit' | 'group' | 'remove'; i: number };
export const chatItems = (out: ChatOut): Item[] => [
  ...out.edits.map((_, i) => ({ k: 'e' + i, kind: 'edit' as const, i })),
  ...out.groups.map((_, i) => ({ k: 'g' + i, kind: 'group' as const, i })),
  ...out.remove.map((_, i) => ({ k: 'r' + i, kind: 'remove' as const, i })),
];

export async function sendChat(text: string) {
  const bid = app().bid; if (!text.trim() || !bid) return;
  const c = conv(bid), turn: Turn = { req: text.trim(), picked: new Set() };
  c.history.push({ role: 'user', content: turn.req }); c.turns.push(turn); put(bid, c);
  try {
    const out: ChatOut = await send('POST', mapi('review', bid, '/chat'), { history: c.history });
    turn.out = out; turn.picked = new Set(chatItems(out).map(it => it.k));
    c.history.push({ role: 'assistant', content: out.raw });
  } catch (e) { turn.err = 'The request failed: ' + (e as Error).message; c.history.pop(); }
  put(bid, c);
}

/** Opus's proposals from a grid check, as a turn to tick (the Grids tab). */
export function addGridTurn(bid: string, req: string, gridPage: number, out: ChatOut) {
  const c = conv(bid);
  if (out.request) c.history.push({ role: 'user', content: out.request }, { role: 'assistant', content: out.raw });
  c.turns.push({ req, gridPage, out, picked: new Set(chatItems(out).map(it => it.k)) });
  put(bid, c);
  setApp({ chatOpen: true });
}

export function tick(bid: string, ti: number, k: string, on: boolean) {
  const c = conv(bid), t = c.turns[ti];
  const picked = new Set(t.picked); if (on) picked.add(k); else picked.delete(k);
  c.turns[ti] = { ...t, picked }; put(bid, c);
}

export async function applyChat(ti: number, after: (out: any) => Promise<void>, toast: (m: string) => void) {
  const bid = app().bid; if (!bid) return;
  const c = conv(bid), t = c.turns[ti]; if (!t || !t.out || t.applied) return;
  const pick = <T,>(arr: T[], p: string) => arr.filter((_, i) => t.picked.has(p + i));
  const body = {
    edits: pick(t.out.edits, 'e'), groups: pick(t.out.groups, 'g'), remove: pick(t.out.remove, 'r'),
    ...(t.gridPage ? { grid_page: t.gridPage, confirmed: t.out.confirmed || [] } : {}),
  };
  if (!body.edits.length && !body.groups.length && !body.remove.length) { toast('Nothing ticked.'); return; }
  c.turns[ti] = { ...t, applying: true }; put(bid, c);
  try {
    const out = await send('POST', mapi('review', bid, '/chat_apply'), body);
    const c2 = conv(bid);
    c2.turns[ti] = { ...c2.turns[ti], applying: false, applied: true, result: out, refused: out.refused || [],
      ...((out.accepted || []).length ? { accepted: out.accepted } : {}) };
    put(bid, c2);
    await after(out);
    toast(`Chat: ${out.changes.length} change(s) went into the working copy${out.errors.length ? `; ${out.errors.length} not applied` : ''}. Save as usual.`);
  } catch (e) {
    const c2 = conv(bid); c2.turns[ti] = { ...c2.turns[ti], applying: false }; put(bid, c2);
    alert('Apply failed: ' + (e as Error).message);
  }
}
