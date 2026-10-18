"""Does the grid resolver standardize equivalent wordings in code, and only those? (Andrew, 2026-10-18: "for row and
column, we need to ask if we are using an iteration number or a description, and if we are using a description, can
we standardize it without going to opus? (if there are multiple equivalent names, it doesn't matter which one we
choose)".)

On the validated forms' tables that pass the code check (Andrew's own names), one change is planted at a time and the
resolver runs with no model (score=None), so only the code decides:

  equivalent (should settle: the resolver fixes it and the table is on pattern again, in any equivalent spelling):
    suffix     a cell's suffix spelled out or shortened (nm <-> name, nbr <-> num, dt <-> date, amt <-> amount, cd <-> code)
    number     a numbered cell's number moved to the end (owner_2_nm -> owner_nm_2)
    plural     a description word given an s (owner_2_nm -> owners_2_nm)
    label      a labelled table's row label given an s on one cell (taxpayer_city_nm -> taxpayers_city_nm)
  different (must not settle in code: the resolver leaves it unsure, for the caption, Jev or Opus):
    column     a cell given another column's wording (its row's number or label kept)
    rowlabel   a labelled table's cell given another row's label

    PYTHONPATH=. venv/bin/python eval/grid_equiv_eval.py [--save out.json]
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

from petey.validate import grid_check as gc, hand_review as h  # noqa: E402

SPELL = {"nm": "name", "nbr": "num", "dt": "date", "amt": "amount", "cd": "code"}


def _tok(name: str) -> list[str]:
    return name.split("_")


def plants(g: list[dict], rnd: random.Random):
    """[(kind, expected, the grid with the change, the cell changed)]: at most one of each kind."""
    cells = G.body(g)
    out = []
    labelled = G.keyed(g)

    def swap(cell, new):
        return [dict(c, name=new) if c["name"] == cell["name"] else dict(c) for c in g], cell["name"]
    pick = rnd.sample(cells, len(cells))
    # suffix spelling
    for c in pick:
        t = _tok(c["name"])
        if t[-1] in SPELL:
            out.append(("suffix", "settle", *swap(c, "_".join(t[:-1] + [SPELL[t[-1]]]))))
            break
    if not labelled:
        for c in pick:                        # the number moved to the end (one number only: in two, the second may
            t = _tok(c["name"])                # be part of the value, address_line_1)
            its = [i for i, x in enumerate(t) if x.isdigit()]
            if len(its) == 1 and its[-1] < len(t) - 1:
                i = its[-1]
                out.append(("number", "settle", *swap(c, "_".join(t[:i] + t[i + 1:] + [t[i]]))))
                break
    for c in pick:                            # a plural
        t = _tok(c["name"])
        i = next((i for i, x in enumerate(t) if x.isalpha() and len(x) > 3 and not x.endswith("s")
                  and x not in SPELL and x not in SPELL.values()), None)
        if i is not None:
            out.append(("plural", "settle", *swap(c, "_".join(t[:i] + [t[i] + "s"] + t[i + 1:]))))
            break
    # another column's wording, in this cell's row
    by_col = collections.defaultdict(list)
    for c in cells:
        by_col[c["col"]].append(c)
    if len(by_col) >= 2:
        c = pick[0]
        other = next((o for o in pick if o["col"] != c["col"] and o["row"] == c["row"]), None)
        if other is not None:
            out.append(("column", "unsettled", *swap(c, other["name"] + "_x")))
    if labelled:
        split = G.keyed_split(cells)
        if split:
            c = pick[0]
            lab, mid, end = split[c["name"]]
            rest = "_".join(mid + end)
            if lab and lab[-1].isalpha() and len(lab[-1]) > 3:     # not a lone letter (an iteration) or a code (wv)
                out.append(("label", "settle", *swap(c, "_".join(lab[:-1] + [lab[-1] + "s"]) + "_" + rest)))
            other = next((split[o["name"]][0] for o in cells if o["row"] != c["row"] and split[o["name"]][0] != lab), None)
            if other:
                out.append(("rowlabel", "unsettled", *swap(c, "_".join(other) + "_" + rest + "_x")))
    return out


def judge(bp: dict, planted: list[dict], expected: str, changed: str) -> tuple[bool, str]:
    new = next(c["name"] for c in planted if c["name"] not in (bp.get("fields") or {}))
    fields = {(new if n == changed else n): v for n, v in (bp.get("fields") or {}).items()}   # the plant in the blueprint too
    bp = dict(bp, fields=fields)
    r = G.resolve(bp, planted, {}, None)
    if expected == "settle":
        after = [dict(c, name=r["renames"].get(c["name"], c["name"])) for c in planted]
        ok = r["status"] in ("ok", "fixed") and G.on_pattern(after)[0]
        return ok, r["status"] + ("" if ok else f" ({r['why'][:90]})")
    ok = r["status"] in ("unsure", "confused")
    return ok, r["status"] + ("" if ok else f" (renames: {list(r['renames'].items())[:2]})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--save")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    st = h.State()
    st.index()
    val = [e["id"] for e in st.listing() if (e.get("checked") or {}).get("validated")]
    tally, misses, n_tables = collections.Counter(), [], 0
    for bid in val:
        bp = h._load(h.working_path(bid))
        for g in gc.found(bp):
            if not G.on_pattern(g)[0] or len(G.body(g)) < 4:
                continue
            n_tables += 1
            for kind, expected, planted, changed in plants(g, rnd):
                ok, how = judge(bp, planted, expected, changed)
                tally[(kind, ok)] += 1
                if not ok:
                    misses.append({"form": bid, "page": g[0]["page"], "kind": kind, "changed": changed,
                                   "to": next(c["name"] for c in planted if c["name"] not in {x["name"] for x in g}),
                                   "result": how})
    print(f"{len(val)} validated forms, {n_tables} tables on pattern")
    for kind in ("suffix", "number", "plural", "label", "column", "rowlabel"):
        ok, bad = tally[(kind, True)], tally[(kind, False)]
        if ok + bad:
            print(f"  {kind:9} {ok}/{ok + bad} as expected")
    for m in misses[:25]:
        print(f"    miss {m['kind']:8} {m['form']} p{m['page']}: {m['changed']} -> {m['to']}: {m['result']}")
    if args.save:
        Path(args.save).write_text(json.dumps({"tally": {f"{k}:{v}": n for (k, v), n in tally.items()}, "misses": misses},
                                              indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
