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
checked and validated against its confirmed type on its own (`validate_block`). Blocks are kept in the order the
publisher put the widgets in the PDF (`widget_order`), top then left only without widgets.

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


def widget_order(bp: dict) -> dict[str, tuple]:
    """{field name: (page, place)}: where the field's first widget sits in its page's list of widgets, the order the
    publisher put in the PDF (Andrew, 2026-10-21: "we need to defer to the order hard-coded"; I-130 page 12, tab order
    /S, lists items 3a, 4a, 5a, 6a, 7a down its two columns where top-then-left reads 5, 3, 6, 4, 7). Empty without
    the blank (a flat form has no widgets: top then left)."""
    import pymupdf
    from petey.validate.retype import resolve_blank
    blank = resolve_blank(bp)
    if not blank or not blank.exists():
        return {}
    at: dict[tuple, tuple] = {}
    doc = pymupdf.open(str(blank))
    try:
        for i, pg in enumerate(doc, 1):
            for k, w in enumerate(pg.widgets() or []):
                at.setdefault((i, w.field_name), (i, k))
    finally:
        doc.close()
    out = {}
    for n, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        ws = [spec["widget"]] if spec.get("widget") else list((spec.get("widgets") or {}).values())
        places = [at[(w.get("page"), w.get("path"))] for w in ws if (w.get("page"), w.get("path")) in at]
        if places:
            out[n] = min(places)
    return out


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
    """Blocks in the PDF's widget order (each block's first box); top then left without widgets."""
    by_code = {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    wo, at = widget_order(bp), {b["code"]: b for b in _boxes(bp)}
    def key(b):
        if by_code.get(_bid(b)) in wo:
            return (0,) + wo[by_code[_bid(b)]]
        r = at.get(_bid(b))
        return (1, r["page"], round(r["rect"][1] / 2), r["rect"][0]) if r else (2,)
    return sorted(blocks, key=key)


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


def detect(bid: str, bp: dict, page: int) -> dict:
    """Every block type's copies on a page added as its blocks (Andrew, 2026-10-21: "can we detect existing block types
    on a page?"); boxes already in a block are left where they are. {found: {type: [block numbers]}, n}."""
    rec = gc.load_set(bid)
    held = {c for t in rec.get("types") or [] for b in t["blocks"] for c in b}
    found = {}
    for t in rec.get("types") or []:
        free = [x for x in _boxes(bp) if x["page"] == page and x["code"] not in held]
        fresh = copies_in(free, t)
        if fresh:
            held |= {c for f in fresh for c in f}
            t["blocks"] = _sorted_blocks(bp, t["blocks"] + fresh)
            found[t["id"]] = [next(i for i, b in enumerate(t["blocks"], 1) if b == f) for f in fresh]
    if found:
        gc._save_set(bid, rec)
    return {"found": found, "n": sum(len(v) for v in found.values())}


FIT_MAX = 1.5            # a pair scoring above this is no pair (`fit`)
STOP = {"with", "at", "of", "the", "a", "an", "to", "for", "and", "or", "in", "on", "by"}


def _same_word(a: str, b: str) -> bool:
    """One word in two spellings (2026-10-21, VA 21-686c BT7-3: resides / residence, ended / end): equal, one stem
    (grid_naming._stem), or the first 5 letters alike."""
    if a == b:
        return True
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import grid_naming as G
    return G._stem(a) == G._stem(b) or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])
ENDINGS = {"txt", "nm", "nbr", "cd", "amt", "dt", "ind", "qty", "cnt", "pct", "yr", "type", "rate", "name", "number", "code",
           "date", "amount"}   # a type's ending says nothing about which field it is (ACORD 80: years_at_previous_address_qty
                               # and years_with_current_employer_qty agreed on years and qty, and were paired)


def fit(bp: dict, t: dict, bs: list[dict]) -> tuple[list[Optional[str]], list[str]]:
    """The block's boxes `bs` ({code, kind, rect}) paired with the type's template boxes by best fit (Andrew,
    2026-10-21: "cross-check box sizes or locations or labels to find a best fit"): boxes of one kind only, each
    pair scored by place within the block and size (in units of 4 x the type's tolerance) and, twice over, by label
    (0 when the box's name ends with the position's wording, else the share of the wording's words, type endings left
    out, it lacks); the pairing with the
    least total, a pair above `FIT_MAX` dropped. ([code or None per template position], [codes left out])."""
    from scipy.optimize import linear_sum_assignment
    want, rw, T = t["boxes"], _rel(t["boxes"]), tol(t["boxes"])
    words, names = wordings(bp, t), _names(bp)
    x0, y0 = min(b["rect"][0] for b in bs), min(b["rect"][1] for b in bs)
    big = 1e6
    cost = []
    for b in bs:
        n = names.get(b["code"]) or ""
        row = []
        for k, w in enumerate(want):
            if b["kind"] != w["kind"]:
                row.append(big)
                continue
            place = (abs(b["rect"][0] - x0 - rw[k][0]) + abs(b["rect"][1] - y0 - rw[k][1])) / (4 * T)
            size = (abs(b["rect"][2] - b["rect"][0] - w["w"]) + abs(b["rect"][3] - b["rect"][1] - w["h"])) / (4 * T)
            wt = [x for x in words[k].split("_") if x and x not in ENDINGS and x not in STOP] if k < len(words) else []
            nt = n.split("_")
            label = 0.0 if not wt or n.endswith("_" + words[k]) else 1 - sum(any(_same_word(x, y) for y in nt) for x in wt) / len(wt)
            # sharing less than half the wording is another field, however well it lines up (ACORD 80: the
            # co-applicant's years_with_current_employer_qty where the applicant has years_at_previous_address_qty)
            row.append(big if label > 0.5 else place + size + 2 * label)
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
        return {"type": tid, "block": i + 1, "of": len(t["blocks"]), "was": tid, "refit": True,
                "missing": [k + 1 for k, c in enumerate(codes) if not c], "extra": [names.get(c) for c in extra
                                                                                   if c not in set(b)]}
    _drop_blocks(rec, bp, set(b))                    # out of its old type
    rec["types"] = [x for x in rec["types"] if x["blocks"] or x is t]
    t["blocks"] = _sorted_blocks(bp, t["blocks"] + [codes])
    gc._save_set(bid, rec)
    names = _names(bp)
    return {"type": tid, "block": t["blocks"].index(codes) + 1, "of": len(t["blocks"]), "was": old["id"],
            "missing": [k + 1 for k, c in enumerate(codes) if not c], "extra": [names.get(c) for c in extra]}


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
    type's order (the PDF's widget order), `code` its first box (how the page names it)."""
    boxes = {b["code"]: b for b in _boxes(bp)}
    names = {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    out = []
    for t in rec.get("types") or []:
        blocks, words, parts = [], wordings(bp, t), block_parts(bp, t)
        checks = type_checks(bp, t, rec)
        for i, b in enumerate(t["blocks"], 1):
            bs = [boxes[c] for c in b if c in boxes]
            if bs:
                chk = checks[_bid(b)]
                acc = sum((verdicts or {}).get(names.get(c), {}).get("verdict") == "accept" for c in b)
                blocks.append({"n": i, "code": _bid(b), "page": bs[0]["page"], 
                               "names": [names.get(c, c) if c else None for c in b], "differs": chk["differs"], "start": chk["start"],
                               "kept": chk["kept"], "prefix": chk["prefix"], "iteration": chk["iteration"],
                               "parts_set": parts[_bid(b)]["set"], "same_as": chk.get("same_as") or [],
                               "cells": [{"name": names.get(c, c), "rect": boxes[c]["rect"],
                                          "accepted": (verdicts or {}).get(names.get(c), {}).get("verdict") == "accept"}
                                         if c in boxes else None for c in b],
                               "validated": acc == sum(1 for c in b if c),
                               "template": b == [x["code"] for x in t["boxes"]],
                               "bbox": [min(x["rect"][0] for x in bs), min(x["rect"][1] for x in bs),
                                        max(x["rect"][2] for x in bs), max(x["rect"][3] for x in bs)]})
        out.append({"id": t["id"], "label": t.get("label") or "", "auto": bool(t.get("auto")), "page": t["page"],
                    "boxes": len(t["boxes"]),
                    "blocks": blocks, "wordings": words,
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


def wordings(bp: dict, t: dict) -> list[str]:
    """Each position's wording, the part of every block's name after the block's own start (Andrew, 2026-10-21, I-134
    BT3: supporter_mailing_ / physical_address_ / beneficiary_mailing_ then in_care_of_nm, street_address_txt, ...):
    the confirmed ones, else the rest most of the type's blocks give, else the template block's."""
    if t.get("wordings"):
        return list(t["wordings"])
    names = _names(bp)
    blocks = [[names.get(c) for c in b] for b in t["blocks"]]
    tpl = [x["code"] for x in t["boxes"]]
    own = next((b for b, codes in zip(blocks, t["blocks"]) if codes == tpl), blocks[0] if blocks else [])
    rests = [[_rest(n, block_start(b)) for n in b] for b in blocks]
    own_rest = [_rest(n, block_start(own)) for n in own]
    out = []
    for k in range(len(t["boxes"])):
        cnt = collections.Counter(r[k] for r in rests if r[k])
        top = cnt.most_common(1)
        out.append(top[0][0] if top and 2 * top[0][1] > len(rests) else (own_rest[k] if k < len(own_rest) else "") or "")
    return out


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
    prefix and carrying no number are numbered 1, 2, ... in the type's order (the PDF's widget order), skipping the
    numbers the others carry (a block alone with its prefix: 1); '-' set by hand is no iteration."""
    names = _names(bp)
    set_ = t.get("parts") or {}
    out = {}
    auto = _slug(t.get("label")) if t.get("auto") else ""
    for n, b in enumerate(t["blocks"], 1):
        pre, it = _split_start(block_start([names.get(c) for c in b]))
        if auto:                         # named from the type's label, numbered in the type's order (Andrew, 2026-10-21)
            pre, it = auto, str(n)
        mine = set_.get(_bid(b)) or {}
        own = mine.get("iteration") or None          # '' (the box left empty) is the next number free; '-' is none
        out[_bid(b)] = {"prefix": mine.get("prefix", pre), "iteration": own if own else it, "set": bool(mine)}
    if auto:
        return out
    by_prefix = collections.defaultdict(list)
    for b in t["blocks"]:
        by_prefix[out[_bid(b)]["prefix"]].append(_bid(b))
    # an empty iteration takes the next number free among the blocks with its prefix, in the type's order (Andrew,
    # 2026-10-21: "if an iteration is empty, give it the next number available"); '-' set by hand is none
    for pre, codes in by_prefix.items():
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


def check_block(bp: dict, t: dict, block: list[str], words: Optional[list[str]] = None,
                parts: Optional[dict] = None) -> dict:
    """A block against its type: every name [prefix]_[iteration]_[the position's wording] (`block_parts`; no
    iteration where the person set '-'). {start, prefix, iteration, ok, differs: [{pos, name, want}], kept}."""
    words = words or wordings(bp, t)
    names = _names(bp)
    ns = [names.get(c) for c in block]
    part = (parts or block_parts(bp, t)).get(_bid(block)) or {"prefix": block_start(ns), "iteration": None}
    start = "_".join(x for x in [part["prefix"], part["iteration"]] if x)
    keep = set((t.get("keep") or {}).get(_bid(block)) or [])         # suggestions the person cancelled: names kept
    differs_ = []
    for k, (n, w) in enumerate(zip(ns, words)):
        if n is None:                    # the type's box this block lacks
            continue
        st = start.split("_")
        wt = w.split("_")
        while st and wt and st[-1] == wt[0] and len(wt) > 1:       # the start's last word repeated: once (mailing)
            wt = wt[1:]
        want = "_".join([x for x in st if x] + wt) if start else w
        if n != want and k + 1 not in keep:
            differs_.append({"pos": k + 1, "name": n, "want": want})
    return {"start": start, "prefix": part["prefix"], "iteration": part["iteration"], "ok": not differs_,
            "differs": differs_, "kept": sorted(keep)}


def set_parts(bid: str, code: str, prefix: Optional[str], iteration: Optional[str]) -> dict:
    """A block's prefix and iteration as the person set them (None: back to the default)."""
    rec = gc.load_set(bid)
    t, b = _block_by_code(rec, code)
    mine = {}
    if prefix is not None:
        prefix = str(prefix).strip().strip("_")
        if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", prefix):
            raise ValueError("a prefix is lower case words joined by _")
        mine["prefix"] = prefix
    if iteration is not None:
        iteration = str(iteration).strip()
        if iteration and not re.fullmatch(r"[0-9]+[a-z]?|[a-z]|-", iteration):
            raise ValueError("an iteration is a number (or a letter), - for none, or empty for the next number free")
        mine["iteration"] = iteration
    if mine:
        t.setdefault("parts", {})[_bid(b)] = mine
    else:
        (t.get("parts") or {}).pop(_bid(b), None)
    gc._save_set(bid, rec)
    return {"type": t["id"], **mine}


def confirm(bid: str, bp: dict, tid: str, words: list[str]) -> dict:
    """The type's wordings, one per position, as the person confirmed them (one each, no two alike, words only)."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    words = [str(w).strip().strip("_") for w in words]
    if len(words) != len(t["boxes"]) or not all(re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", w) for w in words):
        raise ValueError("one wording per position: lower case words joined by _")
    if len(set(words)) < len(words):
        raise ValueError("two positions with one wording")
    t["wordings"], t["confirmed"] = words, time.strftime("%Y-%m-%d %H:%M:%S")
    gc._save_set(bid, rec)
    return {"id": tid, "wordings": words}


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
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import grid_naming as G
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
