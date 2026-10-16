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


def grids(bp: dict) -> list[list[dict]]:
    """[[cell]] per grid; a cell = {name, page, row, col}."""
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
    for page, cells in by_page.items():
        cols: dict[tuple, list[dict]] = collections.defaultdict(list)
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


def _close(a: str, b: str) -> bool:
    """Two shapes for the same thing (gross_rents_amt_N / gross_rents_N_amt, property_desc / property_desc_N), not
    two different items that happen to share a column: most of their words the same."""
    ta, tb = set(a.split("_")) - {"N"}, set(b.split("_")) - {"N"}
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def breaks(grid: list[dict]) -> tuple[str, list[str]]:
    """(reading, [cell problems]) for one grid. A last row of totals (every name starting total_) is left out."""
    last = max(c["row"] for c in grid)
    if all(c["name"].startswith("total") for c in grid if c["row"] == last):
        grid = [c for c in grid if c["row"] != last]
    def score(shape_axis: str, num_axis: str):
        shapes, nums = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
        for c in grid:
            shapes[c[shape_axis]][_shape(c["name"])] += 1
            nums[c[num_axis]][_number(c["name"])] += 1
        probs = []
        for c in grid:
            want_s = shapes[c[shape_axis]].most_common(1)[0][0]
            want_n = nums[c[num_axis]].most_common(1)[0][0]
            if _shape(c["name"]) != want_s and _close(_shape(c["name"]), want_s):
                probs.append(f"{c['name']}: its {('column' if shape_axis == 'col' else 'row')} is named {want_s}")
            elif _shape(c["name"]) == want_s and want_n is not None and _number(c["name"]) != want_n:
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
        print(f"{bid}: {len(grids(bp))} grid(s), {len(lines)} cell(s) breaking the pattern")
        if not args.fix:
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
