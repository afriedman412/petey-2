"""Checkbox / radio groups on a flat form for pennies? (Andrew, 2026-10-15: "see if you can do check/radio groupings
at all, even if it's just easy yes/no stuff")

Every option group of a validated blueprint is broken back into loose checkboxes (what a flat form gives: boxes, no
groups), and the groups are rebuilt three ways:
  * code: Yes / No pairs by their printed labels (yes_no_groups.pairs) and rows of checkboxes with no ruling line,
    item number or question mark between them (cell_groups.groups);
  * Jev: for each pair of nearby checkboxes on a page (each box with its nearest few), one Noul: do the two answer
    the same printed question? Pairs over CUT joined (union-find); page image with the boxes numbered, no names;
  * both: code's groups, plus Jev's joins.
Truth: the validated groups (a lone checkbox stands alone). Scored on box pairs: precision (of the pairs a method
puts in one group, how many the validated blueprint does), recall (of the validated pairs, how many it finds), and
the share of validated groups rebuilt exactly.

    PYTHONPATH=. venv/bin/python eval/cheap_groups.py --forms-list ID ... --save runs/jev/cheap_groups_2026-10-15.json
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import copy
import itertools
import json
import math
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_groups  # noqa: E402
import yes_no_groups  # noqa: E402
from petey.validate.jev_is_field import flat_copy  # noqa: E402

from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate.jev_page import LIMITS, MODEL, _key, ask_split, image_ref  # noqa: E402

NEAR = 3                       # each box asked against its nearest NEAR boxes on the page
MAX_GAP = 160.0                # ... within this many points (centre to centre)
PER_REQUEST = 20
CUT = 0.7                      # Jev joins a pair over this (2026-10-15: code + Jev at 0.7 rebuilt 81% of groups exactly, 90% of yes / no pairs; 0.5 78% / 85%)
QUESTION = ("`page` is one page of a blank form; checkboxes are outlined in red and tagged with numbers. Do the two "
            "boxes tagged `pair` answer the same printed question, as two of its options (pick one or pick several: "
            "Yes / No, Male / Female, a list of choices under one heading or on one line)?")
CRITERIA = {"true": "Both boxes are options of one question.",
            "false": "They answer different questions or items (separate statements, separate table rows, separate "
                     "yes / no questions), or one of them is not an option of a question."}


def explode(bp: dict) -> tuple[dict, dict[str, str | None]]:
    """(blueprint with every option a loose boolean checkbox, {loose field: validated group or None})."""
    out = copy.deepcopy(bp)
    fields, truth = {}, {}
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        if s.get("widgets"):
            for k, w in s["widgets"].items():
                if not w.get("rect"):
                    continue
                f = f"{n}__{k}"
                fields[f] = {"type": "boolean", "widget": {"page": w["page"], "rect": w["rect"], "widget_type": "checkbox"},
                             "x_petey_id": f}
                truth[f] = n
        else:
            fields[n] = s
            w = s.get("widget") or {}
            if s.get("type") == "boolean" and w.get("rect"):
                truth[n] = None
    out["fields"] = fields
    return out, truth


def partition(groups: list[set[str]], boxes: list[str]) -> dict[str, int]:
    gid = {}
    for i, g in enumerate(groups):
        for b in g:
            gid[b] = i
    nxt = len(groups)
    for b in boxes:
        if b not in gid:
            gid[b], nxt = nxt, nxt + 1
    return gid


def union(pairs: list[tuple[str, str]], boxes: list[str]) -> list[set[str]]:
    parent = {b: b for b in boxes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        parent[find(a)] = find(b)
    g = collections.defaultdict(set)
    for b in boxes:
        g[find(b)].add(b)
    return [s for s in g.values() if len(s) > 1]


def code_groups(bpx: dict, blank: Path, boxes: list[str]) -> list[set[str]]:
    items, _units = yes_no_groups.g.option_items(bpx)
    pairs = []
    for _name, yi, ni in yes_no_groups.pairs(bpx, blank):
        pairs.append((items[yi]["field"], items[ni]["field"]))
    for grp in cell_groups.groups(bpx, blank):
        for a, b in zip(sorted(grp), sorted(grp)[1:]):
            pairs.append((a, b))
    return union([(a, b) for a, b in pairs if a in boxes and b in boxes], boxes)


def jev_jobs(bid: str, bpx: dict, blank: Path, boxes: list[str]):
    flat = flat_copy(blank)
    rows = [r for r in pc.numbered(bpx) if r["name"] in boxes]
    by_page = collections.defaultdict(list)
    for r in rows:
        by_page[r["boxes"][0]["page"]].append(r)
    jobs = []
    for page_no, rs in by_page.items():
        if len(rs) < 2:
            continue
        png, _dpi, px = pc.render(flat, page_no, rs, limits=LIMITS)
        ref = image_ref(png)
        cen = {r["id"]: ((r["boxes"][0]["rect"][0] + r["boxes"][0]["rect"][2]) / 2,
                         (r["boxes"][0]["rect"][1] + r["boxes"][0]["rect"][3]) / 2) for r in rs}
        name = {r["id"]: r["name"] for r in rs}
        pairs = set()
        for a in cen:
            near = sorted((math.dist(cen[a], cen[b]), b) for b in cen if b != a)
            for d, b in near[:NEAR]:
                if d <= MAX_GAP:
                    pairs.add(tuple(sorted((a, b), key=int)))
        items = [{"id": r["id"], "pixel_box": [round(v) for v in px[r["id"]]]} for r in rs if r["id"] in px]
        pl = sorted(pairs)
        for i in range(0, len(pl), PER_REQUEST):
            qs, names = {}, {}
            for a, b in pl[i:i + PER_REQUEST]:
                qid = f"p{a}_{b}"
                qs[qid] = {"type": "noul", "instructions": {"pair": [a, b], "question": QUESTION}, "criteria": CRITERIA}
                names[qid] = (name[a], name[b])
            body = {"model": MODEL, "state": {"page_number": page_no, "page": ref, "boxes": items}, "questions": qs}
            jobs.append((bid, page_no, body, {ref: png}, names))
    return jobs


def score(groups: list[set[str]], truth: dict[str, str | None], boxes: list[str]) -> dict:
    gid = partition(groups, boxes)
    tp = fp = fn = 0
    for a, b in itertools.combinations(boxes, 2):
        same_t = truth[a] is not None and truth[a] == truth[b]
        same_p = gid[a] == gid[b]
        tp += same_t and same_p
        fp += same_p and not same_t
        fn += same_t and not same_p
    tg = collections.defaultdict(set)
    for b in boxes:
        if truth[b]:
            tg[truth[b]].add(b)
    pg = {frozenset(g) for g in groups}
    exact = sum(frozenset(g) in pg for g in tg.values())
    yn = [g for g in tg.values() if {b.rsplit("__", 1)[-1] for b in g} <= {"yes", "no", "y", "n"} and len(g) == 2]
    big = [g for g in tg.values() if len(g) >= 3]
    return {"tp": tp, "fp": fp, "fn": fn, "groups": len(tg), "exact": exact, "yn": len(yn),
            "yn_exact": sum(frozenset(g) in pg for g in yn), "big": len(big), "big_exact": sum(frozenset(g) in pg for g in big)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms-list", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    forms, jobs = {}, []
    for bid in args.forms_list:
        bp = h._load(h.working_path(bid))
        blank = pc.resolve_blank(bp)
        bpx, truth = explode(bp)
        boxes = sorted(truth)
        if len(boxes) < 2:
            continue
        forms[bid] = (bpx, blank, truth, boxes)
        jobs += jev_jobs(bid, bpx, blank, boxes)
    print(f"{len(forms)} forms with 2+ checkboxes, {sum(len(f[3]) for f in forms.values())} checkboxes, "
          f"{sum(len(j[4]) for j in jobs)} pairs asked in {len(jobs)} requests", file=sys.stderr)
    key, p, tokens = _key(), {}, 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[2], j[3]): j for j in jobs}
        for fut in cf.as_completed(futs):
            j = futs[fut]
            res = fut.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, pair in j[4].items():
                v = ((res.get("answers") or {}).get(qid) or {}).get("noul")
                if v is not None:
                    p[(j[0], pair)] = v
    T = collections.defaultdict(collections.Counter)
    out = {}
    for bid, (bpx, blank, truth, boxes) in forms.items():
        cg = code_groups(bpx, blank, boxes)
        jp = [pair for (b, pair), v in p.items() if b == bid and v > CUT]
        jg = union(jp, boxes)
        both = union(jp + [(a, b) for g in cg for a, b in zip(sorted(g), sorted(g)[1:])], boxes)
        out[bid] = {}
        for k, g in (("code", cg), ("Jev", jg), ("code + Jev", both)):
            s = score(g, truth, boxes)
            T[k].update(s)
            out[bid][k] = s
    Path(args.save).write_text(json.dumps({"forms": out, "pairs": [[b, list(pr), v] for (b, pr), v in p.items()]}))
    pages = len({(j[0], j[1]) for j in jobs})
    print(f"input tokens {tokens:,} (~${tokens / 1e6 * 0.042:.3f}, ${tokens / 1e6 * 0.042 / max(pages, 1):.4f}/page)")
    for k in ("code", "Jev", "code + Jev"):
        s = T[k]
        print(f"{k:11} precision {s['tp'] / max(s['tp'] + s['fp'], 1):4.0%}  recall {s['tp'] / max(s['tp'] + s['fn'], 1):4.0%}  "
              f"groups rebuilt exactly {s['exact']} of {s['groups']} ({s['exact'] / max(s['groups'], 1):.0%}); "
              f"yes / no pairs {s['yn_exact']} of {s['yn']} ({s['yn_exact'] / max(s['yn'], 1):.0%}); "
              f"groups of 3+ {s['big_exact']} of {s['big']} ({s['big_exact'] / max(s['big'], 1):.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
