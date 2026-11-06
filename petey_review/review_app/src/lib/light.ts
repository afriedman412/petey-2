// The light path's misses and junk on one page (the "light misses" / "light junk" layers, 2026-11-04): what the
// show layer draws and the counts the show bar gives
import type { LightLayer, MissCause } from './types';

export const CAUSE_LABEL: Record<MissCause, string> = {
  'no box': 'no box', jev: 'Jev out', 'one box': 'one box', later: 'lost later',
};
export const CAUSE_TIP: Record<MissCause, string> = {
  'no box': 'the finder proposed no box here',
  jev: "the finder's box here was screened out by Jev",
  'one box': 'a kept box covers this field and another one too',
  later: 'a kept box was here, lost after the screen',
};

export function lightOnPage(l: LightLayer | null | undefined, page: number) {
  const missed = (l?.missed || []).filter(m => m.page === page), junk = (l?.junk || []).filter(j => j.page === page);
  const byCause: Partial<Record<MissCause, number>> = {};
  missed.forEach(m => { byCause[m.cause] = (byCause[m.cause] || 0) + 1; });
  return { missed, junk, byCause };
}

/** "12: no box 7, Jev out 4, one box 1" for the show bar's title */
export function causeSummary(byCause: Partial<Record<MissCause, number>>): string {
  const n = Object.values(byCause).reduce((a, b) => a + (b || 0), 0);
  const parts = (Object.keys(CAUSE_LABEL) as MissCause[]).filter(c => byCause[c]).map(c => `${CAUSE_LABEL[c]} ${byCause[c]}`);
  return parts.length ? `${n}: ${parts.join(', ')}` : '0';
}
