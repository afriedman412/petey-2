"""Inventory cross-reference (Andrew, 2026-09-30): the case's boxes against the
blueprint's, by rect, both directions and many-to-one. A scoring step.

Set 2 reads clean by path, but a field no page box reached is left out of
the ground truth and scored as agree-on-empty (10-10EZ 122/122 while the
finder misses seven of its page-5 boxes). This gives every mismatch between
the two inventories a taxonomy class, so coverage is a number beside the
value verdicts rather than a silence inside them:

    box_unreached          a field (or option) no case box landed on
    merged_box             one case box holds two or more field rects
    split_box              several case boxes inside one field rect (benign:
                           the filler concatenates, rect_join joins the same)
    uncovered_widget       a case box with no field under it but a widget
    unbacked_box           a case box with no field and no widget under it
    option_group_mismatch  the classifier's `group` and the blueprint's
                           option groups partition the same boxes differently

The widget layer is read here, after the case is made, as the third
reference that says whether the finder or the labeler is wrong (never as an
input to generation). On a flat blank it is absent and every mismatch is a
flag for review.

Option groups follow the three-way rule: page and blueprint agree on the
member boxes -> confirmed (the metadata, if any, may drive mechanics);
page and blueprint disagree -> `option_group_mismatch`, and the metadata
only attributes it: a page group across several radio paths is a publisher
split; a blueprint field across several page groups is a labeler merge.
Option MEANING never comes from the metadata.

Ties in the rect match (two candidates fully contained, both at 1.0) are
recorded on the row instead of resolved silently.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Any, Optional

import pymupdf

from petey.synth.boxes import match_rect_scored, overlap, parse_rect_key

_OPTION_TYPES = {"category", "multi_category", "boolean"}


def _widgets(blank_pdf: Optional[Path]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    if not blank_pdf or not Path(blank_pdf).exists():
        return out
    doc = pymupdf.open(str(blank_pdf))
    try:
        for pno, page in enumerate(doc, start=1):
            for w in page.widgets() or []:
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON):
                    continue
                out.setdefault(pno, []).append({
                    "rect": [float(c) for c in w.rect], "path": w.field_name,
                    "radio": w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
                    "checkbox": w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX})
    finally:
        doc.close()
    return out


def _field_rects(bpt: dict) -> list[dict]:
    """One row per blueprint widget rect: fields and their options."""
    rows = []
    for name, spec in (bpt.get("fields") or {}).items():
        if spec.get("widgets"):
            for opt, wb in spec["widgets"].items():
                rect = wb.get("rect") or wb.get("box")
                if rect:
                    rows.append({"field": name, "option": opt, "page": wb.get("page"), "rect": rect,
                                 "path": wb.get("path"), "kind": "option"})
        else:
            w = spec.get("widget") or {}
            if w.get("rect"):
                rows.append({"field": name, "option": None, "page": w.get("page"), "rect": w["rect"],
                             "path": w.get("path"),
                             "kind": "option" if spec.get("type") in _OPTION_TYPES else "text"})
    return rows


def cross_reference(bpt: dict, cmap: dict, blank_pdf: Optional[Path] = None) -> dict:
    """The two inventories against each other. Returns rows per class and a
    summary. `cmap` is the classifier's map (boxes keyed by rect key, with
    `class`, `group`, `page`, `rect`)."""
    case_boxes = [{"key": k, **b} for k, b in cmap["boxes"].items() if b.get("class") != "none"]
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for b in case_boxes:
        by_page[b["page"]].append(b)
    fields = _field_rects(bpt)
    frects_by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for f in fields:
        frects_by_page[f["page"]].append(f)
    widgets = _widgets(blank_pdf)
    has_widgets = any(widgets.values())

    rows: list[dict] = []
    claimed_boxes: dict[str, list[str]] = collections.defaultdict(list)   # box key -> fields it covers

    # fields -> case boxes
    for f in fields:
        scored = match_rect_scored(f["rect"], by_page.get(f["page"], []))
        if not scored:
            rows.append({"class": "box_unreached", "field": f["field"], "option": f["option"],
                         "page": f["page"], "rect": f["rect"], "kind": f["kind"]})
            continue
        best_s, best = scored[0]
        ties = [c["key"] for s, c in scored[1:] if abs(s - best_s) < 1e-6]
        claimed_boxes[best["key"]].append(f"{f['field']}" + (f".{f['option']}" if f["option"] else ""))
        for c in ties:
            claimed_boxes[c].append(f"{f['field']}" + (f".{f['option']}" if f["option"] else ""))
        # several case boxes inside this field rect: a split (benign)
        inside = [c for s, c in scored if _contained(c["rect"], f["rect"]) and _area(c["rect"]) < 0.9 * _area(f["rect"])]
        if len(inside) > 1:
            rows.append({"class": "split_box", "field": f["field"], "option": f["option"], "page": f["page"],
                         "boxes": [c["key"] for c in inside]})
        if ties:
            rows.append({"class": "tie", "field": f["field"], "option": f["option"], "page": f["page"],
                         "boxes": [best["key"]] + ties, "overlap": round(best_s, 3)})

    # case boxes -> fields: merged (holds >=2 field rects), uncovered, unbacked
    for b in case_boxes:
        covered = claimed_boxes.get(b["key"], [])
        distinct_fields = sorted({c.split(".")[0] for c in covered})
        if len(distinct_fields) >= 2 or (len(covered) >= 2 and b["class"] != "option"):
            # two field rects inside one page box (ACORD address lines, a
            # date's parts): the finder merged what the blueprint splits
            rows.append({"class": "merged_box", "box": b["key"], "page": b["page"], "rect": b["rect"],
                         "page_class": b["class"], "fields": covered})
            continue
        if covered:
            continue
        under = match_rect_scored(b["rect"], widgets.get(b["page"], [])) if has_widgets else []
        if under:
            rows.append({"class": "uncovered_widget", "box": b["key"], "page": b["page"], "rect": b["rect"],
                         "page_class": b["class"], "label": b.get("label"),
                         "widget_paths": sorted({c["path"].split(".")[-1] for _, c in under})})
        else:
            rows.append({"class": "unbacked_box", "box": b["key"], "page": b["page"], "rect": b["rect"],
                         "page_class": b["class"], "label": b.get("label"), "flat": not has_widgets})

    rows.extend(_option_groups(bpt, cmap, by_page, widgets))

    counts = collections.Counter(r["class"] for r in rows)
    n_fields = len({f["field"] for f in fields})
    # a field is unreached when every one of its rects is
    reached_fields = {r["field"] for r in rows if r["class"] in ("split_box", "tie", "merged_box") and r.get("field")}
    reached_fields |= {c.split(".")[0] for cs in claimed_boxes.values() for c in cs}
    unreached_fields = sorted({f["field"] for f in fields} - reached_fields)
    return {
        "summary": {"fields": n_fields, "case_boxes": len(case_boxes), "field_rects": len(fields),
                    **{k: counts.get(k, 0) for k in ("box_unreached", "merged_box", "split_box", "uncovered_widget",
                                                       "unbacked_box", "option_group_mismatch", "tie")},
                    "fields_unreached": len(unreached_fields), "has_widgets": has_widgets},
        "unreached_fields": unreached_fields,
        "rows": rows,
    }


def _option_groups(bpt: dict, cmap: dict, by_page: dict[int, list[dict]], widgets: dict[int, list[dict]]) -> list[dict]:
    """Page groups (classifier `group`) against blueprint option groups
    (`widgets`), by member boxes."""
    rows = []
    # page side: (page, group) -> set of box keys
    page_groups: dict[tuple, set[str]] = collections.defaultdict(set)
    for k, b in cmap["boxes"].items():
        if b.get("class") == "option" and b.get("group"):
            page_groups[(b["page"], b["group"])].add(k)
    box_to_pgroup = {k: g for g, ks in page_groups.items() for k in ks}
    for name, spec in (bpt.get("fields") or {}).items():
        widgets_map = spec.get("widgets")
        if not widgets_map or len(widgets_map) < 2:
            continue
        members: set[str] = set()
        unreached = 0
        pages = set()
        for opt, wb in widgets_map.items():
            rect = wb.get("rect") or wb.get("box")
            if not rect:
                continue
            pages.add(wb.get("page"))
            scored = match_rect_scored(rect, by_page.get(wb.get("page"), []))
            if scored:
                members.add(scored[0][1]["key"])
            else:
                unreached += 1
        if not members:
            continue
        pgs = {box_to_pgroup.get(k) for k in members}
        pgs.discard(None)
        if len(pgs) == 1:
            g = next(iter(pgs))
            extra = page_groups[g] - members
            if not extra and unreached == 0:
                continue  # page and blueprint agree on the member boxes
            rows.append({"class": "option_group_mismatch", "field": name, "page_group": g[1],
                         "shape": "page_group_wider" if extra else "blueprint_options_unreached",
                         "blueprint_members": len(widgets_map), "page_members": len(page_groups[g]),
                         "extra_page_boxes": sorted(extra), "unreached_options": unreached,
                         **_attribute(members | extra, widgets, pages)})
        elif len(pgs) == 0:
            rows.append({"class": "option_group_mismatch", "field": name, "page_group": None,
                         "shape": "page_sees_no_group", "blueprint_members": len(widgets_map),
                         **_attribute(members, widgets, pages)})
        else:
            rows.append({"class": "option_group_mismatch", "field": name,
                         "page_group": sorted(g[1] for g in pgs), "shape": "blueprint_field_spans_page_groups",
                         "blueprint_members": len(widgets_map), "page_groups": len(pgs),
                         **_attribute(members, widgets, pages)})
    return rows


def _attribute(box_keys: set[str], widgets: dict[int, list[dict]], pages: set) -> dict:
    """What the widget layer says about a set of option boxes: how many radio
    paths they span. Attribution only, never meaning."""
    paths = set()
    for k in box_keys:
        page, rect = parse_rect_key(k)
        for w in widgets.get(page, []):
            if (w["radio"] or w["checkbox"]) and overlap(rect, w["rect"]) >= 0.5:
                paths.add(w["path"])
    if not widgets:
        return {"attribution": "flat_blank_no_metadata"}
    if len(paths) <= 1:
        return {"attribution": "one_path" if paths else "no_widget_under_boxes", "radio_paths": len(paths)}
    return {"attribution": "several_paths", "radio_paths": len(paths)}


def _area(r) -> float:
    return max((r[2] - r[0]) * (r[3] - r[1]), 1e-6)


def _contained(inner, outer, tol: float = 2.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def check_case(bpt: dict, cmap: dict, case_dir: Path, blank_pdf: Optional[Path]) -> dict:
    res = cross_reference(bpt, cmap, blank_pdf)
    (case_dir / "inventory_check.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> int:
    import argparse
    import yaml
    from petey.paths import BLUEPRINTS
    from petey.synth.classify import classify_form
    from petey.validate.retype import resolve_blank
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True)
    ap.add_argument("--bpt", type=Path, default=None)
    ap.add_argument("--all", action="store_true", help="print every row")
    args = ap.parse_args()
    bpt_path = args.bpt or BLUEPRINTS / f"{args.form}.bpt"
    bpt = yaml.safe_load(bpt_path.read_text(encoding="utf-8"))
    blank = resolve_blank(bpt)
    cmap = classify_form(blank, cache_only=True)
    if cmap is None:
        raise SystemExit(f"{args.form}: no cached classification for {blank}")
    res = cross_reference(bpt, cmap, blank)
    print(json.dumps({"form": args.form, **res["summary"]}))
    for r in res["rows"]:
        if r["class"] in ("split_box", "tie") and not args.all:
            continue
        print("  ", json.dumps({k: v for k, v in r.items() if k not in ("rect",)}, default=str)[:220])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
