"""Grids are named consistently (Andrew, 2026-10-15: "the naming conventions for each column should be identical").

A grid: text boxes in two or more columns (same left edge and width) that share two or more rows (same height on the
page); checked when it is numbered along one side (3+ cells one way, 2+ the other, most names carrying an iteration:
a number, or a lone letter as in property_b_). In a grid every cell's name has one shape, its iteration standing in
for N: either the column decides the
shape and the row decides the number (AO 40B's expense table: expense_private_N_amt, N = row), or the row decides the
shape and the column decides the number (Form 8825's income grid: gross_rents_N_amt, N = property column). The check
picks the reading most cells agree with and lists the cells that break it: another shape than their column's (or
row's), or another number than their row's (or column's). Found by layout only, no names or forms listed.

    PYTHONPATH=. venv/bin/python eval/grid_naming.py je__ao040b je__f8825 ...
"""
from __future__ import annotations

import collections
import re
import sys

NUM = re.compile(r"\d+")
LINE = re.compile(r"^\d+[a-z]?$")          # an iteration or a line number (2, 12, 4a)
TOL_X, TOL_W, TOL_Y = 3.0, 4.0, 3.0


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
    from petey.validate import hand_review as h
    for bid in sys.argv[1:]:
        bp = h._load(h.working_path(bid))
        gs = grids(bp)
        lines = check(bp)
        print(f"{bid}: {len(gs)} grid(s), {len(lines)} cell(s) breaking the pattern")
        for ln in lines[:25]:
            print("  " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
