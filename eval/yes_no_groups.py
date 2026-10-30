"""Loose Yes / No checkboxes made into one group each (2026-10-14, Andrew: "lots of yes/no left ungrouped"; I-485 had
64 such pairs on pages 16-21, CMS-855A one stacked pair). Two loose boxes on one page form a pair when they sit side by
side on a line (within 90 pt) or one above the other (within 30 pt), and the page prints Yes beside the first and No
beside the second (YES / NO too, with anything after: 'YES - continue below'). The group is named after what the two
names share (`item_38_yes_ind` + `item_38_no_ind` -> `item_38`), is one-of (`category`), keeps the boxes keyed by
their former names, and goes into the review page's working copy through the Groups code (`group_review.apply`), so
Andrew checks it like any other change. `--also NAME=ID,ID,...` adds any other group in the same pass.

    PYTHONPATH=. venv/bin/python eval/yes_no_groups.py lib__i485 [--dry]
"""
from __future__ import annotations

import argparse
import re
import sys

import pymupdf

from petey.validate import draft, group_review as g
from petey.validate.hand_review import _load, _sha, blueprint_paths, working_path
from petey.validate.retype import resolve_blank

YES = re.compile(r"^\s*yes\b", re.I)
NO = re.compile(r"^\s*no\b", re.I)


def _label(words: list, r) -> str:
    """The first word printed right of the box on its line (a text clip can return 'No' before 'Yes' when both
    fall inside it)."""
    cy = (r[1] + r[3]) / 2
    right = [w for w in words if abs((w[1] + w[3]) / 2 - cy) <= 4 and r[2] - 1 <= w[0] <= r[2] + 40]
    return min(right, key=lambda w: w[0])[4] if right else ""


def _group_name(a: str, b: str) -> str:
    """What two names share, less the yes / no part: `item_38_yes_ind` + `item_38_no_ind` -> `item_38`."""
    ta, tb = a.split("_"), b.split("_")
    keep = [x for x, y in zip(ta, tb) if x == y and x not in ("yes", "no", "ind")]
    # the shared tokens in order, as they stand in the first name
    out = [t for t in ta if t in keep]
    return "_".join(out) or a


def pairs(bp: dict, blank) -> list[tuple[str, str, str]]:
    """[(group name, yes item, no item)] among the blueprint's loose boxes."""
    items, units = g.option_items(bp)
    loose = [items[u["items"][0]] for u in units if len(u["items"]) == 1 and u["type"] == "boolean"]
    doc = pymupdf.open(str(blank))
    try:
        words = {pg: doc[pg - 1].get_text("words") for pg in {it["page"] for it in loose}}
        lab = {it["id"]: _label(words[it["page"]], it["rect"]) for it in loose}
    finally:
        doc.close()
    yes = [it for it in loose if YES.match(lab[it["id"]])]
    no = [it for it in loose if NO.match(lab[it["id"]])]
    out, used = [], set()
    for y in yes:
        cy = (y["rect"][1] + y["rect"][3]) / 2
        best = None
        for n in no:
            if n["id"] in used or n["page"] != y["page"]:
                continue
            cn = (n["rect"][1] + n["rect"][3]) / 2
            side = abs(cy - cn) <= 4 and 0 < n["rect"][0] - y["rect"][0] <= 90
            stacked = abs(n["rect"][0] - y["rect"][0]) <= 4 and 0 < cn - cy <= 30
            if side or stacked:
                d = abs(n["rect"][0] - y["rect"][0]) + abs(cn - cy)
                if best is None or d < best[0]:
                    best = (d, n)
        if best:
            used.add(best[1]["id"])
            out.append((_group_name(y["field"], best[1]["field"]), y["id"], best[1]["id"]))
    return out


def run(bid: str, dry: bool, also: list[tuple[str, list[str]]]) -> int:
    real = blueprint_paths()[bid]
    p = working_path(bid)
    bp = _load(p)
    blank = resolve_blank(bp)
    found = pairs(bp, blank)
    names = set(bp.get("fields") or {})
    new = []
    for name, y, n in found:
        k, i = name, 2
        while k in names - {y, n} or any(k == x[0] for x in new):
            k, i = f"{name}_{i}", i + 1
        new.append((k, [y, n]))
    for name, ids in also:               # other groups in the same pass (the row groups), names kept unique
        k, i = name, 2
        while k in names - set(ids) or any(k == x[0] for x in new):
            k, i = f"{name}_{i}", i + 1
        new.append((k, ids))
    for name, ids in new:
        print(f"  {name}: {' / '.join(ids)}")
    print(f"{bid}: {len(found)} Yes / No pairs{f', {len(also)} more groups' if also else ''}")
    if dry or not new:
        return len(new)
    p = draft.ensure(bid, real)
    bp = _load(p)
    items, units, _ = g.current_units(bid, bp, _sha(p))
    taken = {i for _, ids in new for i in ids}
    units = [dict(u, items=[i for i in u["items"] if i not in taken]) for u in units]
    units = [u for u in units if u["items"]] + [{"name": n, "type": "category", "items": ids, "confirmed": False}
                                                  for n, ids in new]
    pl = g.plan(bp, units, blank)
    if pl["errors"]:
        print("not applied:\n  " + "\n  ".join(pl["errors"]))
        return 0
    before = _sha(p)
    g.State().put_units(bid, {"units": units})
    out = g.apply(bid)
    draft.follow(bid, before, _sha(working_path(bid)))
    draft.log(bid, "claude", [f"group: {c}" for c in out["changes"]])
    return len(new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--also", action="append", default=[], metavar="NAME=ID,ID,...")
    args = ap.parse_args()
    also = [(a.split("=", 1)[0], a.split("=", 1)[1].split(",")) for a in args.also]
    for bid in args.ids:
        run(bid, args.dry, also)
    return 0


if __name__ == "__main__":
    sys.exit(main())
