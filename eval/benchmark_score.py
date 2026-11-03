"""Score a system's pages against the flat-structure benchmark's key (`benchmark_key.py`). Predictions come in the
key's own shape, one JSON a page named by its page id, field ids of the system's choosing:

    {"fields": [{"id", "rect": [x0, y0, x1, y1], "kind": "text" | "choice" | "printed"}],   points, top left origin
     "groups": [[field id, ...]]}                  fields that make one answer (option group boxes, a split value)

A page with no prediction file scores as an empty prediction.

Four scores (Andrew, 2026-10-30: "we are only scoring on identifying fields, typing them correctly, grouping them,
combining splits"; not blocks or grids):

    fields found      a field is a choice box, or a text answer: a group of text fields taken whole (a Split Field,
                      a date in three boxes), else one text field (a comb drawn as one box). Printed fields
                      (signatures, initials, printed names; 2026-10-31) are text answers of their own type. Values graded whole
                      (2026-10-29): found and key fields match when their boxes (around all their parts) overlap by
                      `IOU` or more (intersection over union), one to one, best overlaps first, whatever their kind;
                      so a comb, a date in three boxes and one box over the whole date are the same answer. Short of
                      that, they still match when one box sits mostly inside the other or the two share a line with
                      half their width in common (2026-11-02, question 15: a text field's height, and which side of a
                      caption inside its box it takes, are arbitrary on a flat page); the plain overlap count is
                      reported alongside
    typed right       text / choice / printed right, of the fields found; and a line a type, found and typed it
                      end to end (precision over the system's fields of that type, recall over the key's)
    grouped           option groups: pairs of the key's choice boxes found as choice boxes, grouped alike or not
                      (precision / recall), and key groups rebuilt exactly (every box found, all in one found group
                      holding nothing else)
    splits combined   recall: the key's text values of two or more fields found whole; precision: the system's
                      combinations of two or more text fields that are a key value

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


def _inside(a, b) -> bool:
    """Most (80%) of the smaller box inside the larger, the smaller at least a fifth of the larger."""
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])  # noqa: E731
    s, big = sorted((area(a), area(b)))
    return s > 0 and inter / s >= 0.8 and s / big >= 0.2


def _same_line(a, b) -> bool:
    """Half their joint width shared, and each box's middle inside the other's height."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) / max(max(a[2], b[2]) - min(a[0], b[0]), 1e-9)
    ma, mb = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
    return w >= 0.5 and (b[1] <= ma <= b[3] or a[1] <= mb <= a[3])


def overlap(a, b, at: float = IOU, loose: bool = True) -> float:
    """`iou`, or `at` (a match, ranked below every true overlap match) when the boxes fall short of `at` but one sits
    mostly inside the other or they share a line (2026-11-02, question 15: a text field's height and the side of a
    caption it is drawn on are arbitrary on a flat page)."""
    v = iou(a, b)
    return at if loose and v < at and (_inside(a, b) or _same_line(a, b)) else v


def match(keys: dict[str, list], found: dict[str, list], at: float, loose: bool = True,
          whole: tuple = ((), ())) -> dict[str, str]:
    """{found id: key id}, one to one, best overlaps first, `overlap` >= `at` (`loose=False`: plain iou). Values made
    of several fields (`whole`: the key's, the system's) match by plain iou only: one part of a date inside the
    date's area, or two answers joined over one, is not the value."""
    pairs = sorted(((overlap(fr, kr, at, loose and k not in whole[0] and f not in whole[1]), f, k)
                    for f, fr in found.items() for k, kr in keys.items()
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


KINDS = ("text", "choice", "printed")


def units(page: dict) -> tuple[dict[str, str], dict[str, list], dict[str, str]]:
    """(field -> unit, text value -> its box, field -> kind). A unit is a group (its fields' kinds decide: the text
    and printed fields of a group make one value, its choice boxes one option group), or a field alone."""
    kind = {f["id"]: f.get("kind") or "text" for f in page.get("fields") or []}
    rect = {f["id"]: f["rect"] for f in page.get("fields") or []}
    unit = {f: f for f in kind}
    for k, g in enumerate(page.get("groups") or []):
        for f in g:
            if f in kind:
                unit[f] = f"g{k}{'c' if kind[f] == 'choice' else 't'}"   # mixed: its text and its choices apart
    values = collections.defaultdict(list)
    for f, u in unit.items():
        if kind[f] != "choice":
            values[u].append(rect[f])
    return unit, {u: _union(rs) for u, rs in values.items()}, kind


def score_page(key: dict, pred: Optional[dict], at: float = IOU) -> collections.Counter:
    pred = pred or {}
    c = collections.Counter()
    k_unit, k_vals, k_kind = units(key)
    p_unit, p_vals, p_kind = units(pred)
    k_rect = {f["id"]: f["rect"] for f in key.get("fields") or []}
    p_rect = {f["id"]: f["rect"] for f in pred.get("fields") or []}
    # the units found: text values whole, choice boxes one by one; matched whatever their kind
    k_units = {**k_vals, **{f: r for f, r in k_rect.items() if k_kind[f] == "choice"}}
    p_units = {**p_vals, **{f: r for f, r in p_rect.items() if p_kind[f] == "choice"}}
    k_ukind = _unit_kinds(k_units, k_vals, k_unit, k_kind)
    p_ukind = _unit_kinds(p_units, p_vals, p_unit, p_kind)
    whole = tuple({u for u, n in collections.Counter(un[f] for f in kd if kd[f] != "choice").items() if n >= 2}
                  for un, kd in ((k_unit, k_kind), (p_unit, p_kind)))          # values of two or more fields
    m = match(k_units, p_units, at, whole=whole)                    # found unit -> key unit
    c["found_key"], c["found_found"], c["found_hit"] = len(k_units), len(p_units), len(m)
    c["found_hit_iou"] = len(match(k_units, p_units, at, loose=False))   # plain overlap, reported alongside
    c["kind_right"] = sum(p_ukind[f] == k_ukind[k] for f, k in m.items())
    for t in KINDS:
        c[f"type_{t}_key"] = sum(v == t for v in k_ukind.values())
        c[f"type_{t}_found"] = sum(v == t for v in p_ukind.values())
        c[f"type_{t}_hit"] = sum(p_ukind[f] == k_ukind[k] == t for f, k in m.items())

    # grouping (option groups), over the key's choice boxes found as choice boxes
    k_grp = {f: k_unit[f] for f in k_rect if k_kind[f] == "choice"}
    p_grp = {k: p_unit[f] for f, k in m.items() if k in k_grp and p_ukind[f] == "choice"}   # key box -> found unit
    seen = sorted(x for x in k_grp if x in set(m.values()))
    for i, a in enumerate(seen):
        for b in seen[i + 1:]:
            they = k_grp[a] == k_grp[b] and k_grp[a] != a
            we = a in p_grp and b in p_grp and p_grp[a] == p_grp[b]
            c["group_tp"] += they and we
            c["group_fp"] += we and not they
            c["group_fn"] += they and not we
    k_groups = collections.defaultdict(set)
    for f, u in k_grp.items():
        if u != f:
            k_groups[u].add(f)
    p_size = collections.Counter(u for f, u in p_unit.items() if p_kind[f] == "choice")
    c["group_key"] = len(k_groups)
    for fs in k_groups.values():
        us = {p_grp.get(f) for f in fs}
        if len(us) == 1 and None not in us:
            c["group_exact"] += p_size[us.pop()] == len(fs)

    # combining splits: the key's text values of two or more fields, found whole (a found value over the same area:
    # its parts combined, or one box over the whole); the found combinations that are a key value
    k_parts = collections.Counter(k_unit[f] for f in k_rect if k_kind[f] != "choice")
    p_parts = collections.Counter(p_unit[f] for f in p_rect if p_kind[f] != "choice")
    k_split = {u for u, n in k_parts.items() if n >= 2}
    p_split = {u for u, n in p_parts.items() if n >= 2}
    c["split_key"], c["split_found"] = len(k_split), len(p_split)
    c["split_hit"] = sum(1 for f, k in m.items() if k in k_split and p_ukind[f] != "choice")
    c["split_found_hit"] = sum(1 for f in p_split if f in m and k_ukind[m[f]] != "choice")
    return c


def _unit_kinds(units_: dict, vals: dict, unit: dict, kind: dict) -> dict[str, str]:
    """A unit's type: choice for a choice box; a value is printed when all its fields are, else text."""
    parts = collections.defaultdict(set)
    for f, u in unit.items():
        if u in vals:
            parts[u].add(kind[f])
    return {u: ("printed" if parts[u] == {"printed"} else "text") if u in vals else "choice" for u in units_}


def _pr(tp: int, found: int, key: int) -> str:
    p = tp / found if found else 0.0
    r = tp / key if key else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return f"P {p:6.1%}  R {r:6.1%}  F1 {f:6.1%}"


def report(c: collections.Counter) -> list[str]:
    tp = c["group_tp"]
    return [f"  fields found      {_pr(c['found_hit'], c['found_found'], c['found_key'])}   ({c['found_key']} in the key)",
            f"    plain overlap   {_pr(c['found_hit_iou'], c['found_found'], c['found_key'])}",
            f"  typed right       {c['kind_right'] / max(c['found_hit'], 1):6.1%} of those found",
            *(f"    {t:15} {_pr(c[f'type_{t}_hit'], c[f'type_{t}_found'], c[f'type_{t}_key'])}   "
              f"({c[f'type_{t}_key']} in the key)" for t in KINDS),
            f"  grouped (pairs)   {_pr(tp, tp + c['group_fp'], tp + c['group_fn'])}   "
            f"groups rebuilt exactly {c['group_exact']} of {c['group_key']}",
            f"  splits combined   P {c['split_found_hit'] / max(c['split_found'], 1):6.1%}  "
            f"R {c['split_hit'] / max(c['split_key'], 1):6.1%}   ({c['split_key']} in the key, "
            f"{c['split_found']} combined)"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pred", type=Path)
    ap.add_argument("--key", type=Path, default=KEY)
    ap.add_argument("--iou", type=float, default=IOU)
    ap.add_argument("--save", type=Path, help="per-page counts as JSON")
    args = ap.parse_args()
    index = json.loads((args.key / "index.json").read_text())
    from petey.validate import ignored_forms, ignored_pages
    ignored, ignored_f = ignored_pages.load(), ignored_forms.load()
    gone = lambda pid: pid in ignored or ignored_forms.page_form(pid) in ignored_f      # noqa: E731
    if dropped := [x for x in index if gone(x["page_id"])]:   # pages or whole forms ignored since the key was built
        index = [x for x in index if not gone(x["page_id"])]
        print(f"{len(dropped)} key pages ignored on the review page since the key was built: left out (rebuild the key)")
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
        print("\n".join(report(c)))
    if args.save:
        args.save.write_text(json.dumps(per, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
