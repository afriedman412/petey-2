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
        out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when")},
                    "grid": [dict(c) for c in g]})
    for e in rec["grids"]:
        if e["source"] == "finder":
            continue
        cells = [{"name": name[c], "page": e["page"], "row": r, "col": k, **({"block": True} if e["kind"] == "block" else {})}
                 for c, r, k in e["cells"] if c in name]
        if cells:
            out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when")},
                        "grid": cells})
    mine = [set(c["name"] for c in t["grid"]) for t in out if t["source"] != "finder" and t["status"] == "active"]
    for t in out:                   # a finder grid mostly inside one the person made or combined is shown as that one
        if t["source"] == "finder" and t["status"] == "active" and any(
                len(set(c["name"] for c in t["grid"]) & m) >= 0.5 * len(t["grid"]) for m in mine):
            t["status"] = "replaced"
    if changed:
        _save_set(bid, rec)
    return out


def set_status(bid: str, gid: str, cancel: bool) -> dict:
    """Cancel a grid or block (not a grid or block), or restore it. Cancelling a combined one gives its parts back."""
    import time
    rec = load_set(bid)
    e = next((e for e in rec["grids"] if e["id"] == gid), None)
    if e is None:
        raise ValueError(f"no grid {gid}")
    e["status"] = "cancelled" if cancel else "active"
    e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if e["source"] == "combined":
        for x in rec["grids"]:
            if x["id"] in (e.get("from") or []) and x.get("into") == gid:
                x["status"] = "active" if cancel else "combined"
    _save_set(bid, rec)
    return {"id": gid, "status": e["status"]}


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
    col_of = lambda r: max(range(len(cols)), key=lambda i: min(cols[i][1], r[2]) - max(cols[i][0], r[0]))
    placed = []                                  # (line, column, rank on that line and column, name, box)
    for li, ln in enumerate(lines):
        seen: dict = {}
        for n, r in sorted(ln["cells"], key=lambda b: b[1][0]):
            ci = col_of(r)
            placed.append((li, ci, seen.get(ci, 0), n, r))
            seen[ci] = seen.get(ci, 0) + 1
    row_of, slot_of = {}, {}
    if kind == "block" and len(lines) > 1:
        sig = [{(ci, round((r[3] - r[1]) / 4)) for li2, ci, _k, _n, r in placed if li2 == li} for li in range(len(lines))]
        tops = [ln["y0"] for ln in lines]

        def score(step):                         # the share of lines that come again one step lower, alike
            ok = tried = 0
            for i, t in enumerate(tops):
                if t + step > tops[-1] + 3:
                    continue
                tried += 1
                j = min(range(len(tops)), key=lambda j: abs(tops[j] - (t + step)))
                ok += abs(tops[j] - (t + step)) <= 3 and len(sig[i] & sig[j]) >= 0.8 * len(sig[i] | sig[j])
            return ok / tried if tried else 0
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
    return _add(bid, bp, page, kind, cells, "person", [])


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
    return out


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
                    **{k: e.get(k) for k in ("source", "status", "from", "into")},
                    "lines": len({c[num_axis] for c in body}), "positions": positions, "reading": reading,
                    "rows_info": rows_info(g, body, pos_axis, num_axis), "keyed": G.keyed(g),
                    "aside": [{"row": r + 1, "why": why} for r, why in sorted(G.aside(g).items())],
                    "title": _title(bbox, page_text.get(page), heads.get(page), [p["caption"] for p in positions]),
                    "rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1,
                    "bbox": bbox,
                    "cells": [dict({k: c[k] for k in ("name", "rect", "row", "col")}, total=c["name"] not in body_names)
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
