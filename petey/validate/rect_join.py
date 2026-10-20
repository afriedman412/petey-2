"""Join a rect-keyed case to the blueprint, for scoring.

The synthetic path keys everything by page and rect (`synth.boxes.rect_key`)
and never by AcroForm path. The scorer, the by-path readback and the
name-based reader all speak the blueprint's field names, and the blueprint
carries a page and rect for every widget and every option. So the join is
geometric: each field's rect is matched to the case's rect that best
overlaps it (`boxes.match_rect`), and the result is written in the shape
`score()` already consumes: a path-keyed dictionary where an option group
holds the marked option's on-state and a standalone checkbox holds a bool.

`case_to_paths` is the only place the two keyings meet, and it runs at
scoring time. Fields whose rect matches no case box are absent from the
result (the field is then scored as empty ground truth), and boxes no field
claims are returned separately: those are the page's fillable boxes the
blueprint does not know about.

A widget with no path (a flat blueprint, `path: null`) is keyed by its page
and rect instead (`boxes.widget_key`), so a flat form scores like any other
(2026-10-05).
"""
from __future__ import annotations

from typing import Any, Optional

from petey.synth.boxes import match_rect, overlap, parse_rect_key, widget_key


def _case_rows(case: dict[str, Any]) -> dict[int, list[dict]]:
    by_page: dict[int, list[dict]] = {}
    for key, value in case.items():
        page, rect = parse_rect_key(key)
        by_page.setdefault(page, []).append({"key": key, "rect": rect, "value": value})
    return by_page


def _target_rows(targets: dict[str, list[dict]]) -> dict[int, list[dict]]:
    by_page: dict[int, list[dict]] = {}
    for key, tg in targets.items():
        for t in tg:
            by_page.setdefault(int(t["page"]), []).append({"key": key, "rect": t["rect"], "value": t["value"]})
    return by_page


def unreached_fields(bpt: dict, gt: dict[str, Any]) -> set[str]:
    """Blueprint fields none of whose widget paths the join reached: no
    synthetic box landed on them, so the case says nothing about them."""
    out = set()
    for name, spec in (bpt.get("fields") or {}).items():
        if spec.get("widgets"):
            paths = [widget_key(wb) for wb in spec["widgets"].values()]
        else:
            paths = [widget_key(spec.get("widget") or {})]
        paths = [p for p in paths if p]
        if paths and not any(p in gt for p in paths):
            out.add(name)
    return out


def case_to_paths(bpt: dict, case: dict[str, Any],
                  targets: Optional[dict[str, list[dict]]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(gt_by_path, unclaimed)`: the case in the path-keyed shape the scorer
    reads, and the case boxes no blueprint field claimed. With `targets`
    (the filler's report of where each value landed) fields are matched to
    the landing rects, so a field is credited with what its own widget
    holds; without, to the page boxes themselves (a flat blank)."""
    by_page = _target_rows(targets) if targets else _case_rows(case)
    gt: dict[str, Any] = {}
    used: set[str] = set()
    for name, spec in (bpt.get("fields") or {}).items():
        widgets = spec.get("widgets")
        if widgets:
            # an option group: one path per option (distinct paths for
            # labeler clusters, one shared path with on-states for kids)
            shared = len({widget_key(wb) for wb in widgets.values()}) == 1
            for opt, wb in widgets.items():
                path = widget_key(wb)
                rect = wb.get("rect") or wb.get("box")
                if not path or not rect:
                    continue
                m = match_rect(rect, by_page.get(wb.get("page"), []))
                if m is None:
                    continue
                used.add(m["key"])
                marked = m["value"] is True or (isinstance(m["value"], str) and m["value"].strip().lower() in ("x", "yes", "true"))
                if shared:
                    if marked and wb.get("on_state"):
                        gt[path] = wb["on_state"]
                    else:
                        gt.setdefault(path, False)
                else:
                    gt[path] = marked
            continue
        w = spec.get("widget") or {}
        path, rect = widget_key(w), w.get("rect")
        if not path or not rect:
            continue
        rows = by_page.get(w.get("page"), [])
        m = match_rect(rect, rows)
        if m is None:
            continue
        # a field whose rect covers several case cells (a comb the finder
        # split) holds their concatenation in reading order, as the filler wrote it
        # the filler's rule (synth.render): a cell is inside when its AREA is under 0.9 of the field's; a width rule
        # missed the lines of a two-line box (full width, half height: Form 8825's address cells, 2026-10-20) and
        # reported the second line as a box no field claims
        area = lambda r: max(r[2] - r[0], 0) * max(r[3] - r[1], 0)    # noqa: E731
        inside = [r for r in rows if isinstance(r["value"], str) and overlap(rect, r["rect"]) >= 0.5
                  and area(r["rect"]) < area(rect) * 0.9]
        if len(inside) > 1:
            inside.sort(key=lambda r: (round(r["rect"][1] / 4), r["rect"][0]))
            for r in inside:
                used.add(r["key"])
            # the filler stored the joined string on every member; take it once
            v = inside[0]["value"]
            gt[path] = v if spec.get("type") != "boolean" else bool(v)
            continue
        used.add(m["key"])
        # with the filler's targets, the cells of a split widget all landed at the widget's own rect (one value,
        # the joined string, reported on each): every one of them is this field's, not a box no field claims
        for r in rows:
            if r["rect"] == m["rect"] and r["value"] == m["value"]:
                used.add(r["key"])
        v = m["value"]
        if spec.get("type") == "boolean":
            gt[path] = v is True or (isinstance(v, str) and v.strip().lower() in ("x", "yes", "true"))
        elif isinstance(v, bool):
            gt[path] = "X" if v else ""
        else:
            gt[path] = v
    unclaimed = {k: v for k, v in case.items() if k not in used}
    return gt, unclaimed
