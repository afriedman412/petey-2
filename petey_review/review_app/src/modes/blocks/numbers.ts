// "reset numbers" (Andrew, 2026-10-26: "a 'rename' button that resets all the fields in the box to the lowest
// possible value ... regular_corp_year_6_4 should just go back to regular_corp_year_2"; "by convention if we have _2 we
// have to have _1"): a type's positions with the same subject, suffix and part are one set, numbered 1, 2, ... in the
// type's order; a position alone in its set has no number. A number left on the end of a subject is folded in when
// the rest is another position's subject (depreciation_2 + 2 is depreciation's second). Messed-up names in bulk, so
// nothing else is kept: the old numbers go.

export interface Parts { subject: string; suffix: string; iteration: string; part: string }

export function lowestNumbers(slots: Parts[]): Parts[] {
  const subjects = new Set(slots.map(s => s.subject));
  const bare = slots.map(s => {
    const m = /^(.+?)(?:_\d+)+$/.exec(s.subject);
    return { ...s, subject: m && subjects.has(m[1]) ? m[1] : s.subject, iteration: '' };
  });
  const key = (s: Parts) => `${s.subject}|${s.suffix}|${s.part}`;
  const size: Record<string, number> = {}, seen: Record<string, number> = {};
  for (const s of bare) size[key(s)] = (size[key(s)] || 0) + 1;
  return bare.map(s => {
    const k = key(s);
    if (size[k] < 2) return s;
    seen[k] = (seen[k] || 0) + 1;
    return { ...s, iteration: String(seen[k]) };
  });
}
