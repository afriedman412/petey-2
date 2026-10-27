"""Block types (Andrew, 2026-10-21): "select an area to define a block type, then use that template to validate
blocks that look like it, manually or even programmatically"; one form at a time. Block groups are gone ("we can
basically ditch the entire block group concept now"): a type and its blocks carry what they did.

A block type is a template drawn once: the fields whose box has its middle inside an area, each kept as its offset
from the boxes' top left, its size and its kind (a text box, a checkbox, an option group of n boxes). An area drawn on
the Blocks tab (`draw`) is a block of an existing type when its boxes pair with the template's by place (`align`:
same kinds and sizes at the same places, within `tol`), several blocks when it holds several copies of one type,
else a new type. `detect` finds a page's copies of every type; `assign` gives a block another type by best fit
(`fit`: place, size and label), the type's boxes it lacks left empty.

Names: [block prefix]_[block iteration]_[the type's wording] (`check_block`). The type's wordings, one per position,
are confirmed by the person (`confirm`); each block's prefix and iteration are read from its names or set by hand
(`block_parts`, `set_parts`), or come from the type's label and the block's place in the type (`set_auto`). A block is
checked and validated against its confirmed type on its own (`validate_block`). Blocks are kept in the page's
order, from where they sit (`_sorted_blocks`), never the PDF's widget order.

Record: runs/hand_review/grids/<bid>.json "types": [{id (BT1), page, rect, boxes: [{code, dx, dy, w, h, kind}],
blocks: [[code or None, ...] in template order], label, auto, wordings, confirmed, parts, keep, when}].
"""
from __future__ import annotations

import collections
import re
import time
from typing import Optional

from petey.validate import grid_check as gc

TOL = 8.0                  # points: a copy's boxes sit within this of the template's places and sizes (2026-10-21,
                           # boxes paired by place: 1 pt matched 51% of kept block groups, 3 pt 72%, 8 pt 83%, flat
                           # after; I-589's blocks, validated, drift 4-6 pt: heights 16 vs 14.9, a box 6 pt over)
GROW = 0.15                # ... or this share of the template's height, when more (VA 21P-527EZ p13, 2026-10-21: a 90 pt
                           # care-payment block drawn loosely, its purpose box 30.6 pt tall in one copy, 18 in another,
                           # the amount box 13 pt higher as it shrinks)


def tol(want: list[dict]) -> float:
    """The tolerance for a template's copies: `TOL`, or `GROW` of the template's height when more."""
    rw = _rel(want) if want else []
    height = max((r[1] + w["h"] for r, w in zip(rw, want)), default=0.0)
    return max(TOL, GROW * height)


def _boxes(bp: dict) -> list[dict]:
    """Every field with one page as a box: {name, code, page, rect, kind}. An option group's box is the one around its
    boxes, and its kind counts them (a Yes / No pair is not a lone checkbox)."""
    out = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("x_petey_id") is None:
            continue
        ws = [s["widget"]] if s.get("widget") else list((s.get("widgets") or {}).values())
        pages = {w.get("page") for w in ws}
        r = gc._rect(bp, n)
        if not r or len(pages) != 1:
            continue
        kind = f"{ws[0].get('widget_type') or 'text'}x{len(ws)}"
        out.append({"name": n, "code": str(s["x_petey_id"]), "page": pages.pop(), "rect": [float(x) for x in r],
                    "kind": kind})
    return out


def _order(b: dict) -> tuple:
    return (b["page"], round(b["rect"][1] / 2), b["rect"][0])


def template(bp: dict, page: int, rect) -> dict:
    """The template for the fields inside `rect` on `page`: {boxes: [{code, name, dx, dy, w, h, kind}]}, first box at
    0, 0."""
    names = set(gc._in_area(bp, page, rect))
    bs = sorted([b for b in _boxes(bp) if b["name"] in names], key=_order)
    if len(bs) < 2:
        raise ValueError("fewer than two fields in that area")
    x0, y0 = bs[0]["rect"][0], bs[0]["rect"][1]
    return {"boxes": [{"code": b["code"], "name": b["name"], "dx": b["rect"][0] - x0, "dy": b["rect"][1] - y0,
                       "w": b["rect"][2] - b["rect"][0], "h": b["rect"][3] - b["rect"][1], "kind": b["kind"]}
                      for b in bs]}


def _fits(b: dict, t: dict, x0: float, y0: float) -> bool:
    r = b["rect"]
    return (b["kind"] == t["kind"] and abs(r[0] - x0 - t["dx"]) <= TOL and abs(r[1] - y0 - t["dy"]) <= TOL
            and abs(r[2] - r[0] - t["w"]) <= TOL and abs(r[3] - r[1] - t["h"]) <= TOL)


def find(bp: dict, tpl: dict) -> list[dict]:
    """The template's exact copies on the form, the template's own block among them: [{page, cells: [(name, code,
    position)]}] in reading order. A copy is every template box matched by one field at its offset; no field is in
    two copies (the first in reading order keeps it)."""
    boxes = sorted(_boxes(bp), key=_order)
    by_page = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    first, rest = tpl["boxes"][0], tpl["boxes"][1:]
    used, out = set(), []
    for a in boxes:
        if a["name"] in used or a["kind"] != first["kind"] or abs(a["rect"][2] - a["rect"][0] - first["w"]) > TOL \
                or abs(a["rect"][3] - a["rect"][1] - first["h"]) > TOL:
            continue
        x0, y0 = a["rect"][0], a["rect"][1]
        cells = [(a["name"], a["code"], 0)]
        for k, t in enumerate(rest, 1):
            hit = next((b for b in by_page[a["page"]] if b["name"] not in used and b["name"] != a["name"]
                        and _fits(b, t, x0, y0)), None)
            if hit is None:
                break
            cells.append((hit["name"], hit["code"], k))
        else:
            if len({c[0] for c in cells}) == len(cells):
                out.append({"page": a["page"], "cells": cells})
                used |= {c[0] for c in cells}
    return out


def _new_type_id(rec: dict) -> str:
    n = rec.setdefault("next", {}).get("BT", 1)
    rec["next"]["BT"] = n + 1
    return f"BT{n}"


def said(kind: str) -> str:
    """textx1 -> a text box; checkboxx3 -> a group of 3 checkboxes."""
    what, _, n = kind.rpartition("x")
    what = {"text": "text box", "radiobutton": "radio button", "combobox": "dropdown"}.get(what, what)
    return f"a {what}" if n == "1" else f"a group of {n} {what}es" if what.endswith("x") else f"a group of {n} {what}s"


def _rel(boxes: list[dict]) -> list[tuple]:
    """Each box's place from the top left of the boxes together (not from a first box: which box sorts first can
    change with a point of drift)."""
    x0, y0 = min(b["dx"] for b in boxes), min(b["dy"] for b in boxes)
    return [(b["dx"] - x0, b["dy"] - y0) for b in boxes]


def align(got: list[dict], want: list[dict]) -> tuple[Optional[list[int]], list[str]]:
    """(for each template box, the index of the box in `got` at its place, or None; what differs). Boxes are paired by
    place, kind and size within `TOL`, not by their order (2026-10-21, I-589 p3: boxes on one line a point or two
    apart sorted otherwise from block to block, and box 5 was compared with the template's box 4)."""
    if len(got) != len(want):
        return None, [f"{len(got)} boxes, the template {len(want)}"]
    rg, rw = _rel(got), _rel(want)
    T = tol(want)
    used, pair, out = set(), [], []
    for k, w in enumerate(want):
        cands = [(abs(rg[i][0] - rw[k][0]) + abs(rg[i][1] - rw[k][1]), i) for i, g in enumerate(got)
                 if i not in used and g["kind"] == w["kind"]]
        fit = [(d, i) for d, i in cands if abs(rg[i][0] - rw[k][0]) <= T and abs(rg[i][1] - rw[k][1]) <= T
               and abs(got[i]["w"] - w["w"]) <= T and abs(got[i]["h"] - w["h"]) <= T]
        if fit:
            i = min(fit)[1]
            used.add(i)
            pair.append(i)
            continue
        pair.append(None)
        if not cands:
            out.append(f"the template's box {k + 1} ({said(w['kind'])}) has no {said(w['kind'])[2:]} to match")
            continue
        i = min(cands)[1]
        g = got[i]
        off = [(n, a, b) for n, a, b in (("across", rg[i][0], rw[k][0]), ("down", rg[i][1], rw[k][1]),
                                         ("width", g["w"], w["w"]), ("height", g["h"], w["h"])) if abs(a - b) > T]
        out.append(f"{g.get('name') or 'a box'} sits or sizes otherwise than the template's box {k + 1}: "
                   + ", ".join(f"{n} {a:.1f} pt, the template's {b:.1f}" for n, a, b in off))
    return (pair if not out else None), out


def differs(got: list[dict], want: list[dict]) -> list[str]:
    """What keeps boxes `got` from being a copy of the template `want`: [] when they are one (`align`)."""
    return align(got, want)[1]


def _bid(b: list) -> Optional[str]:
    """A block's id: the code of its first box that is there (a block fitted to a type can lack some of its boxes)."""
    return next((c for c in b if c), None)


def _pages(bp: dict) -> dict[str, int]:
    return {b["code"]: b["page"] for b in _boxes(bp)}


def _sorted_blocks(bp: dict, blocks: list[list[str]]) -> list[list[str]]:
    """Blocks in the page's order, from where they sit, never the PDF's widget order (Andrew, 2026-10-26: "the labels
    should follow the page not the widget order"; "the widget order can be completely arbitrary": I-129S page 8 lists
    its items 3, 5, 6, 4, 7). Page by page; on a page the blocks whose spans across overlap make a column. Columns
    are read down, left column first (I-129S and I-130's items 3-4 left, 5-7 right), unless blocks in two columns
    start level, a layout in rows read across then down (IHT400 p16's declarations 1 | blank, 2 | 3). A block with no
    box on the form goes last."""
    at = {b["code"]: b for b in _boxes(bp)}
    box, rest = {}, []
    for i, b in enumerate(blocks):
        rs = [at[c] for c in b if c in at]
        if not rs:
            rest.append(i)
            continue
        box[i] = (rs[0]["page"], min(r["rect"][0] for r in rs), min(r["rect"][1] for r in rs),
                  max(r["rect"][2] for r in rs))
    out = []
    for page in sorted({x[0] for x in box.values()}):
        idx = sorted((i for i in box if box[i][0] == page), key=lambda i: box[i][1])
        cols: list[list[int]] = []
        for i in idx:                       # by left edge: a block joins the column it overlaps (2 pt slack)
            hit = [c for c in cols if any(box[i][1] < box[j][3] - 2 and box[j][1] < box[i][3] - 2 for j in c)]
            if not hit:
                cols.append([i])
                continue
            for c in hit[1:]:               # a wide block joins two columns
                hit[0] += c
                cols.remove(c)
            hit[0].append(i)
        level = lambda i: round(box[i][2] / 6)          # noqa: E731  tops within a few points start level
        rows = any(level(i) == level(j) for a, ca in enumerate(cols) for cb in cols[a + 1:] for i in ca for j in cb)
        if len(cols) == 1 or rows:
            out += sorted(idx, key=lambda i: (level(i), box[i][1]))
        else:
            out += [i for c in sorted(cols, key=lambda c: min(box[i][1] for i in c))
                    for i in sorted(c, key=lambda i: box[i][2])]
    return [blocks[i] for i in out + rest]


def resort(bid: str, bp: dict) -> list[str]:
    """Every block type's blocks put in the page's order (`_sorted_blocks`), saved when one moved: the types that
    did. For records kept in the widget order before 2026-10-26."""
    rec, moved = gc.load_set(bid), []
    for t in rec.get("types") or []:
        new = _sorted_blocks(bp, t["blocks"])
        if new != t["blocks"]:
            t["blocks"] = new
            moved.append(t["id"])
    if moved:
        gc._save_set(bid, rec)
    return moved


def _drop_blocks(rec: dict, bp: dict, codes: set) -> list[str]:
    """Blocks holding any of `codes` leave their type (one block per field): what moved."""
    said_ = []
    for t in rec.get("types") or []:
        gone = [b for b in t["blocks"] if set(b) & codes]
        if gone:
            t["blocks"] = [b for b in t["blocks"] if b not in gone]
            said_ += [f"a block of {t['id']} replaced" for _ in gone]
    return said_


def copies_in(boxes: list[dict], t: dict) -> list[list[str]]:
    """The type's copies among `boxes` (each {code, kind, rect}), paired by place as `align` pairs them: each copy
    anchored on a box like the template's top-left one, every other template box found at its offset (kind and size
    within `TOL`), no box in two copies. Each copy's codes in the template's order."""
    want, rw = t["boxes"], _rel(t["boxes"])
    T = tol(want)
    k0 = min(range(len(want)), key=lambda k: (rw[k][1], rw[k][0]))
    used, out = set(), []
    for a in sorted(boxes, key=lambda b: (b["page"], b["rect"][1], b["rect"][0])):
        w0 = want[k0]
        if a["code"] in used or a["kind"] != w0["kind"] or abs(a["rect"][2] - a["rect"][0] - w0["w"]) > T \
                or abs(a["rect"][3] - a["rect"][1] - w0["h"]) > T:
            continue
        ox, oy = a["rect"][0] - rw[k0][0], a["rect"][1] - rw[k0][1]
        got, taken = [], {a["code"]}
        for k, w in enumerate(want):
            if k == k0:
                got.append(a["code"])
                continue
            fit = [(abs(b["rect"][0] - ox - rw[k][0]) + abs(b["rect"][1] - oy - rw[k][1]), b["code"]) for b in boxes
                   if b["code"] not in used and b["code"] not in taken and b["page"] == a["page"] and b["kind"] == w["kind"]
                   and abs(b["rect"][0] - ox - rw[k][0]) <= T and abs(b["rect"][1] - oy - rw[k][1]) <= T
                   and abs(b["rect"][2] - b["rect"][0] - w["w"]) <= T and abs(b["rect"][3] - b["rect"][1] - w["h"]) <= T]
            if not fit:
                break
            got.append(min(fit)[1])
            taken.add(got[-1])
        else:
            out.append(got)
            used |= set(got)
    return out


def draw(bid: str, bp: dict, page: int, rect) -> dict:
    """An area drawn on the Blocks tab (Andrew, 2026-10-21: "drag to create a block type from a new set of fields (it
    should auto-detect existing block types though)"). Its fields are a block: of an existing type when they are an
    exact copy of its template; several blocks when they are copies of one type that between them cover the area
    (VA 21P-527EZ p8: an area round four dates of BT1); else a new type whose template they are, with the closest
    existing type and what differs said (a near copy should not pass unnoticed). A field in another block leaves it
    (one block per field).
    {type, new, block: its number in the type, of, closest, left}."""
    got = template(bp, page, rect)["boxes"]
    codes = [g["code"] for g in got]
    rec = gc.load_set(bid)
    rec.setdefault("types", [])
    same = next(((t, b) for t in rec["types"] for b in t["blocks"] if set(b) == set(codes)), None)
    if same:
        same, b = same
        return {"type": same["id"], "new": False, "block": same["blocks"].index(b) + 1, "of": len(same["blocks"]),
                "code": _bid(b),
                "closest": None, "left": [], "already": True}
    match, closest = None, None
    for t in rec["types"]:
        pair, d = align(got, t["boxes"])
        if pair is not None:
            match, codes = t, [got[i]["code"] for i in pair]       # the block in the template's order
            break
        if len(got) == len(t["boxes"]) and (closest is None or len(d) < closest[1]):
            closest = (t["id"], len(d), d[0])
    if match is None:              # several copies of a type that cover the area: each a block of it (Andrew, 2026-10-21)
        inside = [x for x in _boxes(bp) if x["code"] in set(codes)]
        for t in rec["types"]:
            found = copies_in(inside, t)
            if len(found) >= 2 and {c for f in found for c in f} == set(codes):
                had = [f for f in found if any(set(f) == set(b) for b in t["blocks"])]
                fresh = [f for f in found if f not in had and not any(set(f) == set(b) for b in t["blocks"])]
                left = _drop_blocks(rec, bp, {c for f in fresh for c in f})
                t["blocks"] = _sorted_blocks(bp, t["blocks"] + fresh)
                gc._save_set(bid, rec)
                nums = [next(i for i, b in enumerate(t["blocks"], 1) if set(b) == set(f)) for f in found]
                return {"type": t["id"], "new": False, "found": len(found), "fresh": len(fresh), "blocks": nums,
                        "of": len(t["blocks"]), "closest": None, "left": left}
    left = _drop_blocks(rec, bp, set(codes))
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    new = match is None
    if new:
        match = {"id": _new_type_id(rec), "page": page, "rect": [float(x) for x in rect],
                 "boxes": [{k: x[k] for k in ("code", "dx", "dy", "w", "h", "kind")} for x in got],
                 "blocks": [], "when": now}
        rec["types"].append(match)
    match["blocks"] = _sorted_blocks(bp, match["blocks"] + [codes])
    gc._save_set(bid, rec)
    return {"type": match["id"], "new": new, "block": match["blocks"].index(codes) + 1, "of": len(match["blocks"]),
            "code": _bid(codes), "closest": {"type": closest[0], "differs": closest[2]} if new and closest else None,
            "left": left}


LABEL_TOL = 3.0           # points: a printed line starts within this of the template's, across (typeset text does not
                          # drift as drawn boxes do)
LABEL_TOL_Y = 10.0        # ... and within this down: a copy set more tightly moves its lower lines up (B 106D page 2,
                          # 2026-10-22: the middle claim's description box 26 pt tall, not 34; its lines 8 pt higher
                          # from there: 67 of 137 label words at 3 pt, 107 at 10)
LABEL_SHARE = 0.7         # this share of the words of the type's printed lines must repeat for a place to be a copy
LABEL_WORDS = 0.5         # two lines are one label when they share this share of the longer one's words (Andrew,
                          # 2026-10-22: "spouse first name and child first name are congruent")
_ENUM = re.compile(r"^[\(\[]?(\d+[a-z]?|[a-z]|[ivx]+)[\)\]\.:]?$", re.I)
_STOP = {"of", "the", "a", "an", "if", "and", "or", "in", "to", "for", "on", "at", "by", "any"}
_LINES: dict[tuple, list] = {}


def _label_word(w: str) -> Optional[str]:
    """A printed word as part of a label: lower case, a possessive dropped (spouse's -> spouse), item numbers and
    letters dropped (10e., (b), iii) and numbers inside a word made alike (Child 1 / Child 2), since copies differ just
    there; None for a word that is only that."""
    w = re.sub(r"['\u2019]s$", "", w.lower().strip(".,:;()[]"))
    if not w or _ENUM.match(w) or not re.search(r"[a-z]", w):
        return None
    return re.sub(r"\d+", "#", w)


def page_lines(blank, page: int) -> list[tuple]:
    """The page's printed lines as labels: [(words, x0, y0)], each line's words (a frozenset, `_label_word`) and
    where it starts, read once per blank and page. A line, not a word: after "Spouse's" or "Child's" the rest of the
    line sits further right or left, so only its start lines up."""
    import pymupdf
    k = (str(blank), blank.stat().st_mtime, page)
    if k not in _LINES:
        doc = pymupdf.open(str(blank))
        try:
            ws = doc[page - 1].get_text("words")
        finally:
            doc.close()
        lines: dict[tuple, list] = {}
        for w in ws:
            lines.setdefault((w[5], w[6]), []).append(w)
        out = []
        for v in lines.values():
            words = frozenset(x for x in (_label_word(w[4]) for w in v) if x)
            if words:
                out.append((words, min(w[0] for w in v), min(w[1] for w in v), max(w[2] for w in v), max(w[3] for w in v)))
        _LINES[k] = out
    return _LINES[k]


def _alike(a: frozenset, b: frozenset) -> bool:
    """Two printed lines that say the same thing of different subjects (spouse / child first name)."""
    a, b = (a - _STOP) or a, (b - _STOP) or b
    return len(a & b) >= LABEL_WORDS * max(len(a), len(b))


def _origin(t: dict, b: list, at: dict) -> Optional[tuple]:
    """A block's top left in the type's template frame, from the boxes it has (the median, so one drifted box does
    not move it)."""
    pres = [(k, at[c]) for k, c in enumerate(b) if c and c in at]
    if not pres:
        return None
    xs = sorted(x["rect"][0] - t["boxes"][k]["dx"] for k, x in pres)
    ys = sorted(x["rect"][1] - t["boxes"][k]["dy"] for k, x in pres)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def type_labels(t: dict, blank, at: dict) -> list[tuple]:
    """The type's printed labels, [(words, dx, dy)]: each line printed in its area, from the block's top left (Andrew,
    2026-10-22: "the relative location of labels is more important than the actual intended content of the field"):
    the lines whose middle is inside the area drawn for its template, else round its fullest block (20 pt above and
    left, where captions sit)."""
    tpl_codes = [x["code"] for x in t["boxes"]]
    tpl = next((b for b in t["blocks"] if b == tpl_codes), None)
    own = tpl or max(t["blocks"], key=lambda b: sum(1 for c in b if c and c in at), default=None)
    o = _origin(t, own, at) if own else None
    if o is None:
        return []
    page = next(at[c]["page"] for c in own if c and c in at)
    if tpl is not None and t.get("rect"):
        r = t["rect"]
    else:
        rs = [at[c]["rect"] for c in own if c and c in at]
        r = [min(x[0] for x in rs) - 20, min(x[1] for x in rs) - 20, max(x[2] for x in rs) + 4, max(x[3] for x in rs) + 4]
    return [(ws, x0 - o[0], y0 - o[1]) for ws, x0, y0, x1, y1 in page_lines(blank, page)
            if r[0] <= (x0 + x1) / 2 <= r[2] and r[1] <= (y0 + y1) / 2 <= r[3]]


def label_copies(t: dict, lines: list[tuple], boxes: list[dict], labs: list[tuple]) -> list[list[Optional[str]]]:
    """The type's copies among one page's `boxes`, found by its printed labels: each place where `LABEL_SHARE` of
    the words of the lines `labs` repeat, each starting where it does (within `LABEL_TOL`) and alike in words (`_alike`: half the
    words, so Spouse's First Name is Child's First Name), its boxes paired with the template's by place (same kind,
    within a quarter of the block's height or 12 pt; the size only roughly), a position with no box there left empty,
    a copy with fewer than half the boxes dropped. Measured 2026-10-22 on the saved blocks (each looked for with the
    others held): layout finds 826 of 852, labels 8 more (boxes drawn a few points off); no help to the 47 of 243 types
    with no printed words in their area (rows of a table, captioned in its header), nor to a copy that prints fewer
    labels (ACORD 80's co-applicant), which layout still finds."""
    from scipy.optimize import linear_sum_assignment
    if len(labs) < 2 or not boxes:
        return []
    def hits(ox: float, oy: float) -> int:          # words, not lines: a one-word caption (County) weighs less than
        return sum(len(ws) for ws, dx, dy in labs     # a line of five (N-336: a US address prints no county / country)
                   if any(abs(x0 - ox - dx) <= LABEL_TOL and abs(y0 - oy - dy) <= LABEL_TOL_Y and _alike(ws, pw)
                          for pw, x0, y0, _, _ in lines))
    total = sum(len(ws) for ws, _, _ in labs)
    places: list[tuple] = []
    for ws, dx, dy in labs:
        for pw, x0, y0, _, _ in lines:
            if not _alike(ws, pw):
                continue
            ox, oy = x0 - dx, y0 - dy
            if not any(abs(ox - a) <= LABEL_TOL and abs(oy - b) <= LABEL_TOL_Y for a, b in places) \
                    and hits(ox, oy) >= max(2, LABEL_SHARE * total):
                places.append((ox, oy))
    want = t["boxes"]
    height = max(w["dy"] + w["h"] for w in want) - min(w["dy"] for w in want)
    near = max(TOL, 0.25 * height, 12.0)
    out, used = [], set()
    for ox, oy in places:
        cand = [b for b in boxes if b["code"] not in used]
        if not cand:
            break
        cost = [[abs(b["rect"][0] - ox - w["dx"]) + abs(b["rect"][1] - oy - w["dy"]) if b["kind"] == w["kind"] else 1e6
                 for w in want] for b in cand]
        codes: list[Optional[str]] = [None] * len(want)
        for i, k in zip(*linear_sum_assignment(cost)):
            b, w = cand[i], want[k]
            if cost[i][k] <= near and abs(b["rect"][2] - b["rect"][0] - w["w"]) <= max(near, 0.5 * w["w"]):
                codes[k] = b["code"]
        if 2 * sum(1 for c in codes if c) >= len(want):
            out.append(codes)
            used |= {c for c in codes if c}
    return out


def detect(bid: str, bp: dict, page: int) -> dict:
    """Every block type's copies on a page added as its blocks (Andrew, 2026-10-21: "can we detect existing block types
    on a page?"); boxes already in a block are left where they are. First by layout (`copies_in`, exact copies), then
    by printed labels among the boxes left (`label_copies`, 2026-10-22), whose copies can lack a box or two.
    {found: {type: [block numbers]}, n, by_labels: {type: [block numbers]}, empty: {"BT1-3": positions empty}}."""
    from petey.validate.retype import resolve_blank
    rec = gc.load_set(bid)
    held = {c for t in rec.get("types") or [] for b in t["blocks"] for c in b}
    found, by_labels, empty = {}, {}, {}
    boxes = _boxes(bp)
    for t in rec.get("types") or []:
        free = [x for x in boxes if x["page"] == page and x["code"] not in held]
        fresh = copies_in(free, t)
        if fresh:
            held |= {c for f in fresh for c in f}
            t["blocks"] = _sorted_blocks(bp, t["blocks"] + fresh)
            found[t["id"]] = [next(i for i, b in enumerate(t["blocks"], 1) if b == f) for f in fresh]
    blank = resolve_blank(bp)
    if blank and blank.exists():
        at = {b["code"]: b for b in boxes}
        lines = page_lines(blank, page)
        for t in rec.get("types") or []:
            free = [x for x in boxes if x["page"] == page and x["code"] not in held]
            fresh = label_copies(t, lines, free, type_labels(t, blank, at))
            if fresh:
                held |= {c for f in fresh for c in f if c}
                t["blocks"] = _sorted_blocks(bp, t["blocks"] + fresh)
                nums = [next(i for i, b in enumerate(t["blocks"], 1) if b == f) for f in fresh]
                by_labels[t["id"]] = nums
                found.setdefault(t["id"], []).extend(nums)
                for n, f in zip(nums, fresh):
                    if None in f:
                        empty[f"{t['id']}-{n}"] = f.count(None)
    if found:
        gc._save_set(bid, rec)
    return {"found": found, "n": sum(len(v) for v in found.values()), "by_labels": by_labels, "empty": empty}


FIT_MAX = 1.5            # a pair scoring above this is no pair (`fit`)
STOP = {"with", "at", "of", "the", "a", "an", "to", "for", "and", "or", "in", "on", "by"}


def _same_word(a: str, b: str) -> bool:
    """One word in two spellings (2026-10-21, VA 21-686c BT7-3: resides / residence, ended / end): equal, one stem
    (grid_naming._stem), or the first 5 letters alike."""
    if a == b:
        return True
    from petey.validate import grid_naming as G
    return G._stem(a) == G._stem(b) or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])
ENDINGS = {"txt", "nm", "nbr", "cd", "amt", "dt", "ind", "qty", "cnt", "pct", "yr", "type", "rate", "name", "number", "code",
           "date", "amount"}   # a type's ending says nothing about which field it is (ACORD 80: years_at_previous_address_qty
                               # and years_with_current_employer_qty agreed on years and qty, and were paired)


def fit(bp: dict, t: dict, bs: list[dict], labels: bool = False) -> tuple[list[Optional[str]], list[str]]:
    """The block's boxes `bs` ({code, kind, rect}) paired with the type's template boxes by best fit (Andrew,
    2026-10-22: "assigning a block to a type should just overwrite the labels using the type info, by location":
    place and size only, the names not consulted; with `labels`, 2026-10-21's "cross-check box sizes or locations or
    labels to find a best fit" as it was): boxes of one kind only, each
    pair scored by place within the block and size (in units of 4 x the type's tolerance) and, twice over, by label
    (0 when the box's name ends with the position's wording, else the share of the wording's words, type endings left
    out, it lacks; a name sharing no word with any wording is not counted); the pairing with the
    least total, a pair above `FIT_MAX` dropped. ([code or None per template position], [codes left out])."""
    from scipy.optimize import linear_sum_assignment
    want, rw, T = t["boxes"], _rel(t["boxes"]), tol(t["boxes"])
    words, names = wordings(bp, t), _names(bp)
    x0, y0 = min(b["rect"][0] for b in bs), min(b["rect"][1] for b in bs)
    big = 1e6
    def content(k: int) -> list[str]:
        return [x for x in words[k].split("_") if x and x not in ENDINGS and x not in STOP] if k < len(words) else []

    def label(n: str, k: int) -> float:
        wt, nt = content(k), n.split("_")
        return 0.0 if not wt or n.endswith("_" + words[k]) else 1 - sum(any(_same_word(x, y) for y in nt) for x in wt) / len(wt)
    cost = []
    for b in bs:
        n = names.get(b["code"]) or ""
        # a name that shares no word with any of the type's wordings says nothing: place and size decide (VA 21-686c
        # BT35, 2026-10-21: a date's month / day / year boxes named school_3_dt, _2_dt, _1_dt against day, month, yr)
        says = labels and any(label(n, k) < 1 for k in range(len(want)) if b["kind"] == want[k]["kind"] and content(k))
        row = []
        for k, w in enumerate(want):
            if b["kind"] != w["kind"]:
                row.append(big)
                continue
            place = (abs(b["rect"][0] - x0 - rw[k][0]) + abs(b["rect"][1] - y0 - rw[k][1])) / (4 * T)
            size = (abs(b["rect"][2] - b["rect"][0] - w["w"]) + abs(b["rect"][3] - b["rect"][1] - w["h"])) / (4 * T)
            lab = label(n, k) if says else 0.0
            # sharing less than half the wording is another field, however well it lines up (ACORD 80: the
            # co-applicant's years_with_current_employer_qty where the applicant has years_at_previous_address_qty)
            row.append(big if lab > 0.5 else place + size + 2 * lab)
        cost.append(row)
    codes: list[Optional[str]] = [None] * len(want)
    used = set()
    for i, k in zip(*linear_sum_assignment(cost)):
        if cost[i][k] <= FIT_MAX:
            codes[k] = bs[i]["code"]
            used.add(bs[i]["code"])
    return codes, [b["code"] for b in bs if b["code"] not in used]


def assign(bid: str, bp: dict, code: str, tid: str) -> dict:
    """A block given another block type by hand (Andrew, 2026-10-21: "can we assign a block type to a block?"), a copy
    or not, its boxes paired with the type's by best fit (`fit`): the type's boxes it lacks stay empty, its boxes the
    type has no place for stay out of it. It leaves its old type (dropped when left with no blocks). {type, block,
    of, was, missing: [template positions], extra: [names]}."""
    rec = gc.load_set(bid)
    old, b = _block(rec, code)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    at = {x["code"]: x for x in _boxes(bp)}
    bs = [at[c] for c in b if c in at]
    if t is old:                     # fitted again (a block that left boxes out, VA 21-686c BT7-3, 2026-10-21): the
        held = {c for x in rec.get("types") or [] for bb in x["blocks"] for c in bb if c and bb is not b}   # boxes
        T = tol(t["boxes"])          # in and round it that no other block holds
        x0, y0 = min(x["rect"][0] for x in bs) - T, min(x["rect"][1] for x in bs) - T
        x1, y1 = max(x["rect"][2] for x in bs) + T, max(x["rect"][3] for x in bs) + T
        bs = [x for x in at.values() if x["page"] == bs[0]["page"] and x["code"] not in held
              and x0 <= (x["rect"][0] + x["rect"][2]) / 2 <= x1 and y0 <= (x["rect"][1] + x["rect"][3]) / 2 <= y1]
    codes, extra = fit(bp, t, bs)
    if sum(1 for c in codes if c) * 2 < len(t["boxes"]):
        raise ValueError(f"fewer than half of {tid}'s boxes found in the block ({sum(1 for c in codes if c)} of {len(t['boxes'])})")
    if t is old:
        i = t["blocks"].index(b)
        t["blocks"][i] = codes
        for key in ("parts", "keep"):
            if (t.get(key) or {}).get(_bid(b)) is not None and _bid(b) != _bid(codes):
                t[key][_bid(codes)] = t[key].pop(_bid(b))
        gc._save_set(bid, rec)
        names = _names(bp)
        return {"type": tid, "block": i + 1, "of": len(t["blocks"]), "was": tid, "refit": True, "code": _bid(codes),
                "missing": [k + 1 for k, c in enumerate(codes) if not c], "extra": [names.get(c) for c in extra
                                                                                   if c not in set(b)]}
    _drop_blocks(rec, bp, set(b))                    # out of its old type
    rec["types"] = [x for x in rec["types"] if x["blocks"] or x is t]
    t["blocks"] = _sorted_blocks(bp, t["blocks"] + [codes])
    gc._save_set(bid, rec)
    names = _names(bp)
    return {"type": tid, "block": t["blocks"].index(codes) + 1, "of": len(t["blocks"]), "was": old["id"],
            "code": _bid(codes), "missing": [k + 1 for k, c in enumerate(codes) if not c],
            "extra": [names.get(c) for c in extra]}


def _block(rec: dict, code: str):
    """(type, block) holding the block whose first box is `code`."""
    for t in rec.get("types") or []:
        for b in t["blocks"]:
            if _bid(b) == code:
                return t, b
    raise ValueError("no such block (drawn again since?)")


def listing(bp: dict, rec: dict, verdicts: Optional[dict] = None) -> list[dict]:
    """The form's block types for the page: [{id, label, auto, page, boxes, wordings, confirmed, blocks: [{n, code,
    page, bbox, template, names, cells, prefix, iteration, differs, kept, validated}]}], each block numbered in the
    type's order (the page's, `_sorted_blocks`), `code` its first box (how the page names it)."""
    boxes = {b["code"]: b for b in _boxes(bp)}
    names = {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    out = []
    for t in rec.get("types") or []:
        blocks, ss, parts = [], slots(bp, t), block_parts(bp, t)
        words = [slot_text(s) for s in ss]
        checks = type_checks(bp, t, rec)
        for i, b in enumerate(t["blocks"], 1):
            bs = [boxes[c] for c in b if c in boxes]
            if bs:
                chk = checks[_bid(b)]
                acc = sum((verdicts or {}).get(names.get(c), {}).get("verdict") == "accept" for c in b)
                blocks.append({"n": i, "code": _bid(b), "page": bs[0]["page"], 
                               "names": [names.get(c, c) if c else None for c in b], "differs": chk["differs"], "start": chk["start"],
                               "kept": chk["kept"], "prefix": chk["prefix"], "iteration": chk["iteration"],
                               "parts_set": parts[_bid(b)]["set"], "by": parts[_bid(b)]["by"],
                               "same_as": chk.get("same_as") or [],
                               "cells": [{"name": names.get(c, c), "rect": boxes[c]["rect"],
                                          "accepted": (verdicts or {}).get(names.get(c), {}).get("verdict") == "accept"}
                                         if c in boxes else None for c in b],
                               "validated": acc == sum(1 for c in b if c),
                               "template": b == [x["code"] for x in t["boxes"]],
                               "bbox": [min(x["rect"][0] for x in bs), min(x["rect"][1] for x in bs),
                                        max(x["rect"][2] for x in bs), max(x["rect"][3] for x in bs)]})
        out.append({"id": t["id"], "label": t.get("label") or "", "auto": bool(t.get("auto")), "page": t["page"],
                    "from": t.get("from"),
                    "boxes": len(t["boxes"]),
                    "blocks": blocks, "wordings": words, "slots": ss,
                    "confirmed": t.get("confirmed")})
    return out


def remove_block(bid: str, bp: dict, code: str) -> dict:
    """A block that is no longer one: it leaves its type (a type left with no blocks is dropped). {said}."""
    rec = gc.load_set(bid)
    t, b = _block(rec, code)
    t["blocks"].remove(b)
    said_ = [f"no longer a block of {t['id']}"]
    if not t["blocks"]:
        rec["types"].remove(t)
        said_.append(f"{t['id']} dropped (no blocks left)")
    gc._save_set(bid, rec)
    return {"said": said_}


def remove_type(bid: str, tid: str) -> dict:
    """A block type dismissed with all its blocks (Andrew, 2026-10-27: "a 'cancel' button to the block type (to dismiss
    all blocks of a given type, behind a warning message)"): the fields stay as they are, names and verdicts. {said}."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid} (dropped since?)")
    rec["types"].remove(t)
    gc._save_set(bid, rec)
    n = len(t["blocks"])
    return {"said": [f"{tid} dismissed with its {n} block{'' if n == 1 else 's'}"]}


def reattach(bid: str, bp: dict) -> dict:
    """Block positions whose field is gone pointed at the field now at that spot (Andrew, 2026-10-22: "groups should
    act independently from the block logic ... creating a group shouldn't pull those fields out of the block"; a new
    group, or text boxes combined, is a new field with a new id, and the members' ids vanish from the blocks: 192
    positions on 1095-B). The spot is the type's box placed by the block's other boxes; the field is the one with a
    widget there (within the type's tolerance, the size roughly), so a group can fill several positions of one block,
    one per box it covers. Saved when anything moved. {moved, left}."""
    rec = gc.load_set(bid)
    if not rec.get("types"):
        return {"moved": 0, "left": 0}
    at = {b["code"]: b for b in _boxes(bp)}
    widgets = []                                     # (code, page, rect) of every widget, a group's each of its boxes
    for spec in (bp.get("fields") or {}).values():
        if not isinstance(spec, dict) or spec.get("x_petey_id") is None:
            continue
        for w in ([spec["widget"]] if spec.get("widget") else list((spec.get("widgets") or {}).values())):
            if w.get("rect"):
                widgets.append((str(spec["x_petey_id"]), w.get("page"), w["rect"]))
    moved = left = 0
    for t in rec["types"]:
        T = tol(t["boxes"])
        for i, b in enumerate(t["blocks"]):
            gone = [k for k, c in enumerate(b) if c and c not in at]
            if not gone:
                continue
            o = _origin(t, b, at)
            pages = {at[c]["page"] for c in b if c and c in at}
            nb = list(b)
            for k in gone:
                w = t["boxes"][k]
                hit = None
                if o is not None and len(pages) == 1:
                    x, y = o[0] + w["dx"], o[1] + w["dy"]
                    near = [(abs(r[0] - x) + abs(r[1] - y), c) for c, pg, r in widgets if pg in pages
                            and abs(r[0] - x) <= T and abs(r[1] - y) <= T
                            and abs((r[2] - r[0]) - w["w"]) <= max(T, 0.5 * w["w"])
                            and abs((r[3] - r[1]) - w["h"]) <= max(T, 0.5 * w["h"])]
                    hit = min(near)[1] if near else None
                nb[k] = hit
                moved += hit is not None
                left += hit is None
            t["blocks"][i] = nb
            _rekey(t, _bid(b), _bid(nb))
    merged = sum(merge_groups(t, bp, at) for t in rec["types"])
    if moved or left or merged:
        gc._save_set(bid, rec)
    return {"moved": moved, "left": left, "merged": merged}


def merge_groups(t: dict, bp: dict, at: Optional[dict] = None) -> int:
    """A group over several positions in EVERY block of the type made one position of the type (Andrew, 2026-10-23:
    "if you edit it in one window it should affect the other -- field names persist from group to block and v/v"):
    the position's box the one around the group's boxes, its kind the group's, its wording the group's name less the
    block's start, so the block names it, the type's matrix renames it and a rename in Groups shows there. While some
    blocks still have those boxes apart, nothing merges (the block leaves the group's name alone, `check_block`).
    Returns how many position sets merged."""
    at = at if at is not None else {b["code"]: b for b in _boxes(bp)}
    names = _names(bp)
    merged = 0
    while True:
        sets = None
        for b in t["blocks"]:
            pos: dict = collections.defaultdict(list)
            for k, c in enumerate(b):
                if c:
                    pos[c].append(k)
            mine = {tuple(v) for v in pos.values() if len(v) > 1}
            sets = mine if sets is None else sets & mine
        K = sorted(sets or [], key=lambda x: x[0])
        if not K:
            return merged
        K = list(K[0])
        k0 = K[0]
        tpl = t["blocks"][0]
        code0 = tpl[k0]
        bs = [t["boxes"][k] for k in K]
        x0, y0 = min(w["dx"] for w in bs), min(w["dy"] for w in bs)
        box = {"code": code0, "dx": x0, "dy": y0, "w": max(w["dx"] + w["w"] for w in bs) - x0,
               "h": max(w["dy"] + w["h"] for w in bs) - y0, "kind": (at.get(code0) or {}).get("kind") or bs[0]["kind"]}
        old_slots = slots(bp, t)
        _, _, rest = _read_block([names.get(c) for c in dict.fromkeys(c for c in tpl if c)])
        group_rest = dict(zip(dict.fromkeys(c for c in tpl if c), rest)).get(code0)
        drop = set(K[1:])
        keep_idx = [k for k in range(len(t["boxes"])) if k not in drop]
        new_at = {k: i for i, k in enumerate(keep_idx)}
        t["boxes"] = [box if k == k0 else t["boxes"][k] for k in keep_idx]
        t["blocks"] = [[b[k] for k in keep_idx] for b in t["blocks"]]
        if t.get("slots") or t.get("wordings"):
            ss = [slot(group_rest or names.get(code0) or "group") if k == k0 else old_slots[k] for k in keep_idx]
            t["slots"], t["wordings"] = ss, [slot_text(x) for x in ss]
        for bk, ks in list((t.get("keep") or {}).items()):
            t["keep"][bk] = sorted({new_at[k - 1] + 1 for k in ks if k - 1 in new_at})
        merged += 1


def discover(bid: str, bp: dict) -> dict:
    """The review page's "run finders" (Andrew, 2026-10-23: "both, one button"): the block types there are first
    (filled, grown, their copies found on every page: `primed`), then repeated blocks found with no type drawn
    (block_discovery.find, SIA) among the fields in no block, each pattern saved as a new block type marked `from:
    "finder (SIA)"`, its copies its blocks (a copy that has lost fields to a block keeps the rest, 3 or more); then the
    grids, settled against the blocks both ways (grid_check.listing: a grid replaces the blocks mostly inside it, as
    1095-B's rows; a grid mostly inside blocks gives way, as B 106D p2's city / state / zip across three claims).
    {primed: {filled, grew, found}, grids: [active grid ids], superseded: [blocks a grid took], types: [ids], blocks,
    fields}."""
    from petey.validate import block_discovery
    rec = gc.load_set(bid)
    rec.setdefault("types", [])
    # primed with the blocks there are (Andrew, 2026-10-23: "priming 'run finders' with the existing blocks, so that
    # creating one iteration of the intended block will push it to find other ones like it"): every type's blocks
    # filled where a position is empty, each type grown to the free fields repeating in all its blocks and its copies
    # found on every page, then filled again (a copy found by its labels can lack a box). A field in a grid counts as
    # free: the blocks come first, and the grid listing after settles which wins
    primed = {"filled": fill_blocks(bp, rec)}
    if rec["types"]:
        gc._save_set(bid, rec)
    grew, found = {}, {}
    for page in sorted({x["page"] for x in _boxes(bp)}):
        out = rescan(bid, bp, page)
        for k, v in (out.get("grew") or {}).items():
            grew.setdefault(k, []).extend(v)
        for k, v in (out.get("found") or {}).items():
            found.setdefault(k, []).extend(v)
    rec = gc.load_set(bid)
    rec.setdefault("types", [])
    more = fill_blocks(bp, rec)
    if more:
        gc._save_set(bid, rec)
        rec = gc.load_set(bid)
    primed.update(grew=grew, found=found)
    for k, v in more.items():
        primed["filled"].setdefault(k, []).extend(v)
    held = {c for t in rec["types"] for b in t["blocks"] for c in b if c}
    rec.setdefault("types", [])
    at = {b["code"]: b for b in _boxes(bp)}
    made, nb, nf = [], 0, 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for p in block_discovery.find(bp):
        copies = [[c if c and c not in held and c in at else None for c in o] for o in p["slots"]]
        copies = [o for o in copies if sum(1 for c in o if c) >= block_discovery.MIN_BOXES]
        if len(copies) < 2:
            continue
        tpl = max(copies, key=lambda o: sum(1 for c in o if c))
        # each position's box from the copy that has it, put in the template copy's frame by the copies' shift
        x0 = min(at[c]["rect"][0] for c in tpl if c)
        y0 = min(at[c]["rect"][1] for c in tpl if c)
        boxes = []
        for k in range(len(tpl)):
            src = tpl if tpl[k] else next((o for o in copies if o[k]), None)
            sx = sorted(at[a]["rect"][0] - at[b]["rect"][0] for a, b in zip(tpl, src) if a and b) if src is not tpl else [0]
            sy = sorted(at[a]["rect"][1] - at[b]["rect"][1] for a, b in zip(tpl, src) if a and b) if src is not tpl else [0]
            r = at[src[k]]["rect"]
            dx, dy = (sx[len(sx) // 2], sy[len(sy) // 2]) if sx and sy else (0, 0)
            boxes.append({"code": src[k], "dx": r[0] + dx - x0, "dy": r[1] + dy - y0, "w": r[2] - r[0], "h": r[3] - r[1],
                          "kind": at[src[k]]["kind"]})
        rs = [at[c]["rect"] for c in tpl if c]
        t = {"id": _new_type_id(rec), "page": at[next(c for c in tpl if c)]["page"],
             "rect": [min(r[0] for r in rs) - 20, min(r[1] for r in rs) - 20, max(r[2] for r in rs) + 4,
                      max(r[3] for r in rs) + 4],
             "boxes": boxes, "blocks": _sorted_blocks(bp, copies), "when": now, "from": "finder (SIA)"}
        rec["types"].append(t)
        held |= {c for o in copies for c in o if c}
        made.append(t["id"])
        nb += len(copies)
        nf += sum(1 for o in copies for c in o if c)
    if made:
        gc._save_set(bid, rec)
    # then the grids, settled against the blocks (grid_check.listing): a grid replaces the blocks lying mostly inside
    # it, and gives way to blocks it lies mostly inside
    grids = [g for g in gc.listing(bid, bp) if g["status"] == "active"]
    rec = gc.load_set(bid)
    superseded = sorted({b for e in rec.get("grids") or [] for b in e.get("supersedes") or []})
    return {"primed": primed, "grids": [g["id"] for g in grids], "superseded": superseded, "types": made, "blocks": nb,
            "fields": nf}


def _rekey(t: dict, old: Optional[str], new: Optional[str]) -> None:
    """A block's settings (parts, cancelled renames) follow it when its first box, its id, changes."""
    if old == new:
        return
    for key in ("parts", "keep"):
        v = (t.get(key) or {}).pop(old, None)
        if v is not None and new:
            t[key][new] = v


def _take(rec: dict, code: str, keep_in: Optional[list] = None) -> list[str]:
    """A field out of whatever block holds it (but `keep_in`), its position left empty; a block left with no box
    leaves its type, a type left with no blocks is dropped. What moved."""
    said_ = []
    for t in list(rec.get("types") or []):
        for i, b in enumerate(list(t["blocks"])):
            if b is keep_in or code not in b:
                continue
            was = _bid(b)
            nb = [None if c == code else c for c in b]
            if _bid(nb) is None:
                t["blocks"].remove(b)
                said_.append(f"a block of {t['id']} left empty and dropped")
            else:
                t["blocks"][t["blocks"].index(b)] = nb
                _rekey(t, was, _bid(nb))
                said_.append(f"out of {t['id']}-{i + 1}")
        if not t["blocks"]:
            rec["types"].remove(t)
            said_.append(f"{t['id']} dropped (no blocks left)")
    return said_


def add_field(bid: str, bp: dict, code: str, field: str, grow: bool = False) -> dict:
    """A field dropped on a block (Andrew, 2026-10-22: "can we drag fields on to a block to add them?" - boxes left
    out of a block were one of the big reasons for forcing blocks to types). It takes the block's empty position of
    its own kind nearest its place (place and size from the block's other boxes, no tolerance: the person put it
    there); with none free, `grow` adds a position to the type, worded from the field's name and empty in the type's
    other blocks, and without `grow` nothing changes and `grow_needed` says why. A field in another block leaves it
    (one block per field). `field` is the field's code (x_petey_id). {type, block, pos, grew, code, said} or
    {grow_needed, why}."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    at = {x["code"]: x for x in _boxes(bp)}
    f = at.get(str(field))
    if f is None:
        raise ValueError("that field has no box on one page, so it can't be part of a block")
    if str(field) in b:
        return {"type": t["id"], "block": t["blocks"].index(b) + 1, "pos": b.index(str(field)) + 1, "grew": False,
                "code": _bid(b), "said": ["already in this block"]}
    present = [(k, at[c]) for k, c in enumerate(b) if c and c in at]
    if not present:
        raise ValueError("the block has no boxes left to place the field by")
    if f["page"] != present[0][1]["page"]:
        raise ValueError("the field is on another page than the block")
    want = t["boxes"]
    ox = sorted(x["rect"][0] - want[k]["dx"] for k, x in present)[len(present) // 2]    # the block's top left in the
    oy = sorted(x["rect"][1] - want[k]["dy"] for k, x in present)[len(present) // 2]    # template's frame
    w_, h_ = f["rect"][2] - f["rect"][0], f["rect"][3] - f["rect"][1]
    free = [(abs(f["rect"][0] - ox - want[k]["dx"]) + abs(f["rect"][1] - oy - want[k]["dy"])
             + abs(w_ - want[k]["w"]) + abs(h_ - want[k]["h"]), k)
            for k, c in enumerate(b) if c is None and want[k]["kind"] == f["kind"]]
    if not free and not grow:
        empty = [k + 1 for k, c in enumerate(b) if c is None]
        why = (f"no empty position for {said(f['kind'])}" + (f" (empty: {', '.join(map(str, empty))}, other kinds)"
                                                              if empty else " (every position is filled)"))
        return {"grow_needed": True, "why": why, "type": t["id"]}
    was = _bid(b)
    said_ = _take(rec, str(field), keep_in=b)
    names = _names(bp)
    if free:
        d, k = min(free)
        nb = list(b)
        nb[k] = str(field)
        grew = False
    else:                                # a new position for the type, empty in its other blocks
        ss = slots(bp, t)                # the positions' parts as they stand, before the type changes
        k = len(want)
        want.append({"code": str(field), "dx": f["rect"][0] - ox, "dy": f["rect"][1] - oy, "w": w_, "h": h_,
                     "kind": f["kind"]})
        _, _, rest = _read_block([names.get(c) for c in b] + [names.get(str(field))])
        ss.append(slot(rest[-1] or names.get(str(field)) or f"position_{k + 1}"))
        if t.get("slots") or t.get("wordings"):
            t["slots"], t["wordings"] = ss, [slot_text(s) for s in ss]
        t["blocks"] = [x + [None] for x in t["blocks"]]
        b = t["blocks"][[_bid(x) for x in t["blocks"]].index(was)]
        nb = b[:-1] + [str(field)]
        grew = True
    i = t["blocks"].index(b)
    t["blocks"][i] = nb
    _rekey(t, was, _bid(nb))
    gc._save_set(bid, rec)
    said_.insert(0, f"{names.get(str(field), field)} in {t['id']}-{i + 1} at position {k + 1}"
                 + (" (a new position of the type)" if grew else ""))
    return {"type": t["id"], "block": i + 1, "pos": k + 1, "grew": grew, "code": _bid(nb), "said": said_}


SIZE_TOL = TOL            # points: a box's copy in another block is its size within this (place within `tol`); 3 pt
                          # until 2026-10-23, when B 106D p3's "part / line" box, 17 pt tall in the first row and 11 in
                          # the rest, kept BT4 from growing to it; finding copies already allowed TOL
BAND_UP = 12.0            # points: a block's band starts this far above its top (a first line set a little higher)


def _frame_at(t: dict, b: list, at: dict) -> Optional[tuple]:
    """(page, x, y): where the block's template frame sits, from its boxes there (the median, as `add_field` does)."""
    present = [(k, at[c]) for k, c in enumerate(b) if c and c in at]
    if not present:
        return None
    want = t["boxes"]
    ox = sorted(x["rect"][0] - want[k]["dx"] for k, x in present)[len(present) // 2]
    oy = sorted(x["rect"][1] - want[k]["dy"] for k, x in present)[len(present) // 2]
    return present[0][1]["page"], ox, oy


def grow_type(bp: dict, rec: dict, t: dict, page: int) -> list[str]:
    """`t` takes in the fields in no block that sit at one place in EVERY block of it (Andrew, 2026-10-22: "we should
    be able to rescan a page to allow blocks to reform"; VA 21P-534EZ p13's children: the old block group held 4 of
    each child's boxes, the rest in grids since cancelled). Candidates are the free fields in the band of a block on
    `page` (from just above its top to the top of the type's next block on the page); one joins when every block of the
    type, on any page, has a free field of its kind and size at the same place in its own frame (`tol`). Each is a
    new position, worded from its name, filled in every block. The names added in the reference block."""
    at = {x["code"]: x for x in _boxes(bp)}
    held = {c for y in rec.get("types") or [] for b in y["blocks"] for c in b if c}
    org = [(b, _frame_at(t, b, at)) for b in t["blocks"]]
    org = [(b, o) for b, o in org if o]
    if len(org) < 2:
        return []
    tl = tol(t["boxes"])
    here = sorted((o for o in org if o[1][0] == page), key=lambda o: o[1][2])
    free = [x for x in at.values() if x["code"] not in held]
    added, names = [], _names(bp)
    for i, (b, (pg, ox, oy)) in enumerate(here[:-1]):
        top = min(at[c]["rect"][1] for c in b if c and c in at) - BAND_UP
        nxt = min(at[c]["rect"][1] for c in here[i + 1][0] if c and c in at) - BAND_UP
        for f in sorted((x for x in free if x["page"] == pg and top <= x["rect"][1] < nxt), key=_order):
            if f["code"] in held:
                continue
            dx, dy = f["rect"][0] - ox, f["rect"][1] - oy
            w, h = f["rect"][2] - f["rect"][0], f["rect"][3] - f["rect"][1]
            row = {}
            for b2, (pg2, ox2, oy2) in org:
                if b2 is b:
                    row[id(b2)] = f["code"]
                    continue
                cands = [x for x in free if x["page"] == pg2 and x["code"] not in held and x["kind"] == f["kind"]
                         and abs(x["rect"][0] - ox2 - dx) <= tl and abs(x["rect"][1] - oy2 - dy) <= tl
                         and abs(x["rect"][2] - x["rect"][0] - w) <= SIZE_TOL and abs(x["rect"][3] - x["rect"][1] - h) <= SIZE_TOL]
                if not cands:
                    break
                row[id(b2)] = min(cands, key=lambda x: abs(x["rect"][0] - ox2 - dx) + abs(x["rect"][1] - oy2 - dy))["code"]
            else:
                if len(set(row.values())) < len(row):
                    continue
                ss = slots(bp, t)                # the positions' parts as they stand, before the type changes
                t["boxes"].append({"code": f["code"], "dx": dx, "dy": dy, "w": w, "h": h, "kind": f["kind"]})
                _, _, rest = _read_block([names.get(c) for c in b] + [names.get(f["code"])])
                ss.append(slot(rest[-1] or names.get(f["code"]) or f"position_{len(ss) + 1}"))
                if t.get("slots") or t.get("wordings"):
                    t["slots"], t["wordings"] = ss, [slot_text(x) for x in ss]
                for b2, _o in org:
                    b2.append(row[id(b2)])
                for b2 in t["blocks"]:           # a block with no frame (no box found) gets an empty place
                    if len(b2) < len(t["boxes"]):
                        b2.append(None)
                held |= set(row.values())
                added.append(names.get(f["code"], f["code"]))
    if added:
        _reorder(t)
    return added


def fill_blocks(bp: dict, rec: dict) -> dict:
    """Each block's empty positions filled with the free field at its place (Andrew, 2026-10-23: B 106D p2's claims 3-5
    without their city / state / zip, held by a grid when the claims were found): the field in no block, of the
    position's kind, within `tol` of where the position sits in the block's frame and its size within `SIZE_TOL`; a
    field in a grid counts as free (blocks first, the grid then gives way: grid_check.listing). {"BT1-3": [names]}."""
    at = {x["code"]: x for x in _boxes(bp)}
    names = _names(bp)
    held = {c for y in rec.get("types") or [] for b in y["blocks"] for c in b if c}
    got: dict[str, list] = {}
    for t in rec.get("types") or []:
        tl = tol(t["boxes"])
        for i, b in enumerate(t["blocks"], 1):
            if all(b[k] for k in range(min(len(b), len(t["boxes"])))) and len(b) >= len(t["boxes"]):
                continue
            fr = _frame_at(t, b, at)
            if not fr:
                continue
            pg, ox, oy = fr
            while len(b) < len(t["boxes"]):
                b.append(None)
            for k, want in enumerate(t["boxes"]):
                if b[k]:
                    continue
                cands = [x for x in at.values() if x["page"] == pg and x["code"] not in held and x["kind"] == want["kind"]
                         and abs(x["rect"][0] - ox - want["dx"]) <= tl and abs(x["rect"][1] - oy - want["dy"]) <= tl
                         and abs(x["rect"][2] - x["rect"][0] - want["w"]) <= SIZE_TOL
                         and abs(x["rect"][3] - x["rect"][1] - want["h"]) <= SIZE_TOL]
                if not cands:
                    continue
                f = min(cands, key=lambda x: abs(x["rect"][0] - ox - want["dx"]) + abs(x["rect"][1] - oy - want["dy"]))
                was = _bid(b)
                b[k] = f["code"]
                held.add(f["code"])
                if was != _bid(b):
                    _rekey(t, was, _bid(b))
                got.setdefault(f"{t['id']}-{i}", []).append(names.get(f["code"], f["code"]))
    return got


def _reorder(t: dict) -> None:
    """The type's positions in reading order (top, then left, in its frame), after positions were added at its end; a
    block's settings follow it when its first box, its id, changes (`_rekey`), and cancelled renames their position."""
    bx = t["boxes"]
    order = sorted(range(len(bx)), key=lambda k: (round(bx[k]["dy"] / 4), bx[k]["dx"]))
    if order == list(range(len(bx))):
        return
    new_pos = {old + 1: new + 1 for new, old in enumerate(order)}
    old_ids = [_bid(b) for b in t["blocks"]]
    t["boxes"] = [bx[k] for k in order]
    t["blocks"] = [[b[k] if k < len(b) else None for k in order] for b in t["blocks"]]
    for key in ("slots", "wordings"):
        if t.get(key) and len(t[key]) == len(order):
            t[key] = [t[key][k] for k in order]
    for code, ps in (t.get("keep") or {}).items():
        t["keep"][code] = sorted(new_pos.get(x, x) for x in ps)
    for was, b in zip(old_ids, t["blocks"]):
        _rekey(t, was, _bid(b))


def rescan(bid: str, bp: dict, page: int) -> dict:
    """The Blocks tab's "rescan this page": every block type with a block on the page grows to the free fields that
    repeat in all its blocks (`grow_type`), then the types' copies are looked for again (`detect`). {grew: {type:
    [names added]}, **detect's answer}."""
    rec = gc.load_set(bid)
    grew = {}
    for t in rec.get("types") or []:
        if any(_frame_at(t, b, {x["code"]: x for x in _boxes(bp)}) and any(
                c and c in {x["code"] for x in _boxes(bp) if x["page"] == page} for c in b) for b in t["blocks"]):
            got = grow_type(bp, rec, t, page)
            if got:
                grew[t["id"]] = got
    if grew:
        gc._save_set(bid, rec)
    return {"grew": grew, **detect(bid, bp, page)}


def _suffix_votes(names: list[str]) -> Optional[str]:
    """The longest ending (whole words) more than half of `names` share; None when there is none."""
    toks = [n.split("_") for n in names if n]
    for L in range(max((len(t) for t in toks), default=0) - 1, 0, -1):     # a word left for the block's own start
        cnt = collections.Counter(tuple(t[-L:]) for t in toks if len(t) > L)
        if cnt:
            suf, k = cnt.most_common(1)[0]
            if 2 * k > len(toks):
                return "_".join(suf)
    return None


def _common_start(names: list[str]) -> list[str]:
    toks = [n.split("_") for n in names if n]
    out = []
    for parts in zip(*toks):
        if len(set(parts)) > 1:
            break
        out.append(parts[0])
    return out


def block_start(names: list[str]) -> str:
    """A block's own start: the longest beginning (whole words) more than half its names share, a word left for the
    wording (I-134 BT3: supporter_mailing, physical_address, beneficiary_mailing); the beginning all share when no
    longer one has a majority."""
    toks = [n.split("_") for n in names if n]
    best: list[str] = []
    for L in range(1, max((len(t) for t in toks), default=0)):
        cnt = collections.Counter(tuple(t[:L]) for t in toks if len(t) > L)
        if not cnt:
            break
        pre, k = cnt.most_common(1)[0]
        if 2 * k <= len(toks):
            break
        best = list(pre)
    return "_".join(best or _common_start(names))


def _rest(name: Optional[str], start: str) -> Optional[str]:
    """A name after its block's start (after the words it shares with the start when it does not begin with all of it:
    supporter_in_care_of_nm in a supporter_mailing block -> in_care_of_nm)."""
    if not name:
        return None
    if start and name.startswith(start + "_"):
        return name[len(start) + 1:]
    shared = _common_start([name, start]) if start else []
    toks = name.split("_")
    return "_".join(toks[len(shared):]) if len(shared) < len(toks) else toks[-1]


SLOT_KEYS = ("subject", "suffix", "iteration", "part")   # a position's parts; the block gives its own number and
                                               # prefix; `iteration` is the field's own number within the block (two
                                               # "other coverage options" boxes: other_coverage_opts_txt_2), after the
                                               # suffix as the naming standard has it (2026-10-25)
LINE_WORDS = {"line", "row", "box", "item", "page", "part", "question", "q", "col", "column", "section", "step"}


def _ids():
    """petey/validate/field_identifiers (the one function names are printed by) and the naming standard's suffixes."""
    from petey.validate import field_identifiers
    from petey.validate import standardize_names
    return field_identifiers, standardize_names


def slot(w) -> dict:
    """A position's parts, the inputs a field's name is printed from (Andrew, 2026-10-22: "we just need to have the
    same inputs that go into the standalone fields for the block fields"): {subject, suffix, part}, absent ones left
    out. A wording string is read as a field name is: city_nm -> city + nm, birth_dt_month -> birth + dt + month."""
    if isinstance(w, dict):
        out = {k: str(w[k]).strip().strip("_") for k in SLOT_KEYS if str(w.get(k) or "").strip().strip("_")}
        st = out.get("subject", "").split("_")      # a stored subject ending in the field's own number (confirmed
        if not out.get("iteration") and out.get("suffix") and len(st) > 1 and st[-1].isdigit() \
                and st[-2] not in LINE_WORDS:       # before 2026-10-25): the number after the suffix, as a wording's
            out["subject"], out["iteration"] = "_".join(st[:-1]), st[-1]
        return out
    from petey import naming
    _, sn = _ids()
    toks = [x for x in str(w or "").split("_") if x]
    while len(toks) > 1 and toks[0].isdigit():   # a wording never starts with a number: it is the block's (B 106D BT4,
        toks = toks[1:]                          # 2026-10-24: 1_last_4_digits_account_nbr -> notify_others_1_1_...)
    out: dict = {}
    if len(toks) > 1 and (re.fullmatch(r"part\d+", toks[-1])
                          or toks[-2] in sn.SUFFIXES and (toks[-1] in sn.PARTS_AFTER or toks[-1].isdigit())):
        out["part"] = toks.pop()                 # part1 is a part with or without a suffix (ssn_part1)
    if toks and toks[-1] in sn.SUFFIXES:
        out["suffix"] = toks.pop()
    # a number left at the end of the subject is the field's own (other_coverage_opts_2_txt: the second such box in
    # the block), unless it labels a line (address_line_1_txt) (Andrew, 2026-10-25, ACORD 80 BT4)
    if len(toks) > 1 and toks[-1].isdigit() and toks[-2] not in LINE_WORDS:
        out["iteration"] = toks.pop()
    if toks:
        out["subject"] = "_".join(toks)
    return {k: v for k, v in naming.standard(out).items() if v}      # short suffix, part1 (the naming standard)


def slot_text(s: dict) -> str:
    """A position's parts as one wording (city_nm), the way the field name prints them."""
    return "_".join(s[k] for k in SLOT_KEYS if s.get(k))


def _read_block(names: list[Optional[str]]) -> tuple[str, Optional[str], list[Optional[str]]]:
    """(prefix, iteration, each name's wording) of one block's names, whichever order they were printed in
    (child_2_city_nm, child_city_nm_2): the iteration is the number most of the names carry (at the place most of them
    have it when a name has it twice: child_1_address_line_1_txt), the prefix the start the names share once it is
    taken out (`block_start`), the wording what follows."""
    from collections import Counter
    LINE = re.compile(r"^\d+[a-z]?$")
    toks = [n.split("_") if n else None for n in names]
    have = [t for t in toks if t]
    cnt = Counter(v for t in have for v in {x for x in t if LINE.match(x)})
    it = None
    if cnt:
        v, k = cnt.most_common(1)[0]
        if 2 * k > len(have):
            it = v
    bare = []
    if it is not None:
        lone = Counter(t.index(it) for t in have if t.count(it) == 1)
        at = lone.most_common(1)[0][0] if lone else None
        for t in toks:
            if not t or it not in t:
                bare.append(t)
                continue
            idx = [i for i, x in enumerate(t) if x == it]
            i = at if at in idx else idx[-1]
            bare.append(t[:i] + t[i + 1:])
    else:
        bare = toks
    plain = ["_".join(t) if t else None for t in bare]
    start = block_start([p for p in plain if p])
    return start, it, [_rest(p, start) if p else None for p in plain]


def slots(bp: dict, t: dict) -> list[dict]:
    """Each position's parts: the confirmed ones (older records keep wordings, read as names are), else what most of
    the type's blocks give once their prefix and iteration are taken out, else the template block's."""
    if t.get("slots"):
        return [slot(s) for s in t["slots"]]
    if t.get("wordings"):
        return [slot(w) for w in t["wordings"]]
    names = _names(bp)
    blocks = [[names.get(c) for c in b] for b in t["blocks"]]
    tpl = [x["code"] for x in t["boxes"]]
    own = next((b for b, codes in zip(blocks, t["blocks"]) if codes == tpl), blocks[0] if blocks else [])
    # each block's positions from its fields' stored parts where they say the block (`_parts_of_block`), as
    # wordings, else read from its names
    fmap = _fields_by_code(bp)
    def rest_of(codes, nms):           # each position's parts (dicts), or its wording read from the names
        got = _parts_of_block(bp, codes, fmap)
        if got:
            return [dict(x) if x else None for x in got[2]]
        return _read_block(nms)[2]
    key = lambda x: slot_text(x) if isinstance(x, dict) else x          # noqa: E731
    rests = [rest_of(codes, b) for codes, b in zip(t["blocks"], blocks)]
    own_codes = next((codes for codes in t["blocks"] if codes == tpl), t["blocks"][0] if t["blocks"] else [])
    own_rest = rest_of(own_codes, own) if own else []
    out = []
    for k in range(len(t["boxes"])):
        got = [r[k] for r in rests if k < len(r) and r[k]]
        cnt = collections.Counter(key(x) for x in got)
        top = cnt.most_common(1)
        if top and 2 * top[0][1] > len(rests):
            out.append(slot(next(x for x in got if key(x) == top[0][0])))     # parts as stored, not re-read
        else:
            out.append(slot((own_rest[k] if k < len(own_rest) else "") or ""))
    return out


def wordings(bp: dict, t: dict) -> list[str]:
    """Each position's parts as one wording (city_nm), for the page and the older callers (`slots`)."""
    return [slot_text(s) for s in slots(bp, t)]


def _parts_of_block(bp: dict, codes: list, fmap: Optional[dict] = None):
    """(prefix, iteration, [each position's parts or None]) from the block's fields' stored parts (Andrew, 2026-10-26:
    "block and groups need to consider parts as well"), when every field's parts print its name and they share one
    block prefix and number; None otherwise (the names are read instead, `_read_block`)."""
    from petey import naming
    if fmap is None:
        fmap = _fields_by_code(bp)
    ps = []
    for c in codes:
        if not c:
            ps.append(None)
            continue
        n, sp = fmap.get(str(c), (None, {}))
        st = sp.get(naming.KEY) if isinstance(sp.get(naming.KEY), dict) else None
        if not st or naming.print_name(st) != n:
            return None
        ps.append(st)
    have = [x for x in ps if x]
    pre = {x.get("block_prefix") for x in have}
    it = {x.get("block_iteration") for x in have}
    if not have or len(pre) != 1 or None in pre or len(it) != 1:
        return None
    return next(iter(pre)), next(iter(it)), [{k: v for k, v in x.items() if k in SLOT_KEYS and v} if x else None
                                             for x in ps]


def _fields_by_code(bp: dict) -> dict:
    return {str(sp.get("x_petey_id")): (n, sp) for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}


def _names(bp: dict) -> dict[str, str]:
    return {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}


def _split_start(start: str) -> tuple[str, Optional[str]]:
    """(prefix, iteration) of a block's start: a last word that is a number is the iteration (child_3 -> child, 3)."""
    toks = [x for x in start.split("_") if x]
    if len(toks) > 1 and toks[-1].isdigit():
        return "_".join(toks[:-1]), toks[-1]
    return "_".join(toks), None


def block_parts(bp: dict, t: dict) -> dict[str, dict]:
    """{block's first code: {prefix, iteration}} for every block of the type (Andrew, 2026-10-21: "for each block
    type [field_name]_[block iteration] and for each block: [prefix] ... beneficiary_prior_spouse_1_first_nm"): what
    the person set on the block, else the block's start split into its prefix and a last number. Blocks sharing a
    prefix and carrying no number are numbered 1, 2, ... in the type's order (the page's, `_sorted_blocks`), skipping the
    numbers the others carry; a block alone with its prefix has no number unless one is typed for it (the naming
    standard, 2026-10-24, petey/naming.py); '-' set by hand is no iteration."""
    names = _names(bp)
    set_ = t.get("parts") or {}
    out = {}
    auto = _slug(t.get("label")) if t.get("auto") else ""
    fmap = _fields_by_code(bp)
    for n, b in enumerate(t["blocks"], 1):
        got = _parts_of_block(bp, list(dict.fromkeys(b)), fmap)     # the stored parts' block prefix and number
        pre, it = (got[0], got[1]) if got else _read_block([names.get(c) for c in dict.fromkeys(b)])[:2]
        if auto:                         # named from the type's label, numbered in the type's order (Andrew, 2026-10-21)
            pre, it = auto, str(n)
        mine = set_.get(_bid(b)) or {}
        own = mine.get("iteration") or None          # '' (the box left empty) is the next number free; '-' is none
        by = mine.get("by") or "number"
        if by == "prefix":               # told apart by its prefix: a number only where the prefix repeats (set_parts)
            out[_bid(b)] = {"prefix": mine.get("prefix", pre), "iteration": own, "by": by, "set": True}
            continue
        # the number read from the names only while the person has set neither an iteration (left empty: the next
        # number free) nor another prefix (Andrew, 2026-10-22: "updating the prefix doesn't automatically populate
        # the iteration": the old prefix's number stuck)
        read = it if "iteration" not in mine and mine.get("prefix", pre) == pre else None
        out[_bid(b)] = {"prefix": mine.get("prefix", pre), "iteration": own if own else read, "by": by, "set": bool(mine)}
    if auto:
        for c in out:
            if out[c]["iteration"] == "-" or len(t["blocks"]) == 1:     # one block: no number (the standard)
                out[c]["iteration"] = None
        return out
    by_prefix = collections.defaultdict(list)
    for b in t["blocks"]:
        by_prefix[out[_bid(b)]["prefix"]].append(_bid(b))
    # an empty iteration takes the next number free among the blocks with its prefix, in the type's order (Andrew,
    # 2026-10-21: "if an iteration is empty, give it the next number available"); '-' set by hand is none
    typed = {_bid(b) for b in t["blocks"] if (set_.get(_bid(b)) or {}).get("iteration")}
    for pre, codes in by_prefix.items():
        if len(codes) == 1:              # alone with its prefix: no number, by number or by prefix (Andrew, 2026-10-24,
            if codes[0] not in typed:    # the naming standard: "a block alone gets no number"; VA 20-0996's veteran_1_
                out[codes[0]]["iteration"] = None      # and claimant_1_); one typed by hand stays
            continue
        taken = {out[c]["iteration"] for c in codes if out[c]["iteration"] and out[c]["iteration"] != "-"}
        n = 1
        for c in codes:
            if out[c]["iteration"]:
                continue
            while str(n) in taken:
                n += 1
            out[c]["iteration"] = str(n)
            taken.add(str(n))
    for c in out:
        if out[c]["iteration"] == "-":
            out[c]["iteration"] = None
    return out


def block_ident(prefix: Optional[str], iteration: Optional[str], s: dict) -> dict:
    """A block field's parts: the block's prefix and number, then the position's subject, suffix and part (Andrew,
    2026-10-22: "[block prefix]_[block iteration]_[field subject]_[field iteration] ... child_2_ssn_1 would be the first
    ssn field of the second 'child' block"; the validated names are the guide). The prefix's last word is said once
    when the subject starts with it (mailing + mailing_street). A block with no prefix keeps its number last
    (field_identifiers.ORDERS: a name does not start with a number)."""
    pt = [x for x in (prefix or "").split("_") if x]
    st = [x for x in (s.get("subject") or "").split("_") if x]
    while pt and st and pt[-1] == st[0] and (len(st) > 1 or s.get("suffix")):
        st = st[1:]
    if not pt:                           # no prefix: the block's number is the field's; the position's own stays
        st = st + ([s["iteration"]] if s.get("iteration") else [])          # in the subject, as before
        out = {"subject": "_".join(st), "suffix": s.get("suffix"), "iteration": iteration, "part": s.get("part")}
    else:
        out = {"block_prefix": "_".join(pt), "block_iteration": iteration, "subject": "_".join(st),
               "suffix": s.get("suffix"), "iteration": s.get("iteration"), "part": s.get("part")}
    return {k: v for k, v in out.items() if v}


def check_block(bp: dict, t: dict, block: list[str], words: Optional[list] = None,
                parts: Optional[dict] = None) -> dict:
    """A block against its type: every name printed from its parts as every field's is (`block_ident`,
    field_identifiers.print_name: [block prefix]_[block iteration]_[subject]_[suffix]_[part], Andrew 2026-10-22). {start, prefix, iteration, ok, differs: [{pos, name, want,
    ident}], kept}."""
    fi, _ = _ids()
    ss = [slot(w) for w in words] if words else slots(bp, t)
    names = _names(bp)
    ns = [names.get(c) for c in block]
    part = (parts or block_parts(bp, t)).get(_bid(block)) or {"prefix": block_start(ns), "iteration": None}
    start = "_".join(x for x in [part["prefix"], part["iteration"]] if x)
    keep = set((t.get("keep") or {}).get(_bid(block)) or [])         # suggestions the person cancelled: names kept
    differs_ = []
    many = {c for c in block if c and block.count(c) > 1}       # a group over several positions (`reattach`): the
    for k, (n, s) in enumerate(zip(ns, ss)):                    # Groups tab names it, not the block
        if n is None or block[k] in many:  # the type's box this block lacks
            continue
        ident = block_ident(part["prefix"], part["iteration"], s)
        want = fi.print_name(ident)
        if want and n != want and k + 1 not in keep:
            differs_.append({"pos": k + 1, "name": n, "want": want, "ident": ident})
    return {"start": start, "prefix": part["prefix"], "iteration": part["iteration"], "ok": not differs_,
            "differs": differs_, "kept": sorted(keep)}


def set_parts(bid: str, code: str, prefix: Optional[str], iteration: Optional[str], by: Optional[str] = None) -> dict:
    """A block's prefix and iteration as the person set them (None: back to the default), and how the block is told
    apart from the type's others (Andrew, 2026-10-21: "provide a prefix instead of an iteration ... preparer_address";
    "this should be a block-level decision"): "number", the default ([prefix]_[iteration]_[wording], an empty iteration
    the next number free, a block alone with its prefix 1), or "prefix" (its prefix tells it apart: preparer_address,
    no number unless another block of the type has the prefix, preparer_1_address / preparer_2_address, or one is
    set here)."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    mine = {}
    if prefix is not None:
        prefix = str(prefix).strip().strip("_")
        if prefix and not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", prefix):
            raise ValueError("a prefix is lower case words joined by _")
        # an empty prefix is an error only for a block told apart by its prefix (Andrew, 2026-10-22); told apart by
        # number, it is none: [wording]_[iteration]
        if not prefix and by == "prefix":
            raise ValueError("a block told apart by its prefix needs one")
        mine["prefix"] = prefix
    if iteration is not None:
        iteration = str(iteration).strip()
        if iteration and not re.fullmatch(r"[0-9]+[a-z]?|[a-z]|-", iteration):
            raise ValueError("an iteration is a number (or a letter), - for none, or empty for the next number free")
        mine["iteration"] = iteration
    if by not in (None, "number", "prefix"):
        raise ValueError("a block is told apart by number or by prefix")
    if by == "prefix":
        mine["by"] = "prefix"
    if mine:
        t.setdefault("parts", {})[_bid(b)] = mine
    else:
        (t.get("parts") or {}).pop(_bid(b), None)
    gc._save_set(bid, rec)
    return {"type": t["id"], **mine}


def confirm(bid: str, bp: dict, tid: str, words: list) -> dict:
    """The type's positions as the person confirmed them, each its parts ({subject, suffix, part}, as a field's) or
    a wording read as a name is: one per position, no two alike, words only. A position left blank is named by its
    block alone (je__uscis_i_129s BT4, 2026-10-26: additional_information_1, the box under its page, part and item
    numbers; Andrew: "it labels correctly, so the bug is raising a non-issue"); a part needs a subject or a suffix."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    ss = [slot(w) for w in words]
    if len(ss) != len(t["boxes"]):
        raise ValueError("one set of parts per position")
    for k, s in enumerate(ss, 1):
        if s.get("part") and not (s.get("subject") or s.get("suffix")):
            raise ValueError(f"position {k}: a part needs a subject or a suffix")
        bad = [x for x in s.values() if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", x)]
        if bad:
            raise ValueError(f"position {k}: {bad[0]!r}: lower case words joined by _")
    # positions alike with no number of their own are numbered in the type's order, 1 up, past any number one of
    # them has (Andrew, 2026-10-25, je__cms855b BT25: "why can't it just renumber them automatically"); the person
    # is told which, as two alike may be a wrong subject rather than a repeat (BT25's two signature dates)
    alike: dict = {}
    for k, s in enumerate(ss):
        alike.setdefault(slot_text({x: v for x, v in s.items() if x != "iteration"}), []).append(k)
    numbered = []
    for ks in alike.values():
        bare = [k for k in ks if not ss[k].get("iteration")]
        if len(bare) < 2:
            continue
        taken, n = {ss[k]["iteration"] for k in ks if ss[k].get("iteration")}, 1
        for k in bare:
            while str(n) in taken:
                n += 1
            ss[k] = {**ss[k], "iteration": str(n)}
            taken.add(str(n))
            numbered.append(k + 1)
    texts = [slot_text(s) for s in ss]
    seen: dict = {}
    for k, w in enumerate(texts):
        seen.setdefault(w, []).append(k)
    same = [ks for ks in seen.values() if len(ks) > 1]       # left: the same number typed on two
    if same:
        raise ValueError("; ".join(
            "positions " + " and ".join(f"{k + 1} ({t['boxes'][k]['code']})" for k in ks) + f" have the same parts, "
            f"{texts[ks[0]]}" for ks in same) + ": give one another subject, or another iteration")
    t["slots"], t["wordings"], t["confirmed"] = ss, texts, time.strftime("%Y-%m-%d %H:%M:%S")
    gc._save_set(bid, rec)
    return {"id": tid, "wordings": texts, "slots": ss, "numbered": sorted(numbered)}


def _slug(label: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")


def set_auto(bid: str, tid: str, on: bool) -> dict:
    """A block type's blocks named from its label and numbered in its order (Andrew, 2026-10-21: "set the blocks to
    automatically iterate and populate the prefix with the block name"): prefix the label as a name, iteration 1..N;
    a block's own prefix or iteration, set by hand, still wins."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    if on and not _slug(t.get("label")):
        raise ValueError(f"give {tid} a label first: its blocks are named from it")
    if on:
        t["auto"] = True
    else:
        t.pop("auto", None)
    gc._save_set(bid, rec)
    return {"id": tid, "auto": bool(on), "prefix": _slug(t.get("label"))}


def set_label(bid: str, tid: str, label: str) -> dict:
    """A block type's label, the person's name for it (Andrew, 2026-10-21: "editable labels to the block types"); ''
    clears it."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    label = " ".join(str(label or "").split())[:80]
    if label:
        t["label"] = label
    else:
        t.pop("label", None)
    gc._save_set(bid, rec)
    return {"id": tid, "label": label}


def _block_by_code(rec: dict, code: str):
    for t in rec.get("types") or []:
        for b in t["blocks"]:
            if _bid(b) == code:
                return t, b
    raise ValueError("no such block (drawn again since?)")


def keep_name(bid: str, code: str, pos: int, on: bool = True) -> dict:
    """A suggested rename cancelled (Andrew, 2026-10-21: "the suggested name changes should be cancelable"): the name
    at position `pos` of the block stays as it is and no longer counts as off the type; `on` False undoes it."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    keep = t.setdefault("keep", {}).setdefault(_bid(b), [])
    if on and pos not in keep:
        keep.append(int(pos))
    if not on and pos in keep:
        keep.remove(int(pos))
    if not keep:
        t["keep"].pop(_bid(b), None)
    gc._save_set(bid, rec)
    return {"type": t["id"], "kept": sorted(keep)}


def type_checks(bp: dict, t: dict, rec: Optional[dict] = None) -> dict[str, dict]:
    """{block id: check_block's result} for every block of the type, read together (Andrew, 2026-10-21, VA 21-686c
    BT7-5 / BT7-6: "what's the best way to automate name clashes when using blocks?"):
      - two blocks that come to one start (prefix and iteration) get `same_as` (the other blocks' ids) and no renames
        until it is settled: each would take the other's names;
      - a rename onto a name some field keeps and will not give up (a field outside the type, or a block whose renames
        are held back) gets `held`: the block that holds it (BT3-2) or "no block"; the renames skip it.
    A rename onto a name another block of the type is giving up (a swap: child_5 / child_6) is fine: the blocks are
    renamed together (`chain`)."""
    words, parts = wordings(bp, t), block_parts(bp, t)
    res = {_bid(b): check_block(bp, t, b, words, parts) for b in t["blocks"]}
    num = {_bid(b): f"{t['id']}-{i}" for i, b in enumerate(t["blocks"], 1)}
    by_start = collections.defaultdict(list)
    for b in t["blocks"]:
        by_start[res[_bid(b)]["start"]].append(_bid(b))
    for start, ids in by_start.items():
        if start and len(ids) > 1:
            for i in ids:
                res[i]["same_as"] = [num[j] for j in ids if j != i]
                res[i]["differs"], res[i]["ok"] = [], False
    names = _names(bp)
    owner = {}                                     # a name -> the block holding it, in any type
    for x in (rec or {}).get("types") or [t]:
        for i, b in enumerate(x["blocks"], 1):
            for c in b:
                if c and names.get(c):
                    owner[names[c]] = f"{x['id']}-{i}"
    leaving = {d["name"] for r in res.values() for d in r["differs"]}
    fields = bp.get("fields") or {}
    for r in res.values():
        for d in r["differs"]:
            if d["want"] in fields and d["want"] not in leaving:
                d["held"] = owner.get(d["want"]) or "no block"
    return res


def chain(res: dict[str, dict], start: str) -> list[dict]:
    """The renames a block needs, with every other block's whose names it moves onto (a swap, a shift down the
    line), so they go in one batch; held ones left out."""
    want_from = {d["name"]: i for i, r in res.items() for d in r["differs"]}
    todo, done, out = [start], set(), []
    while todo:
        i = todo.pop()
        if i in done:
            continue
        done.add(i)
        for d in res[i]["differs"]:
            if d.get("held"):
                continue
            out.append(d)
            if d["want"] in want_from:             # its new name is another block's now: that block moves too
                todo.append(want_from[d["want"]])
    return out


def validate_block(bid: str, bp: dict, code: str) -> dict:
    """Check & validate one block against its confirmed type (Andrew, 2026-10-21: "we need the ability to validate a
    block ... of a confirmed type even if it isn't in a group with other blocks"):
    {ok, names (to accept when ok), differs, start}."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    if not t.get("confirmed"):
        raise ValueError(f"confirm {t['id']}'s wordings first")
    res = type_checks(bp, t, rec)[_bid(b)]
    names = _names(bp)
    return {**res, "type": t["id"], "names": [names.get(c) for c in b if names.get(c)]}


def block_renames(bid: str, bp: dict, code: str) -> dict:
    """The renames that put one block to its type, with the other blocks' that must move with it (`chain`)."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    res = type_checks(bp, t, rec)
    return {"type": t["id"], "renames": chain(res, _bid(b)),
            "held": [d for d in res[_bid(b)]["differs"] if d.get("held")], "same_as": res[_bid(b)].get("same_as") or []}


def type_renames(bid: str, bp: dict, tid: str) -> dict:
    """Every block's renames, held ones left out, and the blocks that come to one name."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    res = type_checks(bp, t, rec)
    num = {_bid(b): f"{tid}-{i}" for i, b in enumerate(t["blocks"], 1)}
    return {"type": tid, "renames": [d for r in res.values() for d in r["differs"] if not d.get("held")],
            "held": [d for r in res.values() for d in r["differs"] if d.get("held")],
            "same": sorted({num[i] for i, r in res.items() if r.get("same_as")})}


def names_from_type(bid: str, bp: dict, tid: str) -> tuple[dict[str, str], list[str]]:
    """({old name: new name}, notes): every block of the type named from the template block's names.

    The blocks' key is the sequence of words that changes from block to block the same way at most positions (1, 2,
    3; a, b, c on FEC 3X; 28a, 29a, 30a on 990-EZ), found where it sits in each position's names; another word that
    varies (FEC 3X's state_4, state_3, state_3) is not the block's and is printed as the template has it. Each block's
    name at a position is the template's name with the key word put to the block's. Keys that already count by one
    are kept as they are, never renumbered (printed numbers can run out of reading order); a run that
    does not count by one is said. A position whose names do not carry the key is left and said;
    so are names another field keeps."""
    from petey.validate import grid_naming as G
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    by_code = {str(s.get("x_petey_id")): n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    blocks = [[by_code.get(c) for c in b] for b in t["blocks"]]
    tpl_codes = [x["code"] for x in t["boxes"]]
    own = [by_code.get(c) for c in next((b for b in t["blocks"] if b == tpl_codes), t["blocks"][0])]
    if len(blocks) < 2:
        return {}, ["one block only: nothing to name against"]
    notes: list[str] = []
    # each position's words that differ in every block, counted from the start (names may differ in length: FEC
    # 3X's row_e_full_name beside row_a_full_name_5); an item-lettered word counts by its number (990-EZ's 28a: the
    # number is the block's, the letter the position's)
    seqs = {}
    for k in range(len(own)):
        names = [b[k] for b in blocks]
        if own[k] is None or any(n is None for n in names):
            continue
        toks = [n.split("_") for n in names]
        short = min(len(x) for x in toks)
        d = {}
        for i in range(min(short, len(own[k].split("_")))):
            sq = tuple(x[i] for x in toks)
            if len(set(sq)) == len(sq):
                d[i] = sq
                core = tuple(G._core(x) for x in sq)
                if core != sq and len(set(core)) == len(core):
                    d.setdefault(("core", i), core)
        seqs[k] = d
    count = collections.Counter(sq for d in seqs.values() for sq in set(d.values()))
    if not count:
        return {}, ["no word changes from block to block at any position: nothing to number"]
    key = max(count, key=lambda sq: (count[sq], all(x.isdigit() for x in sq)))
    vary = {}
    for k in range(len(own)):
        at = [i for i, sq in (seqs.get(k) or {}).items() if sq == key]
        if at:
            vary[k] = sorted(at, key=lambda i: isinstance(i, tuple))[0]
        else:
            notes.append(f"position {k + 1} ({own[k]}): the blocks' key ({', '.join(key)}) is not in its names; left")

    def steps(a: str, b: str) -> bool:           # 1 then 2, a then b, 28a then 29a, row1 then row2
        ca, cb = G._core(a), G._core(b)
        if ca != a and cb != b and a[-1] == b[-1]:
            return G._next(ca, cb)
        ma, mb = re.match(r"([a-z]+)(\d+)$", a), re.match(r"([a-z]+)(\d+)$", b)
        if ma and mb and ma.group(1) == mb.group(1):
            return int(mb.group(2)) == int(ma.group(2)) + 1
        return G._next(a, b)
    # the keys are never renumbered (I-130's 5a, 3a, 6a, 4a, 7a are printed item numbers in two columns, out of
    # reading order on purpose): the blocks keep theirs, and a run that does not count by one is said
    want = list(key)
    if not all(steps(a, b) for a, b in zip(want, want[1:])):
        notes.append(f"blocks keyed {', '.join(want)} in reading order (not counting by one; kept: printed numbers?)")
    ren = {}
    for b, n in zip(blocks, want):
        for k, i in vary.items():
            toks = own[k].split("_")
            if isinstance(i, tuple):                 # the number is the block's, the letter after it the position's
                j = i[1]
                toks[j] = n + toks[j][len(G._core(toks[j])):]
            else:
                toks[i] = n
            new = "_".join(toks)
            if new != b[k]:
                ren[b[k]] = new
    fields = bp.get("fields") or {}
    mine = {n for b in blocks for n in b if n}
    clash = sorted(v for v in ren.values() if v in fields and v not in mine)
    if clash:
        notes.append(f"left: {len(clash)} name(s) another field keeps ({', '.join(clash[:4])})")
        ren = {o: v for o, v in ren.items() if v not in clash}
    final = [ren.get(n, n) for n in mine]
    if len(set(final)) < len(final):
        notes.append("two boxes would share a name; nothing renamed")
        ren = {}
    return ren, notes
