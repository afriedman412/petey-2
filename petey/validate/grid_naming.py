"""Grids are named consistently (Andrew, 2026-10-15: "the naming conventions for each column should be identical").

A grid: text boxes in two or more columns (same left edge and width) that share two or more rows (same height on the
page); checked when it is numbered along one side (3+ cells one way, 2+ the other, most names carrying an iteration:
a number, or a lone letter as in property_b_). In a grid every cell's name has one shape, its iteration standing in
for N: either the column decides the
shape and the row decides the number (AO 40B's expense table: expense_private_N_amt, N = row), or the row decides the
shape and the column decides the number (Form 8825's income grid: gross_rents_N_amt, N = property column). The check
picks the reading most cells agree with and lists the cells that break it: another shape than their column's (or
row's), or another number than their row's (or column's). Found by layout only, no names or forms listed.

    PYTHONPATH=. venv/bin/python -m petey.validate.grid_naming je__ao040b je__f8825 ...            # list what breaks
    PYTHONPATH=. venv/bin/python -m petey.validate.grid_naming je__ao040b --fix                    # the renames it would make
    PYTHONPATH=. venv/bin/python -m petey.validate.grid_naming je__ao040b --fix --apply            # make them

`--fix` (2026-10-15, Andrew: "let's just systematize this"): each cell that breaks the pattern is renamed to its
column's (or row's) wording with the number its row (or column) should carry, worked out from the table itself (the
offset most numbered cells agree on between position and number), so a swap, a stray number and an unnumbered first
row are all fixed. A cell whose wording has more than one number in it, or a table numbered by letters, is listed and
left. `--apply` writes the renames into the review page's working copy as Claude's corrections (`form_chat.apply`:
clashes refused, the person's verdicts follow). Separate tables stacked in one set of columns, or a column that
should be worded differently, still need a person (the chat, or by hand).
"""
from __future__ import annotations

import collections
import re
import sys

NUM = re.compile(r"\d+")
LINE = re.compile(r"^\d+[a-z]?$")          # an iteration or a line number (2, 12, 4a)
TOL_X, TOL_W, TOL_Y = 6.0, 4.0, 3.0      # x 6: a column whose boxes sit a few points apart (EP-2) is one column


def _cluster(vals: list[float], tol: float) -> list[float]:
    """Cluster centres of 1-d values (sorted, gap > tol starts a new cluster)."""
    out: list[list[float]] = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(c) / len(c) for c in out]


def _near(v: float, centres: list[float], tol: float) -> int:
    return min(range(len(centres)), key=lambda i: abs(centres[i] - v)) if centres and min(abs(c - v) for c in centres) <= tol else -1


BLOCK_TOL = 3.0          # pt: a repeated block's spacing may wander this much from one repeat to the next
MIN_REPEATS = 3
CELL_TYPES = ("text", "combobox", "listbox", "checkbox", "radio")   # a lone tick box too (SF 3107 G: "disabled")


def _runs(cs: list[dict]) -> list[list[dict]]:
    """A column cut where its spacing jumps to more than twice the usual (IMM 5645 page 1: Section A's applicant,
    spouse, mother and father, then Section B's children, in the same columns), so each section can be its own
    block."""
    cs = sorted(cs, key=lambda c: c["y"])
    gaps = [b["y"] - a["y"] for a, b in zip(cs, cs[1:])]
    if not gaps:
        return [cs]
    usual = sorted(gaps)[len(gaps) // 2]
    out = [[cs[0]]]
    for c, g in zip(cs[1:], gaps):
        if g > 2 * usual + 2:
            out.append([])
        out[-1].append(c)
    return out


def _phases(cs: list[dict]) -> list[list[dict]]:
    """A column holding two (or three) slots of a block, one above the other with the same left edge and width (IMM 5645
    page 2: each sibling's present address over present occupation), spaced unevenly (address, occupation, address
    ...) but evenly every second (or third) box: split into one column per slot. [] when it is not that."""
    cs = sorted(cs, key=lambda c: c["y"])
    for k in (2, 3):
        if len(cs) < k * MIN_REPEATS or len(cs) % k:
            continue
        steps = [cs[i + k]["y"] - cs[i]["y"] for i in range(len(cs) - k)]
        med = sorted(steps)[len(steps) // 2]
        if med > 8 and all(abs(st - med) <= BLOCK_TOL for st in steps):
            return [cs[j::k] for j in range(k)]
    return []


def repeated_blocks(cells_by_page: dict[int, list[dict]], cols_by_page: dict[int, dict]) -> list[list[dict]]:
    """Repeated blocks (2026-10-16, FAA 8050-1 page 3: nine signer blocks of applicant / signature / date / signer /
    title over three lines each): columns of same-placed, same-width boxes that repeat at one regular spacing, two or
    more of them with the same spacing and count, starting within one spacing of each other. Each repeat is a row
    (the block's iteration), each column a slot, so the table's checks and fixes apply as they are."""
    out = []
    for page, cols in cols_by_page.items():
        periodic = []
        for k0, cs0 in cols.items():
            runs = _runs(cs0)
            for si, cs in enumerate(runs):
                k = k0 + (("s", si),) if len(runs) > 1 else k0
                if len(cs) == 2:                            # two boxes: only ever a slot missing from some repeats
                    cs = sorted(cs, key=lambda c: c["y"])
                    periodic.append((k + (("two",),), cs[1]["y"] - cs[0]["y"], cs[0]["y"], cs))
                    continue
                if len(cs) < MIN_REPEATS:
                    continue
                ys = sorted(c["y"] for c in cs)
                gaps = [b - a for a, b in zip(ys, ys[1:])]
                med = sorted(gaps)[len(gaps) // 2]
                if med > 8 and all(abs(g - med) <= BLOCK_TOL for g in gaps):
                    periodic.append((k, med, ys[0], sorted(cs, key=lambda c: c["y"])))
                    continue
                # a column ending in a total at another spacing (CBP 7512: quantity 1-3, then the total) repeats on the
                # boxes above it
                if len(cs) > MIN_REPEATS and med > 8 and all(abs(g - med) <= BLOCK_TOL for g in gaps[:-1]):
                    periodic.append((k, med, ys[0], sorted(cs, key=lambda c: c["y"])[:-1]))
                    continue
                for j, ph in enumerate(_phases(cs)):           # two slots stacked in one column: a column each
                    periodic.append((k + (("p", j),), ph[1]["y"] - ph[0]["y"], ph[0]["y"], ph))
        split = {k for k, *_ in periodic if any(isinstance(t, tuple) and t[0] == "p" for t in k)}
        # a block is built on its longest column; the others join when each of their boxes sits on one of its repeats
        periodic.sort(key=lambda e: -len(e[3]))
        used = set()
        for i, (k, stride, y0, cs) in enumerate(periodic):
            if k in used or k[0] == "g" or all(c.get("box") for c in cs) or len(cs) < MIN_REPEATS:
                continue                                      # nor do groups, tick boxes or a pair build a block
            # the block's top: the highest first box of the full columns starting within a repeat of this one
            top = min(y2 for k2, s2, y2, cs2 in periodic if k2 not in used and abs(s2 - stride) <= BLOCK_TOL
                      and len(cs2) == len(cs) and abs(y2 - y0) < stride - BLOCK_TOL)
            members = []
            for k2, s2, y2, cs2 in periodic[i:]:
                pair = len(cs2) == 2
                if k2 in used or (abs(s2 - stride) > BLOCK_TOL and not pair):
                    continue
                rows = _on_repeats(cs2, top, stride, len(cs))
                if rows is not None:
                    members.append((k2, rows[0], rows[1]))
            # a pair joins only inside the width of the full slots (CBP 7512: the delivery inspector of rows 2 and 3)
            full = [m for m in members if len(m[2]) == len(cs)]
            if full:
                lo = min(c["x"] for m in full for c in m[2].values())
                hi = max(c["x"] + c["w"] for m in full for c in m[2].values())
                members = [m for m in members if len(m[2]) > 2 or all(lo <= c["x"] <= hi for c in m[2].values())]
            # a block has two or more slots in every repeat; slots missing from some (IMM 5645: the applicant's "will
            # accompany") fill in around them. One column running through two stacked tables, the others each in one
            # (ACORD 90 NY page 1: NEW / USED and the driver-use boxes under it), is not a block
            if len(members) < 2 or sum(len(m[2]) == len(cs) for m in members) < 2:
                continue
            # split columns join a block that has a column repeating evenly on its own (IMM 5645: name, relationship);
            # when every column only repeats once split, it is two-row tables stacked (ACORD 125 page 3: fire code
            # violations, bankruptcies, judgements, two rows each), not a block
            if all(m[0] in split for m in members):
                continue
            # a block runs over two or more lines (FAA 8050-1: three); repeats of one line are tables, found as such
            # (2026-10-16: single-line "blocks" turned 3-row tables into blocks and raised false alarms on ACORD 125/130)
            # (a new line: a slot lower than half the boxes' height; CBP 7512's conveyance boxes, 7 pt above the rest
            # of their row, are the same line)
            offs = sorted((m[1], sorted(c.get("h", 8) for c in m[2].values())[len(m[2]) // 2]) for m in members)
            multi = any(b[0] - a[0] > 0.5 * max(a[1], b[1]) for i, a in enumerate(offs) for b in offs[i + 1:])
            if not multi and len({round(m[1] / 4) for m in members}) < 2:
                continue
            # slots repeating together at different heights on one line (Form 8949: the description box twice as
            # tall as the row's others; CBP 7512: conveyance 7 pt above) are a table whose rows the row finder splits:
            # kept, as a table
            # a slot per column, left to right (Andrew, 2026-10-16: "display the columns ... in order (L to R)"); slots
            # stacked at one left edge (address over occupation) top first
            members.sort(key=lambda m: (round(min(c["x"] for c in m[2].values()) / TOL_X), m[1]))
            used.update(m[0] for m in members)
            out.append([dict({"name": c["name"], "page": page, "row": r, "col": ci}, **({"block": True} if multi else {}))
                        for ci, (_k, _o, rows) in enumerate(members) for r, c in sorted(rows.items())])
    return out


def _on_repeats(cs: list[dict], y0: float, stride: float, n: int):
    """(offset within the block, {repeat: cell}) when every box of the column sits on one of a block's n repeats (first
    at y0, then every stride) at one offset down the block, else None. A column may miss repeats (IMM 5645: the
    applicant has no "will accompany" boxes); a full column must start on the first repeat: one starting a repeat
    lower is the same lines shifted by one (CRA T1 page 3: gross 13499-14299 beside net 13700-14300 and line 27)."""
    cs = sorted(cs, key=lambda c: c["y"])
    off = (cs[0]["y"] - y0 + BLOCK_TOL) % stride - BLOCK_TOL      # y0 is the block's top: slots sit below it
    rows = {}
    for c in cs:
        r = round((c["y"] - y0 - off) / stride)
        if not 0 <= r < n or r in rows or abs(c["y"] - y0 - off - r * stride) > 2 * BLOCK_TOL:
            return None
        rows[r] = c
    if len(cs) < 2 or (len(cs) == n and min(rows) != 0) or len(cs) > n:
        return None
    return off, rows


def grids(bp: dict, blocks: bool = True) -> list[list[dict]]:
    """[[cell]] per grid; a cell = {name, page, row, col}. Repeated blocks (`repeated_blocks`) count as grids, a block per row,
    and a table the code would otherwise find inside one is left to the block. `blocks=False` (2026-10-18: grids and
    blocks apart; block groups are petey/validate/block_groups.py's): tables only, the rows-at-two-heights ones included."""
    by_page = collections.defaultdict(list)
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        # a dropdown or a lone tick box is a cell like a text box (IMM 5645 page 2: each sibling's marital status; SF
        # 3107 section G: each child's "disabled", 2026-10-16)
        if w.get("widget_type") not in CELL_TYPES or not w.get("rect"):
            continue
        x0, y0, x1, y1 = w["rect"]
        by_page[w["page"]].append({"name": n, "page": w["page"], "x": x0, "w": x1 - x0, "y": (y0 + y1) / 2,
                                   "h": y1 - y0, "box": w["widget_type"] in ("checkbox", "radio")})
    out = []
    cols_by_page: dict[int, dict] = {}
    for page, cells in by_page.items():
        cols: dict[tuple, list[dict]] = collections.defaultdict(list)
        cols_by_page[page] = cols
        xs, ws = _cluster([c["x"] for c in cells], TOL_X), None
        for c in cells:
            c["xc"] = _near(c["x"], xs, TOL_X)
            if c["xc"] < 0:                  # no centre within reach (a dense page chains x values into one wide
                c["xc"] = f"x{round(c['x'])}"   # cluster): its own column, not one bogus column for all such boxes
        for xi in set(c["xc"] for c in cells):
            group = [c for c in cells if c["xc"] == xi]
            for wc in _cluster([c["w"] for c in group], TOL_W):
                same = [c for c in group if abs(c["w"] - wc) <= TOL_W]
                for box in (False, True):
                    if [c for c in same if c["box"] == box]:
                        cols[(xi, round(wc)) + (("box",) if box else ())] = [c for c in same if c["box"] == box]
        ys = _cluster([c["y"] for c in cells if not c["box"]], TOL_Y)    # tick boxes would chain rows together
        for c in cells:
            c["row"] = _near(c["y"], ys, TOL_Y)
        # tables are found from text boxes and dropdowns; a tick-box column would join unrelated tables through the
        # rows it shares (the D&D sheet's skill boxes): tick boxes are added to a table afterwards (`_with_groups`)
        keys = [k for k, v in cols.items() if len(v) >= 2 and not any(c["box"] for c in v)]
        rows_of = {k: {c["row"] for c in cols[k]} for k in keys}
        # columns joined when they share two or more rows; a grid is a joined set of two or more columns
        parent = {k: k for k in keys}

        def find(k):
            while parent[k] != k:
                k = parent[k]
            return k
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if len(rows_of[a] & rows_of[b]) >= 2:
                    parent[find(a)] = find(b)
        sets = collections.defaultdict(list)
        for k in keys:
            sets[find(k)].append(k)
        for ks in sets.values():
            if len(ks) < 2:
                continue
            ks.sort(key=lambda k: min(c["x"] for c in cols[k]))
            shared = set.union(*[rows_of[k] for k in ks])
            rows = sorted(r for r in shared if sum(r in rows_of[k] for k in ks) >= 2)
            if len(rows) < 2:
                continue
            # two tables stacked in the same columns (Schedule B: interest, then dividends): split where the row
            # spacing jumps to more than twice the usual
            ycs = [ys[r] for r in rows]
            gaps = sorted(b - a for a, b in zip(ycs, ycs[1:]))
            usual = gaps[len(gaps) // 2] if gaps else 0
            blocks, cur = [], [rows[0]]
            for r, a, b in zip(rows[1:], ycs, ycs[1:]):
                if usual and b - a > 2 * usual + 2:
                    blocks.append(cur)
                    cur = []
                cur.append(r)
            blocks.append(cur)
            # a table's columns numbered one per column, 1..N left to right (ACORD 90 NY coverages: vehicle 1-4
            # premiums beside limit and deductible columns that share their rows) are a table of their own
            parts = []
            for blk in blocks:
                num = {}
                for k in ks:
                    ns = {_number(c["name"]) for c in cols[k] if c["row"] in blk}
                    if len(ns) == 1 and None not in ns and sum(c["row"] in blk for c in cols[k]) >= 0.5 * len(blk):
                        num[k] = next(iter(ns))
                run = [k for k in ks if k in num]
                seq = [num[k] for k in run]
                if len(run) >= 2 and len(run) < len(ks) and seq == [str(i) for i in range(1, len(run) + 1)]:
                    parts.append((blk, run))
                    parts.append((blk, [k for k in ks if k not in num]))
                else:
                    parts.append((blk, ks))
            # tables stacked under each other's headings at the usual spacing (ACORD 90 NY page 1: vehicle description,
            # then cost new / symbols, then class / seat belts; page 2), joined by a column they share: cut where the
            # columns a row fills change from the row above's by more than half
            cut = []
            for blk, kk in parts:
                occ = {r: {k for k in kk if any(c["row"] == r for c in cols[k])} for r in blk}
                blk = [r for r in blk if occ[r]]
                if not blk:
                    continue
                segs = [[blk[0]]]
                for r in blk[1:]:
                    a, b = occ[segs[-1][-1]], occ[r]
                    if len(a & b) < 0.5 * len(a | b):
                        segs.append([])
                    segs[-1].append(r)
                # a cut needs two or more rows on each side. A table whose every row differs (CRA T5's slips) is not
                # cut; a lone row that differs stays with the table beside it when half or more of its columns are the
                # table's (a totals row, AO 40B), and is left out otherwise (ACORD 90 NY: the driver numbers under the
                # vehicle table share one column with it)
                if all(len(sg) < 2 for sg in segs):
                    segs = [blk]
                i = 0
                while len(segs) > 1 and i < len(segs):
                    if len(segs[i]) >= 2:
                        i += 1
                        continue
                    r = segs[i][0]
                    near = [j for j in (i - 1, i + 1) if 0 <= j < len(segs)
                            and len(occ[r] & occ[segs[j][-1 if j < i else 0]]) >= 0.5 * len(occ[r])]
                    if near:
                        j = near[0]
                        lo, hi = min(i, j), max(i, j)
                        segs[lo:hi + 1] = [segs[lo] + segs[hi]]
                    else:
                        del segs[i]
                    i = 0
                cut += [(sg, kk) for sg in segs]
            for blk, kk in cut:
                if len(blk) < 2:
                    continue
                used = [k for k in kk if any(c["row"] in blk for c in cols[k])]
                grid = [{"name": c["name"], "page": page, "row": blk.index(c["row"]), "col": ci}
                        for ci, k in enumerate(used) for c in cols[k] if c["row"] in blk]
                out.append(grid)
    # option groups on one line (a Yes / No pair) are cells of a block (IMM 5645: "will accompany you to Canada?"), as
    # one cell spanning their boxes; tables are found without them
    for n, s in (bp.get("fields") or {}).items():
        ws = list(((s or {}).get("widgets") or {}).values()) if isinstance(s, dict) else []
        rs = [w["rect"] for w in ws if w.get("rect")]
        if len(rs) < 2 or len({w.get("page") for w in ws}) > 1:
            continue
        ycs = [(r[1] + r[3]) / 2 for r in rs]
        if max(ycs) - min(ycs) > 2 * TOL_Y:
            continue
        x0, x1 = min(r[0] for r in rs), max(r[2] for r in rs)
        cell = {"name": n, "page": ws[0]["page"], "x": x0, "w": x1 - x0, "y": sum(ycs) / len(ycs)}
        cols = cols_by_page.setdefault(ws[0]["page"], collections.defaultdict(list))
        key = next((k for k in cols if k[0] == "g" and abs(k[1] - x0) <= TOL_X and abs(k[2] - (x1 - x0)) <= TOL_W),
                   ("g", x0, x1 - x0))
        cols[key].append(cell)
    reps = repeated_blocks(by_page, cols_by_page)
    if not blocks:
        reps = [b for b in reps if not b[0].get("block")]
    names = [{c["name"] for c in b} for b in reps]
    # a table mostly inside a block is the block's (I-130 page 12: a 3 x 6 table took the block's cells and two others)
    out = [g for g in out if not any(len({c["name"] for c in g} & ns) >= 0.5 * len(g) for ns in names)]
    return [_with_groups(bp, g) for g in _merge_offset(bp, out)] + reps


def _merge_offset(bp: dict, tables: list[list[dict]]) -> list[list[dict]]:
    """Two tables that are one, their boxes set at two heights in each row (SF 3107 page 10, Section C: nature of
    action, salary rate, basis and leave a few points above effective date, earned from / to and total; 2026-10-16):
    same page, same number of rows, each row of one overlapping the same row of the other from top to bottom, and no
    column of one over a column of the other. Merged, columns in left-to-right order."""
    fields = bp.get("fields") or {}
    rect = lambda n: ((fields.get(n) or {}).get("widget") or {}).get("rect")

    def shape(g):
        rows, cols = collections.defaultdict(list), collections.defaultdict(list)
        for c in g:
            r = rect(c["name"])
            if r:
                rows[c["row"]].append(r)
                cols[c["col"]].append(r)
        return ({k: (min(r[1] for r in v), max(r[3] for r in v)) for k, v in rows.items()},
                {k: (min(r[0] for r in v), max(r[2] for r in v)) for k, v in cols.items()})
    tables = list(tables)
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(tables):
            for j in range(i + 1, len(tables)):
                b = tables[j]
                if a[0]["page"] != b[0]["page"]:
                    continue
                (ra, ca), (rb, cb) = shape(a), shape(b)
                if len(ra) < 2 or sorted(ra) != list(range(len(ra))) or sorted(rb) != list(range(len(ra))):
                    continue
                if not all(min(ra[k][1], rb[k][1]) - max(ra[k][0], rb[k][0]) > 0.5 * min(ra[k][1] - ra[k][0], rb[k][1] - rb[k][0])
                           for k in ra):
                    continue
                if any(min(x[1], y[1]) - max(x[0], y[0]) > 0 for x in ca.values() for y in cb.values()):
                    continue
                # interleaved across one width (SF 3107: the two heights alternate along the row), not two tables side
                # by side whose rows happen to line up (the D&D sheet's attacks beside its skills)
                sa = (min(v[0] for v in ca.values()), max(v[1] for v in ca.values()))
                sb = (min(v[0] for v in cb.values()), max(v[1] for v in cb.values()))
                if not (sa[0] < sb[0] < sa[1] or sb[0] < sa[0] < sb[1]):
                    continue
                order = sorted([("a", k, v[0]) for k, v in ca.items()] + [("b", k, v[0]) for k, v in cb.items()],
                               key=lambda t: t[2])
                col = {(t, k): n for n, (t, k, _x) in enumerate(order)}
                tables[i] = [dict(c, col=col[("a", c["col"])]) for c in a if ("a", c["col"]) in col] + \
                            [dict(c, col=col[("b", c["col"])]) for c in b if ("b", c["col"]) in col]
                del tables[j]
                merged = True
                break
            if merged:
                break
    return tables


def _with_groups(bp: dict, g: list[dict]) -> list[dict]:
    """A table with its option-group and tick-box columns (SF 3107 Schedule C: each claim's "type of benefit", three
    checkboxes over two lines; section G: each child's "disabled"; 2026-10-16): groups and lone tick boxes on the
    table's page, none in the table yet, whose middle falls inside one of its
    rows, lined up one above the other (same left edge) in two or more rows, one per row, beside or inside the table
    (within 24 pt of its sides)."""
    fields = bp.get("fields") or {}
    page = g[0]["page"]
    rect = lambda n: ((fields.get(n) or {}).get("widget") or {}).get("rect")
    spans = collections.defaultdict(list)
    for c in g:
        r = rect(c["name"])
        if r:
            spans[c["row"]].append(r)
    if not spans:
        return g
    rows = {k: (min(r[1] for r in v), max(r[3] for r in v)) for k, v in spans.items()}
    left, right = min(r[0] for v in spans.values() for r in v), max(r[2] for v in spans.values() for r in v)
    have = {c["name"] for c in g}
    cand = []
    for n, s in fields.items():
        if not isinstance(s, dict) or n in have:
            continue
        w = s.get("widget") or {}
        if w.get("widget_type") in ("checkbox", "radio") and w.get("rect") and w.get("page") == page:
            ws = [w]                                       # a lone tick box (SF 3107 section G: "disabled")
        else:
            ws = list((s.get("widgets") or {}).values())
            if len(ws) < 2:
                continue
        rs = [w["rect"] for w in ws if w.get("rect") and w.get("page") == page]
        if not rs or len(rs) != len(ws):
            continue
        x0, y0, x1, y1 = min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)
        row = next((k for k, (a, b) in rows.items() if a <= (y0 + y1) / 2 <= b), None)
        if row is not None:
            cand.append({"name": n, "row": row, "x": x0, "near": x0 >= left - 24 and x1 <= right + 24 + (x1 - x0)})
    cols = collections.defaultdict(list)
    for c in cand:
        key = next((k for k in cols if abs(k - c["x"]) <= TOL_X), c["x"])
        cols[key].append(c)
    # beside or inside the table; or anywhere on its rows when lined up with most of them (CH-100 item 6: the tick box
    # before each kind of case, the kind's printed name between it and the text columns)
    add = [cs for cs in cols.values() if len(cs) >= 2 and len({c["row"] for c in cs}) == len(cs)
           and (all(c["near"] for c in cs) or len(cs) >= max(3, 0.6 * len(rows)))]
    if not add:
        return g
    # columns in left-to-right order, the groups' among them
    xs = {}
    for c in g:
        r = rect(c["name"])
        if r:
            xs.setdefault(c["col"], []).append(r[0])
    order = sorted([("t", k, min(v)) for k, v in xs.items()] + [("g", i, min(c["x"] for c in cs)) for i, cs in enumerate(add)],
                   key=lambda t: t[2])
    new_col = {(kind, k): ci for ci, (kind, k, _x) in enumerate(order)}
    out = [dict(c, col=new_col[("t", c["col"])]) for c in g if ("t", c["col"]) in new_col]
    out += [{"name": c["name"], "page": page, "row": c["row"], "col": new_col[("g", i)]} for i, cs in enumerate(add) for c in cs]
    return out


def _iter_tokens(name: str) -> list[int]:
    """Positions of the name's iteration tokens: a number (2, 12) or a lone letter (property_b_...)."""
    toks = name.split("_")
    return [i for i, t in enumerate(toks) if LINE.match(t) or (len(t) == 1 and t.isalpha() and 0 < i)]


def _shape(name: str) -> str:
    toks = name.split("_")
    for i in _iter_tokens(name):
        toks[i] = "N"
    return "_".join(toks)


def _number(name: str):
    its = _iter_tokens(name)
    return name.split("_")[its[-1]] if its else None


def _core(tok):
    """A line number's number without its letter (5a -> 5): in a block of item-lettered cells (I-130 page 12: item_5a_
    page_number, item_5b_part_number, ... per row) the number is the row's and the letter the column's (2026-10-16)."""
    return tok[:-1] if tok and len(tok) > 1 and tok[-1].isalpha() and tok[:-1].isdigit() else tok


def _close(a: str, b: str) -> bool:
    """Two shapes for the same thing (gross_rents_amt_N / gross_rents_N_amt, property_desc / property_desc_N), not
    two different items that happen to share a column: most of their words the same."""
    ta, tb = set(a.split("_")) - {"N"}, set(b.split("_")) - {"N"}
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def aside(grid: list[dict]) -> dict[int, str]:
    """{row: why} for the rows outside the pattern: a last row of totals (every name starting total_), and a first
    or last row that is a line of its own kind (ACORD 90 NY: the DRIVER # boxes over the vehicle rows,
    driver_1_nbr .. driver_6_nbr above vehicle_N_driver_1_use_pct): in most of its columns the cell's shape is not
    the shape the column's other rows share, and the row carries no number of the rows' series."""
    rows = sorted({c["row"] for c in grid})
    out = {}
    if len(rows) < 3:
        return out
    last = rows[-1]
    if all(c["name"].startswith("total") for c in grid if c["row"] == last):
        out[last] = "a row of totals"
        rows = rows[:-1]
    if len(rows) < 3:
        return out
    for r in (rows[0], rows[-1]):
        others = [c for c in grid if c["row"] in rows and c["row"] != r]
        by_col = collections.defaultdict(collections.Counter)
        for c in others:
            by_col[c["col"]][_shape(c["name"])] += 1
        mine = [c for c in grid if c["row"] == r]
        if not mine:
            continue
        # the other rows agree on the column's shape (nearly all of them, two at least), and this row's cell is
        # another shape and not a variant of it (an unnumbered first row, class_cd beside class_cd_N, is close to its
        # column and stays; a table whose every row has its own label words agrees on nothing and keeps its rows)
        agreed = {k: v.most_common(1)[0] for k, v in by_col.items()
                  if v.most_common(1)[0][1] >= 2 and v.most_common(1)[0][1] >= 0.8 * sum(v.values())}
        off = sum(1 for c in mine if c["col"] in agreed and _shape(c["name"]) != agreed[c["col"]][0]
                  and not _close(_shape(c["name"]), agreed[c["col"]][0]))
        if len(agreed) >= 0.6 * len(by_col) and off >= 0.6 * len(mine):
            out[r] = "a line of its own kind (its cells are not named like their columns)"
    return out


def body(grid: list[dict]) -> list[dict]:
    """The grid without its rows set aside (`aside`: totals, a header or footer line of another kind)."""
    skip = aside(grid)
    return [c for c in grid if c["row"] not in skip] if skip else grid


def iterated(grid: list[dict]) -> bool:
    """A table numbered along one side: 3+ cells one way and 2+ the other, most cells carrying an iteration; or
    lines named by role or kind (`keyed`): a block's repeats, or a table's 3+ rows of 3+ columns."""
    nrow, ncol = len({c["row"] for c in grid}), len({c["col"] for c in grid})
    if not ((nrow >= 3 and ncol >= 2) or (nrow >= 2 and ncol >= 3)):
        return False
    # a table named by kind needs 3+ rows and 3+ columns: two columns by kind are mostly one value per line in parts
    # (943's dollars / cents, CA 540's count / amount)
    if keyed(grid) and (grid[0].get("block") or (nrow >= 3 and ncol >= 3)):
        return True
    # more than half: a box of separate fields with two address lines each (ACORD 90 NY's agency / applicant header:
    # producer_address_line_1, _2) is half numbered, and not a table
    return sum(_number(c["name"]) is not None for c in grid) > 0.5 * len(grid)


def keyed(grid: list[dict], strict: bool = False) -> bool:
    """Lines named by role or kind, not number (IMM 5645 Section A: applicant_nm, spouse_nm, mother_nm, father_nm;
    CH-100 item 6, other court cases: civil_harassment_case_nbr, domestic_violence_case_nbr ...): each column's names
    share an ending (case_nbr, filed_in_txt), the rest is the line's key; a line's cells share the start of their keys
    and every line's is its own. On pattern as it is: roles and kinds are not renumbered. `strict` (the naming check,
    `on_pattern`): every cell is its line's key and then its column's one wording; the loose reading is the finder's
    (what is a table), so a table named off its pattern is still found and checked."""
    by_col, keys = collections.defaultdict(list), collections.defaultdict(list)
    for c in grid:
        by_col[c["col"]].append(c)
    for cs in by_col.values():
        toks = [c["name"].split("_") for c in cs]
        if len(cs) < 2:
            continue
        n = 0
        while all(len(t) > n + 1 for t in toks) and len({t[-1 - n] for t in toks}) == 1:
            n += 1
        if not n:
            return False
        for c, t in zip(cs, toks):
            keys[c["row"]].append(t[:len(t) - n])
    if len(keys) < 2:
        return False
    line = {}
    for r, ks in keys.items():
        common = []
        for parts in zip(*ks):
            if len(set(parts)) > 1:
                break
            common.append(parts[0])
        if not common:
            return False
        line[r] = "_".join(common)
    if len(set(line.values())) != len(line):
        return False
    # every cell its line's key and then its column's one wording (2026-10-21: a shared last word was not enough, I-730
    # p5-T1's prior_spouse_1_middle_2_nm beside prior_spouse_2_middle_nm passed, and I-130's item-numbered
    # physical_address_1_12b_unit_type beside mailing_unit_type)
    if strict:
        wording = collections.defaultdict(set)
        for c in grid:
            k = line.get(c["row"])
            if k is None or not c["name"].startswith(k + "_"):
                return False
            wording[c["col"]].add(c["name"][len(k) + 1:])
        if any(len(w) > 1 for w in wording.values()):
            return False
    # labelled lines with runs of numbered ones among them (Andrew, 2026-10-21, "grids should be resilient to mixed
    # label/number row labeling": IRS 433-F p2-T4's expense rows named by their printed labels and three blank
    # "Other (specify)" rows other_expenses_row_1 .. _3; ACORD 125's first_named_insured beside other_named_insured_1,
    # _2): fine while one line at least is labelled and each run, one stem, counts down the table by steps of 1, from
    # 1, or by the printed item letters (VA 21P-534EZ's care_10c, care_10d). All numbered is the number check's
    runs = collections.defaultdict(list)
    for r in sorted(line):
        stem, _, last = line[r].rpartition("_")
        if LINE.match(last):
            runs[stem].append(last)
    if not runs:
        return True
    if sum(len(v) for v in runs.values()) == len(line) or not all(runs):
        return False

    def counts(seq):
        if all(s.isdigit() for s in seq):
            return seq[0] == "1" and all(_next(a, b) for a, b in zip(seq, seq[1:]))
        return len({_core(s) for s in seq}) == 1 and all(_next(a[-1], b[-1]) for a, b in zip(seq, seq[1:]))
    return all(counts(seq) for seq in runs.values())

def _pattern(name: str) -> str | None:
    """The name with its iteration (the last one) as N; any other number in it stays (sched_2_line_N_amt)."""
    toks, its = name.split("_"), _iter_tokens(name)
    if not its:
        return None
    toks[its[-1]] = "N"
    return "_".join(toks)


def _next(a: str, b: str) -> bool:
    """b is the iteration after a: 3 then 4, b then c."""
    if a.isdigit() and b.isdigit():
        return int(b) == int(a) + 1
    return len(a) == len(b) == 1 and a.isalpha() and b.isalpha() and ord(b) == ord(a) + 1


def _count_key(t: str):
    """(number, letter) for a line identifier that counts: 3, 3a, a; None for one that does not (words, 5_income)."""
    m = re.fullmatch(r"(\d+)([a-z]?)", t)
    if m:
        return int(m[1]), m[2]
    if len(t) == 1 and t.isalpha():
        return None, t
    return None


def _in_steps(ids: list[str]) -> bool | None:
    """Lines' identifiers counting by steps of 1 (3, 4, 5; b, c; 6a, 6b; 1a, 1b, 2, 3), from wherever they start;
    None when they do not count (labels: real_estate, household_furniture), so only being distinct is asked of them."""
    ks = [_count_key(x) for x in ids]
    if not ks or any(k is None for k in ks):
        return None
    if all(n is None for n, _ in ks):
        return all(ord(b[1]) == ord(a[1]) + 1 for a, b in zip(ks, ks[1:]))
    if any(n is None for n, _ in ks):
        return False
    for (n0, l0), (n1, l1) in zip(ks, ks[1:]):
        if n1 == n0 and l0 and l1 and ord(l1) == ord(l0) + 1:          # 6a -> 6b
            continue
        if n1 == n0 + 1 and l1 in ("", "a"):                           # 1b -> 2, 3 -> 4a
            continue
        return False
    return True


def _cell_tokens(c: dict) -> list[str]:
    """A cell's words in the order its name prints them: from its stored parts when they print its name (the naming
    standard, petey/naming.py), else the name's own words. The same words either way; the parts say which is which."""
    return c["name"].split("_")


def _wording(cells: list[dict], widest: bool = False):
    """(prefix, suffix) of one position's names: the words its cells start and end with around the line's identifier,
    the longest shared by more than half its cells, every such cell keeping a word between. None below two cells."""
    toks = [_cell_tokens(c) for c in cells]
    if len(toks) < 2:
        return None
    cands = set()
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            a, b = toks[i], toks[j]
            if a == b:
                continue
            p = 0
            while p < min(len(a), len(b)) and a[p] == b[p]:
                p += 1
            s = 0
            while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
                s += 1
            for pp in range(p, -1, -1):          # a shorter prefix gives the suffix room (and the reverse)
                ss = min(s, min(len(a), len(b)) - pp - 1)
                if ss >= 0:
                    cands.add((tuple(a[:pp]), tuple(a[len(a) - ss:]) if ss else ()))
    best, best_key = None, None
    for pre, suf in cands:
        n = sum(1 for t in toks if len(t) > len(pre) + len(suf) and tuple(t[:len(pre)]) == pre
                and (not suf or tuple(t[len(t) - len(suf):]) == suf))
        if 2 * n <= len(toks):
            continue
        key = (n, len(pre) + len(suf)) if widest else (len(pre) + len(suf), n)   # most cells, or most words
        if best_key is None or key > best_key:
            best, best_key = (pre, suf), key
    return best


def _middle(c: dict, w) -> tuple | None:
    """The words of a cell between its position's prefix and suffix (`_wording`): its line's identifier."""
    if not w:
        return None
    t, (pre, suf) = _cell_tokens(c), w
    if len(t) <= len(pre) + len(suf) or tuple(t[:len(pre)]) != pre or (suf and tuple(t[len(t) - len(suf):]) != suf):
        return None
    return tuple(t[len(pre):len(t) - len(suf)])


def _sub_at(seq: tuple, sub: tuple) -> int | None:
    """Where `sub` runs inside `seq`, the last place (a line's identifier nearest the suffix), or None."""
    for i in range(len(seq) - len(sub), -1, -1):
        if seq[i:i + len(sub)] == sub:
            return i
    return None


def _line_id(middles: list[tuple]) -> tuple | None:
    """A line's identifier from its cells' middles (`_middle`): what they all carry, else the longest run of words
    more than half of them carry (guns_1 beside note_1: 1), else None."""
    ms = [m for m in middles if m]
    if not ms:
        return None
    if len(set(ms)) == 1:
        return ms[0]
    best = None
    for m in set(ms):
        for i in range(len(m)):
            for j in range(i + 1, len(m) + 1):
                sub = m[i:j]
                n = sum(1 for x in ms if _sub_at(x, sub) is not None)
                if 2 * n > len(ms) and (best is None or (len(sub), n) > (len(best[0]), best[1])):
                    best = (sub, n)
    return best[0] if best else None


def identify(grid: list[dict], both: bool = False):
    """A grid read by identifiers (Andrew, 2026-10-26: "a unique identifier for each row/column from the existing
    data"; "[this word changes]_[these words don't]"): read both ways (positions down the columns and lines across
    the rows, and the transpose). Each position's wording is the words its names share around a middle (`_wording`);
    each line's identifier the run of words its cells' middles share (`_line_id`); each cell's wording its name with
    its line's identifier as N. Which way the grid lies does not matter. {ok, why, pos_axis, num_axis, wordings:
    {pos: (prefix, suffix)}, ids: {line: identifier}, cells: {name: (wording with N, its identifier)}, problems,
    countable: bool | None}: the reading with fewer problems."""
    cells = body(grid)
    out = []
    # each way round, with each position's wording the longest most of its cells share, and the one the most cells
    # share (CMS-855A p68: services_2 beside policies_procedures_2: the shorter wording, every cell in it)
    for pos_axis, num_axis, widest in (("col", "row", False), ("row", "col", False), ("col", "row", True),
                                       ("row", "col", True)):
        pos_word, line_word = ("column", "row") if pos_axis == "col" else ("row", "column")
        lines = sorted({c[num_axis] for c in cells})
        positions = sorted({c[pos_axis] for c in cells})
        r = {"ok": False, "pos_axis": pos_axis, "num_axis": num_axis, "wordings": {}, "ids": {}, "cells": {},
             "problems": [], "countable": None, "unworded": 0}
        if len(lines) < 2:
            r.update(why=f"one {line_word}", problems=[f"one {line_word}"], unworded=len(positions))
            out.append(r)
            continue
        probs, wordings, mid = r["problems"], r["wordings"], {}
        for k in positions:
            pcs = [c for c in cells if c[pos_axis] == k]
            w = _wording(pcs, widest)
            if len(pcs) >= 2 and not (w and (w[0] or w[1])):
                probs.append(f"{pos_word} {k + 1}: no wording most of its cells share")
                r["unworded"] += 1
                continue
            wordings[k] = w
            for c in pcs:
                mid[c["name"]] = _middle(c, w) if w else None
        # I-130 p12, item_5a_page beside item_5b_part: a letter the same down its position is the position's
        letter = set()
        for k in wordings:
            ms = [mid.get(c["name"]) for c in cells if c[pos_axis] == k]
            ls = {(re.fullmatch(r"\d+([a-z])", m[0]) or [None, None])[1] if m and len(m) == 1 else None for m in ms}
            if len(ms) >= 2 and len(ls) == 1 and None not in ls:
                letter.add(k)
        core = lambda c, m: (m[0][:-1],) if m and c[pos_axis] in letter else m          # noqa: E731
        lids = {i: _line_id([core(c, mid.get(c["name"])) for c in cells if c[num_axis] == i and c[pos_axis] in wordings])
                for i in lines}
        # a line's identifier grown by a word every one of its cells has beside it that the other lines do not have
        # there (F1120 Schedule L: accumulated_depreciation, its indented boxes a column of their own whose wording
        # took "accumulated"); a word beside every line's (line_29, line_30: "line") stays the positions'
        def _beside(c, lid, side):
            t = tuple(_cell_tokens(c))
            at = _sub_at(t, lid)
            if at is None:
                return None
            j = at - 1 if side < 0 else at + len(lid)
            return t[j] if 0 <= j < len(t) else None
        first = dict(lids)                       # the others as read, not as grown so far
        for i in lines:
            lc = [c for c in cells if c[num_axis] == i and c[pos_axis] in wordings]
            while lids[i] and len(lc) >= 2 and not letter:      # lettered positions (5a, 5b): the 5 is everywhere
                grown = False
                for side in (-1, 1):
                    ws = {_beside(c, lids[i], side) for c in lc}
                    if len(ws) != 1 or None in ws:
                        continue
                    w = next(iter(ws))
                    elsewhere = sum(1 for j in lines if j != i and first[j] and any(
                        _beside(c, first[j], side) == w for c in cells if c[num_axis] == j and c[pos_axis] in wordings))
                    if 2 * elsewhere < len(lines) - 1:
                        lids[i] = (w, *lids[i]) if side < 0 else (*lids[i], w)
                        grown = True
                if not grown:
                    break
        for i in lines:
            lc = [c for c in cells if c[num_axis] == i and c[pos_axis] in wordings]
            lid = lids[i]
            if lid is None:
                probs.append(f"{line_word} {lines.index(i) + 1}: no identifier its cells share "
                             f"({', '.join(sorted({'_'.join(m) for m in (mid.get(c['name']) for c in lc) if m}))})")
            else:
                r["ids"][i] = "_".join(lid)
            for c in lc:
                pre, suf = wordings[c[pos_axis]] or ((), ())
                m = mid.get(c["name"])
                if m is None:
                    continue
                at = _sub_at(core(c, m), lid) if lid else None
                if lid is not None and at is None and c[pos_axis] not in letter:
                    full = tuple(_cell_tokens(c))      # the position's wording took part of it (F4562: line26_ in
                    at2 = _sub_at(full, lid)           # one column's every cell): found in the whole name
                    if at2 is not None:
                        r["cells"][c["name"]] = ("_".join([*full[:at2], "N", *full[at2 + len(lid):]]), "_".join(lid))
                        continue
                if lid is None or at is None:          # no identifier of its line here: the cell's own number stands
                    if lid is not None:                # in (a shifted row: make_1 beside premium_2), said once
                        probs.append(f"{c['name']}: does not carry its {line_word}'s identifier {'_'.join(lid)}")
                    nums = [j for j, t in enumerate(m) if re.fullmatch(r"\d+[a-z]?|[a-z]", t)]
                    if len(nums) == 1:                 # one number in its middle (not a word: first, last)
                        j = nums[0]
                        r["cells"][c["name"]] = ("_".join([*pre, *m[:j], "N", *m[j + 1:], *suf]), m[j])
                    else:
                        r["cells"][c["name"]] = None
                    continue
                mm = list(m)
                if c[pos_axis] in letter:              # the letter stays the position's: 5a is N, 5 the line's
                    r["cells"][c["name"]] = ("_".join([*pre, "N", *suf]), "_".join(m))
                    continue
                pat = [*pre, *mm[:at], "N", *mm[at + len(lid):], *suf]
                r["cells"][c["name"]] = ("_".join(pat), "_".join(lid))
        for c in cells:                 # a position of one cell: it carries its line's identifier, or it is off
            if c[pos_axis] in wordings and wordings[c[pos_axis]] is None:
                lid = tuple(r["ids"][c[num_axis]].split("_")) if c[num_axis] in r["ids"] else None
                toks = tuple(_cell_tokens(c))
                at = _sub_at(toks, lid) if lid else None
                if at is None:
                    probs.append(f"{c['name']}: does not carry its {line_word}'s identifier "
                                 f"{'_'.join(lid) if lid else '(none)'}")
                else:
                    r["cells"][c["name"]] = ("_".join([*toks[:at], "N", *toks[at + len(lid):]]), "_".join(lid))
        for k in positions:
            if k not in wordings:
                continue
            pcs = [c for c in cells if c[pos_axis] == k]
            for c in pcs:
                if c["name"] not in r["cells"] and wordings[k] and _middle(c, wordings[k]) is None:
                    probs.append(f"{c['name']}: not worded as its {pos_word} ({_show(wordings[k])})")
            pats = collections.Counter(r["cells"][c["name"]][0] for c in pcs if r["cells"].get(c["name"]))
            if len(pats) > 1:
                probs.append(f"{pos_word} {k + 1} has {len(pats)} wordings "
                             f"({', '.join(f'{p} x{n}' for p, n in pats.most_common())})")
        # positions whose wordings differ only by a number are counted lines read the wrong way (ND SFN 5753:
        # source_well_name_and_number, _2, _3 down the side): this reading is no reading
        wtxt = {k: _show(w) for k, w in wordings.items() if w}
        masked = {"_".join(x for x in t.split("_") if not re.fullmatch(r"\d+[a-z]?", x)) for t in wtxt.values()}
        if len(wtxt) >= 2 and len(set(wtxt.values())) > 1 and len(masked) == 1:
            r["numbered"] = (f"its {pos_word}s are numbered ({', '.join(list(wtxt.values())[:3])}): read the other way",
                             len(wtxt))
        seq = [r["ids"][i] for i in lines if i in r["ids"]]
        dup = [x for x, n in collections.Counter(seq).items() if n > 1]
        if dup:
            probs.append(f"two {line_word}s with one identifier ({', '.join(dup)})")
        r["countable"] = _in_steps(seq) if len(seq) == len(lines) else None
        if r["countable"] is False:
            probs.append(f"{line_word}s numbered {', '.join(seq)}, not by steps of 1")
        r["ok"] = not probs
        r["why"] = "; ".join(probs) or f"by {pos_word}s, {line_word}s {_span_say(seq)}"
        out.append(r)
    # a reading whose positions share no wording is no reading; then fewer problems; then the reading whose lines
    # count (1065-X: lines by wording down the side, columns a, b, c across: the letters are the lines); then columns
    # positions numbered one way round only: that reading is the wrong way round; numbered both ways (DD 293) both stand
    if not all(r.get("numbered") for r in out):
        for r in out:
            if r.get("numbered"):
                why_, k = r["numbered"]
                r["problems"].append(why_)
                r["unworded"] += k
                r["ok"], r["why"] = False, "; ".join(r["problems"])
    if both:                                     # each reading, for a look at why one lost
        return out
    if all(r["unworded"] for r in out):          # read neither way: columns are the positions, as the finder lays a
        out = [r for r in out if r["pos_axis"] == "col"]                     # grid out (CBP 7501 p1's mixed names)
    return min(out, key=lambda r: (r["unworded"], len(r["problems"]), r["countable"] is not True, r["pos_axis"] != "col"))


def _show(w) -> str:
    pre, suf = w
    return "_".join([*pre, "#", *suf])


def _span_say(seq: list[str]) -> str:
    return f"{seq[0]} to {seq[-1]}" if seq and _in_steps(seq) else ", ".join(seq[:6]) + (" ..." if len(seq) > 6 else "")


def unfold(grid: list[dict]) -> list[dict] | None:
    """A grid printed in halves (or thirds) side by side, its columns' wordings repeating across its width (Andrew,
    2026-10-24, ACORD 140's blanket list: blankets 1-2 on the left, 3-4 on the right, each number / amount / type;
    "this needs a systematic fix because it's not a unique situation"; ACORD 90 NY's vehicles 1-2 / 3-4, SF 3107's
    children 1-4 / 5-8), read as one: each further half's rows under the first's. None when the columns do not
    repeat. Cells keep their names; only their row and column change."""
    cols = sorted({c["col"] for c in grid})
    if len(cols) < 4:
        return None
    word = {}
    for k in cols:
        pats = collections.Counter(_pattern(c["name"]) for c in grid if c["col"] == k)
        word[k] = pats.most_common(1)[0][0] if pats else None
    rows = max(c["row"] for c in grid) + 1
    for width in range(1, len(cols) // 2 + 1):
        if len(cols) % width:
            continue
        if all(word[cols[i]] is not None and word[cols[i]] == word[cols[i % width]] for i in range(len(cols))):
            at = {k: i for i, k in enumerate(cols)}
            return [dict(c, row=c["row"] + (at[c["col"]] // width) * rows, col=cols[at[c["col"]] % width]) for c in grid]
    return None


def split_stacked(grid: list[dict]) -> list[dict] | None:
    """A column holding two (or more) fields in every row, the same wordings in each (Andrew, 2026-10-25, CMS-1500
    p1-G8: each service line's shaded strip above it, supplemental info over charges, EPSDT over family plan, other ID
    over NPI; picking one wording could only clash), split into one column per wording. None when no column is so."""
    by = collections.defaultdict(list)
    for c in grid:
        by[(c["col"], c["row"])].append(c)
    cols = sorted({c["col"] for c in grid})
    split = {}
    for k in cols:
        rows = [r for (kk, r) in by if kk == k]
        sets = [sorted(_numbers_masked(c["name"]) for c in by[(k, r)]) for r in rows]
        if len(rows) >= 2 and all(len(x) > 1 and len(set(x)) == len(x) for x in sets) and all(x == sets[0] for x in sets):
            split[k] = sets[0]
    if not split:
        return None
    new_col, n = {}, 0
    for k in cols:
        for w in split.get(k, [None]):
            new_col[(k, w)] = n
            n += 1
    return [dict(c, col=new_col[(c["col"], _numbers_masked(c["name"]) if c["col"] in split else None)]) for c in grid]


def _numbers_masked(name: str) -> str:
    """A name with every number as N: its wording whatever it counts (service_line_N_modifier_N_cd)."""
    return "_".join("N" if t.isdigit() else t for t in name.split("_"))


def fold_rows(grid: list[dict]) -> list[dict] | None:
    """A grid whose lines each take two (or three) printed rows (Andrew, 2026-10-25, CMS-1500 p1-G8: each service
    line's shaded strip above it, supplemental info / EPSDT / other ID, then the line itself; a column held
    supplemental info and charges in turn): each run of rows one line, and a column whose wording depends on which
    row of the run, one column per row. None when no period reads the grid so (every column one wording per row of
    the run, and some column changing within it)."""
    rows = sorted({c["row"] for c in grid})
    at = {r: i for i, r in enumerate(rows)}
    for period in (2, 3):
        if len(rows) % period or len(rows) < 2 * period:
            continue
        pats = collections.defaultdict(set)
        for c in grid:
            pats[(c["col"], at[c["row"]] % period)].add(_numbers_masked(c["name"]))
        if any(len(v) > 1 for v in pats.values()):
            continue
        changes = {k for (k, j) in pats} & {k for (k, j), v in pats.items() if any(pats.get((k, i)) not in (None, v)
                                                                                  for i in range(period))}
        if not changes:
            continue
        keys = sorted(pats)
        new_col = {key: n for n, key in enumerate(keys)}
        return [dict(c, row=at[c["row"]] // period, col=new_col[(c["col"], at[c["row"]] % period)]) for c in grid]
    return None


def on_pattern(grid: list[dict]) -> tuple[bool, str]:
    """The quick code check, before any model (Andrew, 2026-10-15: "there should be a pattern for every column that
    will only vary by iteration, and the iterations should descend by 1"): (passes, how it reads or why not). Passes
    when, read by columns (or the transpose): every cell carries an iteration, every column one pattern its cells
    differ from only in that iteration, every row one number, the rows numbered top to bottom by steps of 1. A last
    row of totals is left out. The naming standard's shape is not checked here: it is its own step."""
    ok, why = _on_pattern(grid)
    if ok:
        return ok, why
    stacked = split_stacked(grid)           # two fields in each row of a column: one column each
    if stacked is not None and _on_pattern(stacked)[0]:
        return True, f"stacked fields split into columns ({_on_pattern(stacked)[1]})"
    folded = fold_rows(grid)                # each line two printed rows: one line each
    if folded is not None and _on_pattern(folded)[0]:
        return True, f"lines of two rows read as one ({_on_pattern(folded)[1]})"
    halves = unfold(stacked or grid)        # halves side by side: read as one (each half's rows under the first's)
    if halves is not None and _on_pattern(halves)[0]:
        return True, f"halves side by side, read as one ({_on_pattern(halves)[1]})"
    return ok, why


def read_as_checked(grid: list[dict]) -> list[dict]:
    """The grid as the checks read it: as printed, else its stacked columns split, else its halves stacked, the
    first that is on pattern (as printed when none is)."""
    if _on_pattern(grid)[0]:
        return grid
    stacked = split_stacked(grid)
    if stacked is not None and _on_pattern(stacked)[0]:
        return stacked
    folded = fold_rows(grid)
    if folded is not None and _on_pattern(folded)[0]:
        return folded
    halves = unfold(stacked or grid)
    if halves is not None and _on_pattern(halves)[0]:
        return halves
    return stacked or grid


def _on_pattern(grid: list[dict]) -> tuple[bool, str]:
    """The code check on one arrangement of a grid: every row and column its own identifier (`identify`, 2026-10-26;
    the older readings, rows named by role or kind and one varying number per position, folded into it). (passes,
    how it reads: columns / rows, "... named by role or kind" when the lines are labels; or the first problems)."""
    r = identify(grid)
    if not r["ok"]:
        return False, r["why"]
    line = "rows" if r["pos_axis"] == "col" else "columns"
    if r["countable"] is None and r["ids"]:
        return True, f"{line} named by role or kind"
    return True, "columns" if r["pos_axis"] == "col" else "rows"


def _standard(name: str, spec: dict) -> str:
    """The naming standard's shape for a fixed name (iteration before the suffix): standardize_names.standard."""
    from petey.validate.standardize_names import standard
    return standard(name, spec)[0]


def fixes(bp: dict, blocks: bool = True) -> tuple[dict[str, str], list[str]]:
    """({cell: new name}, [what it cannot fix, said]) for every iterated grid off the code check (`blocks=False`:
    tables only, as the review page reads them since block groups went, 2026-10-22): what the Grids card's
    "standardize all" would do (`standardize`, the identifier reading), the one mechanical fixer (2026-10-26)."""
    ren, left = {}, []
    for g in grids(bp, blocks=blocks):
        if not iterated(g) or on_pattern(g)[0]:
            continue
        r = standardize(bp, read_as_checked(g), {}, None)
        ren.update(r["renames"])
        left += r["left"]
    return ren, left


def check(bp: dict) -> list[str]:
    out = []
    for g in grids(bp):
        if not iterated(g):
            continue
        ok, why = on_pattern(g)
        if not ok:
            nrow, ncol = max(c["row"] for c in g) + 1, max(c["col"] for c in g) + 1
            out.append(f"grid p{g[0]['page']} ({nrow}x{ncol}): {why}")
    return out


def main() -> int:
    import argparse
    from petey.validate import hand_review as h
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--fix", action="store_true", help="list the renames that would put each grid on its pattern")
    ap.add_argument("--apply", action="store_true", help="with --fix: write them into the working copy")
    args = ap.parse_args()
    for bid in args.ids:
        bp = h._load(h.working_path(bid))
        lines = check(bp)
        tables = [g for g in grids(bp) if iterated(g)]
        print(f"{bid}: {len(grids(bp))} grid(s), {len(lines)} cell(s) breaking the pattern; "
              f"{sum(on_pattern(g)[0] for g in tables)} of {len(tables)} numbered table(s) pass the code check")
        if not args.fix:
            for g in tables:
                ok, why = on_pattern(g)
                if not ok:
                    print(f"  table p{g[0]['page']} ({g[0]['name']} ...) off the code check: {why}")
            for ln in lines[:25]:
                print("  " + ln)
            continue
        ren, left = fixes(bp)
        for o, n in ren.items():
            print(f"  {o} -> {n}")
        for ln in left:
            print(f"  left: {ln}")
        if args.apply and ren:
            from petey.validate import form_chat
            out = form_chat.apply(bid, [{"field": o, "edit": {"name": n}, "why": "grid named on one pattern "
                                         "(petey/validate/grid_naming.py --fix)"} for o, n in ren.items()], [])
            print(f"  applied {len(out['changes'])}" + (f"; not applied: {'; '.join(out['errors'])}" if out["errors"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ------------------------------------------------------------------ the resolver (Andrew, 2026-10-16)
# One table or block at a time, the lightest method first: (0) which way it runs; (1) each position's wording: one
# wording, or variants that the name-check model (petey.label.text_match, the small model trained on the name checks)
# scores as describing the position's shared caption, the naming standard breaking ties; (2) the numbers: one per
# line, 1..N, unless the table continues a series from another page; (3) the result checked by the code check and for
# name clashes. Positions the model cannot settle come back "unsure" with their candidates (for Jev, with the page);
# a table whose structure does not come right is "confused" (for Opus).

SAME = 0.5               # text-match score from which a wording describes the position's caption
CLOSE = 0.05             # wordings scoring within this of the best are equally good: the naming standard decides


def _rect(bp: dict, name: str):
    w = ((bp.get("fields") or {}).get(name) or {}).get("widget") or {}
    return w.get("rect"), w.get("page")


def position_caption(bp: dict, cells: list[dict], how: str, lines: dict) -> str | None:
    """The caption a position's cells share: the column header (a table read by columns), the row label (read by
    rows), or the caption printed beside each repeat (a block: FAA 8050-1's 'TYPED/PRINTED NAME OF SIGNER' nine
    times). The commonest over the cells; None when the page text gives none."""
    from petey.validate.field_chain import candidate_captions, column_header, row_header
    got = collections.Counter()
    for c in cells:
        r, page = _rect(bp, c["name"])
        pl = lines.get(page) or []
        if not r or not pl:
            continue
        t = (candidate_captions(r, pl) or [None])[0] if how == "block" else \
            column_header(r, pl) if how == "columns" else row_header(r, pl)
        if t and re.search(r"[A-Za-z]{2}", t):
            got[" ".join(t.split())] += 1
    return got.most_common(1)[0][0] if got else None


def _desc(pattern: str) -> str:
    return "_".join(t for t in pattern.split("_") if t != "N")


SAME_WORD = {"num": "nbr", "number": "nbr", "no": "nbr", "nr": "nbr", "name": "nm", "date": "dt", "amount": "amt",
             "code": "cd", "text": "txt", "year": "yr"}
STOP = {"of", "to", "the", "a", "an", "for", "and", "or", "in", "on", "by"}
LOOSE_SUFFIX = {"txt", "nbr", "cd", "nm"}      # say little about the value: hp_cc_nbr and hp_cc_txt are one text; dt, yr,
                                               # amt, ssn ... say what it is (model_yr is not model_txt)


def _stem(t: str) -> str:
    """A word without its common ending, then without a final e: lease and leased, purchase and purchased read the
    same."""
    t = SAME_WORD.get(t, t)
    # a plural first, then -ing / -ed, then a final e, once each: mailings / mailing -> mail, expenses / expense ->
    # expens, leased / lease -> leas (stripping again and again took expenses to expen but expense to expens)
    if t.endswith("ies") and len(t) > 4:
        t = t[:-3] + "y"
    elif t.endswith("es") and len(t) > 4 and not t.endswith("ses"):
        t = t[:-2]
    elif t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        t = t[:-1]
    if t.endswith("ing") and len(t) > 5:
        t = t[:-3]
    elif t.endswith("ed") and len(t) > 4:
        t = t[:-2]
    return t[:-1] if t.endswith("e") and len(t) > 3 else t


def _words(pattern: str, common: set) -> frozenset:
    """The words that say what a wording is: its description without a loose type suffix (hp_cc_nbr and hp_cc_txt are
    one text; model_yr and model_txt are not), stop words or the words most of the table shares, each without its ending."""
    toks = [SAME_WORD.get(t, t) for t in _desc(pattern).split("_") if t]
    while len(toks) > 1 and toks[-1] in LOOSE_SUFFIX:           # owner_name_txt and owner_nm: both owner
        toks = toks[:-1]
    return frozenset(_stem(t) for t in toks if t not in STOP and t not in common)


def equivalent(a: str, b: str, common: set = frozenset()) -> bool:
    """Two wordings that are the same text (same_words' test): the same words once endings, word order, number place,
    a loose suffix, nbr / num / number and the table's shared words are set aside."""
    wa, wb = _words(a, set()), _words(b, set())
    if wa == wb:
        return True
    ca, cb = _words(a, common), _words(b, common)
    return bool(ca) and ca == cb


def same_words(cells: list[dict], pat, common: set = frozenset()):
    """The wording to keep when a position's wordings are the same text in other spellings (Andrew, 2026-10-18: "we
    can probably standardize descriptions that are just equivalent text before going to opus"; ACORD 90 NY page 1:
    vehicle_N_lease_dt / vehicle_N_leased_dt / vehicle_leased_N_dt, vehicle_N_nbr / vehicle_num_N, location_N_nbr /
    vehicle_N_location_nbr; vehicle_N_hp_cc_nbr / vehicle_hp_cc_N_txt): the same words once endings, word order,
    number place, the type suffix, nbr / num / number and the words most of the table's names share are set aside.
    The commonest, numbered before not, then the one with the table's shared words, then the one already in the
    naming standard's shape, then the shortest; None when they say different things (or there is only one)."""
    pats = collections.Counter(pat(c) for c in cells)
    if len(pats) < 2:
        return None
    full = {p: _words(p, set()) for p in pats}
    base = {p: _words(p, common) for p in pats}
    if len(set(full.values())) > 1 and (len(set(base.values())) > 1 or not all(base.values())):
        return None
    numbered = lambda p: "N" in p.split("_")      # noqa: E731
    std = lambda p: _standard(p, {"type": "string"}) == p      # noqa: E731
    shares = lambda p: len(set(p.split("_")) & set(common))      # noqa: E731   the table's own words (vehicle_)
    return max(pats, key=lambda p: (pats[p], numbered(p), shares(p), std(p), -len(p)))


def choose_wording(cells: list[dict], caption: str | None, score, pat=None) -> tuple[str | None, str]:
    """(the position's pattern, how it was chosen) or (None, why it is unsure). `score(caption, [names])`. Two
    wordings that both fit the caption and are not variants of each other (ACORD 125: building_nbr / location_nbr)
    are a real disagreement: unsure, for Jev, not a vote."""
    pat = pat or (lambda c: _pattern(c["name"]) or c["name"])
    pats = collections.Counter(pat(c) for c in cells)
    numbered = {p for p in pats if "N" in p.split("_")}
    # an unnumbered first row is the column's own wording without its number (class_cd beside class_cd_N)
    for p in list(pats):
        if p not in numbered:
            twin = next((q for q in numbered if _desc(q) == p), None)
            if twin:
                pats[twin] += pats.pop(p)
    if len(pats) == 1:
        return next(iter(pats)), "one wording"
    if caption and score:
        cand = list(pats)
        s = dict(zip(cand, score(caption, [_desc(p) for p in cand])))
        best = max(s.values())
        if best < SAME:
            return None, f"no wording fits the caption {caption!r} ({', '.join(f'{p} {v:.2f}' for p, v in s.items())})"
        good = [p for p in cand if s[p] >= best - CLOSE]
        pick = max(good, key=lambda p: (pats[p], p in numbered, -len(p)))
        rivals = [p for p in cand if p != pick and s[p] >= SAME and not _variant(p, pick)]
        if rivals:
            return None, f"{pick} and {', '.join(rivals)} both fit the caption {caption!r} and say different things"
        return pick, f"fits the caption {caption!r} ({s[pick]:.2f})"
    p, n = pats.most_common(1)[0]
    if n >= 0.6 * sum(pats.values()) and all(_close(p, q) for q in pats):
        return p, "most cells, no caption to check against"
    return None, "several wordings and no caption to check them against"


def _printed(bp: dict, cells: list[dict], lines: dict) -> bool:
    """The table's numbers are printed on the page beside its lines (CA 540 line 43, 44; tax line numbers): most
    numbered cells' number appears in the text of their row label or nearest captions. Then they are the form's own
    numbers, kept as they are."""
    from petey.validate.field_chain import candidate_captions, row_header
    hits = tried = 0
    for c in cells:
        num = _core(_number(c["name"]))
        if not (num or "").isdigit():
            continue
        r, page = _rect(bp, c["name"])
        pl = lines.get(page) or []
        if not r or not pl:
            continue
        tried += 1
        cy = (r[1] + r[3]) / 2                 # the whole printed band level with the cell: CA 540 prints its line
        band = [t for bb, t in pl if bb[1] - 2 <= cy <= bb[3] + 2]     # numbers at the far left margin
        text = " ".join(filter(None, [row_header(r, pl)] + candidate_captions(r, pl)[:2] + band))
        hits += bool(re.search(rf"(?<!\d){num}(?![\d])", text))       # item 3.4 counts for 4
    return tried > 0 and hits >= 0.6 * tried


def _variant(a: str, b: str) -> bool:
    """Two wordings for one thing: the same words once both are in the naming standard's shape (signer_name /
    signer_nm), or most words shared (gross_rents_amt / gross_rents)."""
    da, db = _desc(a) or a, _desc(b) or b
    sa, sb = _standard(da, {"type": "string"}), _standard(db, {"type": "string"})
    strip = lambda n: [t for t in n.split("_") if t not in ("txt", "nm", "nbr", "cd", "amt", "dt", "name")]   # noqa: E731
    return da == db or sa == sb or strip(sa) == strip(sb) or _close(da, db)


def _continues(bp: dict, grid_names: set, pats: list[str], start: int, before_page: int | None = None) -> bool:
    """A series begun elsewhere: a field outside the table on the same pattern numbered start - 1 (FAA 8050-1's
    page 2 signer block before page 3's 2-10); with `before_page`, only one on an earlier page counts (a series
    continues from earlier in the form: ACORD 140's subjects of insurance 1-5 on page 1, 6-10 on page 2)."""
    fields = bp.get("fields") or {}
    if before_page is not None:
        def page_of(s):
            w = s.get("widget") or next(iter((s.get("widgets") or {}).values()), {}) or {}
            return w.get("page")
        fields = {n: s for n, s in fields.items() if isinstance(s, dict) and (page_of(s) or 0) < before_page}
    want = set()
    for p in pats:
        if "N" not in p.split("_"):
            continue
        prev = p.replace("N", str(start - 1))
        want |= {prev, _standard(prev, {"type": "string"})}
        if start == 2:                   # an unnumbered twin before a series from 2 is its first (FAA's old page 2)
            want |= {_desc(p), _standard(_desc(p), {"type": "string"})}
    return any(n in want or (_pattern(n) in pats and _number(n) == str(start - 1))
               for n in fields if n not in grid_names)


def _norm_tok(t: str) -> str:
    """A name word as the equivalence test reads it: one spelling (name / nm, num / nbr ...), no ending, and the loose
    type suffixes (txt / nbr / cd / nm) as one."""
    t = SAME_WORD.get(t, t)
    return "~" if t in LOOSE_SUFFIX else _stem(t)


class _Frame:
    """How a table is read, shared by `resolve` and `standardize`: its body cells, which axis is the position and
    which the line, which number varies per position, the line-numbered positions (locked), and the words nearly
    every cell shares."""

    def __init__(self, g: list[dict]):
        self.cells = cells = body(g)
        # the identifier reading (`identify`, 2026-10-26): which way the grid lies, each position's wording and each
        # cell's line identifier. `sure` when it reads every line for sure (every line its own identifier, every
        # position a wording, the numbers in step): only then does standardize number the lines on its own; on a grid
        # it cannot read so (the finder's mixed outlines, CBP 7501 p1-G2) a wording picked still applies, each placed
        # cell keeping its own line identifier, and a cell it does not place keeps its name
        self.ident = R = identify(g)
        lines_n = len({c[R["num_axis"]] for c in cells})
        self.sure = bool(R["wordings"] and not R["unworded"] and R["countable"] is not False
                         and len(R["ids"]) == lines_n and len(set(R["ids"].values())) == len(R["ids"]))
        self.reading = reading = "columns" if R["pos_axis"] == "col" else "rows"
        self.pos_axis, self.num_axis = ("col", "row") if reading == "columns" else ("row", "col")
        self.how = "block" if g[0].get("block") else reading
        pos_axis = self.pos_axis
        self.positions = sorted({c[pos_axis] for c in cells})

        # line-number names keep their numbers (Andrew's exception: line_116_direct_deposit_amt, line_3_3_make on tax
        # and court forms): a position whose wording has its line's number after "line" is the form's own numbering
        def _line_numbered(k):
            pcs = [c for c in cells if c[pos_axis] == k]
            pats = collections.Counter(self.pat_of(c) for c in pcs)
            toks_k = (pats.most_common(1)[0][0] if pats else "").split("_")
            nums = [self.num_of(c) for c in pcs]          # and the numbers are numbers (CBP 7501's line_no: not one)
            return "N" in toks_k and toks_k.index("N") > 0 and toks_k[toks_k.index("N") - 1] in ("line", "ln") \
                and 2 * sum(1 for x in nums if x and re.fullmatch(r"\d+[a-z]?", x)) > len(pcs)
        self.locked = {k for k in self.positions if _line_numbered(k)}
        # words nearly every cell's name has (ACORD 90 NY's vehicle_): leaving one out does not change what a cell
        # says. Counted over cells, not positions: a row key (taxpayer / spouse, loc1 / loc2) is in every column but
        # only in its own row's cells, and says which row a cell is
        cell_words = [set(_desc(self.pat_of(c)).split("_")) for c in cells]
        self.common = {t for t in set().union(*cell_words) if sum(t in w for w in cell_words) >= 0.8 * len(cell_words)} \
            if cell_words else set()

    @property
    def labelled(self) -> bool:
        """The lines are labels (real_estate, line_5_lesser_earned_income), not counted: not renumbered."""
        return bool(self.ident["ids"]) and any(_count_key(v) is None for v in self.ident["ids"].values())

    def _id(self, c):
        return self.ident["cells"].get(c["name"])

    def pat_of(self, c):
        x = self._id(c)
        return x[0] if x else c["name"]

    def num_of(self, c):
        x = self._id(c)
        return x[1] if x else None

    def at(self, k):
        return [c for c in self.cells if c[self.pos_axis] == k]

    def basis(self) -> dict:
        """{position: its commonest wording}: what `numbers` reads a series' continuation from, the same for every
        button and for the card's "numbered off" count (2026-10-22: a column of vehicles 3-4, continued from another
        grid, was shown off its rows, and its button then did nothing)."""
        return {k: collections.Counter(self.pat_of(c) for c in self.at(k)).most_common(1)[0][0] for k in self.positions}

    def numbers(self, bp: dict, g: list[dict], lines: dict, chosen: dict) -> tuple[dict, bool]:
        """({line index: its number or None}, lettered): one number per line, by position; letters and lettered line
        numbers (5a) keep theirs."""
        cells, num_of = self.cells, self.num_of
        free = [c for c in cells if c[self.pos_axis] not in self.locked]
        toks = [num_of(c) for c in free]
        lines_idx = sorted({c[self.num_axis] for c in cells})
        ids = self.ident["ids"]
        s0 = next((c.get("series_start") for c in g if c.get("series_start")), None)
        if s0:                   # one list across pages (grid_check.series): numbered on from the parts before it,
            return {i: s0 + n for n, i in enumerate(lines_idx)}, False      # whatever its names carry now
        # lines named, not counted (GA 500: line_5_lesser_earned_income ...; real_estate, household_furniture): each
        # line's number is its identifier, the label its cells share (`identify`); a line without one is left
        if ids and any(_count_key(v) is None for v in ids.values()):
            return {i: None for i in lines_idx}, False      # labels are not renumbered: each cell keeps its own
        toks = [t for t in toks if t and _count_key(t) is not None]
        lettered = any(not t.isdigit() for t in toks)
        if lettered:
            return {i: None for i in lines_idx}, True
        offs = collections.Counter(int(num_of(c)) - lines_idx.index(c[self.num_axis])
                                   for c in free if (num_of(c) or "").isdigit())
        top = offs.most_common()
        tied = [o for o, n in top if n == top[0][1]] if top else [1]
        start = 1 if 1 in tied else min(tied)              # a tie (one column shifted in a two-column table): from 1
        names = {c["name"] for c in g}
        # a grid continuing a series from an earlier page (Andrew, 2026-10-24, ACORD 140 p2-G2: subjects of insurance
        # 6-10 under page 1's 1-5; its amount column ran 6-10, the other nine 1-5; "should be easy to detect the
        # consistent row labels though regardless of number"): any column's start that continues a series ending
        # just before it elsewhere on the form is every line's, even when most columns start at 1
        # only a column that itself runs down every line by steps of 1 from that start counts (I-589 p3-G1, a child's
        # fields stacked and all numbered 2, is not a series)
        whole = set()
        for k in {c[self.pos_axis] for c in free}:
            cs = [c for c in free if c[self.pos_axis] == k]
            os_ = {int(num_of(c)) - lines_idx.index(c[self.num_axis]) if (num_of(c) or "").isdigit() else None for c in cs}
            if len(cs) == len(lines_idx) >= 2 and len(os_) == 1 and None not in os_:
                whole |= os_
        for o, _n in top:
            if o > 1 and o != start and o in whole and _continues(bp, names, list(chosen.values()), o,
                                                                  before_page=cells[0]["page"]):
                return {i: o + n for n, i in enumerate(lines_idx)}, False
        if start != 1 and not (start > 1 and (_continues(bp, names, list(chosen.values()), start)
                                              or _printed(bp, cells, lines))):
            start = 1                                      # the first line is 1, unless the series began elsewhere
        return {i: start + n for n, i in enumerate(lines_idx)}, False   # or the numbers are printed on the page

    def rename(self, c: dict, pat: str, number: dict, lettered: bool) -> str:
        """The cell's name under its position's wording `pat` and its line's number."""
        num = number[c[self.num_axis]]
        if num is None and "N" in pat.split("_") and not lettered and self._id(c) and self.pat_of(c) != pat:
            toks_ = pat.split("_")             # a labelled line: the wording picked, with the cell's own line label
            toks_[max(i for i, t in enumerate(toks_) if t == "N")] = self.num_of(c)
            return "_".join(toks_)
        if num is None or "N" not in pat.split("_"):
            base = pat if "N" not in pat.split("_") else c["name"]
            new = base if not lettered else c["name"]
            if lettered and self.pat_of(c) != pat and self.num_of(c):
                toks_ = pat.split("_")
                toks_[max(i for i, t in enumerate(toks_) if t == "N")] = self.num_of(c)
                new = "_".join(toks_)
            return new
        toks_ = pat.split("_")
        toks_[max(i for i, t in enumerate(toks_) if t == "N")] = str(num)
        # in the column's own wording: reshaping to the naming standard is that pass's job, and reshaping only the
        # cells that change left a column in two shapes (ACORD 126: location_1_nbr beside location_number_2)
        return "_".join(toks_)


def resolve(bp: dict, g: list[dict], lines: dict, score=None, forced: dict | None = None) -> dict:
    """{status: ok | fixed | unsure | confused, renames, unsure: [{pos, caption, candidates, cells}], why}."""
    forced = forced or {}
    cells = body(g)
    F = _Frame(g)                      # labelled lines too: each keeps its label, the position's wording settled
    reading, pos_axis, num_axis, how = F.reading, F.pos_axis, F.num_axis, F.how
    names = {c["name"] for c in g}
    fields = bp.get("fields") or {}
    pat_of, locked, num_of, common, positions = F.pat_of, F.locked, F.num_of, F.common, F.positions
    # (1) wording per position
    chosen, unsure, whys = {}, [], []
    for k in positions:
        pc_ = [c for c in cells if c[pos_axis] == k]
        if k in forced:
            chosen[k] = forced[k]
            continue
        pick = same_words(pc_, pat_of, common)
        if pick:                       # one thing in several spellings: settled in code, no caption, no model
            chosen[k] = pick
            continue
        cap = position_caption(bp, pc_, how, lines)
        p, why = choose_wording(pc_, cap, score, pat_of)
        if p is None:
            unsure.append({"pos": k, "caption": cap, "cells": [c["name"] for c in pc_],
                           "candidates": sorted({pat_of(c) for c in pc_})})
            whys.append(f"position {k + 1}: {why}")
        else:
            chosen[k] = p
    if unsure:
        return {"status": "unsure", "renames": {}, "unsure": unsure, "why": "; ".join(whys)}
    # (2) numbers: one per line, by position; letters and lettered line numbers (5a) keep theirs
    number, lettered = F.numbers(bp, g, lines, chosen)
    # (3) the new names, checked
    ren = {}
    for c in cells:
        if c[pos_axis] in locked:
            # line numbers stay; an equivalent spelling of the position's wording takes the chosen one, with this
            # cell's own line number (CA 540: line_44_credit_name beside line_N_credit_nm)
            pat = chosen.get(c[pos_axis])
            mine = pat_of(c)
            if pat and mine != pat and "N" in pat.split("_") and equivalent(mine, pat, common) and num_of(c):
                toks_ = pat.split("_")
                toks_[toks_.index("N")] = num_of(c)
                ren[c["name"]] = "_".join(toks_)
            continue
        new = F.rename(c, chosen[c[pos_axis]], number, lettered)
        if new != c["name"]:
            ren[c["name"]] = new
    # a rename that changes what a cell says (different words, not a variant) is a judgment: Jev, not code
    reworded = [o for o, n in ren.items() if not _variant(_pattern(o) or o, _pattern(n) or n)
                and not equivalent(_pattern(o) or o, _pattern(n) or n, common)]
    # two cells exchanging names: the rows' order is a judgment (FL-100); not in a table of one position, where the
    # numbers only follow the boxes' order (MR01's company number, 2026-10-20: "should be easy to just renumber")
    swaps = [o for o, n in ren.items() if ren.get(n) == o] if len(positions) > 1 else []
    if swaps:
        return {"status": "unsure", "renames": {}, "unsure": [{"pos": None, "caption": None, "cells": swaps,
                "candidates": sorted(swaps)}], "why": f"would swap {swaps[0]} and {ren[swaps[0]]}"}
    if reworded:
        return {"status": "unsure", "renames": {}, "unsure": [{"pos": None, "caption": None, "cells": reworded,
                "candidates": sorted({_pattern(o) or o for o in reworded} | {_pattern(ren[o]) or ren[o] for o in reworded})}],
                "why": f"would change what {len(reworded)} cell(s) say ({reworded[0]} -> {ren[reworded[0]]})"}
    after = [dict(c, name=ren.get(c["name"], c["name"])) for c in g]
    outside = {_standard(n, sp if isinstance(sp, dict) else {}): n for n, sp in fields.items() if n not in names}
    clash = [n for n in ren.values() if (n in fields and n not in ren) or n in outside]   # also in the standard's shape
    dup = len(set(c["name"] for c in after)) < len(after)
    ok, why = _on_pattern(after) if ren else (True, "nothing renamed")     # the renamed grid, read again
    if clash or dup or not ok:
        return {"status": "confused", "renames": ren, "unsure": [],
                "why": "; ".join(filter(None, [f"would take names other fields keep: {', '.join(clash[:4])}" if clash else "",
                                               "two cells would share a name" if dup else "",
                                               "" if ok else f"still off the code check: {why}"]))}
    return {"status": "fixed" if ren else "ok", "renames": ren, "unsure": [], "why": "; ".join(whys) or reading}


def standardize(bp: dict, g: list[dict], lines: dict, score=None, positions: list[int] | None = None,
                lines_: list[int] | None = None, forced: dict | None = None) -> dict:
    """The "standardize" buttons on the Grids card (Andrew, 2026-10-19; reworked 2026-10-22: "it often doesn't work
    and never says why clearly"). {renames, chosen: {pos: (wording, how)}, left: [why a cell or position was left, in
    plain words], why, pulled: [cells of other lines or positions renamed with them]}.

    A position (`positions`, 0-based; None: every position with more than one wording or numbers off its lines) takes
    one wording, each cell its line's number. The wording: `forced` (the person's pick, {pos: wording}), else the
    resolver's (equivalent spellings settled in code, else the caption and the name-check model), else the commonest
    when it has a majority; a position whose wordings split evenly is left, with its wordings, for the person to pick.
    `lines_` (0-based) instead renumbers lines: each cell takes its line's number (a lettered grid: the letter most
    of the line has) under its position's wording. Numbers come from one basis for every button (`_Frame.basis`), so
    the card's "numbered off" and the button agree. A rename onto a name a cell of another line or position holds,
    where that cell is itself off the pattern (a shifted series: rows 2-8 numbered 3-9), takes that cell along
    (`pulled`); a rename onto a name some other field keeps is left and says which field and where."""
    F = _Frame(g)
    forced = forced or {}
    fields, names = bp.get("fields") or {}, {c["name"] for c in g}
    if lines_ is not None:
        r = _lines_renames(bp, g, lines, F, lines_)
        full = lambda: _lines_renames(bp, g, lines, F, sorted({c[F.num_axis] for c in F.cells}))["renames"]   # noqa: E731
    else:
        r = _position_renames(bp, g, lines, F, score, positions, forced)
        full = lambda: _position_renames(bp, g, lines, F, score, None, forced)["renames"]                     # noqa: E731
    ren, left = r["renames"], r["left"]
    pulled = _chain(ren, full, names) if any(n in names and n not in ren for n in ren.values()) else []
    ren = _clashes(ren, fields, names, left, _where(g, fields))
    return {"renames": ren, "chosen": r.get("chosen") or {}, "left": left, "pulled": [p for p in pulled if p in ren],
            "why": r["why"]}


def _position_renames(bp, g, lines, F, score, positions, forced) -> dict:
    want = [k for k in F.positions if positions is None or k in positions]
    chosen, left = {}, []
    number0, lettered0 = F.numbers(bp, g, lines, F.basis())
    for k in want:
        pc_ = F.at(k)
        pats = collections.Counter(F.pat_of(c) for c in pc_)
        if k in forced:
            chosen[k] = (forced[k], "your pick")
            continue
        if len(pats) < 2:                    # one wording: standardize when its numbers are off their lines'
            pat = next(iter(pats))
            if k not in F.locked and any(F.rename(c, pat, number0, lettered0) != c["name"] for c in pc_):
                chosen[k] = (pat, "its own wording, numbered as its lines")
            elif positions is not None:
                left.append(f"position {k + 1}: already one wording, numbered as its lines" if k not in F.locked
                            else f"position {k + 1}: printed line numbers, kept as they are")
            continue
        pick = same_words(pc_, F.pat_of, F.common)
        how = "the same words spelled two ways, settled in code"
        if not pick:
            cap = position_caption(bp, pc_, F.how, lines)
            pick, how = choose_wording(pc_, cap, score, F.pat_of)
        if not pick:
            p, n = pats.most_common(1)[0]
            if n > sum(pats.values()) / 2:
                pick, how = p, f"the commonest wording, {n} of {sum(pats.values())} cells"
            else:
                left.append(f"position {k + 1}: no wording has a majority "
                            f"({', '.join(f'{p} x{n}' for p, n in pats.most_common())}); pick one")
                continue
        chosen[k] = (pick, how)
    if not chosen:
        return {"renames": {}, "chosen": {}, "left": left, "why": "nothing to change"}
    number, lettered = F.numbers(bp, g, lines, {**F.basis(), **{k: v[0] for k, v in chosen.items()}})
    ren = {}
    words = lambda n: sorted(t for t in n.split("_") if not re.fullmatch(r"\d+[a-z]?|N", t))  # noqa: E731
    for k, (pat, how) in chosen.items():
        reworded = []
        for c in F.at(k):
            # a wording the code chose (not the person's pick) renames a cell only as far as its numbers, or a
            # spelling of the same words (equivalent): changing what a cell says is a judgment (Andrew, 2026-10-26;
            # ACORD 131 p3-G2 contractual_agreements_desc_txt -> ..._desc_explanation_txt was proposed)
            if how != "your pick" and words(F.pat_of(c)) != words(pat) and not equivalent(F.pat_of(c), pat, F.common):
                reworded.append(c["name"])
                continue
            if k in F.locked:
                mine = F.num_of(c)
                if not F._id(c):                          # a cell the reading does not place: left as it is
                    continue
                if "N" in pat.split("_") and mine:
                    toks_ = pat.split("_")
                    toks_[toks_.index("N")] = mine
                    new = "_".join(toks_)
                else:
                    continue
            else:
                new = F.rename(c, pat, number, lettered)
            if new != c["name"]:
                ren[c["name"]] = new
        if reworded:
            left.append(f"position {k + 1}: {len(reworded)} cell(s) worded otherwise ({', '.join(reworded[:3])}"
                        f"{' ...' if len(reworded) > 3 else ''}): pick the wording to rename them to it")
    why = "; ".join(f"position {k + 1}: {p} ({how})" for k, (p, how) in sorted(chosen.items()))
    return {"renames": ren, "chosen": dict(chosen), "left": left, "why": why}


def _lines_renames(bp, g, lines, F, which) -> dict:
    """The lines in `which` renumbered: a cell whose number is not its line's takes it, under the wording most of its
    position has (its own when the position agrees). A lettered grid: the letter most of the line's cells carry."""
    left, ren = [], {}
    number, lettered = F.numbers(bp, g, lines, F.basis())
    idx = sorted({c[F.num_axis] for c in F.cells})
    for i in which:
        mine = [c for c in F.cells if c[F.num_axis] == i and c[F.pos_axis] not in F.locked]
        if lettered:               # the letter most of the line carries, its printed line numbers (locked) counted
            every = [c for c in F.cells if c[F.num_axis] == i]
            toks = collections.Counter(F.num_of(c) for c in every if F.num_of(c))
            if not toks:
                continue
            tok, n = toks.most_common(1)[0]
            if n <= len(every) / 2 and len(toks) > 1:
                left.append(f"line {idx.index(i) + 1 if i in idx else i + 1}: its cells carry "
                            f"{', '.join(t for t, _ in toks.most_common())}, none a majority; rename them by hand")
                continue
        for c in mine:
            pats = collections.Counter(F.pat_of(x) for x in F.at(c[F.pos_axis]))
            pat, n = pats.most_common(1)[0]
            if n <= sum(pats.values()) / 2 and F.pat_of(c) != pat:
                why = (f"position {c[F.pos_axis] + 1}: no wording has a majority "
                       f"({', '.join(p for p, _ in pats.most_common())}); standardize it first, then renumber")
                if why not in left:                      # once per position, not once per cell
                    left.append(why)
                continue
            if lettered:
                toks_ = pat.split("_")
                if "N" not in toks_ or F.num_of(c) == tok:
                    continue
                toks_[max(j for j, t in enumerate(toks_) if t == "N")] = tok
                new = "_".join(toks_)
            else:
                new = F.rename(c, pat, number, lettered)
            if new != c["name"]:
                ren[c["name"]] = new
    why = "; ".join(f"line {idx.index(i) + 1 if i in idx else i + 1}: "
                    + ("its letter" if lettered else f"number {number.get(i)}") for i in which)
    return {"renames": ren, "left": left, "why": why}


def _chain(ren: dict, full, names: set) -> list:
    """Cells of the grid holding a name `ren` moves onto, renamed too when the whole grid's standardizing renames them
    (a shifted series): pulled in until nothing more moves. `full` is called once, when needed."""
    whole = full()
    out = []
    while True:
        add = {h: whole[h] for h in ren.values() if h in names and h not in ren and h in whole}
        if not add:
            return out
        ren.update(add)
        out += list(add)


def _where(g: list[dict], fields: dict):
    """A name's holder, said for a person: a cell of this grid by row and column, or a field elsewhere by page."""
    at = {c["name"]: (c["row"], c["col"]) for c in g}

    def where(n):
        if n in at:
            return f"row {at[n][0] + 1}, column {at[n][1] + 1} of this grid"
        spec = fields.get(n) if isinstance(fields.get(n), dict) else {}
        w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
        return f"a field outside this grid, p{w.get('page')}" if w.get("page") else "a field outside this grid"
    return where


def _clashes(ren: dict, fields: dict, names: set, left: list, where=None) -> dict:
    where = where or (lambda n: "another field")
    for o, n in list(ren.items()):
        if (n in fields and n not in ren) or (n in names and n not in ren):
            left.append(f"{o} -> {n}: {n} is taken by {where(n)}; rename that one first")
            ren.pop(o)
    targets = collections.Counter(ren.values())
    for o, n in list(ren.items()):
        if targets[n] > 1:
            left.append(f"{o} -> {n}: two cells would both become {n}; left")
            ren.pop(o)
    return ren


def text_match_score():
    """The name-check model as `score(caption, [descriptions])`, or None when it is not installed."""
    try:
        from petey.label import text_match as tm
        if not tm.available():
            return None
    except Exception:
        return None
    return lambda caption, descs: tm.score_pairs([(caption, tm.name_words(d, text=caption)) for d in descs])
