"""Names for a flat form's fields for pennies? (Andrew, 2026-10-15: "we can read all the text on the page for cheap
too, and we get can a lot of labels just off that ... it takes a lot of higher order thinking to nail down EVERY
field, but we can get a lot of the way there for cheap.")

For each text field and lone checkbox of a validated blueprint (its box taken as given: the finder plus Jev's "is it a
field" decide that step, eval/jev_is_field.py):
  1. candidates (code, free): the printed lines nearest the box, its column header, its row label, column + row
     together (`witness.page_texts`), cleaned; nothing from the widget layer (a flat form has no tooltips);
  2. pick (Jev, a choice question): which candidate is the box's caption, with the page image (widgets stripped,
     every box outlined and numbered, no names shown);
  3. name (code, free): the caption slugged (`field_add.name_from`), then the naming standard with the field's type
     (`standardize_names.standard`; the kind is its own step).
Scored against the validated name on the description words (suffixes and iteration numbers left out): exact, same
words (any order), close (half the words shared), wrong. Beside Jev's pick: the nearest line (no model) and the best
candidate (the ceiling of step 1).

    PYTHONPATH=. venv/bin/python eval/cheap_names.py --forms 40 --save runs/jev/cheap_names_2026-10-15.json
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import random
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev_is_field import cached_boxes, flat_copy  # noqa: E402
from standardize_names import SUFFIXES, standard  # noqa: E402

from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate import witness as W  # noqa: E402
from petey.validate.field_add import clean_caption, name_from  # noqa: E402
from petey.validate.field_chain import _page_lines  # noqa: E402
from petey.validate.jev_page import LIMITS, MODEL, _key, ask_split, image_ref  # noqa: E402

QUESTION = ("`page` is one page of a blank form; every fillable box is outlined in red and tagged with its number at "
            "its top-left. Look at the box tagged `box.id`. Which of the printed texts listed as choices is its "
            "caption: the words that tell a person what to write or mark in that box (a table cell's caption may be "
            "its column header with its row label)?")
PER_REQUEST = 20
STOP = {"of", "the", "a", "an", "and", "or", "for", "to", "in", "on", "at", "by", "if", "is", "your", "you", "this",
        "please", "enter", "with", "from", "any"}


def words(name: str) -> list[str]:
    """A name's description words: suffixes, iteration numbers and filler left out."""
    return [t for t in name.split("_") if t and t not in SUFFIXES and not t.isdigit() and t not in STOP and t != "ind"]


def grade(got: str | None, want: str) -> str:
    if not got:
        return "none"
    g, w = words(got), words(want)
    if g == w:
        return "exact"
    if set(g) == set(w):
        return "same words"
    if w and len(set(g) & set(w)) >= max(1, len(set(w)) / 2):
        return "close"
    return "wrong"


ORDER = ["exact", "same words", "close", "wrong", "none"]


def to_name(caption: str | None, spec: dict) -> str | None:
    kind = "option" if spec.get("type") == "boolean" else "text"
    n = name_from(caption, kind)
    return standard(n, spec)[0] if n else None


def form_items(bid: str):
    """The fields to name with their candidates, and the requests for Jev."""
    bp = h._load(h.working_path(bid))
    blank = pc.resolve_blank(bp)
    lines = _page_lines(str(blank))
    rows = pc.numbered(bp)
    flat = flat_copy(blank)
    fields = []
    for r in rows:
        spec = r["spec"]
        if spec.get("widgets"):
            continue                                   # option groups: their captions are another question
        cands = []
        for t in W.page_texts(spec, lines):
            c = clean_caption(t)
            if c and c not in cands:
                cands.append(c)
        w = spec.get("widget") or {}
        pl = lines.get(w.get("page"), [])
        if w.get("rect") and pl:
            col, row = W.column_header(w["rect"], pl), W.row_header(w["rect"], pl)
            if col and row:
                both = clean_caption(f"{row} {col}")
                if both and both not in cands:
                    cands.append(both)
        fields.append({"bid": bid, "id": r["id"], "page": r["boxes"][0]["page"], "name": r["name"],
                       "type": spec.get("type"), "spec": spec, "cands": cands[:8]})
    jobs = []
    for page_no in sorted({f["page"] for f in fields}):
        png, _dpi, px = pc.render(flat, page_no, rows, limits=LIMITS)
        ref = image_ref(png)
        boxes = [{"id": r["id"], "kind": "checkbox" if r["spec"].get("type") == "boolean" else "text",
                  "pixel_box": [round(v) for v in px[r["id"]]]} for r in rows if r["id"] in px and not r["spec"].get("widgets")]
        ask = [f for f in fields if f["page"] == page_no and len(f["cands"]) >= 2]
        for i in range(0, len(ask), PER_REQUEST):
            qs, names = {}, {}
            for f in ask[i:i + PER_REQUEST]:
                crit = {f"c{k}": c for k, c in enumerate(f["cands"])}
                crit["none"] = "None of these texts is this box's caption."
                qs[f"b{f['id']}"] = {"type": "choice", "instructions": {"box": {"id": f["id"]}, "question": QUESTION},
                                     "criteria": crit}
                names[f"b{f['id']}"] = f["id"]
            body = {"model": MODEL, "state": {"page_number": page_no, "page": ref, "boxes": boxes}, "questions": qs}
            jobs.append((bid, page_no, body, {ref: png}, names))
    return fields, jobs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", type=int, default=40)
    ap.add_argument("--max-pages", type=int, default=4)
    ap.add_argument("--list", default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    listing = json.loads(Path(args.list).read_text()) if args.list else httpx.get("http://127.0.0.1:5005/api/blueprints", timeout=120).json()
    cands = [e["id"] for e in listing if (e.get("checked") or {}).get("validated") and (e.get("pages") or 99) <= args.max_pages
             and (b := pc.resolve_blank(h._load(h.working_path(e["id"])))) and cached_boxes(b) is not None]
    random.Random(7).shuffle(cands)
    forms = cands[:args.forms]
    fields, jobs = [], []
    for bid in forms:
        f, j = form_items(bid)
        fields += f
        jobs += j
    print(f"{len(forms)} forms, {len(fields)} fields, {len(jobs)} requests", file=sys.stderr)
    key, picks, tokens = _key(), {}, 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[2], j[3]): j for j in jobs}
        for fut in cf.as_completed(futs):
            j = futs[fut]
            res = fut.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, fid in j[4].items():
                a = (res.get("answers") or {}).get(qid) or {}
                picks[(j[0], fid)] = a.get("choice"), a.get("probabilities") or a.get("probability")
    out, G = [], collections.defaultdict(collections.Counter)
    for f in fields:
        c = f["cands"]
        choice, _p = picks.get((f["bid"], f["id"]), (None, None))
        jev_cap = c[0] if len(c) == 1 else (c[int(choice[1:])] if choice and choice.startswith("c") and choice[1:].isdigit()
                                            and int(choice[1:]) < len(c) else None)
        names = {"nearest line": to_name(c[0], f["spec"]) if c else None, "Jev's pick": to_name(jev_cap, f["spec"])}
        grades = {k: grade(v, f["name"]) for k, v in names.items()}
        best = min((grade(to_name(x, f["spec"]), f["name"]) for x in c), key=ORDER.index) if c else "none"
        grades["best candidate"] = best
        for k, g in grades.items():
            G[k][g] += 1
        out.append({k: v for k, v in f.items() if k != "spec"} | {"names": names, "grades": grades, "jev_choice": choice})
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(out, indent=1))
    pages = len({(j[0], j[1]) for j in jobs})
    print(f"input tokens {tokens:,} (~${tokens / 1e6 * 0.042:.3f}, ${tokens / 1e6 * 0.042 / max(pages, 1):.4f}/page)")
    print(f"\n{len(fields)} fields ({sum(1 for f in fields if not f['cands'])} with no printed text near them)")
    print(f"{'':16}" + "".join(f"{g:>12}" for g in ORDER))
    for k in ("nearest line", "Jev's pick", "best candidate"):
        print(f"{k:16}" + "".join(f"{G[k][g]:>8} {G[k][g] / len(fields):3.0%}" for g in ORDER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
