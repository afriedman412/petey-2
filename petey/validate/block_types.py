"""Block types (Andrew, 2026-10-21: "select an area to define a block type, then use that template to validate blocks
that look like it, manually or even programmatically ... lets start with exact matches, and start with limiting the
scope to a single form").

A block type is a template drawn once: the fields whose box has its middle inside an area, each kept as its offset
from the template's first box (top, then left), its size and its kind (text, checkbox, an option group of n boxes,
...). Defining a type stores the template only (Andrew, 2026-10-21: no copies found automatically; finding them comes
later). `find` gives the template's exact copies anywhere on the form, the same kinds and sizes at the same offsets,
within `TOL` points; when copies are used, their order is to be the one the publisher put the widgets in the PDF (the
page's widget list), top then left only without widgets. The blocks on one page are to be kept as one block group (grid_check's record, source "type", with
the type's id), so the Blocks tab's cards, check & validate and the one-block-group-per-field rule work on them as on
any other. A grid is a block type whose template is one row (later: Grids and Blocks folded into one tab).

Names come from the template (`names_from_type`): each block's names are the template block's, with the word that
keys the blocks (1, 2; a, b; 28a, 29a) put to the block's own key. Keys are never renumbered; fix the template
block's names first and the rest follow.

Record: runs/hand_review/grids/<bid>.json gains "types": [{id (BT1), page, rect, boxes: [{code, dx, dy, w, h, kind}],
groups: [block group ids], when}].
"""
from __future__ import annotations

import collections
import re
import time
from typing import Optional

from petey.validate import grid_check as gc

TOL = 1.0                  # points: an exact copy's boxes sit within this of the template's offsets and sizes


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


def define(bid: str, bp: dict, page: int, rect) -> dict:
    """A block type from an area: the fields in it, as the template, and nothing else (Andrew, 2026-10-21: "we just
    want it to select the selection and interpret that as a type, don't automatically find other versions"; finding
    copies comes later). {id, boxes}."""
    tpl = template(bp, page, rect)
    rec = gc.load_set(bid)
    tid = _new_type_id(rec)
    rec.setdefault("types", []).append({"id": tid, "page": page, "rect": [float(x) for x in rect],
                                        "boxes": [{k: x[k] for k in ("code", "dx", "dy", "w", "h", "kind")}
                                                  for x in tpl["boxes"]],
                                        "groups": [], "blocks": [[x["code"] for x in tpl["boxes"]]],
                                        "when": time.strftime("%Y-%m-%d %H:%M:%S")})
    gc._save_set(bid, rec)
    return {"id": tid, "boxes": len(tpl["boxes"])}


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


def designate(bid: str, bp: dict, tid: str, page: int, rect) -> dict:
    """An area designated a block of type `tid` by hand (Andrew, 2026-10-21: "define and designate manually"): its
    fields must be an exact copy of the template (the same kinds and sizes at the same offsets from the first box,
    within `TOL`), else nothing is kept and what differs is said. The type's blocks on one page are kept as one block
    group (source "type"), in the PDF's widget order (`widget_order`; top then left without widgets), each field
    leaving any other block group (`grid_check.exclusive`). {id, block, of, page, group, left}."""
    rec = gc.load_set(bid)
    t = next((x for x in rec.get("types") or [] if x["id"] == tid), None)
    if t is None:
        raise ValueError(f"no block type {tid}")
    got = template(bp, page, rect)["boxes"]
    want = t["boxes"]
    def said(kind):                              # textx1 -> a text box; checkboxx3 -> a group of 3 checkboxes
        what, _, n = kind.rpartition("x")
        what = {"text": "text box", "radiobutton": "radio button", "combobox": "dropdown"}.get(what, what)
        return f"a {what}" if n == "1" else f"a group of {n} {what}es" if what.endswith("x") else f"a group of {n} {what}s"
    diffs = []
    if len(got) != len(want):
        diffs.append(f"the area has {len(got)} boxes, the template {len(want)}")
    else:
        for k, (g, w) in enumerate(zip(got, want), 1):
            off = [x for x in ("dx", "dy", "w", "h") if abs(g[x] - w[x]) > TOL]
            if g["kind"] != w["kind"]:
                diffs.append(f"box {k} ({g['name']}) is {said(g['kind'])}, the template's {said(w['kind'])}")
            elif off:
                diffs.append(f"box {k} ({g['name']}) sits or sizes otherwise: " + ", ".join(
                    f"{dict(dx='across', dy='down', w='width', h='height')[x]} {g[x]:.1f} pt, the template's {w[x]:.1f}"
                    for x in off))
    if diffs:
        raise ValueError(f"not an exact copy of {tid}: " + "; ".join(diffs[:4]))
    codes = [g["code"] for g in got]
    blocks = [b for b in t["blocks"] if not set(b) & set(codes)]       # designated again: the newer one stands
    blocks.append(codes)
    by_code = {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    pages = {b["code"]: b["page"] for b in _boxes(bp)}
    wo = widget_order(bp)
    key = lambda b: wo.get(by_code.get(b[0])) or (pages.get(b[0]), 10 ** 6)       # noqa: E731
    blocks.sort(key=key)
    t["blocks"] = blocks
    rec["grids"] = [e for e in rec["grids"] if not (e.get("source") == "type" and e.get("type") == tid
                                                    and e.get("page") == page)]
    here = [b for b in blocks if pages.get(b[0]) == page]
    group, now = None, time.strftime("%Y-%m-%d %H:%M:%S")
    if len(here) >= 2:
        group = gc._new_id(rec, page, "block")
        rec["grids"].append({"id": group, "kind": "block", "page": page, "source": "type", "status": "active",
                             "type": tid, "when": now,
                             "cells": gc._compact([[c, i, k] for i, b in enumerate(here) for k, c in enumerate(b)])})
    t["groups"] = sorted({e["id"] for e in rec["grids"] if e.get("source") == "type" and e.get("type") == tid
                          and e.get("status") == "active"})
    gc._save_set(bid, rec)
    left = gc.exclusive(bid, bp, [group]) if group else []
    return {"id": tid, "block": blocks.index(codes) + 1, "of": len(blocks), "page": page, "group": group, "left": left}


def listing(bp: dict, rec: dict) -> list[dict]:
    """The form's block types for the page: [{id, page, rect, boxes, groups, blocks: [{n, page, bbox}]}], each block
    with its number in the type's order and the box around its fields."""
    by_code = {str(s.get("x_petey_id")): n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    boxes = {b["code"]: b for b in _boxes(bp)}
    out = []
    for t in rec.get("types") or []:
        blocks = []
        for i, b in enumerate(t["blocks"], 1):
            bs = [boxes[c] for c in b if c in boxes]
            if bs:
                blocks.append({"n": i, "page": bs[0]["page"], "template": b == [x["code"] for x in t["boxes"]], "bbox": [min(x["rect"][0] for x in bs), min(x["rect"][1] for x in bs),
                                                                       max(x["rect"][2] for x in bs), max(x["rect"][3] for x in bs)]})
        out.append({"id": t["id"], "page": t["page"], "rect": t["rect"], "boxes": len(t["boxes"]),
                    "groups": t.get("groups") or [], "blocks": blocks})
    return out


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
