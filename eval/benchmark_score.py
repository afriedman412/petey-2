"""Score a system's pages against the flat-structure benchmark's key (`benchmark_key.py`). Predictions come in the
key's own shape, one JSON a page named by its page id, field ids of the system's choosing:

    {"fields": [{"id", "rect": [x0, y0, x1, y1], "kind": "text" | "choice"}],     points, top left origin
     "groups": [[field id, ...]],                  fields that make one answer (option group boxes, a split value)
     "grids":  [{"cells": [{"field", "row", "col"}]}],
     "blocks": [{"cells": [{"field", "copy", "slot"}]}]}

Row, column, copy and slot are any labels; only which fields share one counts. A page with no prediction file scores
as an empty prediction.

How it counts (docs/BENCHMARK_JUDGEMENT_QS.md, Decided, 2026-10-26 to 10-30):

    values   tier 1. A value is a choice box, or a text answer: a group of text fields taken whole (a Split Field, a
             date in three boxes), else one text field (a comb drawn as one box). Values graded whole (2026-10-29):
             a found text value matches a key one when the boxes around their fields overlap by `IOU` or more
             (intersection over union), one to one, best overlaps first; so a comb, a date in three boxes and one
             box over the whole date are the same answer. Choice boxes match box to box the same way
    fields   tier 1 detail: box to box, whatever the grouping; kind right among the matched (text / choice)
    groups   tier 2, option groups: pairs of matched key choice boxes, grouped alike or not (precision / recall),
             and key groups rebuilt exactly (every box found, all in one found group holding nothing else)
    grids    tier 3: same row, same column; blocks: same copy, same slot. Pairs of key units, a unit being an
             option group or a text value (they sit in a grid or block as one field, 2026-10-28); pairs count only
             among units the system found. Rebuilt exactly: every unit found, one found grid (block) holding just
             those units, with the key's rows and columns (copies and slots)

What a grouping is (option group, date, address) is not graded (2026-10-30).

    PYTHONPATH=. venv/bin/python eval/benchmark_score.py <predictions dir> [--key runs/benchmark/key] [--iou 0.5]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Optional

KEY = Path(__file__).resolve().parent.parent / "runs" / "benchmark" / "key"
IOU = 0.5


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])  # noqa: E731
    return inter / (area(a) + area(b) - inter)


def match(keys: dict[str, list], found: dict[str, list], at: float) -> dict[str, str]:
    """{found id: key id}, one to one, best overlaps first, overlap >= `at`."""
    pairs = sorted(((iou(fr, kr), f, k) for f, fr in found.items() for k, kr in keys.items()
                    if fr[0] < kr[2] and kr[0] < fr[2] and fr[1] < kr[3] and kr[1] < fr[3]), reverse=True)
    out, used = {}, set()
    for v, f, k in pairs:
        if v < at:
            break
        if f in out or k in used:
            continue
        out[f] = k
        used.add(k)
    return out


def _union(rs: list) -> list:
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]


def units(page: dict) -> tuple[dict[str, str], dict[str, list], dict[str, str]]:
    """(field -> unit, text value -> its box, field -> kind). A unit is a group (its fields' kinds decide: the text
    fields of a group make one value, its choice boxes one option group), or a field alone."""
    kind = {f["id"]: f.get("kind") or "text" for f in page.get("fields") or []}
    rect = {f["id"]: f["rect"] for f in page.get("fields") or []}
    unit = {f: f for f in kind}
    for k, g in enumerate(page.get("groups") or []):
        for f in g:
            if f in kind:
                unit[f] = f"g{k}{kind[f][0]}"            # a group of mixed kinds splits into its text and its choices
    values = collections.defaultdict(list)
    for f, u in unit.items():
        if kind[f] == "text":
            values[u].append(rect[f])
    return unit, {u: _union(rs) for u, rs in values.items()}, kind


def _pairs(members: dict[str, set]) -> set:
    """Unordered pairs of keys sharing a member label."""
    by = collections.defaultdict(set)
    for u, labels in members.items():
        for x in labels:
            by[x].add(u)
    return {tuple(sorted((a, b))) for us in by.values() for a in us for b in us if a < b}


def _relation(coll: dict, unit_of, a: str, b: str) -> list[tuple[dict, dict, dict]]:
    """Per collection: ({unit: {a labels}}, {unit: {b labels}}, units) with fields mapped through `unit_of` (None
    drops a field)."""
    out = []
    for c in coll:
        A, B = collections.defaultdict(set), collections.defaultdict(set)
        for cell in c.get("cells") or []:
            u = unit_of(cell["field"])
            if u is None:
                continue
            A[u].add(str(cell[a]))
            B[u].add(str(cell[b]))
        out.append((A, B))
    return out


def _partition(lab: dict) -> frozenset:
    return frozenset(_pairs(lab))


def score_page(key: dict, pred: Optional[dict], at: float = IOU) -> collections.Counter:
    pred = pred or {}
    c = collections.Counter()
    k_unit, k_vals, k_kind = units(key)
    p_unit, p_vals, p_kind = units(pred)
    k_rect = {f["id"]: f["rect"] for f in key.get("fields") or []}
    p_rect = {f["id"]: f["rect"] for f in pred.get("fields") or []}

    # fields, box to box
    fm = match(k_rect, p_rect, at)
    c["field_key"], c["field_found"], c["field_hit"] = len(k_rect), len(p_rect), len(fm)
    c["kind_right"] = sum(p_kind[f] == k_kind[k] for f, k in fm.items())

    # values: text values whole, choice boxes one by one
    vm = match(k_vals, p_vals, at)                      # found value -> key value
    k_ch = {f: r for f, r in k_rect.items() if k_kind[f] == "choice"}
    p_ch = {f: r for f, r in p_rect.items() if p_kind[f] == "choice"}
    cm = match(k_ch, p_ch, at)                          # found box -> key box
    c["text_key"], c["text_found"], c["text_hit"] = len(k_vals), len(p_vals), len(vm)
    c["choice_key"], c["choice_found"], c["choice_hit"] = len(k_ch), len(p_ch), len(cm)

    # groups (option groups), over matched choice boxes
    k_grp = {f: k_unit[f] for f in k_ch}
    p_grp = {cm[f]: p_unit[f] for f in cm}             # key box -> found unit
    seen = sorted(p_grp)
    for i, a in enumerate(seen):
        for b in seen[i + 1:]:
            they = k_grp[a] == k_grp[b] and k_grp[a] != a
            we = p_grp[a] == p_grp[b] and p_grp[a] not in p_ch
            c["group_tp"] += they and we
            c["group_fp"] += we and not they
            c["group_fn"] += they and not we
    k_groups = collections.defaultdict(set)
    for f, u in k_grp.items():
        if u != f:
            k_groups[u].add(f)
    p_size = collections.Counter(u for f, u in p_unit.items() if p_kind[f] == "choice")
    c["group_key"] = len(k_groups)
    for g, fs in k_groups.items():
        us = {p_grp.get(f) for f in fs}
        if len(us) == 1 and None not in us:
            u = us.pop()
            c["group_exact"] += u not in p_ch and p_size[u] == len(fs)

    # grids and blocks, as pairs of key units
    val_of = {}                                         # found field -> key unit
    for f, u in p_unit.items():
        if p_kind[f] == "text" and u in vm:
            val_of[f] = vm[u]                           # a key text value's unit is itself (`units`)
        elif p_kind[f] == "choice" and f in cm:
            val_of[f] = k_unit[cm[f]]
    found_units = set(val_of.values())
    for name, coll, a, b in (("grid", "grids", "row", "col"), ("block", "blocks", "copy", "slot")):
        kr = _relation(key.get(coll) or [], lambda f: k_unit.get(f), a, b)
        pr = _relation(pred.get(coll) or [], lambda f: val_of.get(f), a, b)
        for rel, i in ((a, 0), (b, 1)):
            theirs = set().union(*(_pairs(x[i]) for x in kr)) if kr else set()
            theirs = {p for p in theirs if p[0] in found_units and p[1] in found_units}
            ours = set().union(*(_pairs(x[i]) for x in pr)) if pr else set()
            c[f"{rel}_tp"] += len(ours & theirs)
            c[f"{rel}_fp"] += len(ours - theirs)
            c[f"{rel}_fn"] += len(theirs - ours)
        c[f"{name}_key"] += len(kr)
        for A, B in kr:
            us = set(A)
            if not us <= found_units:
                continue
            for PA, PB in pr:
                if set(PA) == us and _partition(PA) == _partition(A) and _partition(PB) == _partition(B):
                    c[f"{name}_exact"] += 1
                    break
    return c


def _pr(tp: int, found: int, key: int) -> str:
    p = tp / found if found else 0.0
    r = tp / key if key else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return f"P {p:6.1%}  R {r:6.1%}  F1 {f:6.1%}"


def report(c: collections.Counter) -> list[str]:
    tp_v, fd_v, k_v = c["text_hit"] + c["choice_hit"], c["text_found"] + c["choice_found"], c["text_key"] + c["choice_key"]
    out = [f"  values      {_pr(tp_v, fd_v, k_v)}   ({k_v} in the key)",
           f"    text      {_pr(c['text_hit'], c['text_found'], c['text_key'])}   ({c['text_key']})",
           f"    choice    {_pr(c['choice_hit'], c['choice_found'], c['choice_key'])}   ({c['choice_key']})",
           f"  fields      {_pr(c['field_hit'], c['field_found'], c['field_key'])}   kind right "
           f"{c['kind_right'] / max(c['field_hit'], 1):.1%} of matched"]
    for rel, name in (("group", "groups"), ("row", "grid rows"), ("col", "grid cols"), ("copy", "block copies"),
                      ("slot", "block slots")):
        tp = c[f"{rel}_tp"]
        out.append(f"  {name:12}{_pr(tp, tp + c[f'{rel}_fp'], tp + c[f'{rel}_fn'])}   pairs")
    for rel, name in (("group", "groups"), ("grid", "grids"), ("block", "blocks")):
        out.append(f"  {name} rebuilt exactly: {c[f'{rel}_exact']} of {c[f'{rel}_key']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pred", type=Path)
    ap.add_argument("--key", type=Path, default=KEY)
    ap.add_argument("--iou", type=float, default=IOU)
    ap.add_argument("--save", type=Path, help="per-page counts as JSON")
    args = ap.parse_args()
    index = json.loads((args.key / "index.json").read_text())
    tot, by_set, per = collections.Counter(), collections.defaultdict(collections.Counter), {}
    missing = 0
    for x in index:
        key = json.loads((args.key / f"{x['page_id']}.json").read_text())
        pf = args.pred / f"{x['page_id']}.json"
        pred = json.loads(pf.read_text()) if pf.exists() else None
        missing += pred is None
        c = score_page(key, pred, args.iou)
        tot.update(c)
        by_set[x["set"]].update(c)
        per[x["page_id"]] = dict(c)
    print(f"{len(index)} pages ({missing} with no prediction), overlap >= {args.iou}")
    print("\n".join(report(tot)))
    for s, c in sorted(by_set.items()):
        print(f"\n{s}:")
        print("\n".join(report(c)[:1] + report(c)[4:5]))
    if args.save:
        args.save.write_text(json.dumps(per, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
