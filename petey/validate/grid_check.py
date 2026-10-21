"""Grids and blocks: the review page's view for tables (Andrew, 2026-10-16: "add a 'grids and blocks' view to the
reviewer and just route the skill through there ... a button to check and validate it in one click").

Every numbered table and repeated block the layout code finds (eval/grid_naming.grids) is listed with its cells, and
one click runs the lightest method that settles it, in order:

  1. the code check: already on pattern -> its cells accepted, nothing else;
  2. the resolver (grid_naming.resolve): each position's wording, settled by the name-check model against the
     position's shared caption, then the numbers (1..N, unless the series continues from another page or the
     numbers are printed line numbers) -> the renames applied as Claude's, the cells accepted;
  3. Jev: a position the model could not settle, chosen from its candidate wordings with the page image ->
     resolved again with that wording, applied and accepted;
  4. Opus (the chat with the grid-validation skill's rules, this page only): only what is still unclear; its
     proposals come back for the person to tick, nothing applied.

Nothing is stored about the tables in the blueprint (they may get names there later). The form's grids and blocks
are kept apart from it (2026-10-17, `listing`: runs/hand_review/grids/<id>.json): ids that last (p1-T2, p2-B1),
cancelled ones ("not a grid or block"), ones the person drew around an area and ones combined from others, each with
its provenance (finder, person, combined).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import grid_naming as G  # noqa: E402

from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

_LINES: dict[str, dict] = {}
JEV_MIN = 0.5            # Jev's probability for its chosen wording, below which the position stays unsure


def _lines(blank: Path) -> dict:
    from petey.validate.field_chain import _page_lines
    k = str(blank)
    if k not in _LINES:
        _LINES[k] = _page_lines(k)
    return _LINES[k]


NOT_GRIDS = h.OUT / "not_grids.json"      # {bid: [{page, cells, when}]}: what the person said is not a grid or block


def not_grids(bid: str) -> list[dict]:
    """The tables the person set aside as not a grid or block (Andrew, 2026-10-16: 'lets add a "not a grid or block"
    button'), by page and cell names, so the decision outlives renumbering of the listing; also a record of where the
    finder is wrong."""
    import json
    try:
        return (json.loads(NOT_GRIDS.read_text(encoding="utf-8")) if NOT_GRIDS.exists() else {}).get(bid) or []
    except (OSError, ValueError):
        return []


def set_not_grid(bid: str, page: int, cells: list[str], on: bool) -> list[dict]:
    import json
    import time
    rec = json.loads(NOT_GRIDS.read_text(encoding="utf-8")) if NOT_GRIDS.exists() else {}
    have = [e for e in rec.get(bid) or [] if not (e["page"] == page and _same(e["cells"], cells))]
    if on:
        have.append({"page": page, "cells": sorted(cells), "when": time.strftime("%Y-%m-%d %H:%M:%S")})
    rec[bid] = have
    if not have:
        rec.pop(bid)
    NOT_GRIDS.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    return have


def _same(a, b) -> bool:
    """The same table, near enough: most of its cells (a rename or a cell joining moves a few)."""
    a, b = set(a), set(b)
    return bool(a and b) and len(a & b) >= 0.8 * max(len(a), len(b))


def dismissed(entries: list[dict], page: int, cells) -> bool:
    return any(e["page"] == page and _same(e["cells"], cells) for e in entries)


# ------------------------------------------------------------------ the form's grids and blocks, kept (2026-10-17)
# Andrew: "add IDs to grids and blocks; the ability to cancel; to create new ones by selecting an area; to combine
# existing ones of the same kind" and "they should be the same button -- the provenance will distinguish them".
# runs/hand_review/grids/<bid>.json: {"grids": [entry], "next": {"1T": 3}}; an entry is {id (p1-T2 / p1-B1), kind
# (table | block), page, source (finder | person | combined), status (active | cancelled | combined: taken into
# another), cells: [[field code, row, col]], from: [ids], into: id, when}. Cells are kept by field code (x_petey_id),
# so a rename moves nothing. The finder runs on every read; its grids are matched to their entries by cells (most
# in common, same page) and keep their ids; a new one gets the next id. A grid the person made or combined hides the
# finder's grids that are mostly inside it.

SETS = h.OUT / "grids"


def _set_path(bid: str) -> Path:
    return SETS / f"{bid}.json"


def load_set(bid: str) -> dict:
    import json
    p = _set_path(bid)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"grids": [], "next": {}}
    except (OSError, ValueError):
        return {"grids": [], "next": {}}


def _save_set(bid: str, rec: dict) -> None:
    import json
    SETS.mkdir(parents=True, exist_ok=True)
    _set_path(bid).write_text(json.dumps(rec, indent=1), encoding="utf-8")


def _new_id(rec: dict, page: int, kind: str) -> str:
    """p1-T2 for a table (grid), p2-BG1 for a block group."""
    tag = "BG" if kind == "block" else "T"
    k = f"{page}{tag}"
    n = rec.setdefault("next", {}).get(k, 1)
    rec["next"][k] = n + 1
    return f"p{page}-{tag}{n}"


def found(bp: dict) -> list[list[dict]]:
    """What the finders find (2026-10-18: grids and blocks apart): block groups (eval/block_groups.py), and the
    numbered tables (grid_naming, without its old blocks) that are not mostly inside one of them."""
    import block_groups
    groups = block_groups.find(bp)
    inside = [{c["name"] for c in g} for g in groups]
    tables = [g for g in G.grids(bp, blocks=False) if G.iterated(g)
              and not any(len({c["name"] for c in g} & ns) >= 0.5 * len(g) for ns in inside)]
    return tables + groups


def listing(bid: str, bp: dict) -> list[dict]:
    """The form's grids and blocks: [{id, kind, page, source, status, from, into, when, grid}] where `grid` is the
    cells as the checks take them ([{name, page, row, col, block?}]). Every finder grid gets (and keeps) an id; the
    record is written when one is new."""
    import time
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    code = {n: str(s.get("x_petey_id")) for n, s in fields.items() if s.get("x_petey_id") is not None}
    name = {c: n for n, c in code.items()}
    rec, changed = load_set(bid), False
    legacy = not_grids(bid)                                   # "not a grid or block" before ids (2026-10-16)
    out, claimed = [], set()

    def at(g):                                  # top, then left: new ids are given in reading order
        rs = [r for r in (_rect(bp, c["name"]) for c in g) if r]
        return (g[0]["page"], min((r[1] for r in rs), default=0), min((r[0] for r in rs), default=0))
    for g in sorted(found(bp), key=at):
        page, kind = g[0]["page"], "block" if g[0].get("block") else "table"
        codes = [code.get(c["name"], c["name"]) for c in g]
        e = next((e for e in rec["grids"] if e["source"] == "finder" and e["page"] == page and id(e) not in claimed
                  and _same([c[0] for c in e["cells"]], codes)), None)
        if e is None:
            e = {"id": _new_id(rec, page, kind), "kind": kind, "page": page, "source": "finder",
                 "status": "cancelled" if dismissed(legacy, page, [c["name"] for c in g]) else "active",
                 "when": time.strftime("%Y-%m-%d %H:%M:%S")}
            rec["grids"].append(e)
            changed = True
        if [list(x) for x in e.get("cells") or []] != [[cd, c["row"], c["col"]] for cd, c in zip(codes, g)]:
            e["cells"] = [[cd, c["row"], c["col"]] for cd, c in zip(codes, g)]
            changed = True
        claimed.add(id(e))
        out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when", "blocks", "parts")},
                    "grid": [dict(c) for c in g]})
    for e in rec["grids"]:
        if e["source"] == "finder":
            continue
        cells = [{"name": name[c], "page": e["page"], "row": r, "col": k, **({"block": True} if e["kind"] == "block" else {})}
                 for c, r, k in e["cells"] if c in name]
        if cells:
            out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when", "blocks", "parts")},
                        "grid": cells})
    mine = [set(c["name"] for c in t["grid"]) for t in out if t["source"] != "finder" and t["status"] == "active"]
    for t in out:                   # a finder grid mostly inside one the person made or combined is shown as that one
        if t["source"] == "finder" and t["status"] == "active" and any(
                len(set(c["name"] for c in t["grid"]) & m) >= 0.5 * len(t["grid"]) for m in mine):
            t["status"] = "replaced"
    if changed:
        _save_set(bid, rec)
    return out


def set_status(bid: str, gid: str, cancel: bool, bp: Optional[dict] = None) -> dict:
    """Cancel a grid or block (not a grid or block), or restore it. Cancelling a combined one gives its parts back.
    With `bp`, what comes back takes its fields from the others of its kind (`exclusive`)."""
    import time
    rec = load_set(bid)
    e = next((e for e in rec["grids"] if e["id"] == gid), None)
    if e is None:
        raise ValueError(f"no grid {gid}")
    e["status"] = "cancelled" if cancel else "active"
    e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    back = [] if cancel else [gid]
    if e["source"] in ("combined", "edited"):
        for x in rec["grids"]:
            if x["id"] in (e.get("from") or []) and x.get("into") == gid:
                x["status"] = "active" if cancel else "combined"
                back += [x["id"]] if cancel else []
    if cancel:
        _give_back(rec, gid)
    _save_set(bid, rec)
    return {"id": gid, "status": e["status"], "left": exclusive(bid, bp, back) if bp is not None and back else []}


def _give_back(rec: dict, gid: str) -> None:
    """Cancelling one that took fields from others (`exclusive`) gives them back: each table or block group it took
    from as it was, if it has not changed since and the fields are in no other one now."""
    held = {c[0] for e in rec["grids"] if e["status"] == "active" and e["id"] != gid for c in e.get("cells") or []}
    for x in rec["grids"]:
        u = x.get("undo") or {}
        if u.get("by") != gid or x.get("cells") != u.get("after"):
            continue
        if u.get("drop"):                        # the finder's, whole again; the copy without the fields goes
            orig = next((o for o in rec["grids"] if o["id"] in (x.get("from") or []) and o.get("into") == x["id"]), None)
            if orig is None or x["status"] != "active":
                continue
            x["status"] = "undone"
            orig["status"] = "active"
            orig.pop("into", None)
        else:
            if {c[0] for c in u["cells"]} - {c[0] for c in x["cells"]} & held:
                continue
            x["cells"], x["status"] = u["cells"], "active"
            x.pop("into", None)
        x.pop("undo", None)


def exclusive(bid: str, bp: dict, winners: list[str]) -> list[str]:
    """A field is in one table and one block group at most (Andrew, 2026-10-20: "if you drag it into a group, it should
    join that one and leave the other one"): the fields of `winners` (what was just drawn, combined, laid out or
    restored) leave every other table, or block group, shown on the form. One the finder found becomes an edited copy
    without them; one left with fewer than two fields, or a block group with fewer than two blocks, is emptied.
    Cancelling the winner gives them back (`_give_back`). A table inside a block group is one of its parts, not a second membership,
    so tables and block groups are kept apart. What left where, for the page to say."""
    import time
    shown = {t["id"] for t in listing(bid, bp) if t["status"] == "active"}     # also records any new finder ids
    rec = load_set(bid)
    by = {e["id"]: e for e in rec["grids"]}
    said, changed = [], False
    for w in winners:
        we = by.get(w)
        if we is None or we["status"] != "active":
            continue
        mine = {c[0] for c in we.get("cells") or []}
        for e in list(rec["grids"]):
            if e["id"] == w or e["kind"] != we["kind"] or e["id"] not in shown or e["status"] != "active":
                continue
            left = [list(c) for c in e.get("cells") or [] if c[0] not in mine]
            n = len(e.get("cells") or []) - len(left)
            if not n:
                continue
            small = len(left) < 2 or (e["kind"] == "block" and len({c[1] for c in left}) < 2)
            if small:
                e["undo"] = {"by": w, "cells": e.get("cells"), "after": e.get("cells")}
                e["status"], e["into"] = "emptied", w
                said.append(f"{e['id']} emptied ({n} field{'s' if n != 1 else ''} to {w})")
            elif e["source"] == "finder":
                c = {"id": _new_id(rec, e["page"], e["kind"]), "kind": e["kind"], "page": e["page"], "source": "edited",
                     "status": "active", "cells": _compact(left), "from": [e["id"]], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
                c["undo"] = {"by": w, "drop": True, "after": c["cells"]}
                e["status"], e["into"] = "combined", c["id"]
                rec["grids"].append(c)
                by[c["id"]] = c
                shown.add(c["id"])
                said.append(f"{n} field{'s' if n != 1 else ''} left {e['id']} (now {c['id']})")
            else:
                e["undo"] = {"by": w, "cells": e.get("cells"), "after": _compact(left)}
                e["cells"] = e["undo"]["after"]
                e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
                said.append(f"{n} field{'s' if n != 1 else ''} left {e['id']}")
            changed = True
    if changed:
        _save_set(bid, rec)
    return said


def arrange(bp: dict, names: list[str], kind: str) -> list[dict]:
    """Rows and columns for fields the person grouped (an area drawn, or grids combined), from their boxes on the page.
    Lines: a box joins a line it overlaps from top to bottom by half the smaller height; ordinary boxes widen the
    line, a box much taller than most (Form 8949's description, IMM 5645's relationship) joins the line its top is on
    without widening it. Columns: boxes overlapping across by half the narrower (two on one line and column are two
    columns). A table: each line a row. A block: the step down the page at which most lines come again with the
    same boxes (column and height) is the repeat; each repeat a row, each column at each line within the repeat a
    slot; slots left to right, stacked ones top first."""
    boxes = [(n, _rect(bp, n)) for n in names]
    boxes = [(n, r) for n, r in boxes if r]
    if not boxes:
        return []
    hs = sorted(r[3] - r[1] for _n, r in boxes)
    tall = 1.6 * hs[len(hs) // 2]
    lines: list[dict] = []
    for n, r in sorted(boxes, key=lambda b: (b[1][1], b[1][3] - b[1][1])):
        h = r[3] - r[1]
        ln = next((ln for ln in lines if min(ln["y1"], r[3]) - max(ln["y0"], r[1])
                   >= 0.5 * min(ln["y1"] - ln["y0"], h)), None)
        if ln is None:
            ln = {"y0": r[1], "y1": r[3] if h <= tall else r[1] + hs[len(hs) // 2], "cells": []}
            lines.append(ln)
        elif h <= tall:
            ln["y0"], ln["y1"] = min(ln["y0"], r[1]), max(ln["y1"], r[3])
        ln["cells"].append((n, r))
    lines.sort(key=lambda ln: ln["y0"])
    cols: list[list] = []
    for _n, r in sorted(boxes, key=lambda b: (b[1][0], b[1][2])):
        c = next((c for c in cols if min(c[1], r[2]) - max(c[0], r[0]) >= 0.5 * min(c[1] - c[0], r[2] - r[0])), None)
        if c is None:
            cols.append([r[0], r[2]])
    cols.sort()
    # the column it overlaps most; a wide box overlapping several alike (N-600 p14's additional information box over
    # the page, part and item columns, 60 pt each, the winner set by float noise, 2026-10-20): the one its left edge is at
    col_of = lambda r: max(range(len(cols)), key=lambda i: (round(min(cols[i][1], r[2]) - max(cols[i][0], r[0])),  # noqa: E731
                                                            -abs(cols[i][0] - r[0])))
    placed = []                                  # (line, column, rank on that line and column, name, box)
    for li, ln in enumerate(lines):
        seen: dict = {}
        for n, r in sorted(ln["cells"], key=lambda b: b[1][0]):
            ci = col_of(r)
            placed.append((li, ci, seen.get(ci, 0), n, r))
            seen[ci] = seen.get(ci, 0) + 1
    row_of, slot_of = {}, {}
    if kind == "block" and len(lines) > 1:
        # a line's boxes as (column, height); heights alike within 2 pt or a quarter (a bucket of 4 pt split I-526
        # p18's 54 pt boxes, 53.99997 against 54.0; N-600 p14's text boxes are 72 pt in two blocks, 90 in two, 2026-10-20)
        sig = [[(ci, r[3] - r[1]) for li2, ci, _k, _n, r in placed if li2 == li] for li in range(len(lines))]
        tops = [ln["y0"] for ln in lines]

        def alike(i, j, loose=True):
            left, hit = list(sig[j]), 0
            for ci, hh in sig[i]:
                m = next((x for x in left if x[0] == ci
                          and abs(x[1] - hh) <= (max(2, 0.25 * max(x[1], hh)) if loose else 2)), None)
                if m:
                    left.remove(m)
                    hit += 1
            return hit >= 0.8 * (len(sig[i]) + len(sig[j]) - hit)

        def score(step):                         # the share of lines that come again one step lower, alike
            ok = tried = 0
            for i, t in enumerate(tops):
                if t + step > tops[-1] + 3:
                    continue
                tried += 1
                j = min(range(len(tops)), key=lambda j: abs(tops[j] - (t + step)))
                ok += abs(tops[j] - (t + step)) <= 3 and alike(i, j, loose=False)
            return ok / tried if tried else 0
        # the lines come again every p lines, alike, however far apart the repeats sit (I-526 p18, 2026-10-20:
        # four blocks 102 pt apart, the fifth 108; the even step below took one pair of lines for a repeat)
        p = next((p for p in range(2, len(lines) // 2 + 1) if len(lines) % p == 0
                  and all(alike(i, i + p) for i in range(len(lines) - p))
                  and not all(alike(i, i + 1) for i in range(p - 1))), None)
        if p:
            row_of = {li: li // p for li in range(len(lines))}
            slot_of = {li: li % p for li in range(len(lines))}
        elif (side := _side_by_side(boxes)):     # repeats across the page, not down it (CBP 7512 p2's transfers)
            out = []
            for n, (blk, pos) in side.items():
                spec = bp["fields"][n]
                w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
                out.append({"name": n, "page": w.get("page"), "row": blk, "col": pos, "block": True})
            return sorted(out, key=lambda c: (c["row"], c["col"]))
        else:                                    # a repeat with a line missing: an even step down the page
            steps = sorted({round(b - a, 1) for i, a in enumerate(tops) for b in tops[i + 1:] if b - a > 3})
            step = next((st for st in steps if score(st) >= 0.8), None)
            if step:
                for li, ln in enumerate(lines):
                    row_of[li] = int((ln["y0"] - tops[0] + 3) // step)
                    slot_of[li] = round((ln["y0"] - tops[0] - row_of[li] * step) / 3)
    if not row_of:                               # a table (or a block with no repeat found): a line is a row
        row_of = {li: li for li in range(len(lines))}
        slot_of = {li: 0 for li in range(len(lines))}
    slots = sorted({(ci, k, slot_of[li]) for li, ci, k, _n, _r in placed}, key=lambda t: (t[0], t[2], t[1]))
    slot_ix = {s_: i for i, s_ in enumerate(slots)}
    rows = sorted(set(row_of.values()))
    out = []
    for li, ci, k, n, _r in placed:
        spec = bp["fields"][n]
        w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
        cell = {"name": n, "page": w.get("page"), "row": rows.index(row_of[li]), "col": slot_ix[(ci, k, slot_of[li])]}
        if kind == "block":
            cell["block"] = True
        out.append(cell)
    return out


def _side_by_side(boxes: list[tuple]) -> Optional[dict]:
    """{name: (block, position)} when the boxes are two or more copies of one block set side by side (CBP 7512 page 2,
    2026-10-20: the two certificates of transfer, every box of the second 225 pt right of its twin in the first), else
    None. Each box's twin one step right sits on its line (3 pt), is its size (2 pt high, a tenth wide) and the step
    is the same for all (4 pt); the twins chain left to right, every chain as long, and every box in one. A chain is
    a position, numbered by where its first box is (top, then left); a box's place in its chain is its block."""
    if len(boxes) < 4:
        return None

    def twin(a, b, d):
        return (abs(b[1] - a[1]) <= 3 and abs((b[3] - b[1]) - (a[3] - a[1])) <= 2
                and abs((b[2] - b[0]) - (a[2] - a[0])) <= max(3, 0.1 * (a[2] - a[0])) and abs(b[0] - a[0] - d) <= 4)
    steps = sorted({round(rb[0] - ra[0]) for _a, ra in boxes for _b, rb in boxes
                    if rb[0] - ra[0] > 20 and abs(rb[1] - ra[1]) <= 3})
    for d in steps:
        nxt = {}
        for a, ra in boxes:
            m = [b for b, rb in boxes if b != a and twin(ra, rb, d)]
            if len(m) > 1:
                break
            if m:
                nxt[a] = m[0]
        else:
            if not nxt or len(set(nxt.values())) < len(nxt):
                continue
            starts = [a for a, _r in boxes if a not in set(nxt.values())]
            chains = []
            for a in starts:
                ch = [a]
                while ch[-1] in nxt:
                    ch.append(nxt[ch[-1]])
                chains.append(ch)
            if len({len(c) for c in chains}) != 1 or len(chains[0]) < 2 or sum(map(len, chains)) != len(boxes):
                continue
            rect = dict(boxes)
            chains.sort(key=lambda c: (round(rect[c[0]][1] / 3), rect[c[0]][0]))
            return {n: (blk, pos) for pos, c in enumerate(chains) for blk, n in enumerate(c)}
    return None


def _in_area(bp: dict, page: int, rect) -> list[str]:
    """The fields whose box (an option group's box around its boxes) has its middle inside the area."""
    out = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        ws = [s["widget"]] if s.get("widget") else list((s.get("widgets") or {}).values())
        if not ws or any(w.get("page") != page for w in ws):
            continue
        r = _rect(bp, n)
        if r and rect[0] <= (r[0] + r[2]) / 2 <= rect[2] and rect[1] <= (r[1] + r[3]) / 2 <= rect[3]:
            out.append(n)
    return out


def create(bid: str, bp: dict, page: int, rect, kind: str) -> dict:
    """A grid or block the person drew: the fields inside the area, arranged (`arrange`)."""
    names = _in_area(bp, page, rect)
    if len(names) < 2:
        raise ValueError("fewer than two fields in that area")
    cells = arrange(bp, names, kind)
    out = _add(bid, bp, page, kind, cells, "person", [])
    return {**out, "left": exclusive(bid, bp, [out["id"]])}


def combine(bid: str, bp: dict, gids: list[str]) -> dict:
    """Two or more grids (or two or more blocks) on one page as one: their cells arranged again together. The parts are
    kept, marked as taken into the new one; cancelling it gives them back."""
    have = {t["id"]: t for t in listing(bid, bp)}
    parts = [have[g] for g in gids if g in have]
    if len(parts) < 2:
        raise ValueError("pick two or more")
    if len({t["kind"] for t in parts}) > 1:
        raise ValueError("a table and a block cannot be combined")
    if len({t["page"] for t in parts}) > 1:
        raise ValueError("combining across pages is not supported yet")
    names = list(dict.fromkeys(c["name"] for t in parts for c in t["grid"]))
    out = _add(bid, bp, parts[0]["page"], parts[0]["kind"], arrange(bp, names, parts[0]["kind"]), "combined",
               [t["id"] for t in parts])
    rec = load_set(bid)
    for e in rec["grids"]:
        if e["id"] in gids:
            e["status"], e["into"] = "combined", out["id"]
    _save_set(bid, rec)
    return {**out, "left": exclusive(bid, bp, [out["id"]])}


def _add(bid: str, bp: dict, page: int, kind: str, cells: list[dict], source: str, parts: list[str]) -> dict:
    import time
    code = {n: str(s.get("x_petey_id")) for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    rec = load_set(bid)
    e = {"id": _new_id(rec, page, kind), "kind": kind, "page": page, "source": source, "status": "active",
         "cells": [[code[c["name"]], c["row"], c["col"]] for c in cells], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    if parts:
        e["from"] = parts
    rec["grids"].append(e)
    _save_set(bid, rec)
    return {"id": e["id"], "cells": len(cells)}


# ------------------------------------------------------------------ a block group's layout (2026-10-19)
# Andrew, on je__cra_t5013 p1-BG2 (two slips): "we need some kind of way to edit the block layout". The repeat step
# `arrange` looks for misses when one block's boxes sit a few points off the other's (slip 2's header boxes shift
# right), and a table's two panes read as one line (the finder's T2: T6 and T7 side by side). So the person marks
# the blocks (`layout`): the fields in each, paired with the first block's, a kept table inside a block taken whole
# (T6 in slip 1 pairs with T8 in slip 2 cell by cell), the rest by where they sit inside their block. The pairing is
# then edited by hand (`set_cells`): swap, move, take out, add. The entry keeps `blocks` (the areas drawn) and
# `parts` (which kept tables fill which positions). A finder's block group is edited as a copy ("edited", `from` the
# finder's), since the finder's entry follows the finder on every read; cancelling the copy gives the original back.

def _editable(rec: dict, gid: str) -> dict:
    import time
    e = next((e for e in rec["grids"] if e["id"] == gid), None)
    if e is None:
        raise ValueError(f"no block group {gid}")
    if e["kind"] != "block":
        raise ValueError(f"{gid} is a table, not a block group")
    if e["source"] != "finder":
        return e
    c = {"id": _new_id(rec, e["page"], "block"), "kind": "block", "page": e["page"], "source": "edited",
         "status": "active", "cells": [list(x) for x in e.get("cells") or []], "from": [gid],
         "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    e["status"], e["into"] = "combined", c["id"]
    rec["grids"].append(c)
    return c


def _units(bp: dict, names: list[str], tables: list[dict]) -> tuple[list[dict], tuple]:
    """One block's parts: the kept tables mostly inside it, whole, and its other fields one by one; each with its box
    and its place relative to the block's top left (the block's boxes, not the area drawn: drawn by hand, it is loose)."""
    rect = {n: _rect(bp, n) for n in names}
    rect = {n: r for n, r in rect.items() if r}
    if not rect:
        return [], (0, 0)
    o = (min(r[0] for r in rect.values()), min(r[1] for r in rect.values()))
    units, used = [], set()
    for t in tables:
        mine = [c for c in t["grid"] if c["name"] in rect and c["name"] not in used]
        if len(mine) < 0.5 * len(t["grid"]) or len(mine) < 2:
            continue
        rs = [rect[c["name"]] for c in mine]
        units.append({"table": t["id"], "cells": {(c["row"], c["col"]): c["name"] for c in mine},
                      "shape": (max(c["row"] for c in t["grid"]) + 1, max(c["col"] for c in t["grid"]) + 1),
                      "box": [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]})
        used |= {c["name"] for c in mine}
    units += [{"name": n, "box": r} for n, r in rect.items() if n not in used]
    for u in units:
        b = u["box"]
        u["rel"] = ((b[0] + b[2]) / 2 - o[0], (b[1] + b[3]) / 2 - o[1])
    units.sort(key=lambda u: (round(u["box"][1] / 4), u["box"][0]))
    return units, o


def _pair(ref: list[dict], other: list[dict]) -> dict[int, int]:
    """Which of `other`'s parts is which of `ref`'s: tables with tables (same shape first), fields with fields, by
    where they sit in their block, the least total distance; a pair more than PAIR_MAX points apart is no pair."""
    from scipy.optimize import linear_sum_assignment
    out = {}
    for is_tab in (True, False):
        R = [i for i, u in enumerate(ref) if ("table" in u) == is_tab]
        O = [j for j, u in enumerate(other) if ("table" in u) == is_tab]
        if not R or not O:
            continue
        cost = [[((ref[i]["rel"][0] - other[j]["rel"][0]) ** 2 + (ref[i]["rel"][1] - other[j]["rel"][1]) ** 2) ** 0.5
                 + (0 if not is_tab or ref[i]["shape"] == other[j]["shape"] else PAIR_MAX) for j in O] for i in R]
        for a, b in zip(*linear_sum_assignment(cost)):
            if cost[a][b] <= PAIR_MAX:
                out[R[a]] = O[b]
    return out


PAIR_MAX = 60.0          # points: further apart than this inside their blocks, two fields are not the same position


def layout(bid: str, bp: dict, gid: str, blocks: list) -> dict:
    """The block group as the person marked it: `blocks` the areas drawn, one per block, in order. Each block's
    fields are the ones inside its area; the first block sets the positions (its parts top to bottom, left to right,
    a table's cells row by row), the others' parts are paired with them (`_pair`), a table's cells by row and column.
    A field with no pair gets a position of its own."""
    import time
    if len(blocks) < 2:
        raise ValueError("mark two or more blocks")
    rec = load_set(bid)
    e = _editable(rec, gid)
    page = e["page"]
    code = {n: str(s.get("x_petey_id")) for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    tables = [t for t in listing(bid, bp) if t["kind"] == "table" and t["status"] == "active" and t["page"] == page]
    taken: set = set()
    per = []
    for r in blocks:
        names = [n for n in _in_area(bp, page, r) if n not in taken]
        taken |= set(names)
        per.append(_units(bp, names, tables)[0])
    if sum(1 for u in per if u) < 2:
        raise ValueError("fewer than two of the blocks have fields in them")
    ref = per[0]
    slots: list = []                      # a position: (ref unit index, table cell or None)
    for i, u in enumerate(ref):
        slots += [(i, rc) for rc in sorted(u["cells"])] if "table" in u else [(i, None)]
    cells = []
    parts = []
    for i, u in enumerate(ref):
        if "table" in u:
            first = slots.index((i, min(u["cells"])))
            parts.append({"from": first + 1, "to": first + len(u["cells"]), "tables": [u["table"]]})
    for b, units in enumerate(per):
        pair = {i: i for i in range(len(units))} if b == 0 else _pair(ref, units)
        back = {j: i for i, j in pair.items()}
        for i, j in pair.items():
            if b and "table" in ref[i]:
                next(p for p in parts if p["tables"][0] == ref[i]["table"])["tables"].append(units[j]["table"])
        for j, u in enumerate(units):
            i = back.get(j)
            if i is None:                                   # no pair in the first block: positions of its own
                for n in (u["cells"].values() if "table" in u else [u["name"]]):
                    slots.append(("extra", n))
                    cells.append([code[n], b, len(slots) - 1])
                continue
            if "table" in u:
                for rc, n in u["cells"].items():
                    k = slots.index((i, rc)) if (i, rc) in slots else None
                    if k is None:
                        slots.append(("extra", n))
                        k = len(slots) - 1
                    cells.append([code[n], b, k])
            else:
                cells.append([code[u["name"]], b, slots.index((i, None))])
    e["cells"] = _compact(cells)
    e["blocks"] = [list(map(float, r)) for r in blocks]
    e["parts"] = parts
    e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_set(bid, rec)
    return {"id": e["id"], "cells": len(cells), "blocks": len(blocks), "positions": len({c[2] for c in e["cells"]}),
            "left": exclusive(bid, bp, [e["id"]])}


def _compact(cells: list) -> list:
    """Positions numbered 0..n-1 in their order (an emptied one dropped), blocks likewise; cells by block, then
    position."""
    pos = {k: i for i, k in enumerate(sorted({c[2] for c in cells}))}
    blk = {k: i for i, k in enumerate(sorted({c[1] for c in cells}))}
    return sorted([[c[0], blk[c[1]], pos[c[2]]] for c in cells], key=lambda c: (c[1], c[2]))


def set_cells(bid: str, bp: dict, gid: str, cells: list) -> dict:
    """The layout as edited on the card: [[field code, block, position]] (swapped, moved, taken out, added). A field
    once, a block and position once; positions and blocks renumbered in order."""
    import time
    have = {str(s.get("x_petey_id")) for s in (bp.get("fields") or {}).values() if isinstance(s, dict)}
    cells = [[str(c), int(r), int(k)] for c, r, k in cells]
    if len({c[0] for c in cells}) < len(cells):
        raise ValueError("a field is in two places")
    if len({(c[1], c[2]) for c in cells}) < len(cells):
        raise ValueError("two fields in one place")
    if any(c[0] not in have for c in cells):
        raise ValueError("a field that is not on the form")
    if len({c[1] for c in cells}) < 2:
        raise ValueError("a block group needs two or more blocks")
    rec = load_set(bid)
    e = _editable(rec, gid)
    e["cells"] = _compact(cells)
    e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_set(bid, rec)
    return {"id": e["id"], "cells": len(cells), "left": exclusive(bid, bp, [e["id"]])}


def page_fields(bp: dict, page: int) -> list[dict]:
    """Every field on the page with its code and box: what can be added to a block by clicking it."""
    out = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("x_petey_id") is None:
            continue
        ws = [s["widget"]] if s.get("widget") else list((s.get("widgets") or {}).values())
        r = _rect(bp, n)
        if r and ws and all(w.get("page") == page for w in ws):
            out.append({"name": n, "code": str(s["x_petey_id"]), "rect": r})
    return out


def _rect(bp: dict, name: str):
    """A field's box; an option group's (a column of a table or block since 2026-10-16) is the box around its boxes."""
    spec = (bp.get("fields") or {}).get(name) or {}
    w = spec.get("widget") or {}
    if w.get("rect") or not spec.get("widgets"):
        return w.get("rect")
    rs = [x["rect"] for x in spec["widgets"].values() if x.get("rect")]
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)] if rs else None


_HEADS: dict[str, dict] = {}


def _title(bbox, page_lines, heads=None, captions=()) -> Optional[str]:
    """The heading printed above a table: the nearest section heading (bold, capitals, larger type, Section / Part;
    `cheap_names.headings`) above it that overlaps it across, within 250 pt (ACORD 126: SCHEDULE OF HAZARDS, not
    its column header PREM/OPS); else the nearest line within 60 pt above."""
    from cheap_names import JUNK
    width = bbox[2] - bbox[0]

    caps = {" ".join(str(c).split()).lower() for c in captions if c}

    def titleish(bb, t):                 # a title starts at the table's left edge or spans much of it; not a column
        if " ".join(t.split()).lower() in caps:                                  # header (the table's own captions),
            return False                                                         # an instruction or a caption
        if __import__("re").match(r"^\(?\s*(rev\.?|revised|form\b|page\b|omb\b)", t.strip(), __import__("re").I):
            return False                                                         # a revision or form stamp
        return ((bb[0] <= bbox[0] + 12 or bb[2] - bb[0] >= 0.3 * width)
                and not JUNK.search(t) and not t.rstrip().endswith(":") and any(ch.isalpha() for ch in t))
    hs = [(bbox[1] - bb[3], " ".join(t.split())) for bb, t in heads or []
          if 0 <= bbox[1] - bb[3] <= 250 and min(bbox[2], bb[2]) - max(bbox[0], bb[0]) > 0 and titleish(bb, t)]
    if hs:
        return min(hs)[1]
    best = None
    for bb, t in page_lines or []:
        gap = bbox[1] - bb[3]
        if 0 <= gap <= 60 and min(bbox[2], bb[2]) - max(bbox[0], bb[0]) > 0 and len(t.split()) <= 12 and titleish(bb, t):
            if best is None or gap < best[0]:
                best = (gap, " ".join(t.split()))
    return best[1] if best else None


def tables(bp: dict, bid: Optional[str] = None, kind: Optional[str] = None) -> list[dict]:
    """[{id, page, kind, rows, cols, lines, positions, title, bbox, cells: [{name, rect, row, col}], on_pattern, why,
    source, status, from, into}] for every numbered table and block, in page order; with `bid`, the form's kept
    grids (`listing`: ids that last, cancelled ones, the person's and combined ones). `lines` is how many rows (or
    blocks) it numbers, `positions` each column (or a block's field) with its wording and the caption printed for
    it."""
    blank = resolve_blank(bp)
    page_text = _lines(blank) if blank and blank.exists() else {}
    if blank and blank.exists() and str(blank) not in _HEADS:
        from cheap_names import headings
        _HEADS[str(blank)] = headings(blank)
    heads = _HEADS.get(str(blank), {}) if blank else {}
    out, n = [], {}
    if bid:
        entries = [t for t in listing(bid, bp) if t["status"] in ("active", "cancelled") and kind in (None, t["kind"])]
    else:
        entries = []
        for g in G.grids(bp):
            if G.iterated(g):
                n[g[0]["page"]] = n.get(g[0]["page"], 0) + 1
                entries.append({"id": f"p{g[0]['page']}t{n[g[0]['page']]}", "source": "finder", "status": "active",
                                "kind": "block" if g[0].get("block") else "table", "grid": g})
    for e in entries:
        g = e["grid"]
        page = g[0]["page"]
        cells = [dict(c, rect=_rect(bp, c["name"])) for c in g]
        rs = [c["rect"] for c in cells if c["rect"]]
        if not rs:
            continue
        ok, why = G.on_pattern(g)
        reading = "columns" if G.keyed(g) else G.breaks(g)[0]      # lines named by role or kind are the rows
        pos_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
        how = "block" if g[0].get("block") else reading
        body = G.body(g)
        body_names = {c["name"] for c in body}             # a totals row is outside the check (and the validation)
        positions = []
        F = G._Frame(g) if body else None      # the number that varies down a column is its N, not the last one
        same_axis = bool(F) and F.pos_axis == pos_axis
        number = F.numbers(bp, g, page_text, {})[0] if same_axis and not G.keyed(g) else {}
        for k in sorted({c[pos_axis] for c in body}):
            pcs = [c for c in body if c[pos_axis] == k]
            wordings = sorted({(F.pat_of(c) if same_axis else (G._pattern(c["name"]) or c["name"])).replace("_N", "_#") for c in pcs})
            # cells whose number is not their line's (a column numbered from 2): the column's standardize button
            off = sum(1 for c in pcs if number and number.get(c[num_axis]) is not None and k not in F.locked
                      and (F.num_of(c) or "").isdigit() and int(F.num_of(c)) != number[c[num_axis]]) if same_axis else 0
            positions.append({"pos": k + 1, "wordings": wordings, "off": off, "caption": G.position_caption(bp, pcs, how, page_text)})
        bbox = [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
        out.append({"id": e["id"], "page": page, "kind": "block" if g[0].get("block") else "grid",
                    **{k: e.get(k) for k in ("source", "status", "from", "into", "blocks", "parts")},
                    "lines": len({c[num_axis] for c in body}), "positions": positions, "reading": reading,
                    "rows_info": rows_info(g, body, pos_axis, num_axis), "keyed": G.keyed(g),
                    "aside": [{"row": r + 1, "why": why} for r, why in sorted(G.aside(g).items())],
                    "title": _title(bbox, page_text.get(page), heads.get(page), [p["caption"] for p in positions]),
                    "rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1,
                    "bbox": bbox,
                    "cells": [dict({k: c[k] for k in ("name", "rect", "row", "col")}, total=c["name"] not in body_names,
                                   code=str(((bp.get("fields") or {}).get(c["name"]) or {}).get("x_petey_id", "")))
                              for c in cells],
                    "on_pattern": ok, "why": why})
    out.sort(key=lambda t: (t["page"], t["bbox"][1], t["bbox"][0]))
    return out


def rows_info(g: list[dict], body: list[dict], pos_axis: str, num_axis: str) -> dict:
    """The table's lines (rows, or columns when the columns are numbered; a block group's blocks) as the card's
    "rows" section says them (Andrew, 2026-10-19: "even if it's just numbers"): {kind: numerical | labelled |
    lettered | mixed, summary, lines: [{line, number | label, numbers: every number its cells carry, cells}]}."""
    blk = bool(g and g[0].get("block"))
    if not body:
        return {"kind": "none", "summary": "no rows", "lines": []}
    if G.keyed(g):
        ks = G.keyed_split(g) or {}
        rows = []
        for i in sorted({c[num_axis] for c in body}):
            labels = sorted({"_".join(ks[c["name"]][0]) for c in body if c[num_axis] == i and c["name"] in ks})
            rows.append({"line": i + 1, "label": labels[0] if labels else None, "cells": sum(1 for c in body if c[num_axis] == i)})
        return {"kind": "labelled", "summary": "labelled: " + ", ".join(r["label"] or "?" for r in rows), "lines": rows}
    F = G._Frame(g)
    rows = []
    for i in sorted({c[num_axis] for c in body}):
        cs = [c for c in body if c[num_axis] == i]
        nums = __import__("collections").Counter(F.num_of(c) for c in cs if F.num_of(c))
        rows.append({"line": i + 1, "number": nums.most_common(1)[0][0] if nums else None,
                     "numbers": [n for n, _ in nums.most_common()], "cells": len(cs)})
    seq = [r["number"] for r in rows]
    noun = "blocks" if blk else ("rows" if num_axis == "row" else "columns")
    if all(n and n.isdigit() for n in seq):
        ints = [int(n) for n in seq]
        kind = "numerical"
        summary = f"numerical, {noun} {ints[0]} to {ints[-1]}" if ints == list(range(ints[0], ints[0] + len(ints))) \
            else f"numerical, {noun} numbered {', '.join(seq)} (not by steps of 1)"
    elif all(n and len(n) == 1 and n.isalpha() for n in seq):
        kind, summary = "lettered", f"lettered, {noun} {seq[0]} to {seq[-1]}"
    else:
        kind, summary = "mixed", f"{noun} numbered {', '.join(n or '?' for n in seq)}"
    return {"kind": kind, "summary": summary, "lines": rows}


def standardize(bid: str, tid: str, *, apply, pos: Optional[int] = None, line: Optional[int] = None) -> dict:
    """The card's "standardize" buttons (Andrew, 2026-10-19): one column (`pos`, 1-based), every inconsistent column
    (neither), or one row (`line`, 1-based) renumbered. {status, steps, applied, left}; nothing accepted."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        return {"status": "gone", "steps": ["the table is no longer found on the page (renamed or moved?)"]}
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank else {}
    r = G.standardize(bp, g, lines, G.text_match_score(), positions=[pos - 1] if pos else None,
                      lines_=[line - 1] if line else None)
    what = f"column {pos}" if pos else f"row {line}" if line else "every column"
    steps = [f"standardize {what}: {r['why']}"] + r["left"]
    if not r["renames"]:
        return {"status": "nothing", "steps": steps + ["no rename to make"], "applied": [], "left": r["left"]}
    out = apply([{"field": o, "edit": {"name": n}, "why": f"grids and blocks: standardize {what} of {tid} ({r['why'][:120]})"}
                 for o, n in r["renames"].items()])
    if out.get("errors"):
        steps.append("not all applied: " + "; ".join(out["errors"][:3]))
    steps.append(f"{len(out.get('changes') or [])} rename(s) applied")
    return {"status": "standardized", "steps": steps, "applied": out.get("changes") or [], "left": r["left"]}


def _grid(bp: dict, tid: str, bid: Optional[str] = None):
    """(the table listed under `tid`, its grid) or (None, None)."""
    if bid:
        e = next((e for e in listing(bid, bp) if e["id"] == tid and e["status"] == "active"), None)
        return ({"id": tid, "page": e["grid"][0]["page"]}, e["grid"]) if e else (None, None)
    want = next((t for t in tables(bp) if t["id"] == tid), None)
    if not want:
        return None, None
    names = {c["name"] for c in want["cells"]}
    g = next((g for g in G.grids(bp) if {c["name"] for c in g} == names), None)
    return want, g


def jev_choose(bp: dict, page: int, unsure: dict) -> Optional[str]:
    """Jev picks one position's wording from its candidates, looking at the page with the position's boxes tagged.
    The candidate pattern, or None when Jev is unsure too."""
    from petey.validate import jev_page
    import httpx
    key = jev_page._key()
    if not key or not unsure.get("candidates"):
        return None
    rows = pc.numbered(bp)
    png, _dpi, px = pc.render(resolve_blank(bp), page, rows, limits=jev_page.LIMITS)
    ref = jev_page.image_ref(png)
    ids = [r["id"] for r in rows if r["name"] in set(unsure["cells"])]
    cands = unsure["candidates"][:12]
    crit = {f"c{i}": G._desc(p).replace("_", " ") or p for i, p in enumerate(cands)}
    crit["none"] = "None of these wordings says what is written in these boxes."
    body = {"model": jev_page.MODEL,
            "state": {"page_number": page, "page": ref,
                      "boxes": [{"id": i, "pixel_box": [round(v) for v in px[i]]} for i in ids if i in px],
                      "printed_caption": unsure.get("caption")},
            "questions": {"w": {"type": "choice", "criteria": crit, "instructions": {
                "question": ("`page` is a page of a blank form with every box outlined and numbered. The boxes listed in "
                             "`boxes` are one column (or one repeated slot) of a table. Which wording says what a person "
                             "writes in them, judging by the headers and captions printed for them?")}}}}
    with httpx.Client() as client:
        res = jev_page.ask_split(client, key, body, {ref: png})
    a = (res.get("answers") or {}).get("w") or {}
    choice = a.get("choice")
    probs = a.get("probabilities") or {}
    p = probs.get(choice) if isinstance(probs, dict) else None
    if not choice or choice == "none" or (p is not None and p < JEV_MIN):
        return None
    return cands[int(choice[1:])] if choice[1:].isdigit() and int(choice[1:]) < len(cands) else None


def check(bid: str, tid: str, *, accept, apply, ask_opus) -> dict:
    """One click on a table: {status, steps, applied, accepted, proposals}. `accept(page, names)` accepts cells,
    `apply(edits)` writes renames (form_chat.apply's result), `ask_opus(page)` returns the chat's proposal."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        return {"status": "gone", "steps": ["the table is no longer found on the page (renamed or moved?)"]}
    page, steps = t["page"], []
    if G.on_pattern(g)[0]:
        acc = accept(page, [c["name"] for c in G.body(g)])
        return {"status": "validated", "steps": [f"code check: on pattern; {len(acc)} cell(s) accepted"], "accepted": acc}
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank else {}
    r = G.resolve(bp, g, lines, G.text_match_score())
    steps.append(f"resolver: {r['status']} ({r['why']})")
    forced = {}
    if r["status"] == "unsure" and all(u.get("pos") is not None for u in r["unsure"]):
        for u in r["unsure"]:
            pick = jev_choose(bp, page, u)
            steps.append(f"Jev, position {u['pos'] + 1}: " + (f"chose {pick}" if pick else "unsure"))
            if pick:
                forced[u["pos"]] = pick
        if len(forced) == len(r["unsure"]):
            r = G.resolve(bp, g, lines, G.text_match_score(), forced=forced)
            steps.append(f"resolver with Jev's wording: {r['status']} ({r['why']})")
    if r["status"] in ("fixed", "ok") and (r["renames"] or r["status"] == "ok"):
        out = apply([{"field": o, "edit": {"name": n}, "why": "grids and blocks: " + ("Jev's wording, " if forced else "")
                      + "each position one wording, each line one number"} for o, n in r["renames"].items()]) \
            if r["renames"] else {"changes": [], "errors": []}
        if out.get("errors"):
            steps.append("not all applied: " + "; ".join(out["errors"][:3]))
        names = [r["renames"].get(c["name"], c["name"]) for c in G.body(g)]
        acc = accept(page, names)
        steps.append(f"{len(out.get('changes') or [])} rename(s) applied; {len(acc)} cell(s) accepted")
        return {"status": "fixed" if r["renames"] else "validated", "steps": steps,
                "applied": out.get("changes") or [], "accepted": acc}
    prop = ask_opus(page)
    steps.append("Opus (this page only): " + (prop.get("reply") or "no proposal"))
    return {"status": "proposed", "steps": steps, "proposals": prop}
