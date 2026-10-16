"""Grids are named consistently (Andrew, 2026-10-15: "the naming conventions for each column should be identical").

A grid: text boxes in two or more columns (same left edge and width) that share two or more rows (same height on the
page); checked when it is numbered along one side (3+ cells one way, 2+ the other, most names carrying an iteration:
a number, or a lone letter as in property_b_). In a grid every cell's name has one shape, its iteration standing in
for N: either the column decides the
shape and the row decides the number (AO 40B's expense table: expense_private_N_amt, N = row), or the row decides the
shape and the column decides the number (Form 8825's income grid: gross_rents_N_amt, N = property column). The check
picks the reading most cells agree with and lists the cells that break it: another shape than their column's (or
row's), or another number than their row's (or column's). Found by layout only, no names or forms listed.

    PYTHONPATH=. venv/bin/python eval/grid_naming.py je__ao040b je__f8825 ...            # list what breaks
    PYTHONPATH=. venv/bin/python eval/grid_naming.py je__ao040b --fix                    # the renames it would make
    PYTHONPATH=. venv/bin/python eval/grid_naming.py je__ao040b --fix --apply            # make them

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


def repeated_blocks(cells_by_page: dict[int, list[dict]], cols_by_page: dict[int, dict]) -> list[list[dict]]:
    """Repeated blocks (2026-10-16, FAA 8050-1 page 3: nine signer blocks of applicant / signature / date / signer /
    title over three lines each): columns of same-placed, same-width boxes that repeat at one regular spacing, two or
    more of them with the same spacing and count, starting within one spacing of each other. Each repeat is a row
    (the block's iteration), each column a slot, so the table's checks and fixes apply as they are."""
    out = []
    for page, cols in cols_by_page.items():
        periodic = []
        for k, cs in cols.items():
            if len(cs) < MIN_REPEATS:
                continue
            ys = sorted(c["y"] for c in cs)
            gaps = [b - a for a, b in zip(ys, ys[1:])]
            med = sorted(gaps)[len(gaps) // 2]
            if med > 8 and all(abs(g - med) <= BLOCK_TOL for g in gaps):
                periodic.append((k, med, ys[0], sorted(cs, key=lambda c: c["y"])))
        used = set()
        for i, (k, stride, y0, cs) in enumerate(periodic):
            if k in used:
                continue
            members = [(k, y0, cs)]
            for k2, s2, y2, cs2 in periodic[i + 1:]:
                if k2 not in used and abs(s2 - stride) <= BLOCK_TOL and len(cs2) == len(cs) and abs(y2 - y0) < stride:
                    members.append((k2, y2, cs2))
            if len(members) < 2:
                continue
            # a block runs over two or more lines (FAA 8050-1: three); repeats of one line are tables, found as such
            # (2026-10-16: single-line "blocks" turned 3-row tables into blocks and raised false alarms on ACORD 125/130)
            if len({round((m[1] - y0) / 4) for m in members}) < 2:
                continue
            # a slot per column, in reading order within the block: by its offset down the block, then across
            members.sort(key=lambda m: (round((m[1] - y0) / 4), min(c["x"] for c in m[2])))
            used.update(m[0] for m in members)
            out.append([{"name": c["name"], "page": page, "row": r, "col": ci, "block": True}
                        for ci, (_k, _y, cs_) in enumerate(members) for r, c in enumerate(cs_)])
    return out


def grids(bp: dict) -> list[list[dict]]:
    """[[cell]] per grid; a cell = {name, page, row, col}. Repeated blocks (`repeated_blocks`) count as grids, a block per row,
    and a table the code would otherwise find inside one is left to the block."""
    by_page = collections.defaultdict(list)
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        if w.get("widget_type") != "text" or not w.get("rect"):
            continue
        x0, y0, x1, y1 = w["rect"]
        by_page[w["page"]].append({"name": n, "page": w["page"], "x": x0, "w": x1 - x0, "y": (y0 + y1) / 2})
    out = []
    cols_by_page: dict[int, dict] = {}
    for page, cells in by_page.items():
        cols: dict[tuple, list[dict]] = collections.defaultdict(list)
        cols_by_page[page] = cols
        xs, ws = _cluster([c["x"] for c in cells], TOL_X), None
        for c in cells:
            c["xc"] = _near(c["x"], xs, TOL_X)
        for xi in set(c["xc"] for c in cells):
            group = [c for c in cells if c["xc"] == xi]
            for wc in _cluster([c["w"] for c in group], TOL_W):
                cols[(xi, round(wc))] = [c for c in group if abs(c["w"] - wc) <= TOL_W]
        ys = _cluster([c["y"] for c in cells], TOL_Y)
        for c in cells:
            c["row"] = _near(c["y"], ys, TOL_Y)
        keys = [k for k, v in cols.items() if len(v) >= 2]
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
            for blk in blocks:
                if len(blk) < 2:
                    continue
                grid = [{"name": c["name"], "page": page, "row": blk.index(c["row"]), "col": ci}
                        for ci, k in enumerate(ks) for c in cols[k] if c["row"] in blk]
                out.append(grid)
    reps = repeated_blocks(by_page, cols_by_page)
    names = [{c["name"] for c in b} for b in reps]
    # a table mostly inside a block is the block's (I-130 page 12: a 3 x 6 table took the block's cells and two others)
    out = [g for g in out if not any(len({c["name"] for c in g} & ns) >= 0.5 * len(g) for ns in names)]
    return out + reps


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


def body(grid: list[dict]) -> list[dict]:
    """The grid without a last row of totals (every name starting total_)."""
    last = max(c["row"] for c in grid)
    if all(c["name"].startswith("total") for c in grid if c["row"] == last):
        return [c for c in grid if c["row"] != last]
    return grid


def breaks(grid: list[dict]) -> tuple[str, list[str]]:
    """(reading, [cell problems]) for one grid. A last row of totals (every name starting total_) is left out."""
    grid = body(grid)
    def score(shape_axis: str, num_axis: str):
        shapes, nums = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
        for c in grid:
            shapes[c[shape_axis]][_shape(c["name"])] += 1
            nums[c[num_axis]][_core(_number(c["name"]))] += 1
        probs = []
        for c in grid:
            want_s = shapes[c[shape_axis]].most_common(1)[0][0]
            want_n = nums[c[num_axis]].most_common(1)[0][0]
            if _shape(c["name"]) != want_s and _close(_shape(c["name"]), want_s):
                probs.append(f"{c['name']}: its {('column' if shape_axis == 'col' else 'row')} is named {want_s}")
            elif (_shape(c["name"]) == want_s and want_n is not None
                  and want_n not in {_core(c["name"].split("_")[i]) for i in _iter_tokens(c["name"])}):
                # any of its numbers may be the row's (ACORD 130: loc_1_address_line_2_txt is location 1's line 2)
                probs.append(f"{c['name']}: its {('row' if num_axis == 'row' else 'column')} is number {want_n}")
        return probs
    def uniform(axis: str) -> float:                # how far one shape runs along each column (or row)
        by = collections.defaultdict(collections.Counter)
        for c in grid:
            by[c[axis]][_shape(c["name"])] += 1
        return sum(v.most_common(1)[0][1] for v in by.values()) / len(grid)
    if uniform("col") >= uniform("row"):        # each column one kind, the row numbers it
        return "columns", score("col", "row")
    return "rows", score("row", "col")          # each row one kind, the column numbers it


def iterated(grid: list[dict]) -> bool:
    """A table numbered along one side: 3+ cells one way and 2+ the other, most cells carrying an iteration."""
    nrow, ncol = len({c["row"] for c in grid}), len({c["col"] for c in grid})
    if not ((nrow >= 3 and ncol >= 2) or (nrow >= 2 and ncol >= 3)):
        return False
    return sum(_number(c["name"]) is not None for c in grid) >= 0.5 * len(grid)


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


def on_pattern(grid: list[dict]) -> tuple[bool, str]:
    """The quick code check, before any model (Andrew, 2026-10-15: "there should be a pattern for every column that
    will only vary by iteration, and the iterations should descend by 1"): (passes, how it reads or why not). Passes
    when, read by columns (or the transpose): every cell carries an iteration, every column one pattern its cells
    differ from only in that iteration, every row one number, the rows numbered top to bottom by steps of 1. A last
    row of totals is left out. The naming standard's shape is not checked here: it is its own step."""
    grid = body(grid)
    for c in grid:
        if _pattern(c["name"]) is None:
            return False, f"{c['name']}: no iteration"
    whys = []
    for reading, pat_axis, num_axis in (("columns", "col", "row"), ("rows", "row", "col")):
        line, other = ("column", "row") if pat_axis == "col" else ("row", "column")
        pats, nums = collections.defaultdict(set), collections.defaultdict(set)
        for c in grid:
            pats[c[pat_axis]].add(_pattern(c["name"]))
            nums[c[num_axis]].add(_number(c["name"]))
        bad = next((f"{line} {k + 1} has {len(v)} patterns ({', '.join(sorted(v))})"
                    for k, v in sorted(pats.items()) if len(v) > 1), None) or \
            next((f"{other} {k + 1} has {len(v)} numbers ({', '.join(sorted(v))})"
                  for k, v in sorted(nums.items()) if len(v) > 1), None)
        if not bad:
            seq = [next(iter(nums[k])) for k in sorted(nums)]
            if not all(_next(a, b) for a, b in zip(seq, seq[1:])):
                bad = f"{other}s numbered {', '.join(seq)}, not by steps of 1"
        if not bad:
            return True, reading
        whys.append(f"by {line}s: {bad}")
    return False, "; ".join(whys)


def _standard(name: str, spec: dict) -> str:
    """The naming standard's shape for a fixed name (iteration before the suffix): standardize_names.standard."""
    try:
        from standardize_names import standard
    except ImportError:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
        from standardize_names import standard
    return standard(name, spec)[0]


def fixes(bp: dict) -> tuple[dict[str, str], list[str]]:
    """({cell: new name}, [cells it cannot fix]) for every iterated grid."""
    ren, left = {}, []
    for g in grids(bp):
        if not iterated(g):
            continue
        reading, probs = breaks(g)
        if not probs:
            continue
        shape_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
        last = max(c["row"] for c in g)
        cells = [c for c in g if not (c["row"] == last and all(x["name"].startswith("total") for x in g if x["row"] == last))]
        shapes = collections.defaultdict(collections.Counter)
        for c in cells:
            shapes[c[shape_axis]][_shape(c["name"])] += 1
        offs = collections.Counter(int(_number(c["name"])) - c[num_axis] for c in cells
                                   if (_number(c["name"]) or "").isdigit())
        k, kn = offs.most_common(1)[0] if offs else (None, 0)
        regular = bool(offs) and kn >= 0.6 * sum(offs.values())
        line_nums = collections.defaultdict(collections.Counter)      # the number the rest of the line carries
        for c in cells:
            if (_number(c["name"]) or "").isdigit():
                line_nums[c[num_axis]][int(_number(c["name"]))] += 1
        bad = {p.split(":")[0] for p in probs}
        here: dict[str, str] = {}
        for c in cells:
            if c["name"] not in bad:
                continue
            want = shapes[c[shape_axis]].most_common(1)[0][0]
            nn = want.split("_").count("N")
            if nn != 1:
                left.append(f"{c['name']}: its column's pattern {want} has " + ("no number" if not nn else "more than one number"))
                continue
            got = line_nums[c[num_axis]].most_common(2)
            if got and (len(got) == 1 or got[0][1] > got[1][1]) and got[0][1] >= 2:
                num = got[0][0]                  # most of its row (or column) agrees
            elif regular:
                num = c[num_axis] + k            # the table's own numbering, by position
            else:
                left.append(f"{c['name']}: no clear number for its row")
                continue
            if num < 1:
                left.append(f"{c['name']}: would be numbered {num}")
                continue
            new = "_".join(str(num) if t == "N" else t for t in want.split("_"))
            new = _standard(new, (bp.get("fields") or {}).get(c["name"]) or {})   # the number before the suffix
            if new != c["name"]:
                here[c["name"]] = new
        if len(here) > 0.4 * len(cells):         # most of the table would change: its pattern is not clear
            left.append(f"grid p{g[0]['page']} ({len(cells)} cells): {len(here)} would change, left for a person")
            continue
        ren.update(here)
    return ren, left


def check(bp: dict) -> list[str]:
    out = []
    for g in grids(bp):
        if not iterated(g):
            continue
        reading, probs = breaks(g)
        if probs:
            nrow, ncol = max(c["row"] for c in g) + 1, max(c["col"] for c in g) + 1
            out += [f"grid p{g[0]['page']} ({nrow}x{ncol}, named by {reading}): {p}" for p in probs]
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
                                         "(eval/grid_naming.py --fix)"} for o, n in ren.items()], [])
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


def _continues(bp: dict, grid_names: set, pats: list[str], start: int) -> bool:
    """A series begun elsewhere: a field outside the table on the same pattern numbered start - 1 (FAA 8050-1's
    page 2 signer block before page 3's 2-10)."""
    fields = bp.get("fields") or {}
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


def _varying(names: list[str]):
    """The token position of the number that changes from line to line in a position's names (CMS-855A
    final_adverse_legal_action_1_txt_3: the 1 changes, the 3 does not); None to take the last as usual."""
    toks = [n.split("_") for n in names]
    if len({len(t) for t in toks}) != 1:
        return None
    for i in reversed(range(len(toks[0]))):
        vals = {t[i] for t in toks}
        if len(vals) > 1 and all(LINE.match(v) for v in vals):
            return i
    return None


def _pattern_at(name: str, i):
    toks = name.split("_")
    if i is None or i >= len(toks) or not LINE.match(toks[i]):
        return _pattern(name)
    toks[i] = "N"
    return "_".join(toks)


def _verify(cells: list[dict], pos_axis: str, num_axis: str, vary: dict) -> tuple[bool, str]:
    """The code check, reading each position's varying number: one pattern per position, one number per line, the
    lines numbered by steps of 1 (letters too)."""
    pats, nums = collections.defaultdict(set), collections.defaultdict(set)
    for c in cells:
        i = vary.get(c[pos_axis])
        pats[c[pos_axis]].add(_pattern_at(c["name"], i) or c["name"])
        toks = c["name"].split("_")
        nums[c[num_axis]].add(toks[i] if i is not None and i < len(toks) else _number(c["name"]))
    bad = next((f"position {k + 1} has {len(v)} wordings" for k, v in sorted(pats.items()) if len(v) > 1), None) or \
        next((f"line {k + 1} has {len(v)} numbers" for k, v in sorted(nums.items()) if len(v) > 1), None)
    if bad:
        return False, bad
    seq = [next(iter(nums[k])) for k in sorted(nums)]
    if None in seq:
        return False, "a line without a number"
    seq = [_core(x) for x in seq]
    if not all(_next(a, b) for a, b in zip(seq, seq[1:])):
        return False, f"lines numbered {', '.join(seq)}, not by steps of 1"
    return True, "on pattern"


def resolve(bp: dict, g: list[dict], lines: dict, score=None, forced: dict | None = None) -> dict:
    """{status: ok | fixed | unsure | confused, renames, unsure: [{pos, caption, candidates, cells}], why}."""
    forced = forced or {}
    cells = body(g)
    reading, _ = breaks(g)
    pos_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
    how = "block" if g[0].get("block") else reading
    names = {c["name"] for c in g}
    fields = bp.get("fields") or {}
    # which number varies, per position (two-number names: CMS-855A final_adverse_legal_action_1_txt_3)
    vary = {k: _varying([c["name"] for c in cells if c[pos_axis] == k]) for k in {c[pos_axis] for c in cells}}
    pat_of = lambda c: _pattern_at(c["name"], vary[c[pos_axis]]) or c["name"]                      # noqa: E731

    # line-number names keep their numbers (Andrew's exception: line_116_direct_deposit_amt, line_3_3_make on tax and
    # court forms): a position whose varying number follows "line" is the form's own numbering, not an iteration
    def _line_numbered(k):
        names_k = [c["name"] for c in cells if c[pos_axis] == k]
        pk = _pattern_at(names_k[0], vary[k]) if names_k else None
        toks_k = (pk or "").split("_")
        return "N" in toks_k and toks_k.index("N") > 0 and toks_k[toks_k.index("N") - 1] in ("line", "ln") or \
            bool(re.match(r"line_\d", names_k[0] if names_k else ""))
    locked = {k for k in vary if _line_numbered(k)}

    def num_of(c):
        i = vary[c[pos_axis]]
        toks = c["name"].split("_")
        return toks[i] if i is not None and i < len(toks) else _number(c["name"])
    # (1) wording per position
    chosen, unsure, whys = {}, [], []
    for k in sorted({c[pos_axis] for c in cells}):
        pc_ = [c for c in cells if c[pos_axis] == k]
        if k in forced:
            chosen[k] = forced[k]
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
    free = [c for c in cells if c[pos_axis] not in locked]
    toks = [num_of(c) for c in free]
    if any(t and not t.isdigit() for t in toks):
        lettered = True
    else:
        lettered = False
    lines_idx = sorted({c[num_axis] for c in cells})
    if lettered:
        number = {i: None for i in lines_idx}
    else:
        offs = collections.Counter(int(num_of(c)) - lines_idx.index(c[num_axis])
                                   for c in free if (num_of(c) or "").isdigit())
        top = offs.most_common()
        tied = [o for o, n in top if n == top[0][1]] if top else [1]
        start = 1 if 1 in tied else min(tied)              # a tie (one column shifted in a two-column table): from 1
        if start != 1 and not (start > 1 and (_continues(bp, names, list(chosen.values()), start)
                                              or _printed(bp, cells, lines))):
            start = 1                                      # the first line is 1, unless the series began elsewhere
        number = {i: start + n for n, i in enumerate(lines_idx)}   # or the numbers are printed on the page
    # (3) the new names, checked
    ren = {}
    for c in cells:
        if c[pos_axis] in locked:
            continue                           # line numbers stay
        pat = chosen[c[pos_axis]]
        num = number[c[num_axis]]
        if num is None or "N" not in pat.split("_"):
            base = pat if "N" not in pat.split("_") else c["name"]
            new = base if not lettered else c["name"]
            if lettered and pat_of(c) != pat:
                new = pat.replace("N", num_of(c) or "N")
        else:
            toks_ = pat.split("_")
            toks_[max(i for i, t in enumerate(toks_) if t == "N")] = str(num)
            # in the column's own wording: reshaping to the naming standard is that pass's job, and reshaping only the
            # cells that change left a column in two shapes (ACORD 126: location_1_nbr beside location_number_2)
            new = "_".join(toks_)
        if new != c["name"]:
            ren[c["name"]] = new
    # a rename that changes what a cell says (different words, not a variant) is a judgment: Jev, not code
    reworded = [o for o, n in ren.items() if not _variant(_pattern(o) or o, _pattern(n) or n)]
    swaps = [o for o, n in ren.items() if ren.get(n) == o]
    if swaps:                                  # two cells exchanging names: the rows' order is a judgment (FL-100)
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
    ok, why = _verify([dict(c, name=ren.get(c["name"], c["name"])) for c in cells if c[pos_axis] not in locked],
                      pos_axis, num_axis, vary) if len(locked) < len(vary) else (True, "line numbers")
    if clash or dup or not ok:
        return {"status": "confused", "renames": ren, "unsure": [],
                "why": "; ".join(filter(None, [f"would take names other fields keep: {', '.join(clash[:4])}" if clash else "",
                                               "two cells would share a name" if dup else "",
                                               "" if ok else f"still off the code check: {why}"]))}
    return {"status": "fixed" if ren else "ok", "renames": ren, "unsure": [], "why": "; ".join(whys) or reading}


def text_match_score():
    """The name-check model as `score(caption, [descriptions])`, or None when it is not installed."""
    try:
        from petey.label import text_match as tm
        if not tm.available():
            return None
    except Exception:
        return None
    return lambda caption, descs: tm.score_pairs([(caption, tm.name_words(d, text=caption)) for d in descs])
