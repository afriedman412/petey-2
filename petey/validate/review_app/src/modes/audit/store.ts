// Audit: versions and run history (run_audit). Andrew, 2026-10-14: "build a 'run audit' into the review interface,
// so you can see the run history and all the data for each form". Read only. Numbers are per page as well: forms
// differ too much in size for per-form numbers.
import { create } from 'zustand';
import { j, mapi } from '../../lib/api';
import { store } from '../../lib/util';
import { openBlueprint, setMode } from '../../state/actions';

export interface PageCheck { name_flags: number; flags: number; problems?: Record<string, number>; model?: string; when?: string; judged?: number }
export interface Jev { below_03: number; below_05: number; when?: string }
export interface ReviewSum { verdicts?: number; looked_at?: number; flags?: number; checked?: { validated?: boolean } | null }
export interface Version {
  id: string; kind: string; path: string; pages: number; fields: number; per_page?: { fields?: number };
  build?: { when?: string; classifier_model?: string; basis?: string } | null; stable?: boolean;
  no_text_pages?: number[]; page_check?: PageCheck | null; jev?: Jev | null;
  name_errors?: number; name_errors_from?: string; unclaimed?: number; unclaimed_error?: string;
  mechanical?: { when: string; fixed: unknown } | null; review?: ReviewSum; corrections?: Record<string, number>;
}
export interface HistEvent { when: string; kind: string; title: string; detail?: unknown; cost?: number | null; cost_per_page?: number | null; minutes_per_page?: number | null }
export interface AuditData { form: string; versions: Version[]; history: HistEvent[] }
export type BatchRow = Partial<Version> & { id: string; form: string; error?: string };
export interface BatchData { rows: BatchRow[]; why?: string }
export type View = 'form' | 'batch';

interface State { A: AuditData | null; B: BatchData | null; view: View }

export const useAudit = create<State>(() => ({ A: null, B: null, view: store('br_audit_view') === 'batch' ? 'batch' : 'form' }));
const S = useAudit.getState, put = useAudit.setState;

export async function load(bid: string) {
  const A: AuditData = await j(mapi('audit', bid));
  put({ A });
  if (S().view === 'batch' && !S().B) loadBatch();         // the batch view opened with the tab: its own data
}

async function loadBatch() {
  put({ B: null });
  let B: BatchData;
  try { B = await j('/api/audit-batch'); } catch (e) { B = { rows: [], why: 'could not load: ' + (e as Error).message }; }
  put({ B });
}

export function setView(view: View) {
  put({ view }); store('br_audit_view', view);
  if (view === 'batch' && !S().B) loadBatch();
}

/** a version opened in Review */
export async function openInReview(id: string) { await openBlueprint(id); await setMode('review'); }
/** a batch row: that form's audit */
export async function openAudit(id: string) { setView('form'); await openBlueprint(id); }

export function key(e: KeyboardEvent): boolean {
  if (e.key === 'b') { setView(S().view === 'batch' ? 'form' : 'batch'); return true; }
  return false;
}
