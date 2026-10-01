"""Debugging yardstick: the page box finder against the blank's widget layer.

Case generation takes its boxes from the page (step2flat's finder on the
rendered blank), never from the AcroForm layer (Andrew, 2026-09-30). The
widget layer is still the best available truth about where the fillable
boxes ARE, so this reports, per form, which widgets the finder missed and
which finder boxes have no widget behind them. It feeds nothing; it tells
us where the finder needs work.

Size-aware since 2026-10-01: `boxes.match_rect` scores intersection over the
SMALLER area, so a widget inside a big region box counted as found and
recall on table forms was overstated (ND 10RR: one finder box over a whole
table column holds 25 widgets). A widget is `hit` only when its best box is
comparable in size (within SIZE_RATIO of its area, either way); a box more
than SIZE_RATIO times larger is a `region` and the widget is `in_region`; a
box more than SIZE_RATIO times smaller is a `part` (a comb cell under a wide
widget). Region boxes are reported on their own with the widgets they hold.

    PYTHONPATH=. venv/bin/python eval/finder_vs_widgets.py --tier core [--json out.json]
    PYTHONPATH=. venv/bin/python eval/finder_vs_widgets.py --list runs/judge_eval/forms44.txt \
        --json runs/judge_eval/finder_vs_widgets_before.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import SOURCE_PDFS  # noqa: E402
from petey.synth.boxes import find_boxes, match_rect_scored  # noqa: E402
from petey.validate.test_forms import forms  # noqa: E402

SIZE_RATIO = 3.0        # a hit's box is within this factor of the widget's area, either way
MIN_OVERLAP = 0.5


def _area(r) -> float:
    return max((r[2] - r[0]) * (r[3] - r[1]), 1e-6)


def widget_rects(pdf: Path) -> list[dict]:
    out = []
    doc = pymupdf.open(str(pdf))
    try:
        for pno, page in enumerate(doc, start=1):
            for w in page.widgets() or []:
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON):
                    continue
                kind = {pymupdf.PDF_WIDGET_TYPE_TEXT: "text", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "option",
                        pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "option", pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "text",
                        pymupdf.PDF_WIDGET_TYPE_LISTBOX: "text"}.get(w.field_type, "other")
                out.append({"page": pno, "rect": [round(c, 2) for c in w.rect], "kind": kind, "path": w.field_name})
    finally:
        doc.close()
    return out


def classify_match(widget: dict, boxes: list[dict]) -> tuple[str, dict | None]:
    """`hit`, `in_region`, `part` or `miss`, with the best-overlapping box.

    Among boxes at or above MIN_OVERLAP the comparable-size one wins when
    there is one (a comb cell AND the comb group over the same widget: the
    group is the hit); otherwise the best overlap decides the class."""
    scored = match_rect_scored(widget["rect"], boxes, MIN_OVERLAP)
    if not scored:
        return "miss", None
    wa = _area(widget["rect"])
    for _, b in scored:
        ratio = _area(b["rect"]) / wa
        if 1.0 / SIZE_RATIO <= ratio <= SIZE_RATIO:
            return "hit", b
    b = scored[0][1]
    ratio = _area(b["rect"]) / wa
    return ("in_region" if ratio > SIZE_RATIO else "part"), b


def compare(pdf: Path, cache_dir: Path | None = None) -> dict:
    t0 = time.time()
    boxes = find_boxes(pdf, cache_dir) if cache_dir else find_boxes(pdf)
    widgets = widget_rects(pdf)
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    counts: collections.Counter = collections.Counter()
    missed, used = [], set()
    held: dict[str, list[dict]] = collections.defaultdict(list)     # box id -> widgets it swallows as a region
    for w in widgets:
        cls, b = classify_match(w, by_page.get(w["page"], []))
        counts[f"{cls}_{w['kind']}"] += 1
        counts[cls] += 1
        if b is not None:
            used.add(b["id"])
            # the old yardstick: any overlap at or above MIN_OVERLAP was a hit
            counts[f"old_hit_{w['kind']}"] += 1
        if cls == "miss":
            missed.append(w)
        elif cls == "in_region":
            held[b["id"]].append(w)
    by_id = {b["id"]: b for b in boxes}
    regions = [{"page": by_id[i]["page"], "rect": by_id[i]["rect"], "kind": by_id[i]["kind"],
                "widgets": len(ws), "widget_kinds": dict(collections.Counter(w["kind"] for w in ws))}
               for i, ws in held.items()]
    regions.sort(key=lambda r: -r["widgets"])
    extras = [b for b in boxes if b["id"] not in used]
    n_text = sum(1 for w in widgets if w["kind"] == "text")
    n_opt = sum(1 for w in widgets if w["kind"] == "option")
    return {
        "form": pdf.name, "seconds": round(time.time() - t0, 1),
        "widgets": len(widgets), "finder_boxes": len(boxes),
        "n_text": n_text, "n_option": n_opt,
        "hit_text": counts["hit_text"], "hit_option": counts["hit_option"],
        "old_hit_text": counts["old_hit_text"], "old_hit_option": counts["old_hit_option"],
        "in_region": counts["in_region"], "part": counts["part"], "miss": counts["miss"],
        "text_recall": f"{counts['hit_text']}/{n_text}", "option_recall": f"{counts['hit_option']}/{n_opt}",
        "region_boxes": len(regions), "widgets_in_regions": sum(r["widgets"] for r in regions),
        "regions": regions,
        "extras": len(extras),
        "extras_by_kind": dict(collections.Counter(b["kind"] for b in extras)),
        "missed": [{"page": w["page"], "kind": w["kind"], "rect": w["rect"], "path": w["path"].split(".")[-1]}
                   for w in missed],
    }


def _targets(args) -> list[tuple[str, Path]]:
    if args.list:
        out = []
        for line in Path(args.list).read_text().splitlines():
            if "|" in line:
                stem, rel = line.strip().split("|", 1)
                out.append((stem, SOURCE_PDFS / rel))
        return out
    from petey.validate.test_forms import by_stem
    tfs = [by_stem(s) for s in args.forms.split(",")] if args.forms else forms(args.tier)
    return [(tf.stem, tf.blank_path) for tf in tfs]


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.0f}%" if b else "-"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tier", default="core")
    ap.add_argument("--forms", default=None, help="comma-separated stems instead of a tier")
    ap.add_argument("--list", default=None, help="a file of form|path-under-source_pdfs lines (runs/judge_eval/forms44.txt)")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--show-missed", type=int, default=6)
    args = ap.parse_args()
    results = []
    tot: collections.Counter = collections.Counter()
    print(f"{'form':28} {'widg':>5} {'find':>5} {'text hit':>10} {'opt hit':>9} {'old text':>9} {'old opt':>8} "
          f"{'in_reg':>6} {'part':>5} {'miss':>5} {'regions':>8} {'extra':>5}")
    for stem, blank in _targets(args):
        r = compare(blank)
        r["stem"] = stem
        results.append(r)
        for k in ("widgets", "finder_boxes", "n_text", "n_option", "hit_text", "hit_option", "old_hit_text",
                  "old_hit_option", "in_region", "part", "miss", "region_boxes", "widgets_in_regions", "extras"):
            tot[k] += r[k]
        print(f"{stem[:28]:28} {r['widgets']:5} {r['finder_boxes']:5} {r['text_recall']:>10} {r['option_recall']:>9} "
              f"{r['old_hit_text']:>9} {r['old_hit_option']:>8} {r['in_region']:6} {r['part']:5} {r['miss']:5} "
              f"{r['region_boxes']:>3}({r['widgets_in_regions']:>3}) {r['extras']:5}")
        for m in r["missed"][:args.show_missed]:
            print(f"    missed p{m['page']} {m['kind']:6} {m['rect']} {m['path']}")
        if len(r["missed"]) > args.show_missed:
            print(f"    ... {len(r['missed']) - args.show_missed} more")
    if len(results) > 1:
        print(f"{'TOTAL':28} {tot['widgets']:5} {tot['finder_boxes']:5} "
              f"{tot['hit_text']:>4}/{tot['n_text']:<5} {tot['hit_option']:>4}/{tot['n_option']:<4} "
              f"{tot['old_hit_text']:>9} {tot['old_hit_option']:>8} {tot['in_region']:6} {tot['part']:5} {tot['miss']:5} "
              f"{tot['region_boxes']:>3}({tot['widgets_in_regions']:>3}) {tot['extras']:5}")
        print(f"strict recall: text {_pct(tot['hit_text'], tot['n_text'])}, options {_pct(tot['hit_option'], tot['n_option'])}; "
              f"old yardstick: text {_pct(tot['old_hit_text'], tot['n_text'])}, options {_pct(tot['old_hit_option'], tot['n_option'])}; "
              f"widgets inside region boxes {tot['in_region']}, under part boxes {tot['part']}, missed {tot['miss']}")
    if args.json:
        args.json.write_text(json.dumps({"size_ratio": SIZE_RATIO, "min_overlap": MIN_OVERLAP, "forms": results,
                                         "totals": dict(tot)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
