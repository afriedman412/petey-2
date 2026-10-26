"""Blanks the finder misses because nothing is drawn under them (2026-10-15: 62% of its misses on validated forms):
an open band below a printed line, from the line down to the next text or long horizontal rule that overlaps it, at
least MIN_GAP tall, as wide as the line's column. Measured on 83 validated non-IRS forms with a cached finder run:
recovers 26% of the text fields the finder missed (169 / 647), with 1267 new boxes of which 22% real; Jev's "is it a
field" (petey/validate/jev_is_field.py) over them keeps 30% real at 0.5 (678 boxes), 38% at 0.7. A rule for "Label:" plus open
space on its line recovered 8% at 19% precision. Suggestions for Add / remove at best; not clean enough to add.

    PYTHONPATH=. venv/bin/python eval/band_blanks.py ID ...
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from petey.validate.jev_is_field import cached_boxes  # noqa: E402

from petey.synth import boxes as B  # noqa: E402
from petey.validate import hand_review as h, page_check as pc  # noqa: E402

MIN_GAP = 16.0


def band_boxes(pg, min_gap: float = MIN_GAP) -> list[list[float]]:
    words = pg.get_text("words")
    lines = collections.defaultdict(list)
    for w in words:
        lines[(w[5], w[6])].append(w)
    L = [(min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws)) for ws in lines.values()]
    rules = []
    for d in pg.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 1 and abs(it[2].x - it[1].x) > 60:
                rules.append((min(it[1].x, it[2].x), it[1].y, max(it[1].x, it[2].x)))
            if it[0] == "re" and it[1].height < 2 and it[1].width > 60:
                rules.append((it[1].x0, it[1].y0, it[1].x1))
    W, H = pg.rect.width, pg.rect.height
    out = []
    for (x0, _y0, x1, y1) in L:
        below = ([ln[1] for ln in L if ln[1] > y1 + 1 and ln[0] < x1 + 150 and ln[2] > x0]
                 + [r[1] for r in rules if r[1] > y1 + 1 and r[0] < x1 and r[2] > x0] + [H - 30])
        nb = min(below)
        if nb - y1 >= min_gap:
            right = [ln[0] for ln in L if ln[0] > x1 + 20 and ln[1] < nb and ln[3] > y1] + [W - 30]
            out.append([x0, y1 + 1, max(min(right) - 4, x1), nb - 1])
    return out


def main() -> int:
    T = collections.Counter()
    for bid in sys.argv[1:]:
        bp = h._load(h.working_path(bid))
        blank = pc.resolve_blank(bp)
        bx = cached_boxes(blank) if blank else None
        if bx is None:
            continue
        pages = set(bp.get("source_pages") or [])
        doc = pymupdf.open(str(blank))
        fb = [b for s in bp["fields"].values() if isinstance(s, dict) and not s.get("widgets") and s.get("type") != "boolean"
              for b in pc.boxes(s)]
        missed = [f for f in fb if not any(b["page"] == f["page"] and B.overlap(b["rect"], f["rect"]) >= .5 for b in bx)]
        for pno in sorted(pages or {f["page"] for f in fb}):
            cb = band_boxes(doc[pno - 1])
            bpage = [b["rect"] for b in bx if b["page"] == pno]
            new = [c for c in cb if not any(B.overlap(c, r) >= .5 for r in bpage)]
            T["new"] += len(new)
            T["new_real"] += sum(any(B.overlap(c, f["rect"]) >= .3 for f in fb if f["page"] == pno) for c in new)
            for f in missed:
                if f["page"] == pno:
                    T["missed"] += 1
                    T["recovered"] += any(B.overlap(c, f["rect"]) >= .3 for c in cb)
    print(f"missed text fields recovered {T['recovered']}/{T['missed']}; new boxes {T['new']}, real {T['new_real']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
