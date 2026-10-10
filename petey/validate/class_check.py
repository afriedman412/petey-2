"""Two generators compared per box (TODO v6, synthetic data step 4).

The bank draws a value from the blueprint's typing or from the page-grounded
class map; the blind generator draws from the page alone. Where the page's
class and the blueprint's type disagree about what KIND of value a box
holds, the labeler has something to look at. This module writes that list
into a run (`class_disagreements.json` in the case dir) so `iterate.detect`
counts it and `review.flags_from_run` hands it to the reviewer.

Family-level comparison (`classify.CLASS_FAMILY`): a page class of
`last_name` against a blueprint `person_name` is not a disagreement; `zip`
against `id_part` is. Rows are `weak` when the page gave the box no caption
of its own (an unlabeled line under PRODUCER), because there the page class
is a guess by position and the blueprint's name is a guess by convention.

    python -m petey.validate.class_check --form fw9 [--run-dir runs/...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.synth.boxes import match_rect
from petey.synth.classify import CLASS_FAMILY, SEMANTIC_TO_CLASS, classify_form

_TYPE_CLASS = {"date": "date", "number": "money", "integer": "count", "boolean": "option",
               "category": "option", "multi_category": "option"}
_CONTROL_CLASSES = {"option", "yes_no", "choice", "checkbox", "mark"}


def _family(cls: Optional[str]) -> Optional[str]:
    if cls is None:
        return None
    return CLASS_FAMILY.get(cls, cls)


def blueprint_class(name: str, spec: dict) -> tuple[Optional[str], str]:
    """(class in the page vocabulary, how it was derived) for one field."""
    if spec.get("widgets"):
        return "option", "option_group"
    st = spec.get("semantic_type")
    if st and st in SEMANTIC_TO_CLASS:
        return SEMANTIC_TO_CLASS[st], "semantic_type"
    t = spec.get("type", "string")
    if t in _TYPE_CLASS:
        return _TYPE_CLASS[t], "type"
    low = name.lower()
    for suf, cls in (("_mm", "date_month"), ("_dd", "date_day"), ("_yyyy", "date_year"),
                     ("_yy", "date_year")):
        if low.endswith(suf) or f"{suf}_" in low:
            return cls, "name_suffix"
    return None, "untyped"


def compare(bpt: dict, cmap: dict) -> list[dict]:
    """Every field whose page class and blueprint class fall in different
    families. Untyped blueprint fields (plain `string`, no semantic type)
    are reported too, tagged `untyped`, since the page offers a type the
    blueprint lacks; they are `weak` unless the page read a caption."""
    # the class map is keyed by page and rect; join on the field's own rect
    by_page: dict[int, list[dict]] = {}
    for key, b in cmap["boxes"].items():
        by_page.setdefault(b["page"], []).append({**b, "key": key})
    rows = []
    for name, spec in (bpt.get("fields") or {}).items():
        if spec.get("widgets"):
            blocks = [wb for wb in spec["widgets"].values() if wb.get("rect") or wb.get("box")]
        else:
            w = spec.get("widget") or {}
            blocks = [w] if w.get("rect") else []
        hits = []
        for wb in blocks:
            m = match_rect(wb.get("rect") or wb.get("box"), by_page.get(wb.get("page"), []))
            if m is not None:
                hits.append(m)
        if not hits:
            continue
        b = hits[0]
        paths = [wb.get("path") for wb in blocks]
        page_cls = b["class"]
        if page_cls == "none":
            continue  # the page says nothing goes here; counted separately below
        bp_cls, how = blueprint_class(name, spec)
        if page_cls in _CONTROL_CLASSES and (bp_cls in _CONTROL_CLASSES or spec.get("type") == "boolean"):
            continue
        if bp_cls is not None and _family(page_cls) == _family(bp_cls):
            continue
        if page_cls == "other":
            continue  # the page could not say either
        rows.append({
            "field": name,
            "path": paths[0] if paths else None,
            "rect_key": b.get("key"),
            "page": b.get("page"),
            "box": b.get("box"),
            "label": b.get("label"),
            "entity": b.get("entity"),
            "page_class": page_cls,
            "blueprint_class": bp_cls,
            "blueprint_class_from": how,
            "semantic_type": spec.get("semantic_type"),
            "type": spec.get("type"),
            "untyped": bp_cls is None,
            "weak": b.get("label") is None,
            # 1: captioned box, typed field, families differ -> a detection and
            #    a reviewer flag. 2: captioned, blueprint untyped -> the page
            #    offers a type; a suggestion, reported not counted. 3: no
            #    caption -> a guess on both sides.
            "tier": 3 if b.get("label") is None else (2 if bp_cls is None else 1),
        })
    return rows


def check_run_case(bpt: dict, cmap: dict, case_dir: Path) -> list[dict]:
    rows = compare(bpt, cmap)
    (case_dir / "class_disagreements.json").write_text(json.dumps(rows, indent=1))
    return rows


def summarize(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "tier1_contradiction": sum(1 for r in rows if r["tier"] == 1),
        "tier2_suggestion": sum(1 for r in rows if r["tier"] == 2),
        "tier3_uncaptioned": sum(1 for r in rows if r["tier"] == 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True)
    ap.add_argument("--bpt", type=Path, default=None)
    ap.add_argument("--blank", type=Path, default=None)
    ap.add_argument("--run-dir", type=Path, default=None, help="write into this run's intact case(s)")
    ap.add_argument("--all", action="store_true", help="list every row, not only captioned ones")
    args = ap.parse_args()
    from petey.validate.retype import resolve_blank
    bpt_path = args.bpt or BLUEPRINTS / f"{args.form}.bpt"
    bpt = yaml.safe_load(bpt_path.read_text(encoding="utf-8"))
    blank = args.blank or resolve_blank(bpt)
    cmap = classify_form(blank, cache_only=True)
    if cmap is None:
        raise SystemExit(f"{args.form}: no cached classification for {blank}")
    rows = compare(bpt, cmap)
    if args.run_dir:
        for d in sorted(args.run_dir.glob("case_*_intact")):
            check_run_case(bpt, cmap, d)
    print(json.dumps({"form": args.form, **summarize(rows)}))
    for r in rows:
        if r["tier"] > 1 and not args.all:
            continue
        print(f"  t{r['tier']} p{r['page']} box {r['box']:>4} {r['page_class']:15} {str(r['blueprint_class']):14} "
              f"{r['field'][:44]:44} caption={str(r['label'])[:40]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
