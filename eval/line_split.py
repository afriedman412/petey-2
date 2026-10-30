"""One ruled line, several fields (Andrew, 2026-10-27: "single underlines that are actually multiple fields", e.g. the
pick-up table on fl__sd_1443547: one line per row under Name / Address / Phone / Relationship to child). For the light
flat path, on the boxes the is-field screen kept:

  vertical   a long text box that printed column rules cross is cut at them (no model). A comb (3+ equal cells
             <= COMB_CELL pt) stays one field, as the benchmark counts it.
  captions   otherwise, captions printed under the line, or in a header row over it (or over the stack of equal lines
             it sits in), give the columns, and Jev is asked one Noul per such line: several answers side by side?
             At >= JEV_SPLIT the line is cut where each caption starts (midway between headings floating over a
             stack, which are centred over their columns; headings with a rule over them are cell captions, cut at
             their start). AN API CALL (Andrew: "let's not forget it includes an API call"); the blueprint's authoring
             records it and `split_jev=False` in flat_light.build turns it off.

Captions that are not this line's are left out: under a box with its own caption printed at its top-left (a captioned
cell; its bottom rule's captions head the next row; a box labelled at its left has none), with a column rule running
down from the line between them (the next row's cells), a word that is the label of a line starting right after it,
a checkbox's option label or anything holding a symbol-font character (Wingdings 'q Single'), one character ('/',
comb letters), or rotated text (a diagonal watermark). A stack is climbed only through rows with no caption of their
own. A column-rule cut drops a thin end part, or one on a tinted label cell: the box hung into the next cell.

Measured 2026-10-27 in the light path on 107 forms (47 benchmark + 60 homemade fl__, pages <= 2), judged by eye since
publisher widgets draw these rows as one field: 35 lines cut at captions, about 33 rightly; 77 cut or trimmed at column
rules. On 152 lines judged by eye (64 holding several fields), column rules or Jev >= 0.6 cut 60 of the 64; most
wrong cuts are junk boxes the is-field screen kept. Jev question variants tried (a zoomed crop of the line with the
cuts drawn; a reworded question): AUC 0.88 / 0.85 vs 0.90 for this one; averaging two variants gains a little at
twice the cost. The split step's Jev calls: $0.012 for the 107 forms, ~3% of the light path's Jev spend, ~0.1 s a
form. Text widgets found vs the publisher widgets: 86.0 -> 86.4% (benchmark), 77.1 -> 77.7% (homemade); the gain is
mostly rows the widgets cannot show (fl__sd_1443547's pick-up table is now table g1, 5 rows x 4 columns). Lines with
several fields and no rule or caption (two widgets on one "Employee Name" line) are out of reach.
"""
from __future__ import annotations

import re

import pymupdf

from petey.synth import finder_addons as FA
from petey.validate import page_check as pc
from petey.validate.jev_page import LIMITS, MODEL, image_ref

MIN_W = 60.0          # pt: a box narrower than this is one field
MAX_H = 30.0          # pt: a taller box is a free-text area, not a line
COMB_CELL = 25.0      # pt: equal cells this narrow are a comb
SLIVER = 20.0         # pt: an end part this narrow is the edge of the next cell the box hangs into (dropped)
DOUBLE = 6.0          # pt: rules this close are one (a double rule)
CROSS = 0.5           # a column rule crossing at least this share of the box's height cuts it
JEV_SPLIT = 0.6       # Jev's several-answers score a captioned line is cut at (2026-10-27: 0.6-0.7 held 5 right
                      # splits, 2 wrong, 3 junk boxes the screen kept; 0.7 missed fl__sd_7919716's NAME / ADDRESS)
PER_REQUEST = 20
QUESTION = ("`page` is one page of a blank form. Some ruled lines are outlined in red, each tagged with its number at "
            "its top-left; `boxes` gives each number's pixel box and the printed captions found under the line or in a "
            "header row above it. Look at the line tagged `box.id`: does a person filling in this form write SEVERAL "
            "separate answers side by side along this one line (for example one per column under a header row such "
            "as Name / Address / Phone, or one per caption printed under the line such as City / State / ZIP)?")
CRITERIA = {"true": "Several separate answers go side by side along this line, one per column or caption.",
            "false": "One answer goes along the whole line (a name, an address, a sentence), or nothing is written on "
                     "it; captions elsewhere on the row belong to other lines."}


def _verticals(page) -> list[tuple[float, float, float]]:
    vs = []
    for d in page.get_drawings():
        for it in d.get("items") or []:
            if it[0] == "l" and abs(it[1].x - it[2].x) < 0.8 and abs(it[1].y - it[2].y) > 2:
                vs.append(((it[1].x + it[2].x) / 2, min(it[1].y, it[2].y), max(it[1].y, it[2].y)))
            elif it[0] == "re":
                r = pymupdf.Rect(it[1])
                if r.width < 1.5 and r.height > 2:
                    vs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.height > 2:
                    vs += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
    return vs


def _parts(x0: float, y0: float, x1: float, y1: float, cuts: list[float]) -> list[list[float]]:
    """Parts between the cuts; a double rule (cuts within DOUBLE) ends the part before at its first line and starts
    the next after its second."""
    rules: list[list[float]] = []
    for v in sorted(c for c in cuts if x0 + 4 < c < x1 - 4):
        if rules and v - rules[-1][1] <= DOUBLE:
            rules[-1][1] = v
        else:
            rules.append([v, v])
    ends = [x0] + [v for r in rules for v in r] + [x1]
    return [[round(a, 2), y0, round(c, 2), y1] for a, c in zip(ends[::2], ends[1::2])]


def is_comb(parts: list[list[float]]) -> bool:
    ws = [p[2] - p[0] for p in parts]
    return len(parts) >= 3 and max(ws) <= COMB_CELL and max(ws) - min(ws) <= 3


def vertical_parts(rect, verticals) -> list[list[float]]:
    """The box cut at the column rules crossing it, a thin part at either end dropped (the box hung into the next
    cell; fl__sd_3363802's label cells): several parts, or one when only the overhang went; [] when no rule crosses
    it or the cells make a comb."""
    x0, y0, x1, y1 = rect
    h = y1 - y0
    cuts = [vx for vx, a, b in verticals if x0 + 4 < vx < x1 - 4 and min(b, y1) - max(a, y0) >= CROSS * h]
    if not cuts:
        return []
    parts = _parts(x0, y0, x1, y1, cuts)
    if len(parts) >= 2 and is_comb(parts):
        return []
    while len(parts) > 1 and parts[0][2] - parts[0][0] < SLIVER:
        parts = parts[1:]
    while len(parts) > 1 and parts[-1][2] - parts[-1][0] < SLIVER:
        parts = parts[:-1]
    return [] if parts == [[x0, y0, x1, y1]] else parts


def _clusters(words: list, gap_k: float = 1.6) -> list[pymupdf.Rect]:
    out: list[pymupdf.Rect] = []
    for w in sorted(words, key=lambda w: w.x0):
        if out and w.x0 - out[-1].x1 <= gap_k * w.height:
            out[-1] = out[-1] | w
        else:
            out.append(pymupdf.Rect(w))
    return out


def _first_row(words: list, last: bool = False) -> list:
    rows: list[list] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        cy = (w.y0 + w.y1) / 2
        if rows and abs(cy - rows[-1][0]) < 0.5 * w.height:
            rows[-1][1].append(w)
        else:
            rows.append([cy, [w]])
    return rows[-1 if last else 0][1] if rows else []


def _level_words(page) -> list[tuple]:
    """(x0, y0, x1, y1, word) for words on horizontal text lines only: a diagonal watermark in the text layer
    (fl__sd_7919716's "KCG BOSSLADY SERVICES") is no caption."""
    out = []
    for b in page.get_text("rawdict").get("blocks", []):
        for ln in b.get("lines", []):
            if abs(ln.get("dir", (1, 0))[1]) > 0.05:
                continue
            cur: list = []
            for sp in ln.get("spans", []):
                for ch in sp.get("chars", []) + [None]:
                    if ch is not None and ch["c"].strip():
                        cur.append(ch)
                        continue
                    if cur:
                        r = pymupdf.Rect(cur[0]["bbox"])
                        for c in cur[1:]:
                            r |= pymupdf.Rect(c["bbox"])
                        out.append((r.x0, r.y0, r.x1, r.y1, "".join(c["c"] for c in cur)))
                        cur = []
    return out


class Page:
    """What the caption rules read off one page, computed once."""

    def __init__(self, page, marks: list):
        self.page = page
        self.words = [w for w in _level_words(page) if "___" not in w[4]]
        self.rects = [pymupdf.Rect(w[:4]) for w in self.words]
        self.strokes = FA._h_strokes(page)
        self.long = [s for s in self.strokes if s[1] - s[0] >= MIN_W]
        self.verticals = _verticals(page)
        self.fills = [pymupdf.Rect(d["rect"]) for d in page.get_drawings()
                      if d.get("fill") is not None and len(d["fill"]) >= 3 and not all(c > 0.97 for c in d["fill"][:3])
                      and pymupdf.Rect(d["rect"]).get_area() >= 40]
        self.marks = [pymupdf.Rect(m) for m in marks] + FA.glyph_square_rects(page) + FA.square_rects(page) \
            + FA.circle_rects(page)
        self.symbols = [pymupdf.Rect(ch["bbox"]) for b in page.get_text("rawdict").get("blocks", [])
                        for ln in b.get("lines", []) for sp in ln.get("spans", [])
                        if any(k in sp["font"].lower() for k in FA.SYMBOL_FONTS)
                        for ch in sp.get("chars", []) if ch["c"].strip()]

    def off_labels(self, parts: list[list[float]]) -> list[list[float]]:
        """An end part on a tinted fill the others are not on is the label cell the box hung into
        (fl__sd_3363802's green label column): dropped."""
        def tint(r):
            c = pymupdf.Point((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
            return next((i for i, f in enumerate(self.fills) if f.contains(c)), None)
        while len(parts) > 1 and tint(parts[0]) is not None and tint(parts[0]) != tint(parts[-1]):
            parts = parts[1:]
        while len(parts) > 1 and tint(parts[-1]) is not None and tint(parts[-1]) != tint(parts[0]):
            parts = parts[:-1]
        return parts

    def text(self, c) -> str:
        return " ".join(w[4] for w, r in zip(self.words, self.rects) if r.intersects(c))

    def _real(self, c) -> bool:
        t = self.text(c)
        if len(re.sub(r"[^A-Za-z0-9]", "", t)) < 2:
            return False                         # '/', a comb's letters
        if any(0 <= c.x0 - m.x1 <= 15 and m.y0 < c.y1 and m.y1 > c.y0 for m in self.marks):
            return False                         # a checkbox's option label
        if any(c.intersects(r) for r in self.symbols):
            return False                         # option labels around symbol-font boxes (Wingdings 'q Single')
        return not any(abs(s[2] - c.y1) < 4 and 0 <= s[0] - c.x1 < 12 and s[1] - s[0] >= 18 for s in self.strokes)

    def captions(self, rect) -> tuple[list[pymupdf.Rect], str | None]:
        """(caption boxes left to right, 'below' | 'header' | 'stack'), or ([], None)."""
        x0, y0, x1, y1 = rect
        inx = [r for r in self.rects if r.x0 >= x0 - 2 and r.x1 <= x1 + 2]
        # a label printed left of the box on its own line is its caption: words over its left end are another
        # line's (fl__sd_7919716: LAST under the NAME line over PRESENT ADDRESS's box)
        left_label = any(abs(r.y1 - y1) < 5 and 0 <= x0 - r.x1 < 12 for r in self.rects)
        own_cap = not left_label and any(y0 - 14 <= r.y1 <= y0 + 2 and x0 - 2 <= r.x0 <= x0 + 40 for r in self.rects)
        if not own_cap:
            cl = [c for c in _clusters(_first_row([r for r in inx if y1 - 1 < r.y0 < y1 + 12])) if self._real(c)]
            down = any(a.x1 - 1 <= vx <= b.x0 + 1 and abs(vy0 - y1) < 2.5 and vy1 - y1 >= 8
                       for a, b in zip(cl, cl[1:]) for vx, vy0, vy1 in self.verticals)
            if len(cl) >= 2 and not down:
                return cl, "below"
        top = y1                                 # the stack of equal lines this one sits in, up to its first line
        worded = lambda r: len(re.sub(r"[^A-Za-z0-9]", "", self.text(r))) >= 2
        while True:                              # never past a row with its own caption (bm__sd_7180896's cells)
            up = [s for s in self.long if abs(s[0] - x0) < 4 and abs(s[1] - x1) < 4 and top - 40 < s[2] < top - 4]
            if not up:
                break
            ny = max(s[2] for s in up)
            if any(ny < r.y0 and r.y1 < top and worded(r) for r in inx):
                break
            top = ny
        if top != y1:
            hdr, how = [r for r in inx if top - 44 < r.y1 <= top - 12], "stack"
        else:                                    # the stack's first line is cut as the rest of it is
            under = any(abs(s[0] - x0) < 4 and abs(s[1] - x1) < 4 and y1 + 4 < s[2] < y1 + 40 for s in self.long)
            hdr, how = [r for r in inx if y0 - 30 < r.y1 <= y0 + 2], "stack" if under else "header"
        cl = [c for c in _clusters(_first_row(hdr, last=True)) if self._real(c)]
        if len(cl) < 2:
            return [], None
        # headings with a rule just over them are cell captions at their column's left (bm__sd_1698411,
        # fl__sd_5163587): cut where each starts; only headings floating over the lines are centred
        top_cap = min(c.y0 for c in cl)
        if how == "stack" and any(top_cap - 6 <= s[2] <= top_cap + 1 and s[0] <= cl[0].x1 and s[1] >= cl[-1].x0
                                  for s in self.strokes):
            how = "header"
        return cl, how


def caption_parts(rect, cl: list, how: str) -> list[list[float]]:
    x0, y0, x1, y1 = rect
    cuts = [(a.x1 + b.x0) / 2 for a, b in zip(cl, cl[1:])] if how == "stack" else [c.x0 - 2 for c in cl[1:]]
    parts = _parts(x0, y0, x1, y1, cuts)
    return parts if len(parts) >= 2 else []


def plan(raw, kept: list[dict]) -> list[dict]:
    """One entry per long text box that may hold several fields: {'box', 'how', 'parts', 'captions'}; 'how' is
    'vertical' (cut now) or a caption source (cut only if Jev agrees)."""
    out = []
    doc = pymupdf.open(str(raw))
    try:
        for pno in sorted({b["page"] for b in kept}):
            on = [b for b in kept if b["page"] == pno]
            lines = [b for b in on if b.get("kind", "text") not in ("checkbox", "radio")
                     and b["rect"][2] - b["rect"][0] >= MIN_W and b["rect"][3] - b["rect"][1] <= MAX_H]
            if not lines:
                continue
            pg = Page(doc[pno - 1], [b["rect"] for b in on if b.get("kind") in ("checkbox", "radio")])
            for b in lines:
                vp = pg.off_labels(vertical_parts(b["rect"], pg.verticals))
                if vp and vp != [b["rect"]]:
                    out.append({"box": b, "how": "vertical", "parts": vp, "captions": []})
                    continue
                cl, how = pg.captions(b["rect"])
                parts = caption_parts(b["rect"], cl, how) if cl else []
                if parts:
                    out.append({"box": b, "how": how, "parts": parts, "captions": [pg.text(c) for c in cl]})
    finally:
        doc.close()
    return out


def jev_jobs(raw, plans: list[dict]) -> list[tuple]:
    """flat_light._ask_all jobs (page, body, imgs, {qid: box id}) for the captioned lines."""
    jobs = []
    asked = [p for p in plans if p["how"] != "vertical"]
    for pno in sorted({p["box"]["page"] for p in asked}):
        on = [p for p in asked if p["box"]["page"] == pno]
        for i in range(0, len(on), PER_REQUEST):
            chunk = on[i:i + PER_REQUEST]
            png, _dpi, px = pc.render(raw, pno, [{"boxes": [{"page": pno, "rect": p["box"]["rect"],
                                                             "label": p["box"]["id"]} for p in chunk]}], limits=LIMITS)
            ref = image_ref(png)
            items = [{"id": p["box"]["id"], "pixel_box": px[p["box"]["id"]], "captions": p["captions"],
                      "captions_where": "under the line" if p["how"] == "below" else "header row above"}
                     for p in chunk]
            qs = {f"s{it['id']}": {"type": "noul", "instructions": {"box": it, "question": QUESTION},
                                   "criteria": CRITERIA} for it in items}
            body = {"model": MODEL, "state": {"form": raw.stem, "page_number": pno, "page": ref, "boxes": items},
                    "questions": qs}
            jobs.append((pno, body, {ref: png}, {f"s{p['box']['id']}": p["box"]["id"] for p in chunk}))
    return jobs


def apply(boxes: list[dict], kept: list[dict], plans: list[dict], jev: dict[str, float]) -> tuple[list[dict], list[dict]]:
    """(kept with each accepted split's box replaced by its parts, the splits made). Parts take ids after every
    finder box's (int ids, as the structure finder wants), the box's kind and its screen score, and `split_from`."""
    nxt = max((int(b["id"]) for b in boxes), default=0) + 1
    by = {p["box"]["id"]: p for p in plans if p["how"] == "vertical" or jev.get(p["box"]["id"], 0) >= JEV_SPLIT}
    out, made = [], []
    for b in kept:
        p = by.get(b["id"])
        if not p:
            out.append(b)
            continue
        ids = []
        for r in p["parts"]:
            out.append({**b, "id": str(nxt), "rect": r, "split_from": b["id"]})
            ids.append(str(nxt))
            nxt += 1
        made.append({"box": b["id"], "page": b["page"], "how": p["how"], "parts": ids,
                     "jev": round(jev[b["id"]], 2) if b["id"] in jev else None, "captions": p["captions"]})
    return out, made
