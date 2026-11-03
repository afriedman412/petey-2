"""The flat-structure benchmark's answer key (Andrew, 2026-10-30: "let's build it for the data we have and the guidelines
we have"): one JSON a page, from the validated blueprints, in the same shape a system under test hands in
(`benchmark_score.py` reads both). Blocks and grids are not scored (2026-10-30), so not in the key.

A page's key:

    {"page_id": "bm__sd_531654__p1", "form": "bm__sd_531654", "page": 1, "set": "government (corpus)",
     "source_pdf": ..., "size": [w, h],
     "fields": [{"id", "rect": [x0, y0, x1, y1], "kind": "text" | "choice" | "printed"}],   points, top left origin
     "groups": [[field id, ...]]}          the fields that make one answer: an option group's boxes (choice), a Split
                                           Field's parts (text). What a grouping is, is not graded (2026-10-30)

What the guidelines say, as read here (docs/BENCHMARK_JUDGEMENT_QS.md, Decided):

    fields     every box of a validated blueprint on the page; a checkbox typed in a text box (a converted field) is
               choice. The key stays as the publisher cut it (combs whole). Types follow the page (2026-11-01): an
               option group's boxes are choice, and so is a text field drawn as a small square (5-16 pt, Y / N boxes
               included), unless it is a comb's cell or in a text group (`as_seen`)
    printed    (2026-10-31, Andrew: "anything that is expected to be hand-written -- signatures, printed names, etc.")
               text fields tagged x_petey_printed on the blueprint (Andrew, 2026-10-31: "printed types should move
               to blueprints, they are fields"), set on the printed sheet or the Review tab; initials printed, signing
               dates and titles text
    groups     option groups of two or more boxes; Split Fields as tagged on the Groups tab (x_petey_entity). Library
               forms validated before the tag existed carry none

Pages: forms the review page counts as validated (every field has a verdict, none flagged, file unchanged since) or
as STRUCTURE VALIDATED ("accept structure", file unchanged since; 2026-10-31), in
the benchmark's sets (library, first batch, business, government, municipal, big publishers, hand-picked, finance,
private);
at most `PER_FORM` pages a form, those with the most fields, after the pages ignored on the review page are left out
(petey.validate.ignored_pages, 2026-10-31). Nothing is written to the blueprints.

    PYTHONPATH=. venv/bin/python eval/benchmark_key.py [--pdfs] [--forms ID ...]

Writes runs/benchmark/key/<page id>.json and index.json; `--pdfs` also writes each page as its own flat PDF with no
widgets and no metadata (runs/benchmark/key/pages/<page id>.pdf): the system's input.
"""
from __future__ import annotations

import argparse
import collections
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
    for pre, name in (("fin__", "finance"), ("pv__", "private"), ("mg__", "hand-picked"),
                      ("bm__pb_", "big publishers"), ("bm__mu_", "municipal")):
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
    from petey.validate.printed_fields import is_printed
    # an option group's boxes are choices however the publisher drew them (text widgets to type an X in)
    if w.get("widget_type") in CHOICE or spec.get("type") == "boolean" or spec.get("widgets"):
        return "choice"
    return "printed" if is_printed(spec) else "text"


SQUARE = (5.0, 16.0)       # points: a box this size each way, about square, looks like a checkbox on the page
COMB_GAP = 3.0             # points: three or more such boxes this close along a line are a comb's cells


def _square(r: list) -> bool:
    w, h = r[2] - r[0], r[3] - r[1]
    return SQUARE[0] <= w <= SQUARE[1] and SQUARE[0] <= h <= SQUARE[1] and 0.7 <= w / h <= 1.4


def comb_cells(rects: dict[str, list]) -> set[str]:
    """The ids among `rects` (small squares on one page) that sit in a run of three or more alike boxes along a line,
    each within `COMB_GAP` of the next: a comb's cells, not checkboxes."""
    out: set[str] = set()
    ids = sorted(rects, key=lambda i: rects[i][0])
    for i in ids:
        run, last = [i], rects[i]
        for j in ids:
            r = rects[j]
            if j in run or r[0] < last[2] - 1 or r[0] - last[2] > COMB_GAP:
                continue
            if abs((r[3] - r[1]) - (last[3] - last[1])) <= 1.5 and min(r[3], last[3]) - max(r[1], last[1]) >= \
                    0.5 * (last[3] - last[1]):
                run.append(j)
                last = r
        if len(run) >= 3:
            out.update(run)
    return out


def as_seen(page: dict) -> int:
    """Type by what the page shows (Andrew, 2026-11-01: "let's just make everything that looks like a checkbox a
    checkbox"; a Y / N text box and a checkbox look the same): a text field drawn as a small square becomes choice,
    unless it is a comb's cell or part of a text group. Printed fields keep their type. How many it changed."""
    in_group = {f for g in page["groups"] for f in g}
    sq = {f["id"]: f["rect"] for f in page["fields"] if f["kind"] == "text" and _square(f["rect"])}
    keep = comb_cells({f["id"]: f["rect"] for f in page["fields"] if _square(f["rect"])}) | in_group
    n = 0
    for f in page["fields"]:
        if f["id"] in sq and f["id"] not in keep:
            f["kind"] = "choice"
            n += 1
    return n


def page_keys(bp: dict, entities: list[dict] = ()) -> dict[int, dict]:
    """{page: {fields, groups}} for one blueprint. `entities`: Split Fields as `compound_values.from_tags` gives them
    ([{fields: [code, ...]}])."""
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    out: dict[int, dict] = collections.defaultdict(lambda: {"fields": [], "groups": []})
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
    for page in out.values():
        as_seen(page)
    return dict(out)


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
    from petey.validate import ignored_pages
    from petey.validate import printed_fields as pf
    from petey.validate.retype import resolve_blank
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*", help="review ids (default: every validated form in the sets)")
    ap.add_argument("--pdfs", action="store_true", help="also write each page's flat PDF")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    paths = h.blueprint_paths()
    todo = [(b, s) for b, s in candidates() if not args.forms or b in args.forms]
    index, skipped = [], collections.Counter()
    record = pf.load()
    ignored = ignored_pages.load()
    proposed = json.loads(pf.CANDIDATES.read_text()) if pf.CANDIDATES.exists() else {}
    unconfirmed = 0
    for bid, sset in todo:
        v = h.load_verdicts(bid)
        if not v.get("verdicts") and not v.get("structure"):
            skipped["not reviewed"] += 1
            continue
        p = h.working_path(bid, paths)
        bp = h._load(p)
        if not h.structure_ok(v, p, bp):                 # validated, or its structure validated (2026-10-31)
            skipped["not validated"] += 1
            continue
        keys = page_keys(bp, cv.from_tags(bp))
        for pg in [pg for pg in keys if f"{bid}__p{pg}" in ignored]:      # ignored on the review page, before the pick
            del keys[pg]
            skipped["pages ignored"] += 1
        pages = sorted(keys, key=lambda pg: (-len(keys[pg]["fields"]), pg))[:PER_FORM]
        blank = resolve_blank(bp)
        for pg in sorted(pages):
            pid = f"{bid}__p{pg}"
            k = {"page_id": pid, "form": bid, "page": pg, "set": sset, "source_pdf": bp.get("source_pdf"),
                 "size": None, **keys[pg]}
            if pid in proposed and pid not in record:
                unconfirmed += 1
            if args.pdfs:
                if blank is None:
                    skipped["no blank for the page PDF"] += 1
                else:
                    k["size"] = write_page_pdf(blank, pg, args.out / "pages" / f"{pid}.pdf")
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{pid}.json").write_text(json.dumps(k, indent=1))
            index.append({"page_id": pid, "set": sset, "fields": len(k["fields"]), "groups": len(k["groups"]),
                          "printed": sum(f["kind"] == "printed" for f in k["fields"])})
    (args.out / "index.json").write_text(json.dumps(index, indent=1))
    by = collections.defaultdict(collections.Counter)
    for x in index:
        by[x["set"]].update({"pages": 1, "fields": x["fields"], "groups": x["groups"], "printed": x["printed"]})
    forms = collections.Counter(s for _f, s in {(x["page_id"].rsplit("__p", 1)[0], x["set"]) for x in index})
    print(f"{len(index)} pages from {sum(forms.values())} forms -> {args.out}")
    for s, c in sorted(by.items(), key=lambda kv: -kv[1]["pages"]):
        print(f"  {s:22} forms {forms[s]:4}  pages {c['pages']:5}  fields {c['fields']:6}  groups {c['groups']:5}"
              f"  printed {c['printed']:4}")
    print("left out:", dict(skipped))
    if unconfirmed:
        print(f"{unconfirmed} pages with printed candidates not confirmed on the printed sheet (typed text for now)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
