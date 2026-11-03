"""Group loose checkboxes by layout (Andrew, 2026-10-15: "things that are in-line between section-dividing lines should
be easy to group, right?"). Nothing so far groups by layout: groups come from the PDF (one field, several kids; XFA
boxes that clear each other), from the labeler choosing dot notation, and from the Yes / No rule (yes_no_groups.py).

The rule: two loose checkboxes (a boolean checkbox or radio field, not already in a group) are neighbours when they sit
in one row (centres within 4 pt vertically, gap under ROW_GAP) or stacked in one column (left edges within 6 pt, gap
under STACK_GAP); neighbours are joined when the straight line between their centres crosses no ruling line on the
page (a drawn line or rectangle edge of at least MIN_RULE pt) and no printed item number ('12.', '3a.', 'B.', '(4)')
or question mark sits between them. Joined boxes make a group (union-find). Rows win: a box joined to a neighbour on
its row is not also joined to the boxes above and below (stacked Yes / No questions chained into one group). A row
is left alone when its boxes line up in columns with another row's and the captions differ: a table of separate
items (ACORD 125 attachments, Form 1004 amenities), not one question's options; rows that repeat the same captions
(You / Spouse per line) still group. Stacked lists and column questions are not grouped here (2026-10-15: wrong as
often as right; the question's heading has to be read across ruled rows), except one question's options wrapped into
side-by-side columns under one heading (`_column_joins`, 2026-10-31).

Scored on the validated forms against Andrew's blueprints: each loose box of the generated copy (belongs_to_fixture
before copy) belongs in the validated one to a group or stands alone. Pairs: of the box pairs the rule puts in one
group, how many Andrew grouped (precision); of the pairs Andrew grouped among loose boxes, how many the rule found
(recall). Groups: how many of the rule's groups match one of Andrew's exactly.

    PYTHONPATH=. venv/bin/python eval/cell_groups.py [--forms ID ...] [--show 15]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import pymupdf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from belongs_to_fixture import BEFORE  # noqa: E402

from petey.validate.retype import resolve_blank  # noqa: E402

ROW_GAP = 220          # pt between boxes on one row
STACK_GAP = 30         # pt between stacked boxes
MIN_RULE = 14          # pt: shorter strokes are box outlines or glyph bits, not dividers
ITEM = re.compile(r"^\(?(\d{1,2}[a-z]?|[A-Z]|[ivx]{1,4})[.)]$")


def rules(page) -> list[tuple[float, float, float, float]]:
    """Horizontal and vertical strokes on the page, as (x0, y0, x1, y1)."""
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                segs = [(p.x, p.y, q.x, q.y)]
            elif it[0] == "re":
                r = it[1]
                if r.width < 2.5 or r.height < 2.5:          # a filled rect drawn as a rule
                    segs = [(r.x0, (r.y0 + r.y1) / 2, r.x1, (r.y0 + r.y1) / 2)] if r.width >= r.height \
                        else [((r.x0 + r.x1) / 2, r.y0, (r.x0 + r.x1) / 2, r.y1)]
                else:
                    segs = [(r.x0, r.y0, r.x1, r.y0), (r.x0, r.y1, r.x1, r.y1),
                            (r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)]
            else:
                continue
            for x0, y0, x1, y1 in segs:
                if (abs(y0 - y1) < 1 and abs(x1 - x0) >= MIN_RULE) or (abs(x0 - x1) < 1 and abs(y1 - y0) >= MIN_RULE):
                    out.append((x0, y0, x1, y1))
    return out


def _cross(a, b, c, d) -> bool:
    """Segment ab crosses segment cd."""
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def _caption(words: list, r) -> str:
    """The words printed right of the box on its line, up to 60 pt (lower case)."""
    cy = (r[1] + r[3]) / 2
    right = sorted((w for w in words if abs((w[1] + w[3]) / 2 - cy) <= 4 and r[2] - 1 <= w[0] <= r[2] + 60),
                   key=lambda w: w[0])
    return " ".join(w[4] for w in right).lower()


def loose(bp: dict) -> dict[str, dict]:
    """{field: {page, rect}} for boolean checkbox / radio fields not in a group."""
    out = {}
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        if w.get("rect") and (w.get("widget_type") in ("checkbox", "radiobutton") or s.get("type") == "boolean"):
            out[n] = {"page": w["page"], "rect": w["rect"]}
    return out


def groups(bp: dict, blank: Path, stacks: bool = True) -> list[set[str]]:
    boxes = loose(bp)
    parent = {n: n for n in boxes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    doc = pymupdf.open(str(blank))
    try:
        by_page = collections.defaultdict(list)
        for n, b in boxes.items():
            by_page[b["page"]].append(n)
        for pg, names in by_page.items():
            page = doc[pg - 1]
            rl = rules(page)
            allw = page.get_text("words")
            words = [w for w in allw if ITEM.match(w[4]) or w[4].endswith("?")]
            cap = {n: _caption(allw, boxes[n]["rect"]) for n in names}
            links = {"row": [], "stack": []}
            aligned = []                          # boxes one above the other (left edges within 6 pt, < 40 pt apart)
            for i, a in enumerate(names):
                ra = boxes[a]["rect"]
                ca = ((ra[0] + ra[2]) / 2, (ra[1] + ra[3]) / 2)
                for b in names[i + 1:]:
                    rb = boxes[b]["rect"]
                    cb = ((rb[0] + rb[2]) / 2, (rb[1] + rb[3]) / 2)
                    if abs(ra[0] - rb[0]) < 6 and 0 < max(ra[1], rb[1]) - min(ra[3], rb[3]) < 40:
                        aligned.append((a, b))
                    row = abs(ca[1] - cb[1]) < 4 and max(ra[0], rb[0]) - min(ra[2], rb[2]) < ROW_GAP
                    stack = abs(ra[0] - rb[0]) < 6 and max(ra[1], rb[1]) - min(ra[3], rb[3]) < STACK_GAP
                    if not (row or stack):
                        continue
                    if any(_cross(ca, cb, (s[0], s[1]), (s[2], s[3])) for s in rl):
                        continue
                    if row:
                        lo, hi = sorted((ca[0], cb[0]))
                        between = [w for w in words if lo < (w[0] + w[2]) / 2 < hi and abs((w[1] + w[3]) / 2 - ca[1]) < 6]
                    else:
                        lo, hi = sorted((ca[1], cb[1]))
                        between = [w for w in words if lo < (w[1] + w[3]) / 2 < hi and w[0] < max(ra[2], rb[2]) + 4
                                   and w[2] > min(ra[0], rb[0]) - 30]
                    if not between:
                        links["row" if row else "stack"].append((a, b))
            in_row = {n for ab in links["row"] for n in ab}
            rowp = {n: n for n in in_row}

            def rfind(x):
                while rowp[x] != x:
                    x = rowp[x]
                return x
            for a, b in links["row"]:
                rowp[rfind(a)] = rfind(b)
            col = collections.Counter()           # a row whose boxes line up in columns with another row: a grid
            for a, b in aligned:                  # same caption in both rows (You / You, none / none): options repeat
                if a in in_row and b in in_row and rfind(a) != rfind(b) and cap[a] != cap[b]:
                    col[rfind(a)] += 1
                    col[rfind(b)] += 1
            row_kept = set()
            for a, b in links["row"]:
                if col[rfind(a)] < 2:
                    parent[find(a)] = find(b)
                    row_kept |= {a, b}
            if stacks:
                for a, b in links["stack"]:      # a box with a row partner answers its own row's question
                    if a not in in_row and b not in in_row:
                        parent[find(a)] = find(b)
                for a, b in _column_joins(names, boxes, row_kept, rl, allw, words):
                    parent[find(a)] = find(b)
    finally:
        doc.close()
    g = collections.defaultdict(set)
    for n in boxes:
        g[find(n)].add(n)
    return [s for s in g.values() if len(s) > 1]


def _line_caption(words: list, r, stop_x: float) -> str:
    """The words printed right of the box on its line, up to `stop_x` (lower case)."""
    cy = (r[1] + r[3]) / 2
    right = sorted((w for w in words if abs((w[1] + w[3]) / 2 - cy) <= 4 and r[2] - 1 <= w[0] < stop_x),
                   key=lambda w: w[0])
    return " ".join(w[4] for w in right).lower()


def _column_joins(names: list[str], boxes: dict, row_kept: set[str], rl: list, allw: list,
                  stop: list) -> list[tuple[str, str]]:
    """One question's options wrapped into side-by-side columns (Andrew, 2026-10-31: "groups of choice fields that are
    far apart but should all be connected"; the FAFSA's federal benefits question, three columns 190-210 pt apart, came
    out as three groups: its rows line up like a table's, so the row rule leaves them, and no stack crosses columns).
    A column is 2+ boxes of one size on one left edge, each under 40 pt below the last and not starting another
    question (`breaks`), none held by a row group, each with its own caption. Two columns are joined, all their boxes,
    when their top boxes sit on one line and are one size, no box stands between them, no ruling line, printed item
    number or question mark sits between them, nothing else is printed between a left box's caption and the right
    column (CBP 3461's Name:, a fee schedule's amounts) and no caption runs past it, no caption repeats within a
    column or across the two (Yes / No columns), and the right column has no heading of its own (a printed line, not a
    caption, starting at its edge just above its top box: Loan Type / Amortization Type).
    Measured 2026-10-31 on 714 saved blueprints, every group broken apart and rebuilt: of the groups the rule changed,
    143 are one saved group, 11 join saved groups (9 one question saved split; bm__sd_1506275's diagnostic criteria
    beside its work-related question; one through a stack the row rule chained under a heading), 4 take in loose boxes;
    on the validated forms (`main`) +6 pairs, all right. Returns pairs to join."""
    lines = collections.defaultdict(list)
    for w in allw:
        lines[(w[5], w[6])].append(w)
    ext = []                                      # printed lines, split where words stand 15 pt apart (two headings
    for ws in lines.values():                     # on one baseline: Loan Type ... Amortization Type)
        ws.sort(key=lambda w: w[0])
        seg = [ws[0]]
        for w in ws[1:] + [None]:
            if w is not None and w[0] - seg[-1][2] < 15:
                seg.append(w)
                continue
            ext.append((seg[0][0], min(v[1] for v in seg), seg[-1][2], max(v[3] for v in seg)))
            seg = [w]

    def is_caption(e) -> bool:                    # starts just right of a box on its line
        cy = (e[1] + e[3]) / 2
        return any(abs((boxes[m]["rect"][1] + boxes[m]["rect"][3]) / 2 - cy) <= 6
                   and boxes[m]["rect"][2] - 1 <= e[0] <= boxes[m]["rect"][2] + 10 for m in names)
    heads = [(e[0], e[3]) for e in ext if not is_caption(e)]
    def label_left(e) -> bool:                    # a printed line with no box left of it on or just above its line
        return not any(boxes[m]["rect"][2] <= e[0] + 2 and boxes[m]["rect"][1] < e[3] and boxes[m]["rect"][3] > e[1] - 30
                       for m in names)

    def breaks(q, r) -> bool:
        """Box r, below q on one left edge, starts another question: a ruling line between them, a printed line
        between them over the boxes ("6. Hair color" under the eye colours), or a heading or label printed from left
        of r with no box before it ("B This return/report is:", "Purpose of Account")."""
        if any(_cross(((q[0] + q[2]) / 2, (q[1] + q[3]) / 2), ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2),
                      (s[0], s[1]), (s[2], s[3])) for s in rl):
            return True
        for e in ext:
            cy = (e[1] + e[3]) / 2
            if q[3] < cy < r[1] and e[0] < r[2] - 2 and e[2] > r[0] + 2:
                return True
            if q[3] - 1 < cy <= r[3] and e[0] < r[2] and label_left(e) and not any(
                    abs(s[0] - s[2]) < 1 and min(e[2], r[0]) - 1 <= s[0] <= r[0] and min(s[1], s[3]) <= cy <= max(s[1], s[3])
                    for s in rl):                 # not across a ruled panel edge (FFL 7CR p10)
                return True
        return False

    def crowded(n, x: float) -> bool:             # more printed between its caption and x (CBP 3461: Name:, fees)
        r = boxes[n]["rect"]
        cy = (r[1] + r[3]) / 2
        return sum(1 for e in ext if abs((e[1] + e[3]) / 2 - cy) <= 6 and e[0] >= r[2] - 1 and e[2] <= x) > 1

    def runs_into(n, x: float) -> bool:           # its caption's line runs on past x (1040's nonresident box)
        r = boxes[n]["rect"]
        cy = (r[1] + r[3]) / 2
        return any(abs((e[1] + e[3]) / 2 - cy) <= 6 and r[2] - 1 <= e[0] <= r[2] + 10 and e[2] > x for e in ext)

    free = sorted((n for n in names if n not in row_kept), key=lambda n: boxes[n]["rect"][1])
    cols: list[list[str]] = []
    for n in free:
        r = boxes[n]["rect"]
        for c in cols:
            q = boxes[c[-1]]["rect"]
            if abs(q[0] - r[0]) < 6 and 0 <= r[1] - q[3] < 40 and abs((q[2] - q[0]) - (r[2] - r[0])) < 2.5 \
                    and not breaks(q, r):
                c.append(n)
                break
        else:
            cols.append([n])

    def caption(n) -> str:                        # up to the next box on its line
        r = boxes[n]["rect"]
        cy = (r[1] + r[3]) / 2
        nxt = [boxes[m]["rect"][0] for m in names
               if boxes[m]["rect"][0] > r[2] and abs((boxes[m]["rect"][1] + boxes[m]["rect"][3]) / 2 - cy) < 4]
        return _line_caption(allw, r, min(nxt, default=10_000))
    cols = [c for c in cols if len(c) >= 2]
    if len(cols) < 2:
        return []
    out = []
    for a in cols:
        ta = boxes[a[0]]["rect"]
        for b in cols:
            tb = boxes[b[0]]["rect"]
            if b is a or tb[0] <= ta[2] + 40 or abs(ta[1] - tb[1]) >= 4:
                continue
            if abs((ta[2] - ta[0]) - (tb[2] - tb[0])) > 2.5:
                continue
            lo_y, hi_y = ta[1], max(boxes[a[-1]]["rect"][3], boxes[b[-1]]["rect"][3])
            if any(ta[2] < boxes[n]["rect"][0] < tb[0] - 6 and boxes[n]["rect"][1] < hi_y and boxes[n]["rect"][3] > lo_y
                   for n in names):
                continue
            ca = ((ta[0] + ta[2]) / 2, (ta[1] + ta[3]) / 2)
            cb = ((tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2)
            if any(_cross(ca, cb, (s[0], s[1]), (s[2], s[3])) for s in rl):
                continue
            if any(abs(s[0] - s[2]) < 1 and ta[2] < s[0] < tb[0] and min(s[1], s[3]) < hi_y and max(s[1], s[3]) > lo_y
                   for s in rl):
                continue
            if any(ca[0] < (w[0] + w[2]) / 2 < cb[0] and abs((w[1] + w[3]) / 2 - ca[1]) < 6 for w in stop):
                continue
            if any(tb[1] - 30 < y1 <= tb[1] + 1 and tb[0] - 15 < x0 < tb[2] + 15 for x0, y1 in heads):
                continue
            if any(runs_into(n, tb[0]) or crowded(n, tb[0]) for n in a):
                continue
            capa, capb = [caption(n) for n in a], [caption(n) for n in b]
            if not all(capa + capb) or len(set(capa)) < len(a) or len(set(capb)) < len(b) or set(capa) & set(capb):
                continue
            out += list(zip(a, a[1:])) + list(zip(b, b[1:])) + [(a[0], b[0])]
    return out


def group_name(members: list[str]) -> str:
    """The words the members' names start with (`employer1_apt_ind` + `employer1_ste_ind` -> `employer1`); else the
    words they share, once each in the first name's order, less `ind`; else the first name less its last word."""
    toks = [m.split("_") for m in members]
    pre = []
    for col in zip(*toks):
        if len(set(col)) > 1:
            break
        pre.append(col[0])
    pre = [t for t in pre if t != "ind"]
    if pre:
        return "_".join(pre)
    common = set(toks[0]).intersection(*toks[1:]) - {"ind"}
    out = list(dict.fromkeys(t for t in toks[0] if t in common))
    return "_".join(out) or "_".join(toks[0][:-1]) or members[0]


def proposals(bp: dict, blank: Path, skip: set[str] = frozenset()) -> list[tuple[str, list[str]]]:
    """[(group name, field names)] for the mechanical pass: the row groups (no stacked lists), leaving out any group
    that touches a box in `skip` (the Yes / No pairs, applied by their own rule); names made unique."""
    taken = set(bp.get("fields") or {})
    out = []
    for s in groups(bp, blank, stacks=False):
        if s & skip:
            continue
        ms = sorted(s, key=lambda n: list(bp["fields"]).index(n))
        base = group_name(ms)
        k, i = base, 2
        while (k in taken and k not in ms) or any(k == x[0] for x in out):
            k, i = f"{base}_{i}", i + 1
        out.append((k, ms))
    return out


def truth(bp_before: dict, bp_after: dict) -> dict[str, str]:
    """{loose box in the generated copy: the validated field holding it}."""
    key = lambda w: (w.get("page"), *(round(v) for v in w["rect"]))   # noqa: E731
    owner = {}
    for n, s in (bp_after.get("fields") or {}).items():
        if isinstance(s, dict):
            for w in list((s.get("widgets") or {}).values()) or [s.get("widget") or {}]:
                if w.get("rect"):
                    owner[key(w)] = n
    return {n: owner.get(key(b)) for n, b in loose(bp_before).items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*")
    ap.add_argument("--show", type=int, default=12, help="wrong groups and missed groups to list")
    args = ap.parse_args()
    forms = args.forms or list(json.loads(Path("runs/belongs_to/validated_forms_2026-10-14.json").read_text())["forms"])
    T = collections.Counter()
    wrong, missed = [], []
    print(f"{'form':26} {'loose':>5} {'rule groups':>11} {'exact':>5} {'Andrew groups':>13} {'pairs right':>11} {'pairs found':>11}")
    for bid in forms:
        bpt = next((BEFORE / bid).glob("*.bpt"), None)
        rec = Path("runs/hand_review") / f"{bid}.json"
        if not bpt or not rec.exists():
            continue
        before = yaml.safe_load(bpt.read_text())
        after = yaml.safe_load(Path(json.loads(rec.read_text())["blueprint"]).read_text())
        blank = resolve_blank(before)
        pred = groups(before, blank)
        tr = truth(before, after)
        true_g = collections.defaultdict(set)
        for n, f in tr.items():
            if f and (after["fields"].get(f) or {}).get("widgets"):
                true_g[f].add(n)
        true_g = {f: s for f, s in true_g.items() if len(s) > 1}
        tsets = {frozenset(s) for s in true_g.values()}
        same = lambda a, b: tr.get(a) is not None and tr.get(a) == tr.get(b) and tr.get(a) in true_g   # noqa: E731
        pp = [(a, b) for s in pred for a in s for b in s if a < b]
        tp = [(a, b) for s in true_g.values() for a in s for b in s if a < b]
        pset = {frozenset(x) for x in pp}
        right = sum(same(a, b) for a, b in pp)
        found = sum(frozenset(x) in pset for x in tp)
        exact = sum(frozenset(s) in tsets for s in pred)
        T.update(loose=len(tr), pred=len(pred), exact=exact, true=len(true_g), pp=len(pp), right=right, tp=len(tp), found=found)
        print(f"{bid:26} {len(tr):>5} {len(pred):>11} {exact:>5} {len(true_g):>13} {right:>5}/{len(pp):<5} {found:>5}/{len(tp):<5}")
        for s in pred:
            if frozenset(s) not in tsets:
                held = collections.Counter(tr.get(n) or "?" for n in s)
                wrong.append((bid, sorted(s), dict(held)))
        for f, s in true_g.items():
            if not any(s <= p for p in pred):
                missed.append((bid, f, sorted(s), [sorted(p & s) for p in pred if p & s]))
    print(f"\n{'all':26} {T['loose']:>5} {T['pred']:>11} {T['exact']:>5} {T['true']:>13} {T['right']:>5}/{T['pp']:<5} {T['found']:>5}/{T['tp']:<5}")
    print(f"  pairs: precision {T['right'] / max(1, T['pp']):.0%}, recall {T['found'] / max(1, T['tp']):.0%}; "
          f"groups exactly right {T['exact']} of the rule's {T['pred']} (Andrew made {T['true']} from loose boxes)")
    print(f"\nrule groups that are not one of Andrew's ({len(wrong)}):")
    for bid, s, held in wrong[:args.show]:
        print(f"  {bid}  {', '.join(s)[:120]}\n      Andrew: {held}")
    print(f"\nAndrew's groups the rule did not form whole ({len(missed)}):")
    for bid, f, s, parts in missed[:args.show]:
        print(f"  {bid}  {f}: {', '.join(s)[:110]}\n      rule had: {parts if parts else 'nothing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
