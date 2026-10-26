"""A text box stretched across a YES and a NO column becomes a pair of boxes, one of which gets checked (Andrew,
2026-10-15, boat application: "the form directs the user to check one of two boxes, one column is Yes the other is No
... the metadata says otherwise but that's likely a mistake or idiosyncrasy of this copy, and anyone filling this
form out manually is likely to be following the guidance of the page, not the metadata").

Found by where it sits: a text widget about one box pair wide (18-45 pt) and one line high, with a printed YES above
its left half and a printed NO above its right half (within 200 pt). It becomes a `category` group named for its
question (the old name less `_ind`), keys yes / no, each option the half of the old box under its column, with no
widget path: the reader takes the mark from the page (`extract`'s ink path), as on a flat form. The old field is kept
in `x_petey_split`; the change goes into the review page's working copy as Claude's (`x_petey_hand_edit`, kind split).

    PYTHONPATH=. venv/bin/python eval/split_yes_no.py je__boat_application [--also NAME ...] [--dry]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import pymupdf
import yaml

from petey.validate import draft, hand_review as h
from petey.validate.retype import resolve_blank


def candidates(bp: dict, blank, also: set[str] = frozenset()) -> list[str]:
    doc = pymupdf.open(str(blank))
    try:
        words = {i + 1: doc[i].get_text("words") for i in range(len(doc))}
    finally:
        doc.close()
    out = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        if w.get("widget_type") != "text" or not w.get("rect"):
            continue
        x0, y0, x1, y1 = w["rect"]
        mid = (x0 + x1) / 2
        if n not in also and not (18 <= x1 - x0 <= 45 and y1 - y0 <= 20):
            continue
        ws = words.get(w["page"]) or []
        col = lambda word, lo, hi: [t for t in ws if t[4].upper().strip(".:") == word and t[3] <= y0 + 1   # noqa: E731
                                    and lo <= (t[0] + t[2]) / 2 <= hi and y0 - t[3] < 200]
        if n in also or (col("YES", x0 - 4, mid + 2) and col("NO", mid - 2, x1 + 4)):
            out.append(n)
    return out


def split(name: str, spec: dict, now: str) -> tuple[str, dict]:
    w = spec["widget"]
    x0, y0, x1, y1 = w["rect"]
    mid = (x0 + x1) / 2
    new = name[:-4] if name.endswith("_ind") else name
    half = lambda a, b, cap: {"page": w["page"], "rect": [a, y0, b, y1], "widget_type": "checkbox", "path": None,   # noqa: E731
                              "caption": cap, "x_petey_caption_source": "page_text"}
    out = {k: v for k, v in spec.items() if k in ("x_petey_id", "description", "x_petey_description_source", "label_source")}
    out.update(type="category", values=["yes", "no"], widgets={"yes": half(x0, mid, "YES"), "no": half(mid, x1, "NO")})
    out["x_petey_split"] = {"from": name, "path": w.get("path"), "rect": w["rect"], "type": spec.get("type"),
                            "why": "one text widget across the YES and NO columns: the page asks for one of two boxes"}
    out["x_petey_hand_edit"] = {"when": now, "from": {"name": name, "type": spec.get("type")},
                                "to": {"name": new, "type": "category"}, "record": "eval/split_yes_no.py", "by": "claude",
                                "kind": "split", "why": "split into YES / NO boxes as the page lays them out"}
    return new, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bid")
    ap.add_argument("--also", nargs="*", default=[], help="fields to split though the layout test misses them")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    p = h.working_path(args.bid) if args.dry else draft.ensure(args.bid, h.blueprint_paths()[args.bid])
    bp = h._load(p)
    names = candidates(bp, resolve_blank(bp), set(args.also))
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    fields, ren = {}, {}
    for n, s in bp["fields"].items():
        if n in names:
            new, spec = split(n, s, now)
            if new in bp["fields"] and new != n:
                print(f"  {n}: {new!r} is taken, left as it is")
                fields[n] = s
                continue
            fields[new], ren[n] = spec, new
        else:
            fields[n] = s
    for o, nw in ren.items():
        print(f"  {o} -> {nw} (yes / no)")
    print(f"{args.bid}: {len(ren)} split")
    if args.dry or not ren:
        return 0
    before = h._sha(p)
    bp["fields"] = fields
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    draft.follow(args.bid, before, h._sha(p))
    vp = h.verdict_path(args.bid)
    if vp.exists():
        rec = json.loads(vp.read_text())
        vs = rec.get("verdicts") or {}
        for o, nw in ren.items():
            if o in vs:
                vs[nw] = vs.pop(o)
        rec["verdicts"] = vs
        vp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    draft.log(args.bid, "claude", [f"{o} split into yes / no boxes as {nw}" for o, nw in ren.items()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
