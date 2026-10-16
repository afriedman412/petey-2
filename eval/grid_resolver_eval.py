"""The grid resolver (grid_naming.resolve) on validated forms: (1) every numbered table and block as it stands, where
the names are Andrew's and few should change; (2) planted errors on the tables that pass, which it should undo to the
exact validated names: a column numbered one off, the first row's number dropped, the table numbered from 2, one
cell reworded to a variant of its column's wording. No model calls beyond the local name-check model.

    PYTHONPATH=. venv/bin/python eval/grid_resolver_eval.py --list LISTING.json [--save out.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_naming as G  # noqa: E402

from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate.field_chain import _page_lines  # noqa: E402

REWORD = {"nm": "name", "name": "nm", "amt": "amount", "dt": "date", "nbr": "number", "txt": "text", "cd": "code"}


def planted(g: list[dict], kind: str, rnd: random.Random):
    """(the grid with one planted error, {planted name: validated name}) or None when the kind does not apply."""
    cells = G.body(g)
    reading, _ = G.breaks(g)
    pos_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
    ren = {}
    vary = {k: G._varying([c["name"] for c in cells if c[pos_axis] == k]) for k in {c[pos_axis] for c in cells}}

    def it(c):                                 # the number that changes from row to row, as the resolver reads it
        i = vary[c[pos_axis]]
        return i if i is not None else max(G._iter_tokens(c["name"]))
    if kind == "column off by one":
        k = rnd.choice(sorted({c[pos_axis] for c in cells}))
        for c in cells:
            if c[pos_axis] == k and (G._number(c["name"]) or "").isdigit():
                toks = c["name"].split("_")
                i = it(c)
                if not toks[i].isdigit():
                    continue
                toks[i] = str(int(toks[i]) + 1)
                ren[c["name"]] = "_".join(toks)
    elif kind == "first row unnumbered":
        first = min(c[num_axis] for c in cells)
        for c in cells:
            if c[num_axis] == first and c["name"].split("_")[it(c)] == "1":
                toks = c["name"].split("_")
                del toks[it(c)]
                ren[c["name"]] = "_".join(toks)
    elif kind == "numbered from 2":
        for c in cells:
            toks = c["name"].split("_")
            i = it(c)
            if toks[i].isdigit():
                toks[i] = str(int(toks[i]) + 1)
                ren[c["name"]] = "_".join(toks)
    elif kind == "one cell reworded":
        c = rnd.choice(cells)
        toks = c["name"].split("_")
        j = next((i for i, t in enumerate(toks) if t in REWORD), None)
        if j is not None:
            toks[j] = REWORD[toks[j]]
            ren[c["name"]] = "_".join(toks)
    if not ren or len(set(ren.values())) < len(ren):
        return None
    return ren


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", required=True)
    ap.add_argument("--save", default="")
    args = ap.parse_args()
    score = G.text_match_score()
    listing = json.loads(Path(args.list).read_text())
    rnd = random.Random(7)
    asis, plant = collections.Counter(), collections.defaultdict(collections.Counter)
    asis_rows, plant_rows = [], []
    for e in listing:
        if not (e.get("checked") or {}).get("validated"):
            continue
        try:
            bp = h._load(h.working_path(e["id"]))
            lines = _page_lines(str(pc.resolve_blank(bp)))
        except Exception:
            continue
        for g in G.grids(bp):
            if not G.iterated(g):
                continue
            r = G.resolve(bp, g, lines, score)
            asis[r["status"]] += 1
            asis_rows.append({"bid": e["id"], "page": g[0]["page"], "status": r["status"], "renames": r["renames"],
                              "why": r["why"]})
            if r["status"] != "ok":
                continue
            for kind in ("column off by one", "first row unnumbered", "numbered from 2", "one cell reworded"):
                ren = planted(g, kind, rnd)
                if not ren:
                    continue
                f2 = {ren.get(n, n): s for n, s in bp["fields"].items()}
                bp2 = dict(bp, fields=f2)
                g2 = [dict(c, name=ren.get(c["name"], c["name"])) for c in g]
                r2 = G.resolve(bp2, g2, lines, score)
                back = {v: k for k, v in ren.items()}
                std = lambda n: G._standard(n, bp["fields"].get(back.get(n, n)) or {})          # noqa: E731
                undone = all(r2["renames"].get(p, p) in (orig, std(orig)) for p, orig in back.items())
                extra = [n for n, nw in r2["renames"].items() if n not in back and nw != G._standard(n, f2.get(n) or {})]
                res = "undone exactly" if r2["status"] == "fixed" and undone and not extra else \
                      "left for Jev / Opus" if r2["status"] in ("unsure", "confused") else \
                      "wrong fix" if r2["status"] == "fixed" else "missed"
                plant[kind][res] += 1
                plant_rows.append({"bid": e["id"], "page": g[0]["page"], "kind": kind, "result": res,
                                   "planted": ren, "proposed": r2["renames"], "why": r2["why"]})
    print("validated tables as they stand:", dict(asis))
    print("planted errors:")
    for k, c in plant.items():
        n = sum(c.values())
        print(f"  {k:22} {n:4}  " + ", ".join(f"{r} {v} ({v / n:.0%})" for r, v in c.most_common()))
    if args.save:
        Path(args.save).write_text(json.dumps({"as_is": asis_rows, "planted": plant_rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
