"""The flat-structure benchmark's answer key (Andrew, 2026-10-30: "let's build it for the data we have and the guidelines
we have"): one JSON a page, from the validated blueprints and their Grids / Blocks records, in the same shape a system
under test hands in (`benchmark_score.py` reads both).

A page's key:

    {"page_id": "bm__sd_531654__p1", "form": "bm__sd_531654", "page": 1, "set": "government (corpus)",
     "source_pdf": ..., "size": [w, h],
     "fields": [{"id", "rect": [x0, y0, x1, y1], "kind": "text" | "choice"}],     points, top left origin
     "groups": [[field id, ...]],          the fields that make one answer: an option group's boxes (choice), a Split
                                           Field's parts (text). What a grouping is, is not graded (2026-10-30)
     "grids":  [{"cells": [{"field", "row", "col"}]}],
     "blocks": [{"cells": [{"field", "copy", "slot"}]}]}

What the guidelines say, as read here (docs/BENCHMARK_JUDGEMENT_QS.md, Decided):

    fields     every box of a validated blueprint on the page; signatures are text; a checkbox typed in a text box
               (a converted field) is choice. The key stays as the publisher cut it (combs whole)
    groups     option groups of two or more boxes; Split Fields as tagged on the Groups tab (x_petey_entity). Library
               forms validated before the tag existed carry none
    grids      the Grids tab's active grids, as the review page lists them (blocks over grids, set-aside finder grids
               out); a cell holding an option group lists each of its boxes at the cell's row and column
    blocks     block types with two or more copies on the page (single pages: one copy a page makes no block; the
               proposal under question 4, not decided); slot = the position in the type's template

Pages: forms the review page counts as validated (every field has a verdict, none flagged, file unchanged since), in
the benchmark's sets (library, first batch, business, government, municipal, big publishers, hand-picked, finance);
at most `PER_FORM` pages a form, those with the most fields. Nothing is written to the blueprints or the records.

    PYTHONPATH=. venv/bin/python eval/benchmark_key.py [--pdfs] [--forms ID ...]

Writes runs/benchmark/key/<page id>.json and index.json; `--pdfs` also writes each page as its own flat PDF with no
widgets and no metadata (runs/benchmark/key/pages/<page id>.pdf): the system's input.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "benchmark" / "key"
PER_FORM = 2
CHOICE = ("checkbox", "radiobutton")


def _set_of(bid: str, business: set, gov: set) -> Optional[str]:
    if bid in business:
        return "business"
    for pre, name in (("fin__", "finance"), ("mg__", "hand-picked"), ("bm__pb_", "big publishers"),
                      ("bm__mu_", "municipal")):
        if bid.startswith(pre):
            return name
    if bid in gov:
        return "government (corpus)"
    if bid.startswith("fl__sd_"):
        return "first batch"
    if bid.startswith("lib__"):
        return "library"
    return None


def _kind(spec: dict, w: dict) -> str:
    if w.get("widget_type") in CHOICE or spec.get("type") == "boolean":
        return "choice"
    return "text"


def page_keys(bp: dict, grids: list[dict] = (), types: list[dict] = (), entities: list[dict] = ()) -> dict[int, dict]:
    """{page: {fields, groups, grids, blocks}} for one blueprint. `grids`: active grid listings ([{grid: [{name, row,
    col}]}]); `types`: block types from the record ([{blocks: [[code or None, ...]]}]); `entities`: Split Fields as
    `compound_values.from_tags` gives them ([{fields: [code, ...]}])."""
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    out: dict[int, dict] = collections.defaultdict(lambda: {"fields": [], "groups": [], "grids": [], "blocks": []})
    by_code: dict[str, list[str]] = {}             # a field's code -> its box ids (an option group: one a box)
    page_of: dict[str, int] = {}
    for n, s in fields.items():
        code = str(s.get("x_petey_id") if s.get("x_petey_id") is not None else n)
        ws = ({f"{code}.{k}": w for k, w in s["widgets"].items()} if s.get("widgets")
              else {code: s["widget"]} if s.get("widget") else {})
        ids = []
        for i, w in ws.items():
            if not w.get("rect") or w.get("page") is None:
                continue
            p = int(w["page"])
            out[p]["fields"].append({"id": i, "rect": [round(float(x), 2) for x in w["rect"]], "kind": _kind(s, w)})
            page_of[i] = p
            ids.append(i)
        by_code[code] = ids
        on = collections.defaultdict(list)
        for i in ids:
            on[page_of[i]].append(i)
        if s.get("widgets"):
            for p, g in on.items():
                if len(g) >= 2:
                    out[p]["groups"].append(g)
    for e in entities:
        on = collections.defaultdict(list)
        for c in e["fields"]:
            for i in by_code.get(str(c), []):
                on[page_of[i]].append(i)
        for p, g in on.items():
            if len(g) >= 2:
                out[p]["groups"].append(g)
    code_of = {n: str(s.get("x_petey_id") if s.get("x_petey_id") is not None else n) for n, s in fields.items()}
    for t in grids:
        on = collections.defaultdict(list)
        for c in t["grid"]:
            for i in by_code.get(code_of.get(c["name"], ""), []):
                on[page_of[i]].append({"field": i, "row": c["row"], "col": c["col"]})
        for p, cells in on.items():
            if len({x["field"] for x in cells}) >= 2:
                out[p]["grids"].append({"cells": cells})
    for t in types:
        on = collections.defaultdict(list)
        for k, b in enumerate(t.get("blocks") or []):
            for j, c in enumerate(b):
                for i in by_code.get(str(c), []) if c else []:
                    on[page_of[i]].append({"field": i, "copy": k, "slot": j})
        for p, cells in on.items():
            if len({x["copy"] for x in cells}) >= 2:
                out[p]["blocks"].append({"cells": cells})
    return dict(out)


def _records(bid: str, bp: dict) -> tuple[list[dict], list[dict]]:
    """(active grids, block types) as the review page shows them, read without saving: `grid_check.listing` settles
    grids against blocks on a copy of the record and would write it back when something is new."""
    from petey.validate import grid_check as gc
    rec = copy.deepcopy(gc.load_set(bid))
    load, save = gc.load_set, gc._save_set
    gc.load_set, gc._save_set = (lambda _b: rec), (lambda *_a, **_k: None)
    try:
        grids = [t for t in gc.listing(bid, bp) if t.get("status") == "active" and t.get("kind", "table") == "table"]
    finally:
        gc.load_set, gc._save_set = load, save
    return grids, rec.get("types") or []


def candidates() -> list[tuple[str, str]]:
    """[(review id, set)] of the forms in the benchmark's sets."""
    from petey.validate import hand_review as h
    R = ROOT / "runs" / "acquisition" / "safedocs"
    business = {f["review_id"] for f in json.loads((R / "business_set.json").read_text())["forms"]} \
        if (R / "business_set.json").exists() else set()
    gov = {"bm__sd_" + json.loads(ln)["url_id"] for ln in (R / "staged_gov.jsonl").read_text().splitlines() if ln} \
        if (R / "staged_gov.jsonl").exists() else set()
    return [(b, s) for b in h.blueprint_paths() if (s := _set_of(b, business, gov))]


def write_page_pdf(blank: Path, page: int, dst: Path) -> list[float]:
    """The page alone, flat (widget appearances baked in, widgets and annotations gone), no metadata. Its size."""
    import pymupdf
    src = pymupdf.open(blank)
    if any(True for p in src for _ in p.widgets()) or any(True for p in src for _ in p.annots()):
        src.bake(annots=False, widgets=True)
    doc = pymupdf.open()
    doc.insert_pdf(src, from_page=page - 1, to_page=page - 1)
    for p in doc:
        for w in list(p.widgets()):
            p.delete_widget(w)
        for a in list(p.annots()):
            p.delete_annot(a)
    doc.set_metadata({})
    doc.del_xml_metadata()
    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dst, garbage=3, deflate=True)
    return [round(doc[0].rect.width, 2), round(doc[0].rect.height, 2)]


def main() -> int:
    from petey.validate import compound_values as cv
    from petey.validate import hand_review as h
    from petey.validate.retype import resolve_blank
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*", help="review ids (default: every validated form in the sets)")
    ap.add_argument("--pdfs", action="store_true", help="also write each page's flat PDF")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    paths = h.blueprint_paths()
    todo = [(b, s) for b, s in candidates() if not args.forms or b in args.forms]
    index, skipped = [], collections.Counter()
    for bid, sset in todo:
        v = h.load_verdicts(bid)
        if not v.get("verdicts"):
            skipped["not reviewed"] += 1
            continue
        p = h.working_path(bid, paths)
        bp = h._load(p)
        c = h.checked(v, p, bp)
        if not (c and c["validated"]):
            skipped["not validated"] += 1
            continue
        try:
            grids, types = _records(bid, bp)
        except Exception as e:                          # a blank that will not open: grids by names only fail too
            skipped[f"grids unreadable ({type(e).__name__})"] += 1
            continue
        keys = page_keys(bp, grids, types, cv.from_tags(bp))
        pages = sorted(keys, key=lambda pg: (-len(keys[pg]["fields"]), pg))[:PER_FORM]
        blank = resolve_blank(bp)
        for pg in sorted(pages):
            pid = f"{bid}__p{pg}"
            k = {"page_id": pid, "form": bid, "page": pg, "set": sset, "source_pdf": bp.get("source_pdf"),
                 "size": None, **keys[pg]}
            if args.pdfs:
                if blank is None:
                    skipped["no blank for the page PDF"] += 1
                else:
                    k["size"] = write_page_pdf(blank, pg, args.out / "pages" / f"{pid}.pdf")
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{pid}.json").write_text(json.dumps(k, indent=1))
            index.append({"page_id": pid, "set": sset, "fields": len(k["fields"]), "groups": len(k["groups"]),
                          "grids": len(k["grids"]), "blocks": len(k["blocks"])})
    (args.out / "index.json").write_text(json.dumps(index, indent=1))
    by = collections.defaultdict(collections.Counter)
    for x in index:
        by[x["set"]].update({"pages": 1, "fields": x["fields"], "groups": x["groups"], "grids": x["grids"],
                             "blocks": x["blocks"], "forms": 0})
    forms = collections.Counter(s for _f, s in {(x["page_id"].rsplit("__p", 1)[0], x["set"]) for x in index})
    print(f"{len(index)} pages from {sum(forms.values())} forms -> {args.out}")
    for s, c in sorted(by.items(), key=lambda kv: -kv[1]["pages"]):
        print(f"  {s:22} forms {forms[s]:4}  pages {c['pages']:5}  fields {c['fields']:6}  groups {c['groups']:5}  "
              f"grids {c['grids']:4}  blocks {c['blocks']:4}")
    print("left out:", dict(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
